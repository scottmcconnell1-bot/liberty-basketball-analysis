"""E2E journeys: accounts, the sign-in gate, the coach portal, messaging, settings, entitlements.

Every journey drives the real HTTP routes (Flask test client) against the temporary DB from
tests/conftest.py and asserts exact outcomes. Tests marked ``xfail(strict=True)`` assert the
CORRECT behaviour for a verified bug; they flip to XPASS (and fail the run) once it is fixed.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest

from blueprints.users import _hash_password

pytestmark = pytest.mark.e2e

PW = "journey-pass-1"
COACH_PW = "journey-coach-secret"

# Paths the gate leaves public (app.py _AUTH_PUBLIC_PATHS / _AUTH_PUBLIC_PREFIXES).
PUBLIC_EXACT = {"/login", "/logout", "/register", "/sw.js", "/favicon.ico"}
PUBLIC_PREFIXES = ("/static/", "/coach", "/play/share/")
MUTATING = ("POST", "PUT", "PATCH", "DELETE")


# ── helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(app):
    """Own connection OUTSIDE any app context.

    tests/conftest.py's ``db`` keeps an app context pushed, so every test-client request
    would share its ``g`` (cached runtime settings, one connection) and never see flag
    changes made mid-journey.
    """
    import sqlite3

    conn = sqlite3.connect(app.config["DATABASE"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _add_user(db, email, role, password=PW, name=None):
    cur = db.execute(
        """INSERT INTO users (email, password_hash, display_name, role, is_active)
           VALUES (?,?,?,?,1)""",
        (email, _hash_password(password), name or email.split("@")[0].title(), role),
    )
    db.commit()
    return cur.lastrowid


def _login(client, email, password=PW, next_url=None):
    url = "/login" if next_url is None else f"/login?next={next_url}"
    return client.post(url, data={"email": email, "password": password}, follow_redirects=False)


def _signed_in(app, db, email, role, password=PW):
    uid = _add_user(db, email, role, password)
    c = app.test_client()
    r = _login(c, email, password)
    assert r.status_code == 302 and urlsplit(r.headers["Location"]).path == "/", r.headers.get("Location")
    return c, uid


def _set_flag(db, name, on):
    db.execute(
        """INSERT INTO app_settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (f"feature.{name}", "1" if on else "0"),
    )
    db.commit()


def _flag(db, name):
    row = db.execute("SELECT value FROM app_settings WHERE key=?", (f"feature.{name}",)).fetchone()
    return None if row is None else row[0]


def _coach_client(app, monkeypatch):
    monkeypatch.setenv("LIBERTY_COACH_PASSWORD", COACH_PW)
    c = app.test_client()
    r = c.post("/coach", data={"password": COACH_PW}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/coach/progress")
    with c.session_transaction() as s:
        assert s["coach_portal"] is True and "user_id" not in s
    return c


def _is_public(path):
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


def _concrete(rule):
    """Fill every URL variable with '1' (valid for int, string and path converters)."""
    return re.sub(r"<[^>]+>", "1", rule.rule)


def _routes(app):
    out = []
    for rule in app.url_map.iter_rules():
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            out.append((rule.endpoint.split(".")[0], method, rule, _concrete(rule)))
    return out


def _call(client, method, path, **kw):
    return client.open(path, method=method, follow_redirects=False, **kw)


def _redirects_to_login(resp):
    return resp.status_code == 302 and urlsplit(resp.headers["Location"]).path == "/login"


def _counts(db):
    tables = ("users", "messages", "conversations", "issue_reports", "app_settings",
              "seasons", "scheduled_games", "practices", "plays", "team_photos")
    return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def _send(client, **payload):
    return client.post("/api/messages/send", json=payload)


# ── 1. admin bootstrap ───────────────────────────────────────────────────────

def test_admin_bootstrap_creates_accounts_and_logout_clears_session(app, client, db):
    _add_user(db, "admin@example.com", "admin", name="Admin")

    # Anonymous: /register (GET and POST) is refused and creates nothing.
    r = client.get("/register", follow_redirects=False)
    assert _redirects_to_login(r)
    r = client.post("/register", data={"email": "sneaky@example.com", "password": "12345678",
                                       "password2": "12345678", "display_name": "S", "role": "admin"},
                    follow_redirects=False)
    assert _redirects_to_login(r)
    assert db.execute("SELECT COUNT(*) FROM users WHERE email='sneaky@example.com'").fetchone()[0] == 0

    # Admin signs in (next= keeps a local path) and gets the create-user form.
    r = _login(client, "admin@example.com", next_url="/users")
    assert r.status_code == 302 and r.headers["Location"] == "/users"
    with client.session_transaction() as s:
        assert s["user_role"] == "admin" and s["user_name"] == "Admin"
    assert client.get("/register").status_code == 200

    created = {"coach1@example.com": "coach", "player1@example.com": "player"}
    for email, role in created.items():
        r = client.post("/register", data={"email": email.upper(), "password": PW, "password2": PW,
                                           "display_name": role.title() + " One", "role": role},
                        follow_redirects=False)
        assert r.status_code == 302 and r.headers["Location"] == "/users"

    # Validation: duplicate email, bad role, short/mismatched password all refused.
    before = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    for bad in (
        {"email": "coach1@example.com", "password": PW, "password2": PW, "display_name": "Dup", "role": "coach"},
        {"email": "x@example.com", "password": PW, "password2": PW, "display_name": "X", "role": "superuser"},
        {"email": "y@example.com", "password": "short", "password2": "short", "display_name": "Y", "role": "coach"},
        {"email": "z@example.com", "password": PW, "password2": PW + "x", "display_name": "Z", "role": "coach"},
    ):
        assert client.post("/register", data=bad).status_code == 200
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == before

    rows = {r["email"]: r for r in db.execute("SELECT * FROM users")}
    for email, role in created.items():
        assert rows[email]["role"] == role                        # stored lower-cased, role as chosen
        assert rows[email]["is_active"] == 1
        assert rows[email]["password_hash"] != PW and ":" in rows[email]["password_hash"]

    # Each new account signs in with the chosen role; wrong password is rejected.
    for email, role in created.items():
        c = app.test_client()
        bad = _login(c, email, "wrong-password")
        assert bad.status_code == 200 and b"Invalid email or password" in bad.data
        assert _login(c, email).status_code == 302
        with c.session_transaction() as s:
            assert s["user_id"] == rows[email]["id"] and s["user_role"] == role
        # A non-admin cannot create accounts either.
        r = c.post("/register", data={"email": "n@example.com", "password": PW, "password2": PW,
                                      "display_name": "N", "role": "admin"}, follow_redirects=False)
        assert _redirects_to_login(r)
    assert db.execute("SELECT COUNT(*) FROM users WHERE email='n@example.com'").fetchone()[0] == 0

    # Logout clears the session and its DB row.
    with client.session_transaction() as s:
        token = s["session_token"]
    assert db.execute("SELECT COUNT(*) FROM user_sessions WHERE session_token=?", (token,)).fetchone()[0] == 1
    r = client.get("/logout", follow_redirects=False)
    assert _redirects_to_login(r)
    with client.session_transaction() as s:
        assert dict(s) == {}
    assert db.execute("SELECT COUNT(*) FROM user_sessions WHERE session_token=?", (token,)).fetchone()[0] == 0
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    assert _redirects_to_login(client.get("/schedule"))


def test_login_rejects_offsite_next(client, db):
    _add_user(db, "a@example.com", "coach")
    for nxt in ("https://evil.example/", "//evil.example/x"):
        r = _login(client, "a@example.com", next_url=nxt)
        assert r.status_code == 302 and r.headers["Location"] == "/", nxt


def test_login_backslash_next_is_not_protocol_relative(client, db):
    # extract_local_path keeps "/\\evil.example", but Werkzeug percent-encodes the backslash in
    # Location, so browsers get the harmless relative path "/%5Cevil.example".
    _add_user(db, "a@example.com", "coach")
    r = _login(client, "a@example.com", next_url="/%5Cevil.example")
    loc = r.headers["Location"]
    assert r.status_code == 302 and loc == "/%5Cevil.example"
    assert not urlsplit(loc).netloc and "\\" not in loc


def test_coach_login_rejects_offsite_next(app, client, monkeypatch):
    # Regression: /coach?next= was not validated -> open redirect after coach sign-in.
    monkeypatch.setenv("LIBERTY_COACH_PASSWORD", COACH_PW)
    for nxt in ("https://evil.example/phish", "//evil.example/x"):
        c = app.test_client()
        r = c.post(f"/coach?next={nxt}", data={"password": COACH_PW}, follow_redirects=False)
        assert r.status_code == 302
        assert not urlsplit(r.headers["Location"]).netloc, nxt
        assert urlsplit(r.headers["Location"]).path == "/coach/progress", nxt
    # A local next= is still honoured.
    r = client.post("/coach?next=/schedule", data={"password": COACH_PW}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"] == "/schedule"


def test_logged_out_cookie_cannot_be_replayed(app, client, db):
    # Regression: logout only deleted the user_sessions row and _current_user never checked
    # session_token, so a copied cookie stayed valid after logout.
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    _add_user(db, "a@example.com", "coach")
    assert _login(client, "a@example.com").status_code == 302
    stolen = client.get_cookie("session").value
    assert client.get("/schedule").status_code == 200
    replay = app.test_client()
    replay.set_cookie("session", stolen)
    assert replay.get("/schedule").status_code == 200          # live copy works before logout
    client.get("/logout")
    attacker = app.test_client()
    attacker.set_cookie("session", stolen)
    assert _redirects_to_login(attacker.get("/schedule"))
    assert attacker.get("/api/games").status_code == 401
    assert _redirects_to_login(attacker.get("/profile"))      # login_required too
    # Signing in again issues a fresh working session.
    assert _login(client, "a@example.com").status_code == 302
    assert client.get("/schedule").status_code == 200


# ── 2. gate ON ───────────────────────────────────────────────────────────────

def test_gate_on_blocks_anonymous_on_every_route_of_every_blueprint(app, client, db):
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    before = _counts(db)
    seen = set()
    checked = 0
    for bp, method, rule, path in _routes(app):
        if _is_public(path):
            continue
        r = _call(client, method, path)
        if path.startswith("/api/"):
            assert r.status_code == 401, (method, path, r.status_code)
            assert r.get_json() == {"error": "Sign-in required."}
        else:
            assert _redirects_to_login(r), (method, path, r.status_code, r.headers.get("Location"))
            if method == "GET":
                assert parse_qs(urlsplit(r.headers["Location"]).query)["next"] == [path]
        seen.add(bp)
        checked += 1
    # JSON posts to page routes get 401 too.
    r = client.post("/debug/issues", json={"details": "x"})
    assert r.status_code == 401
    assert _counts(db) == before
    blueprints = {name for name in app.blueprints}
    assert blueprints - {"coach"} <= seen, blueprints - seen   # coach is public by design
    assert checked > 200


def test_gate_on_public_paths_stay_public(client, db, monkeypatch):
    monkeypatch.setenv("LIBERTY_COACH_PASSWORD", COACH_PW)
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    assert client.get("/login").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/static/manifest.json").status_code == 200
    assert client.get("/coach").status_code == 200
    assert _redirects_to_login(client.get("/register"))      # public path, admin-only view
    assert _redirects_to_login(client.get("/logout"))
    assert client.get("/play/share/no-such-token").status_code == 404   # reaches the view


def test_gate_on_signed_in_user_reaches_every_parameterless_get(app, db):
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    c, _ = _signed_in(app, db, "coach@example.com", "coach")
    skip = {"/logout", "/coach/logout", "/coach/exit"}
    reached = set()
    for bp, method, rule, path in _routes(app):
        if method != "GET" or rule.arguments or path in skip or _is_public(path):
            continue
        r = _call(c, method, path)
        assert r.status_code != 401, path
        assert not _redirects_to_login(r), path
        reached.add(bp)
    assert {"core", "games", "clips", "stats", "practice", "player_dev", "ai", "playbook",
            "messaging", "users", "scouting", "stat_books", "bulk_import"} <= reached


def test_gate_on_deactivated_user_is_signed_out(app, db):
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    c, uid = _signed_in(app, db, "gone@example.com", "coach")
    assert c.get("/schedule").status_code == 200
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (uid,))
    db.commit()
    assert _redirects_to_login(c.get("/schedule"))
    assert c.get("/api/games").status_code == 401


def test_gate_on_coach_portal_reads_but_every_mutation_is_refused(app, db, monkeypatch):
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    c = _coach_client(app, monkeypatch)
    for path in ("/", "/schedule", "/playbook", "/videos", "/messages", "/coach/progress", "/api/games"):
        assert c.get(path).status_code == 200, path
    # Ops pages are refused (GET), including trailing-slash / HEAD variants.
    for path in ("/settings", "/settings/", "/settings/notifications", "/debug", "/users", "/status",
                 "/preview", "/nfhs-matches"):
        for method in ("GET", "HEAD"):
            r = _call(c, method, path)
            assert r.status_code == 302 and urlsplit(r.headers["Location"]).path == "/", (method, path)
    assert c.get("/api/admin/reset").status_code == 403
    assert c.get("/api/scouting/nfhs/credentials").status_code == 403

    allowed = {"/coach", "/coach/login", "/coach/logout", "/login", "/logout"}
    before = _counts(db)
    refused = 0
    for bp, method, rule, path in _routes(app):
        if method not in MUTATING or path in allowed or path.startswith("/static/"):
            continue
        for kw in ({}, {"json": {"body": "x", "details": "x", "recipient_id": "1"}}):
            r = _call(c, method, path, **kw)
            if r.status_code == 403:
                refused += 1
                continue
            assert r.status_code == 302, (method, path, r.status_code)
            assert urlsplit(r.headers["Location"]).path == "/", (method, path)
            assert not path.startswith("/api/"), (method, path)
            refused += 1
    # Trailing-slash / double-slash variants of mutating routes.
    for path in ("/api/messages/send/", "/api/admin/reset/", "/settings/", "//settings", "/debug/issues/"):
        r = c.post(path, data={"details": "x"}, follow_redirects=False)
        assert r.status_code in (302, 403, 404, 405, 308), path
        assert r.status_code != 200, path
    assert refused > 100
    assert _counts(db) == before
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") == "1"


def test_gate_on_stale_coach_cookie_gets_no_access_after_portal_disabled(app, db, monkeypatch):
    # Regression: with ENABLE_COACH_PORTAL off, a live coach_portal cookie still passed the
    # gate and the read-only denylist was skipped.
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    c = _coach_client(app, monkeypatch)
    assert c.get("/schedule").status_code == 200       # portal on: reads allowed
    _set_flag(db, "ENABLE_COACH_PORTAL", False)       # admin switches the portal off
    r = c.post("/debug/issues", data={"details": "planted", "return_to": "/"}, follow_redirects=False)
    assert db.execute("SELECT COUNT(*) FROM issue_reports").fetchone()[0] == 0
    assert _redirects_to_login(r)
    r = c.post("/settings", data={}, follow_redirects=False)   # would switch every flag off
    assert _redirects_to_login(r)
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") == "1"
    assert _flag(db, "ENABLE_COACH_PORTAL") == "0"
    assert _redirects_to_login(c.get("/schedule"))     # reads are gone too
    assert c.get("/api/games").status_code == 401


def test_gate_on_non_admin_cannot_change_settings(app, db):
    # Regression: POST /settings had no role check; any signed-in player could switch the
    # sign-in gate off.
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    c, _ = _signed_in(app, db, "player@example.com", "player")
    before = _counts(db)
    for role_client in (c, _signed_in(app, db, "coach@example.com", "coach")[0],
                        _signed_in(app, db, "mgr@example.com", "manager")[0]):
        r = role_client.post("/settings", data={}, follow_redirects=False)
        assert r.status_code == 403 and r.get_json() == {"error": "Only an admin can change settings."}
        r = role_client.post("/settings/ollama/pull", data={"model_name": "llama3"}, follow_redirects=False)
        assert r.status_code == 403
        assert role_client.get("/settings").status_code == 200    # viewing stays allowed
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") == "1"
    assert {k: v for k, v in _counts(db).items() if k != "users"} == \
        {k: v for k, v in before.items() if k != "users"}
    # The admin can still change settings with the gate on.
    admin, _ = _signed_in(app, db, "admin@example.com", "admin")
    r = admin.post("/settings", data={"feature_ENABLE_AUTH_MIDDLEWARE": "1"}, follow_redirects=False)
    assert r.status_code == 302 and urlsplit(r.headers["Location"]).path == "/settings"
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") == "1" and _flag(db, "ENABLE_COACH_PORTAL") == "0"


def test_gate_off_settings_open_to_anonymous_but_not_to_signed_in_non_admin(app, client, db):
    # Documented choice: with the gate OFF the app is intentionally open until the owner
    # turns sign-in on, so anonymous saves keep working; a signed-in non-admin is refused.
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") is None
    player, _ = _signed_in(app, db, "player@example.com", "player")
    r = player.post("/settings", data={"feature_ENABLE_WEEKLY_PACKET": "1"}, follow_redirects=False)
    assert r.status_code == 403
    assert _flag(db, "ENABLE_WEEKLY_PACKET") is None
    assert player.post("/settings/ollama/pull", data={"model_name": "llama3"}).status_code == 403
    r = client.post("/settings", data={"feature_ENABLE_WEEKLY_PACKET": "1"}, follow_redirects=False)
    assert r.status_code == 302 and urlsplit(r.headers["Location"]).path == "/settings"
    assert _flag(db, "ENABLE_WEEKLY_PACKET") == "1"


# ── 3. gate OFF (default) ────────────────────────────────────────────────────

def test_gate_off_routes_open_but_admin_reset_needs_admin(app, client, db):
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") is None
    for path in ("/", "/schedule", "/messages", "/playbook", "/scouting", "/api/games", "/api/seasons"):
        assert client.get(path).status_code == 200, path
    assert _redirects_to_login(client.get("/register"))
    assert _redirects_to_login(client.get("/profile"))           # login_required still applies
    assert _redirects_to_login(client.get("/api/notifications"))

    db.execute("""INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes, game_id)
                  VALUES ('g.mp4','g.mp4','/nonexistent/g.mp4',10,'g1')""")
    db.commit()
    assert client.post("/api/admin/reset").status_code == 403
    coach, _ = _signed_in(app, db, "coach@example.com", "coach")
    assert coach.post("/api/admin/reset").status_code == 403
    manager, _ = _signed_in(app, db, "mgr@example.com", "manager")
    assert manager.post("/api/admin/reset").status_code == 403
    assert db.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1
    admin, _ = _signed_in(app, db, "admin@example.com", "admin")
    r = admin.post("/api/admin/reset")
    assert r.status_code == 200 and r.get_json()["success"] is True
    assert db.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0


# ── 4. messaging ─────────────────────────────────────────────────────────────

@pytest.fixture
def trio(app, db):
    _set_flag(db, "ENABLE_AUTH_MIDDLEWARE", True)
    a, a_id = _signed_in(app, db, "alice@example.com", "coach")
    b, b_id = _signed_in(app, db, "bob@example.com", "player")
    c, c_id = _signed_in(app, db, "carol@example.com", "player")
    r = _send(a, recipient_id=str(b_id), body="hi bob", sender_id="999")
    assert r.status_code == 200
    first = r.get_json()
    conv = first["conversation_id"]
    r = _send(b, conversation_id=conv, body="hi alice")
    assert r.status_code == 200
    return {"a": a, "b": b, "c": c, "a_id": a_id, "b_id": b_id, "c_id": c_id, "conv": conv,
            "m1": first["id"], "m2": r.get_json()["id"]}


def test_messaging_two_users_converse(trio, db):
    t = trio
    # Sender comes from the session, never from the payload.
    rows = db.execute("SELECT id, sender_id, body FROM messages ORDER BY id").fetchall()
    assert [(r["sender_id"], r["body"]) for r in rows] == [(str(t["a_id"]), "hi bob"), (str(t["b_id"]), "hi alice")]
    members = {r["user_id"]: r["role"] for r in
               db.execute("SELECT user_id, role FROM conversation_members WHERE conversation_id=?", (t["conv"],))}
    assert members == {str(t["a_id"]): "owner", str(t["b_id"]): "member"}
    conv = db.execute("SELECT * FROM conversations WHERE id=?", (t["conv"],)).fetchone()
    assert conv["title"] == "Chat with Bob" and conv["created_by"] == str(t["a_id"])

    for who in ("a", "b"):
        msgs = t[who].get(f"/api/messages/poll?conversation_id={t['conv']}").get_json()
        assert [m["body"] for m in msgs] == ["hi bob", "hi alice"]
        newer = t[who].get(f"/api/messages/poll?conversation_id={t['conv']}&since_id={t['m1']}").get_json()
        assert [m["body"] for m in newer] == ["hi alice"]
        page = t[who].get(f"/messages?c={t['conv']}")
        assert page.status_code == 200 and b"hi bob" in page.data and b"hi alice" in page.data
    assert t["a"].post("/api/messages/send", json={"conversation_id": t["conv"], "body": "  "}).status_code == 400
    assert t["a"].post("/api/messages/send", json={"body": "orphan"}).status_code == 400


def test_messaging_each_user_lists_only_own_conversations(trio):
    # Regression: the conversation list JOINed conversation_members with no user filter ->
    # every conversation, once per member.
    t = trio
    for who in ("a", "b"):
        ids = [c["id"] for c in t[who].get("/api/messages/conversations").get_json()]
        assert ids == [t["conv"]], (who, ids)
    assert t["c"].get("/api/messages/conversations").get_json() == []
    # Same scoping on the page's sidebar.
    assert b"Chat with Bob" in t["a"].get("/messages").data
    assert b"Chat with Bob" not in t["c"].get("/messages").data


def test_messaging_outsider_cannot_read_conversation(trio):
    # Regression: /api/messages/poll and /messages?c= returned any conversation to any caller (IDOR).
    t = trio
    r = t["c"].get(f"/api/messages/poll?conversation_id={t['conv']}")
    assert r.status_code == 403 and "hi bob" not in r.get_data(as_text=True)
    page = t["c"].get(f"/messages?c={t['conv']}")
    assert page.status_code == 200 and b"hi bob" not in page.data and b"hi alice" not in page.data


def test_messaging_outsider_cannot_post_into_conversation(trio, db):
    # Regression: /api/messages/send never checked membership; outsiders could post anywhere.
    t = trio
    r = _send(t["c"], conversation_id=t["conv"], body="intruder")
    assert r.status_code == 403
    assert db.execute("SELECT COUNT(*) FROM messages WHERE body='intruder'").fetchone()[0] == 0
    # Members still can.
    assert _send(t["b"], conversation_id=t["conv"], body="still here").status_code == 200


def test_messaging_recipient_gets_unread_notification_and_can_mark_it_read(trio, db):
    # Regression: notify_message_received selected conversations.name / inserted
    # notifications.source_type (columns do not exist) and called Row.get -> no message
    # notifications ever.
    t = trio
    notes = t["b"].get("/api/notifications").get_json()
    assert [n["title"] for n in notes] == ["New message from Alice"]
    assert notes[0]["link"] == f"/messages?c={t['conv']}" and notes[0]["body"] == "hi bob"
    assert [n["title"] for n in t["a"].get("/api/notifications").get_json()] == ["New message from Bob"]
    assert t["c"].get("/api/notifications").get_json() == []          # outsiders get nothing
    assert t["b"].post("/api/notifications/read", json={"ids": [notes[0]["id"]]}).get_json() == {"ok": True}
    assert t["b"].get("/api/notifications").get_json() == []
    # With push/email prefs saved (sqlite Row, no SMTP/VAPID configured) it still notifies.
    assert t["b"].post("/settings/notifications", data={"notify_email_messages": "1",
                                                        "notify_push_messages": "1"}).status_code == 302
    assert _send(t["a"], conversation_id=t["conv"], body="second").status_code == 200
    assert [n["body"] for n in t["b"].get("/api/notifications").get_json()] == ["second"]


def test_notifications_unread_list_and_mark_read_are_per_user(trio, db):
    t = trio
    for uid, title in ((t["b_id"], "for bob"), (t["c_id"], "for carol")):
        db.execute("INSERT INTO notifications (user_id, type, title) VALUES (?,?,?)", (uid, "test", title))
    db.commit()
    b_notes = [n for n in t["b"].get("/api/notifications").get_json() if n["type"] == "test"]
    c_notes = [n for n in t["c"].get("/api/notifications").get_json() if n["type"] == "test"]
    assert [n["title"] for n in b_notes] == ["for bob"] and [n["title"] for n in c_notes] == ["for carol"]
    # Carol cannot mark Bob's notification read; Bob can.
    t["c"].post("/api/notifications/read", json={"ids": [b_notes[0]["id"]]})
    assert [n["title"] for n in t["b"].get("/api/notifications").get_json() if n["type"] == "test"] == ["for bob"]
    t["b"].post("/api/notifications/read", json={"ids": [b_notes[0]["id"]]})
    assert [n for n in t["b"].get("/api/notifications").get_json() if n["type"] == "test"] == []
    assert len([n for n in t["c"].get("/api/notifications").get_json() if n["type"] == "test"]) == 1


def test_messaging_mark_read_records_the_signed_in_reader(trio, db):
    # Regression: /api/messages/read took user_id from the payload (default 'coach').
    t = trio
    assert t["b"].post("/api/messages/read", json={"message_ids": [t["m1"]]}).get_json() == {"ok": True}
    t["c"].post("/api/messages/read", json={"message_ids": [t["m1"]], "user_id": str(t["a_id"])})
    readers = {r[0] for r in db.execute("SELECT user_id FROM message_read_receipts WHERE message_id=?", (t["m1"],))}
    assert readers == {str(t["b_id"])}


def test_messaging_mark_read_counts(trio):
    t = trio
    assert t["b"].post("/api/messages/read", json={"message_ids": []}).status_code == 400
    t["b"].post("/api/messages/read", json={"message_ids": [t["m1"]], "user_id": str(t["b_id"])})
    t["b"].post("/api/messages/read", json={"message_ids": [t["m1"]], "user_id": str(t["b_id"])})  # idempotent
    msgs = {m["id"]: m for m in t["a"].get(f"/api/messages/poll?conversation_id={t['conv']}").get_json()}
    assert msgs[t["m1"]]["read_count"] == 1 and msgs[t["m2"]]["read_count"] == 0


def test_messaging_anonymous_cannot_impersonate_sender(app, client, db):
    # Regression: with the gate off an anonymous caller's sender_id was trusted -> could post
    # as any user. Anonymous callers can neither send nor read, even with the gate off.
    assert _flag(db, "ENABLE_AUTH_MIDDLEWARE") is None
    admin, admin_id = _signed_in(app, db, "admin@example.com", "admin")
    bob_id = _add_user(db, "bob@example.com", "player")
    r = _send(client, recipient_id=str(admin_id), body="wire the money", sender_id=str(admin_id))
    assert r.status_code == 401 and r.get_json() == {"error": "Sign-in required."}
    assert db.execute("SELECT COUNT(*) FROM messages WHERE body='wire the money'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0

    conv = _send(admin, recipient_id=str(bob_id), body="real").get_json()["conversation_id"]
    assert _send(client, conversation_id=conv, body="x", sender_id=str(admin_id)).status_code == 401
    assert client.get(f"/api/messages/poll?conversation_id={conv}").status_code == 401
    assert client.get("/api/messages/conversations").status_code == 401
    assert client.post("/api/messages/read", json={"message_ids": [1], "user_id": str(bob_id)}).status_code == 401
    assert db.execute("SELECT COUNT(*) FROM message_read_receipts").fetchone()[0] == 0
    page = client.get(f"/messages?c={conv}")
    assert page.status_code == 200 and b"real" not in page.data
    # A logged-out (replayed) cookie is anonymous too.
    stolen = admin.get_cookie("session").value
    admin.get("/logout")
    replay = app.test_client()
    replay.set_cookie("session", stolen)
    assert _send(replay, conversation_id=conv, body="replayed").status_code == 401


def test_messaging_numeric_recipient_id(trio, db):
    # Regression: numeric JSON recipient_id crashed send ('int' has no .strip) -> 500.
    r = _send(trio["a"], recipient_id=trio["c_id"], body="numeric id")
    assert r.status_code == 200
    conv = r.get_json()["conversation_id"]
    members = {row[0] for row in db.execute("SELECT user_id FROM conversation_members WHERE conversation_id=?", (conv,))}
    assert members == {str(trio["a_id"]), str(trio["c_id"])}
    assert [m["body"] for m in trio["c"].get(f"/api/messages/poll?conversation_id={conv}").get_json()] == ["numeric id"]


# ── 5. settings / profile / notification prefs / entitlements ────────────────

def test_profile_and_notification_prefs_round_trip(app, db):
    c, uid = _signed_in(app, db, "pat@example.com", "player")
    other_id = _add_user(db, "other@example.com", "player", name="Other")
    r = c.post("/profile/edit", data={"display_name": "Pat Q", "phone": "555-0100",
                                      "avatar_url": "https://img.example/p.png", "user_id": str(other_id)},
               follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"] == "/profile"
    me = db.execute("SELECT display_name, phone, avatar_url FROM users WHERE id=?", (uid,)).fetchone()
    assert tuple(me) == ("Pat Q", "555-0100", "https://img.example/p.png")
    assert db.execute("SELECT display_name FROM users WHERE id=?", (other_id,)).fetchone()[0] == "Other"
    with c.session_transaction() as s:
        assert s["user_name"] == "Pat Q"
    page = c.get("/profile")
    assert b"Pat Q" in page.data and b"555-0100" in page.data
    assert c.post("/profile/edit", data={"display_name": "  "}).status_code == 302
    assert db.execute("SELECT display_name FROM users WHERE id=?", (uid,)).fetchone()[0] == "Pat Q"

    r = c.post("/settings/notifications", data={"notify_email_messages": "1", "notify_sms_game_reminder": "on",
                                                "quiet_hours_start": "22:00", "quiet_hours_end": "07:00",
                                                "user_id": str(other_id)}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"] == "/settings/notifications"
    prefs = dict(db.execute("SELECT * FROM user_notification_prefs WHERE user_id=?", (uid,)).fetchone())
    assert {k: prefs[k] for k in ("notify_email_messages", "notify_email_schedule", "notify_push_messages",
                                  "notify_push_schedule", "notify_sms_game_reminder", "quiet_hours_start",
                                  "quiet_hours_end")} == {
        "notify_email_messages": 1, "notify_email_schedule": 0, "notify_push_messages": 0,
        "notify_push_schedule": 0, "notify_sms_game_reminder": 1,
        "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}
    assert db.execute("SELECT COUNT(*) FROM user_notification_prefs WHERE user_id=?", (other_id,)).fetchone()[0] == 0
    assert b"22:00" in c.get("/settings/notifications").data
    # Second save replaces (does not duplicate) the row.
    c.post("/settings/notifications", data={})
    rows = db.execute("SELECT notify_email_messages, quiet_hours_start FROM user_notification_prefs WHERE user_id=?",
                      (uid,)).fetchall()
    assert [tuple(r) for r in rows] == [(0, None)]
    # Anonymous callers are sent to sign in and change nothing.
    anon = app.test_client()
    assert _redirects_to_login(anon.post("/settings/notifications", data={"notify_email_messages": "1"}))
    assert _redirects_to_login(anon.post("/profile/edit", data={"display_name": "Hacked"}))


def test_admin_settings_round_trip(app, db):
    admin, _ = _signed_in(app, db, "admin@example.com", "admin")
    features = app.config["FEATURES"]
    wanted = {name: bool(default) for name, default in features.items()}
    wanted["ENABLE_WEEKLY_PACKET"] = True
    form = {f"feature_{n}": "1" for n, on in wanted.items() if on}
    form.update({"ai_frame_stride": "3", "ai_ball_confidence": "5", "ai_llm_provider": "none"})
    r = admin.post("/settings", data=form, follow_redirects=False)
    assert r.status_code == 302 and urlsplit(r.headers["Location"]).path == "/settings"
    for name, on in wanted.items():
        assert _flag(db, name) == ("1" if on else "0"), name
    ai = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM app_settings WHERE key LIKE 'ai.%'")}
    assert ai["ai.frame_stride"] == "3" and ai["ai.ball_confidence"] == "0.99" and ai["ai.llm_model"] == ""
    page = admin.get("/settings")
    assert page.status_code == 200
    assert re.search(rb'name="feature_ENABLE_WEEKLY_PACKET"[^>]*checked', page.data)


def _entitlement(db, key, enabled=1, starts_at=None, ends_at=None):
    from helpers import get_default_team_id

    team = get_default_team_id(db)
    db.execute(
        """INSERT INTO module_entitlements (team_id, module_key, enabled, starts_at, ends_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(team_id, module_key) DO UPDATE SET enabled=excluded.enabled,
             starts_at=excluded.starts_at, ends_at=excluded.ends_at""",
        (team, key, enabled, starts_at, ends_at),
    )
    db.commit()


def test_entitlements_gate_modules_as_documented(app, client, db):
    # Seeded: base_platform + stats + scouting enabled; playbook row missing -> accessible.
    assert client.get("/scouting").status_code == 200
    assert client.get("/api/scouting/reports").status_code == 200
    assert client.get("/playbook").status_code == 200
    assert client.get("/api/playbook/categories").status_code == 200

    _entitlement(db, "scouting", enabled=0)
    assert client.get("/scouting").status_code == 404
    assert client.get("/api/scouting/reports").status_code == 404
    assert client.get("/playbook").status_code == 200            # other modules unaffected

    _entitlement(db, "scouting", enabled=1, ends_at="2000-01-01 00:00:00")        # expired
    assert client.get("/scouting").status_code == 404
    _entitlement(db, "scouting", enabled=1, starts_at="2999-01-01 00:00:00")      # not started
    assert client.get("/scouting").status_code == 404
    _entitlement(db, "scouting", enabled=1, starts_at="2000-01-01", ends_at="2999-01-01T00:00:00Z")
    assert client.get("/scouting").status_code == 200

    _entitlement(db, "playbook_recognition", enabled=0)
    assert client.get("/playbook").status_code == 404
    _entitlement(db, "playbook_recognition", enabled=1)
    assert client.get("/playbook").status_code == 200

    _entitlement(db, "base_platform", enabled=0)                 # base off -> every add-on off
    assert client.get("/playbook").status_code == 404
    assert client.get("/scouting").status_code == 404
    assert client.get("/schedule").status_code == 200            # non-module pages unaffected


def test_entitlement_window_with_negative_utc_offset(client, db):
    # Regression: a bound with a negative UTC offset (e.g. -06:00) was parsed tz-aware and
    # compared to naive now -> TypeError/500.
    _entitlement(db, "scouting", enabled=1, ends_at="2999-01-01T00:00:00-06:00")
    assert client.get("/scouting").status_code == 200
    _entitlement(db, "scouting", enabled=1, starts_at="2000-01-01T00:00:00-06:00",
                 ends_at="2001-01-01T00:00:00-06:00")                            # expired
    assert client.get("/scouting").status_code == 404
    _entitlement(db, "scouting", enabled=1, starts_at="2999-01-01T00:00:00-06:00")  # not started
    assert client.get("/scouting").status_code == 404


def test_entitlement_negative_offset_is_converted_to_utc():
    from datetime import datetime

    from module_entitlements import _row_is_active

    row = {"starts_at": "2026-01-01T00:00:00-06:00", "ends_at": None}   # == 06:00 UTC
    assert not _row_is_active(row, datetime(2026, 1, 1, 5, 59))
    assert _row_is_active(row, datetime(2026, 1, 1, 6, 0))


# ── issue reports ────────────────────────────────────────────────────────────

def test_issue_report_notifies_admins_and_is_escaped(app, client, db):
    admin, admin_id = _signed_in(app, db, "admin@example.com", "admin")
    _add_user(db, "coach@example.com", "coach")
    payload = '<script>alert(1)</script>'
    r = client.post("/debug/issues", data={"entry_type": "bug", "title": payload, "details": payload,
                                           "return_to": "/schedule", "source_path": "//evil.example/x"},
                    follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"] == "/schedule?message=Report+saved."
    row = db.execute("SELECT * FROM issue_reports").fetchone()
    assert row["entry_type"] == "bug" and row["status"] == "open"
    assert not (row["source_path"] or "").startswith("//")
    notes = db.execute("SELECT user_id, title, link FROM notifications").fetchall()
    assert [(n["user_id"], n["link"]) for n in notes] == [(admin_id, f"/debug/issues?highlight={row['id']}")]
    page = admin.get("/debug")
    assert page.status_code == 200
    assert payload.encode() not in page.data and b"&lt;script&gt;alert(1)&lt;/script&gt;" in page.data


def test_issue_report_offsite_return_to_falls_back_to_debug(client, db):
    # Regression: safe_return_path() fell back to url_for('debug_page') (unqualified) ->
    # BuildError/500 on off-site or missing return_to.
    for data in ({"details": "x", "return_to": "https://evil.example/"},
                 {"details": "y", "return_to": "//evil.example/x"},
                 {"details": "z"}):
        r = client.post("/debug/issues", data=data, follow_redirects=False)
        assert r.status_code == 302, data
        loc = urlsplit(r.headers["Location"])
        assert loc.path == "/debug" and not loc.netloc, data
    assert db.execute("SELECT COUNT(*) FROM issue_reports").fetchone()[0] == 3


def test_admin_can_delete_a_user(app, client, db):
    # Regression: DELETE /api/users/<id> read users.is_admin, which the users schema lacks ->
    # IndexError/500, and had no auth check at all.
    admin, admin_id = _signed_in(app, db, "admin@example.com", "admin")
    coach, _ = _signed_in(app, db, "coach@example.com", "coach")
    victim = _add_user(db, "old@example.com", "player")
    # Anonymous (gate off) and non-admins are refused and delete nothing.
    assert client.delete(f"/api/users/{victim}").status_code == 403
    assert coach.delete(f"/api/users/{victim}").status_code == 403
    assert db.execute("SELECT COUNT(*) FROM users WHERE id=?", (victim,)).fetchone()[0] == 1
    # Admin deletes the player; admins themselves cannot be deleted.
    r = admin.delete(f"/api/users/{victim}")
    assert r.status_code == 200 and r.get_json() == {"status": "deleted"}
    assert db.execute("SELECT COUNT(*) FROM users WHERE id=?", (victim,)).fetchone()[0] == 0
    assert admin.delete(f"/api/users/{victim}").status_code == 404
    assert admin.delete(f"/api/users/{admin_id}").status_code == 403
    assert db.execute("SELECT COUNT(*) FROM users WHERE id=?", (admin_id,)).fetchone()[0] == 1
