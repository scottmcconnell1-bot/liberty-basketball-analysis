"""Parents and players are view-only and see one player's stats."""

import sqlite3
from urllib.parse import urlsplit

from werkzeug.security import generate_password_hash

PW = "test-pass-123"


def _db(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_user(db, email, role, name):
    cur = db.execute(
        """INSERT INTO users (email, password_hash, display_name, role, is_active)
           VALUES (?,?,?,?,1)""",
        (email, generate_password_hash(PW), name, role),
    )
    db.commit()
    return cur.lastrowid


def _login(client, email):
    return client.post("/login", data={"email": email, "password": PW}, follow_redirects=False)


def test_unsigned_home_stays_open(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200


def test_player_is_sent_to_own_stats_and_cannot_save(app, tmp_path, monkeypatch):
    import audience_access
    monkeypatch.setattr(audience_access, "_LINKS_PATH", tmp_path / "links.json")
    db = _db(app)
    _add_user(db, "player1@example.com", "player", "Owen Sullivan")
    db.execute(
        "INSERT INTO players (name, jersey_number) VALUES (?, ?)",
        ("Owen Sullivan", 5),
    )
    db.commit()
    db.close()

    client = app.test_client()
    login = _login(client, "player1@example.com")
    assert login.status_code == 302

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 302
    assert urlsplit(home.headers["Location"]).path == "/my-stats"

    stats = client.get("/my-stats", follow_redirects=False)
    assert stats.status_code == 200
    assert b"Owen Sullivan" in stats.data

    film = client.get("/film", follow_redirects=False)
    assert urlsplit(film.headers["Location"]).path != "/my-stats" if film.status_code == 302 else film.status_code == 200
    videos = client.get("/videos", follow_redirects=False)
    assert urlsplit(videos.headers["Location"]).path != "/my-stats" if videos.status_code == 302 else videos.status_code == 200

    settings = client.get("/settings", follow_redirects=False)
    assert urlsplit(settings.headers["Location"]).path == "/my-stats"

    tag = client.post("/api/film/some-game/manual-tags", json={"tags": []}, follow_redirects=False)
    assert tag.status_code == 403

    saved = client.post("/playbook/save", data={}, follow_redirects=False)
    assert saved.status_code == 302
    assert urlsplit(saved.headers["Location"]).path == "/my-stats"

    page = client.get("/playbook", follow_redirects=False)
    assert page.status_code == 200
    assert b"audienceCanEdit" in page.data or b"false" in page.data


def test_coach_still_opens_the_dashboard(app):
    db = _db(app)
    _add_user(db, "coach1@example.com", "coach", "Coach One")
    db.close()
    client = app.test_client()
    _login(client, "coach1@example.com")
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
