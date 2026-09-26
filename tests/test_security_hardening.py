"""Admin reset protection, flag-gated sign-in, and password hashing."""

import hashlib

from blueprints.users import _hash_password, _verify_password


def _add_user(db, email, role, password="correct-horse-1", pw_hash=None):
    db.execute(
        """INSERT INTO users (email, password_hash, display_name, role, is_active)
           VALUES (?,?,?,?,1)""",
        (email, pw_hash or _hash_password(password), email.split("@")[0], role),
    )
    db.commit()


def _login(client, email, password="correct-horse-1", next_url=None):
    url = "/login" if next_url is None else f"/login?next={next_url}"
    return client.post(url, data={"email": email, "password": password}, follow_redirects=False)


def _enable_auth_gate(db):
    db.execute(
        """INSERT INTO app_settings (key, value) VALUES ('feature.ENABLE_AUTH_MIDDLEWARE', '1')
           ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
    )
    db.commit()


# ── /api/admin/reset ─────────────────────────────────────────────────────────

def _seed_video_with_events(db):
    db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes, game_id)
           VALUES ('g.mp4', 'g.mp4', '/nonexistent/g.mp4', 10, 'reset_game')"""
    )
    cur = db.execute(
        """INSERT INTO events (game_id, event_type, timestamp_ms, source_type, review_status)
           VALUES ('reset_game', 'made_two', 1000, 'ai', 'pending')"""
    )
    event_id = cur.lastrowid
    game_id = db.execute(
        "INSERT INTO games (source_type, source_key) VALUES ('manual', 'reset_game')"
    ).lastrowid
    # A row that references events(id) makes a plain DELETE FROM events fail the FK check.
    db.execute(
        """INSERT INTO possessions (game_id, start_timestamp_ms, start_event_id)
           VALUES (?, 1000, ?)""",
        (game_id, event_id),
    )
    db.commit()


def test_admin_reset_refuses_anonymous(client, db):
    _seed_video_with_events(db)
    resp = client.post("/api/admin/reset")
    assert resp.status_code == 403
    assert db.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_admin_reset_refuses_non_admin(client, db):
    _seed_video_with_events(db)
    _add_user(db, "coach@example.com", "coach")
    assert _login(client, "coach@example.com").status_code in (302, 303)
    assert client.post("/api/admin/reset").status_code == 403
    assert db.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1


def test_admin_reset_by_admin_clears_dependent_rows(client, db):
    _seed_video_with_events(db)
    _add_user(db, "admin@example.com", "admin")
    assert _login(client, "admin@example.com").status_code in (302, 303)
    resp = client.post("/api/admin/reset")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    for table in ("videos", "events", "possessions"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


# ── ENABLE_AUTH_MIDDLEWARE ───────────────────────────────────────────────────

def test_auth_gate_off_by_default_keeps_routes_open(client):
    assert client.get("/schedule").status_code == 200
    assert client.get("/api/games").status_code == 200


def test_auth_gate_on_blocks_anonymous_pages_and_apis(client, db):
    _enable_auth_gate(db)
    page = client.get("/schedule", follow_redirects=False)
    assert page.status_code in (302, 303)
    assert "/login" in page.headers["Location"]
    api = client.get("/api/games")
    assert api.status_code == 401
    assert api.get_json()["error"]


def test_auth_gate_on_leaves_login_and_static_public(client, db):
    _enable_auth_gate(db)
    assert client.get("/login").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/static/manifest.json").status_code == 200


def test_auth_gate_on_allows_signed_in_user(client, db):
    _enable_auth_gate(db)
    _add_user(db, "coach@example.com", "coach")
    assert _login(client, "coach@example.com").status_code in (302, 303)
    assert client.get("/schedule").status_code == 200
    assert client.get("/api/games").status_code == 200


def test_auth_gate_on_allows_coach_portal_session(client, db, monkeypatch):
    monkeypatch.setenv("LIBERTY_COACH_PASSWORD", "test-coach-secret")
    _enable_auth_gate(db)
    assert client.post("/coach", data={"password": "test-coach-secret"}).status_code in (302, 303)
    assert client.get("/schedule").status_code == 200


# ── passwords and login redirect ─────────────────────────────────────────────

def test_new_passwords_use_a_slow_kdf():
    stored = _hash_password("correct-horse-1")
    assert stored.split("$", 1)[0].startswith(("scrypt:", "pbkdf2:"))
    assert _verify_password("correct-horse-1", stored)
    assert not _verify_password("wrong", stored)


def test_legacy_sha256_hash_still_logs_in_and_is_upgraded(client, db):
    salt = "abcd1234"
    legacy = f"{salt}${hashlib.sha256((salt + 'old-password-1').encode()).hexdigest()}"
    _add_user(db, "legacy@example.com", "coach", pw_hash=legacy)
    assert _verify_password("old-password-1", legacy)
    assert not _verify_password("nope", legacy)

    resp = _login(client, "legacy@example.com", "old-password-1")
    assert resp.status_code in (302, 303)
    upgraded = db.execute(
        "SELECT password_hash FROM users WHERE email='legacy@example.com'"
    ).fetchone()[0]
    assert upgraded != legacy
    assert upgraded.split("$", 1)[0].startswith(("scrypt:", "pbkdf2:"))
    assert _verify_password("old-password-1", upgraded)


def test_login_ignores_offsite_next_redirect(client, db):
    _add_user(db, "coach@example.com", "coach")
    resp = _login(client, "coach@example.com", next_url="https://evil.example/phish")
    assert resp.status_code in (302, 303)
    assert "evil.example" not in resp.headers["Location"]
    local = _login(client, "coach@example.com", next_url="/schedule")
    assert local.headers["Location"].endswith("/schedule")


def test_notification_preferences_save(client, db):
    _add_user(db, "coach@example.com", "coach")
    _login(client, "coach@example.com")
    resp = client.post(
        "/settings/notifications",
        data={"notify_email_messages": "1", "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    row = db.execute("SELECT * FROM user_notification_prefs").fetchone()
    assert row["notify_email_messages"] == 1
    assert row["quiet_hours_start"] == "22:00"
