"""
test_player_development.py — Tests for Phase 7: Player Development & Practice Engine.
"""
import os
import sqlite3
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import player_development as pd
import app as app_module


@pytest.fixture
def db():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    app_module.app.config["DATABASE"] = db_path
    with app_module.app.app_context():
        app_module.init_db()
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.close()
    os.unlink(db_path)


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    app_module.app.config.update({"TESTING": True, "DATABASE": db_path})
    with app_module.app.app_context():
        app_module.init_db()
    yield app_module.app
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


# ── Development Clips ──────────────────────────────────────────────

def test_create_and_get_clip(db):
    clip = pd.create_clip(db, "Turnover vs press", 10000, 15000,
                           player_id=None, game_id="game_001", clip_category="turnover")
    assert clip["clip_label"] == "Turnover vs press"
    assert clip["clip_start_ms"] == 10000
    assert clip["clip_end_ms"] == 15000
    assert clip["clip_category"] == "turnover"
    clips = pd.get_clips(db)
    assert len(clips) == 1


def test_create_clip_missing_label(db):
    with pytest.raises(ValueError):
        pd.create_clip(db, "", 10000, 15000)


def test_create_clip_invalid_times(db):
    with pytest.raises(ValueError):
        pd.create_clip(db, "Bad clip", 15000, 10000)


def test_update_clip(db):
    clip = pd.create_clip(db, "Old label", 5000, 8000)
    updated = pd.update_clip(db, clip["id"], clip_label="New label", clip_category="defense")
    assert updated["clip_label"] == "New label"
    assert updated["clip_category"] == "defense"


def test_update_clip_not_found(db):
    with pytest.raises(KeyError):
        pd.update_clip(db, 9999, clip_label="X")


def test_delete_clip(db):
    clip = pd.create_clip(db, "To delete", 1000, 2000)
    pd.delete_clip(db, clip["id"])
    assert pd.get_clips(db) == []


def test_filter_clips_by_category(db):
    pd.create_clip(db, "Turnover", 1000, 2000, clip_category="turnover")
    pd.create_clip(db, "Good play", 3000, 4000, clip_category="good_action")
    clips = pd.get_clips(db, category="turnover")
    assert len(clips) == 1
    assert clips[0]["clip_label"] == "Turnover"


# ── Practice Playlists ─────────────────────────────────────────────

def test_create_and_get_playlist(db):
    pl = pd.create_playlist(db, "Turnover Review", level="jr_high")
    assert pl["name"] == "Turnover Review"
    assert pl["level"] == "jr_high"
    assert pl["status"] == "draft"
    playlists = pd.get_playlists(db)
    assert len(playlists) == 1


def test_create_playlist_missing_name(db):
    with pytest.raises(ValueError):
        pd.create_playlist(db, "")


def test_update_playlist(db):
    pl = pd.create_playlist(db, "Old name")
    updated = pd.update_playlist(db, pl["id"], name="New name", status="active")
    assert updated["name"] == "New name"
    assert updated["status"] == "active"


def test_update_playlist_not_found(db):
    with pytest.raises(KeyError):
        pd.update_playlist(db, 9999, name="X")


def test_delete_playlist(db):
    pl = pd.create_playlist(db, "To delete")
    pd.delete_playlist(db, pl["id"])
    assert pd.get_playlists(db) == []


# ── Playlist Clips ─────────────────────────────────────────────────

def test_add_and_remove_clip_from_playlist(db):
    clip = pd.create_clip(db, "Test clip", 1000, 2000)
    pl = pd.create_playlist(db, "Test playlist")
    pd.add_clip_to_playlist(db, pl["id"], clip["id"])
    clips = pd.get_playlist_clips(db, pl["id"])
    assert len(clips) == 1
    assert clips[0]["clip_label"] == "Test clip"

    pd.remove_clip_from_playlist(db, pl["id"], clip["id"])
    clips = pd.get_playlist_clips(db, pl["id"])
    assert len(clips) == 0


# ── Practice Plan Items ────────────────────────────────────────────

def test_create_and_get_plan_item(db):
    # Need a practice first
    db.execute(
        "INSERT INTO practices (season_id, level, practice_date, status, plan_source, plan_text, coach_notes) VALUES (NULL, 'jr_high', '2025-12-01', 'planned', 'manual', 'Test plan', 'Test notes')"
    )
    db.commit()
    practice_id = db.execute("SELECT id FROM practices ORDER BY id DESC LIMIT 1").fetchone()["id"]

    item = pd.create_plan_item(db, practice_id, "Shell Defense Drill",
                                item_type="drill", description="3-on-3 shell", duration_min=15)
    assert item["title"] == "Shell Defense Drill"
    assert item["item_type"] == "drill"
    assert item["duration_min"] == 15

    items = pd.get_plan_items(db, practice_id)
    assert len(items) == 1


def test_create_plan_item_missing_title(db):
    with pytest.raises(ValueError):
        pd.create_plan_item(db, 1, "")


def test_update_plan_item(db):
    db.execute(
        "INSERT INTO practices (season_id, level, practice_date, status, plan_source, plan_text, coach_notes) VALUES (NULL, 'jr_high', '2025-12-01', 'planned', 'manual', 'Test plan', 'Test notes')"
    )
    db.commit()
    practice_id = db.execute("SELECT id FROM practices ORDER BY id DESC LIMIT 1").fetchone()["id"]
    item = pd.create_plan_item(db, practice_id, "Old drill")
    updated = pd.update_plan_item(db, item["id"], title="New drill", duration_min=20)
    assert updated["title"] == "New drill"
    assert updated["duration_min"] == 20


def test_delete_plan_item(db):
    db.execute(
        "INSERT INTO practices (season_id, level, practice_date, status, plan_source, plan_text, coach_notes) VALUES (NULL, 'jr_high', '2025-12-01', 'planned', 'manual', 'Test plan', 'Test notes')"
    )
    db.commit()
    practice_id = db.execute("SELECT id FROM practices ORDER BY id DESC LIMIT 1").fetchone()["id"]
    item = pd.create_plan_item(db, practice_id, "To delete")
    pd.delete_plan_item(db, item["id"])
    assert pd.get_plan_items(db, practice_id) == []


# ── API Endpoints ──────────────────────────────────────────────────

def test_api_clips_crud(client):
    # Create
    r = client.post("/api/clips", data='{"clip_label": "API clip", "clip_start_ms": 1000, "clip_end_ms": 2000}',
                    content_type="application/json")
    assert r.status_code == 201
    clip = r.get_json()
    assert clip["clip_label"] == "API clip"

    # List
    r = client.get("/api/clips")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Get
    r = client.get(f"/api/clips/{clip['id']}")
    assert r.status_code == 200

    # Update
    r = client.put(f"/api/clips/{clip['id']}", data='{"clip_label": "Updated"}',
                   content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["clip_label"] == "Updated"

    # Delete
    r = client.delete(f"/api/clips/{clip['id']}")
    assert r.status_code == 200
    r = client.get("/api/clips")
    assert r.get_json() == []


def test_api_playlists_crud(client):
    # Create
    r = client.post("/api/playlists", data='{"name": "API playlist"}',
                    content_type="application/json")
    assert r.status_code == 201
    pl = r.get_json()
    assert pl["name"] == "API playlist"

    # List
    r = client.get("/api/playlists")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Get with clips
    r = client.get(f"/api/playlists/{pl['id']}")
    assert r.status_code == 200
    assert r.get_json()["clips"] == []

    # Update
    r = client.put(f"/api/playlists/{pl['id']}", data='{"status": "active"}',
                   content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["status"] == "active"

    # Delete
    r = client.delete(f"/api/playlists/{pl['id']}")
    assert r.status_code == 200


def test_api_plan_items_crud(client):
    # Create a season first
    r = client.post("/api/seasons", data='{"name": "Test", "start_date": "2025-01-01", "end_date": "2025-12-31"}',
                    content_type="application/json")
    assert r.status_code == 201
    season_id = r.get_json()["id"]

    # Create a practice via the practices save endpoint
    r = client.post("/practices/save", data={
        "season_id": season_id,
        "practice_date": "2025-12-10",
        "level": "jr_high",
        "status": "planned",
        "plan_source": "manual",
        "plan_text": "Test plan",
        "coach_notes": "Test notes",
    }, follow_redirects=True)
    assert r.status_code == 200

    # Create plan item via API
    r = client.post(f"/api/practices/1/plan-items",
                    data='{"title": "Drill 1", "item_type": "drill", "duration_min": 10}',
                    content_type="application/json")
    assert r.status_code == 201
    item = r.get_json()
    assert item["title"] == "Drill 1"

    # List
    r = client.get(f"/api/practices/1/plan-items")
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Update
    r = client.put(f"/api/plan-items/{item['id']}", data='{"title": "Updated drill"}',
                   content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["title"] == "Updated drill"

    # Delete
    r = client.delete(f"/api/plan-items/{item['id']}")
    assert r.status_code == 200


# ── UI Pages ──────────────────────────────────────────────────────

def test_player_development_page_renders(client):
    r = client.get("/player-development")
    assert r.status_code == 200
    assert b"Player Development" in r.data


def test_practice_playlists_page_renders(client):
    r = client.get("/practice-playlists")
    assert r.status_code == 200
    assert b"Practice Playlists" in r.data
