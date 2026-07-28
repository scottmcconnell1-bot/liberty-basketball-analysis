"""
test_season_management.py – Unit tests for season_management.py helper functions.
"""
import os
import sqlite3
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import season_management as sm


@pytest.fixture
def db():
    """In-memory SQLite DB seeded with schema."""
    import app as app_module
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


# ── Seasons ──────────────────────────────────────────────────────────

def test_create_and_get_season(db):
    s = sm.create_season(db, "2025-26", "2025-11-01", "2026-03-01")
    assert s["name"] == "2025-26"
    seasons = sm.get_seasons(db)
    assert len(seasons) == 1


def test_create_season_missing_fields(db):
    with pytest.raises(ValueError):
        sm.create_season(db, "", "2025-01-01", "2025-12-31")


def test_update_season(db):
    s = sm.create_season(db, "Old", "2025-01-01", "2025-12-31")
    updated = sm.update_season(db, s["id"], name="New")
    assert updated["name"] == "New"


def test_update_season_not_found(db):
    with pytest.raises(KeyError):
        sm.update_season(db, 9999, name="X")


def test_delete_season(db):
    s = sm.create_season(db, "Temp", "2025-01-01", "2025-12-31")
    sm.delete_season(db, s["id"])
    assert sm.get_seasons(db) == []


def test_delete_season_cascades_games(db):
    s = sm.create_season(db, "CascadeTest", "2025-01-01", "2025-12-31")
    sm.create_scheduled_game(db, s["id"], "2025-12-01", "Opponent A")
    sm.delete_season(db, s["id"])
    games = sm.get_scheduled_games(db)
    assert games == []


# ── Scheduled Games ──────────────────────────────────────────────────

def test_create_and_list_scheduled_game(db):
    s = sm.create_season(db, "S1", "2025-11-01", "2026-03-01")
    g = sm.create_scheduled_game(db, s["id"], "2025-12-10", "Riverside")
    assert g["opponent_name"] == "Riverside"
    games = sm.get_scheduled_games(db)
    assert len(games) == 1


def test_create_scheduled_game_missing_fields(db):
    with pytest.raises(ValueError):
        sm.create_scheduled_game(db, None, "2025-12-01", "Opp")


def test_filter_by_season(db):
    s1 = sm.create_season(db, "Season1", "2025-01-01", "2025-12-31")
    s2 = sm.create_season(db, "Season2", "2026-01-01", "2026-12-31")
    sm.create_scheduled_game(db, s1["id"], "2025-12-01", "TeamA")
    sm.create_scheduled_game(db, s2["id"], "2026-01-15", "TeamB")
    games = sm.get_scheduled_games(db, season_id=s1["id"])
    assert len(games) == 1
    assert games[0]["opponent_name"] == "TeamA"


def test_update_scheduled_game(db):
    s = sm.create_season(db, "S", "2025-01-01", "2025-12-31")
    g = sm.create_scheduled_game(db, s["id"], "2025-12-01", "Old Opp")
    updated = sm.update_scheduled_game(db, g["id"], opponent_name="New Opp")
    assert updated["opponent_name"] == "New Opp"


def test_update_scheduled_game_not_found(db):
    with pytest.raises(KeyError):
        sm.update_scheduled_game(db, 9999, opponent_name="X")


def test_delete_scheduled_game(db):
    s = sm.create_season(db, "S", "2025-01-01", "2025-12-31")
    g = sm.create_scheduled_game(db, s["id"], "2025-12-01", "Opp")
    sm.delete_scheduled_game(db, g["id"])
    assert sm.get_scheduled_games(db) == []
