"""Regression journeys for the open items left after the 2026-09-26 review fixes.

Each test reproduced its bug on 8b5c670 before the fix (see docs/validation/open_items.md).
"""
from __future__ import annotations

import sqlite3

import pytest

pytestmark = pytest.mark.e2e


def _conn(app) -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"], timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _create_game(client, key) -> int:
    resp = client.post("/api/games", json={"source_type": "manual", "source_key": key})
    assert resp.status_code == 201, resp.data
    return int(resp.get_json()["id"])


def _tag(client, game_id, event_type, player, ts, shot_result=None):
    payload = {"game_id": game_id, "event_type": event_type, "player": player, "timestamp_ms": ts}
    if shot_result:
        payload["shot_result"] = shot_result
    resp = client.post("/api/save_event", json=payload)
    assert resp.status_code == 200, resp.data
    return resp.get_json()["id"]


# ── 1. deleting an event that a saved clip points to ─────────────────────────

def test_delete_event_referenced_by_clips_keeps_the_clips(app, client):
    gid = _create_game(client, "open-delete-clipped")
    ev = _tag(client, gid, "made_three", "4", 12_000, "made")
    conn = _conn(app)
    clip_id = conn.execute(
        """INSERT INTO clips (game_id, event_id, clip_type, title, start_timestamp_ms, end_timestamp_ms)
           VALUES (?, ?, 'event', 'Corner three', 9000, 15000)""",
        (gid, ev),
    ).lastrowid
    dev_id = conn.execute(
        """INSERT INTO player_development_clips (event_id, clip_start_ms, clip_end_ms, clip_label)
           VALUES (?, 9000, 15000, 'Catch and shoot')""",
        (ev,),
    ).lastrowid
    conn.commit()
    conn.close()

    resp = client.delete(f"/api/events/{ev}")
    assert resp.status_code == 200, resp.data

    conn = _conn(app)
    try:
        assert conn.execute("SELECT COUNT(*) FROM events WHERE id=?", (ev,)).fetchone()[0] == 0
        # the coach's clips survive, just no longer tied to the deleted tag
        clip = conn.execute("SELECT title, event_id FROM clips WHERE id=?", (clip_id,)).fetchone()
        dev = conn.execute(
            "SELECT clip_label, event_id FROM player_development_clips WHERE id=?", (dev_id,)
        ).fetchone()
        assert dict(clip) == {"title": "Corner three", "event_id": None}
        assert dict(dev) == {"clip_label": "Catch and shoot", "event_id": None}
    finally:
        conn.close()


# ── 2. User management page + deleting a user other rows point at ────────────

def _add_user(conn, email, role, name):
    from blueprints.users import _hash_password

    return conn.execute(
        "INSERT INTO users (email, password_hash, display_name, role, is_active) VALUES (?,?,?,?,1)",
        (email, _hash_password("pw-12345678"), name, role),
    ).lastrowid


def _login(client, email):
    resp = client.post("/login", data={"email": email, "password": "pw-12345678"})
    assert resp.status_code in (302, 303)


def test_admin_user_list_has_the_fields_the_page_renders(app, client):
    conn = _conn(app)
    _add_user(conn, "admin@example.com", "admin", "Ada Admin")
    _add_user(conn, "coach@example.com", "coach", "Cole Coach")
    for i in range(22):  # more than the 20-row autocomplete limit
        _add_user(conn, f"p{i}@example.com", "player", f"Player {i}")
    conn.commit()
    conn.close()

    # anonymous and non-admin callers cannot list accounts
    assert client.get("/api/admin/users").status_code in (401, 403)
    _login(client, "coach@example.com")
    assert client.get("/api/admin/users").status_code == 403
    client.get("/logout")

    _login(client, "admin@example.com")
    rows = client.get("/api/admin/users").get_json()
    assert len(rows) == 24
    by_email = {r["email"]: r for r in rows}
    assert by_email["admin@example.com"]["display_name"] == "Ada Admin"
    assert by_email["admin@example.com"]["role"] == "admin"
    assert by_email["coach@example.com"]["role"] == "coach"
    assert all(r.get("created_at") for r in rows)


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node not installed")
def test_users_page_renders_names_roles_and_no_delete_for_admins(app, client):
    import json
    import re
    import subprocess

    conn = _conn(app)
    _add_user(conn, "admin@example.com", "admin", "Ada Admin")
    _add_user(conn, "coach@example.com", "coach", "<img src=x onerror=alert(1)>")
    conn.commit()
    conn.close()
    _login(client, "admin@example.com")
    html = client.get("/users").get_data(as_text=True)
    rows = client.get("/api/admin/users").get_json()

    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    page_js = next(s for s in scripts if "loadUsers" in s)
    escape_js = next((s for s in scripts if "function escapeHtml" in s), "")
    harness = (
        "const out = {};\n"
        "const document = { getElementById: () => ({ set innerHTML(v) { out.html = v; } }) };\n"
        "const window = globalThis; const alert = () => {}; const confirm = () => true;\n"
        f"const ROWS = {json.dumps(rows)};\n"
        "const fetch = async () => ({ ok: true, json: async () => ROWS });\n"
        + escape_js + "\n" + page_js + "\n"
        "setTimeout(() => console.log(out.html), 20);\n"
    )
    rendered = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True).stdout
    assert "undefined" not in rendered
    assert "Ada Admin" in rendered
    assert "<img" not in rendered and "&lt;img" in rendered
    admin_row = next(r for r in rendered.split("<tr>") if "admin@example.com" in r)
    coach_row = next(r for r in rendered.split("<tr>") if "coach@example.com" in r)
    assert "deleteUser" not in admin_row
    assert "deleteUser" in coach_row


def test_admin_can_delete_a_user_other_rows_point_at(app, client):
    conn = _conn(app)
    _add_user(conn, "admin@example.com", "admin", "Ada Admin")
    coach = _add_user(conn, "coach@example.com", "coach", "Cole Coach")
    conn.commit()
    conn.close()
    gid = _create_game(client, "open-user-refs")
    ev = _tag(client, gid, "steal", "3", 1_000)
    conn = _conn(app)
    conn.execute("UPDATE events SET created_by_user_id=?, reviewed_by_user_id=? WHERE id=?", (coach, coach, ev))
    clip = conn.execute(
        """INSERT INTO clips (game_id, event_id, title, start_timestamp_ms, end_timestamp_ms, created_by_user_id)
           VALUES (?, ?, 'Steal', 0, 3000, ?)""",
        (gid, ev, coach),
    ).lastrowid
    conn.execute("UPDATE review_items SET reviewed_by_user_id=? WHERE entity_id=?", (coach, ev))
    conn.commit()
    conn.close()

    _login(client, "admin@example.com")
    resp = client.delete(f"/api/users/{coach}")
    assert resp.status_code == 200, resp.data

    conn = _conn(app)
    try:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE id=?", (coach,)).fetchone()[0] == 0
        # the coach's work stays, attributed to nobody
        row = conn.execute("SELECT created_by_user_id, reviewed_by_user_id FROM events WHERE id=?", (ev,)).fetchone()
        assert tuple(row) == (None, None)
        assert conn.execute("SELECT created_by_user_id FROM clips WHERE id=?", (clip,)).fetchone()[0] is None
    finally:
        conn.close()
    # admins still cannot be deleted
    admin_id = next(r["id"] for r in client.get("/api/admin/users").get_json() if r["role"] == "admin")
    assert client.delete(f"/api/users/{admin_id}").status_code == 403


# ── 3. Assistant turnover/clip lookups must not substring-match player names ─

def _ai_event(client, game_id, player, event_type, ts):
    """AI draft accepted through the review route (a trusted event)."""
    resp = client.post("/api/save_event", json={
        "game_id": game_id, "player": player, "event_type": event_type, "timestamp_ms": ts,
        "human_verified": False, "source_type": "ai",
    })
    eid = resp.get_json()["id"]
    assert client.post(f"/api/review/events/{eid}/accept", json={}).status_code == 200
    return eid


def _ask(client, question, game_id, player):
    resp = client.post("/api/assistant/query", json={"question": question, "game_id": game_id, "player": player})
    assert resp.status_code == 200, resp.data
    return resp.get_json()


def test_assistant_turnovers_and_clips_use_the_exact_player(app, client):
    gid = _create_game(client, "open-assistant-names")
    al_to = _ai_event(client, gid, "Al", "turnover", 1_000)
    alice_to1 = _ai_event(client, gid, "Alice", "turnover", 2_000)
    _ai_event(client, gid, "Alice", "turnover", 3_000)
    conn = _conn(app)
    for eid, title in ((al_to, "Al turnover"), (alice_to1, "Alice turnover")):
        conn.execute(
            """INSERT INTO clips (game_id, event_id, title, start_timestamp_ms, end_timestamp_ms)
               VALUES (?, ?, ?, 0, 1000)""",
            (gid, eid, title),
        )
    conn.commit()
    conn.close()

    al = _ask(client, "How many turnovers did Al have?", gid, "Al")
    assert al["answer"].startswith("Al has 1 reviewed turnover"), al["answer"]
    alice = _ask(client, "How many turnovers did Alice have?", gid, "Alice")
    assert alice["answer"].startswith("Alice has 2 reviewed turnover"), alice["answer"]

    clips = _ask(client, "Show me clips for Al", gid, "Al")
    titles = [c["title"] for c in clips["citations"] if c.get("type") == "clip"]
    assert titles == ["Al turnover"]
    # a partial name with no exact player still finds the close match
    partial = _ask(client, "How many turnovers did Ali have?", gid, "Ali")
    assert partial["answer"].startswith("Ali has 2 reviewed turnover"), partial["answer"]


# ── 4. Scouting report editor: every stored value is escaped ─────────────────

def _render_editor(client, rid, target_id):
    """Run the editor page's own scripts (with base.html's escapeHtml) under node against the
    real report API and return the innerHTML written into #target_id."""
    import json
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = client.get(f"/scouting/reports/{rid}").get_data(as_text=True)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    escape_js = next(sc for sc in scripts if "function escapeHtml(" in sc)
    page_js = next(sc for sc in scripts if "function loadReport" in sc)
    api = {f"/api/scouting/reports/{rid}": client.get(f"/api/scouting/reports/{rid}").get_json()}
    harness = """
const els = {};
const el = (id) => (els[id] = els[id] || {innerHTML: '', textContent: '', value: '', href: '',
  dataset: {reportId: %s}, addEventListener() {}});
globalThis.document = {getElementById: el, addEventListener() {}, querySelector: () => el('q'),
  querySelectorAll: () => []};
globalThis.window = {location: {}};
const API = %s;
globalThis.fetch = (url) => Promise.resolve({ok: true, json: () => Promise.resolve(API[url])});
%s
%s
loadReport();
setTimeout(() => process.stdout.write(JSON.stringify(el(%s).innerHTML)), 50);
""" % (json.dumps(str(rid)), json.dumps(api), escape_js, page_js, json.dumps(target_id))
    out = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_scouting_editor_escapes_numbers_times_and_jerseys(client):
    from tests.e2e.test_journey_scouting_practice import _assert_inert

    x = "<img src=x onerror=alert(1)>"
    rid = client.post("/api/scouting/reports", json={"opponent_name": "Vale", "scout_date": "2026-01-01"}).get_json()["id"]
    base = f"/api/scouting/reports/{rid}"
    for path, body in (
        ("personnel", {"jersey_number": x, "player_name": "Opp", "role": "wing", "ppp": x}),
        ("offensive-sets", {"set_name": "Horns", "frequency": x, "ppp": x}),
        ("situational", {"situation": "BLOB", "description": "d", "frequency": x, "ppp": x}),
        ("defensive-tendencies", {"scheme": "man", "ppp_allowed": x}),
        ("mismatches", {"opponent_jersey": x, "opponent_name": "Opp", "vulnerability": "v"}),
        ("clips", {"clip_type": "t", "description": "d", "game_time": x}),
    ):
        resp = client.post(f"{base}/{path}", json=body)
        assert resp.status_code == 201, (path, resp.data)

    for target in ("personnel-list", "offensive-sets-list", "situational-list",
                   "defensive-list", "mismatches-list", "clips-list"):
        html = _render_editor(client, rid, target)
        assert html, target
        _assert_inert(html, [x])


# ── 5. Progress/status counters are per run, not summed across a shared game ─

def test_counts_are_per_run_when_runs_share_a_relational_game(app, client):
    gid = _create_game(client, "open-nfhs-counts")
    conn = _conn(app)
    vid = conn.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes, game_id, relational_game_id)
           VALUES ('g.mp4', 'nfhs_open.mp4', '/nonexistent/nfhs_open.mp4', 10, 'nfhs_open', ?)""",
        (gid,),
    ).lastrowid
    runs = {"nfhs_open": (5, 4, "primary"), "nfhs_open__rerun_1": (3, 2, "rerun")}
    for key, (n_det, n_ev, kind) in runs.items():
        conn.execute(
            """INSERT INTO analysis_runs (game_id, analysis_key, video_path, source_video_id, base_analysis_key,
                                          run_kind, status, progress_pct, completed_at)
               VALUES (?, ?, '/nonexistent/nfhs_open.mp4', ?, 'nfhs_open', ?, 'completed', 100, CURRENT_TIMESTAMP)""",
            (gid, key, vid, kind),
        )
        for f in range(n_det):
            conn.execute(
                """INSERT INTO detections (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                                           confidence, x_center, y_center, width, height)
                   VALUES (?, ?, ?, ?, 'person', 0.9, 10, 10, 5, 5)""",
                (key, gid, f, f * 33),
            )
        for i in range(n_ev):
            conn.execute(
                """INSERT INTO events (game_id, relational_game_id, event_type, timestamp_ms, source_type, review_status)
                   VALUES (?, ?, 'possession_change', ?, 'ai', 'pending')""",
                (key, gid, i * 1000),
            )
    conn.commit()
    conn.close()

    for key, (n_det, n_ev, _) in runs.items():
        status = client.get(f"/api/analysis_status/{key}").get_json()
        assert (status["detection_count"], status["event_count"]) == (n_det, n_ev), ("status", key, status)
        progress = client.get(f"/api/analysis_progress/{key}").get_json()
        assert (progress["detection_count"], progress["event_count"]) == (n_det, n_ev), ("progress", key)
    # the video row reports its latest run (the rerun), not the sum of both
    video = client.get(f"/api/videos/{vid}").get_json()
    video = video.get("video", video)
    assert (video["detection_count"], video["event_count"]) == (3, 2), video


# ── 6. /api/upload_video never overwrites an existing file ───────────────────

def test_upload_video_keeps_both_files_with_the_same_name(app, client):
    import io
    import os

    first = client.post("/api/upload_video", data={"file": (io.BytesIO(b"FIRST-FILM"), "game.mp4")},
                        content_type="multipart/form-data")
    second = client.post("/api/upload_video", data={"file": (io.BytesIO(b"SECOND-FILM"), "game.mp4")},
                         content_type="multipart/form-data")
    assert first.status_code == 200 and second.status_code == 200
    a, b = first.get_json()["filename"], second.get_json()["filename"]
    assert a != b
    folder = app.config["UPLOAD_FOLDER"]
    with open(os.path.join(folder, a), "rb") as fh:
        assert fh.read() == b"FIRST-FILM"
    with open(os.path.join(folder, b), "rb") as fh:
        assert fh.read() == b"SECOND-FILM"
    # a name that sanitises to nothing is refused rather than written as ""
    bad = client.post("/api/upload_video", data={"file": (io.BytesIO(b"x"), "../../")},
                      content_type="multipart/form-data")
    assert bad.status_code == 400


# ── 7. Messages page shows "Signed in as" only for a live session ────────────

def test_messages_page_does_not_show_a_logged_out_cookie_as_signed_in(app, client):
    conn = _conn(app)
    _add_user(conn, "coach@example.com", "coach", "Cole Coach")
    conn.commit()
    conn.close()
    _login(client, "coach@example.com")
    page = client.get("/messages").get_data(as_text=True)
    assert "Signed in as <strong>Cole Coach</strong>" in page
    stolen = client.get_cookie("session").value

    client.get("/logout")
    client.set_cookie("session", stolen)  # replay the copied cookie after logout
    page = client.get("/messages").get_data(as_text=True)
    assert "Signed in as" not in page
    assert "Cole Coach" not in page


# ── 8. /uploads never renders active content (ported from 8853d38) ───────────

def test_uploads_force_download_for_active_content(app, client):
    import os

    folder = app.config["UPLOAD_FOLDER"]
    for name, body in (("evil.html", b"<script>alert(1)</script>"), ("evil.svg", b"<svg onload=alert(1)/>"),
                       ("film.png", b"\x89PNG\r\n\x1a\n")):
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(body)
    for name in ("evil.html", "evil.svg"):
        resp = client.get(f"/uploads/{name}")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/octet-stream", name
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert "attachment" in resp.headers.get("Content-Disposition", "")
    img = client.get("/uploads/film.png")
    assert img.headers["Content-Type"].startswith("image/png")
    assert client.get("/uploads/../app.py").status_code == 404


# ── 9. login_required APIs answer JSON 401, not a login redirect ─────────────

def test_login_required_api_returns_json_401(client):
    resp = client.get("/api/users")  # users blueprint, @login_required
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "authentication required"}
    page = client.get("/profile")  # pages still redirect to the login form
    assert page.status_code in (302, 303) and "/login" in page.headers["Location"]
