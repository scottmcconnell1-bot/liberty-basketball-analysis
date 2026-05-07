"""
test_schema.py – Verify all expected tables and key columns exist.
"""
import pytest


EXPECTED_TABLES = [
    "analysis_runs",
    "detections",
    "events",
    "seasons",
    "scheduled_games",
    "games",
    "nfhs_matches",
    "sources",
    "players",
    "stats",
    "practices",
    "player_development_clips",
    "practice_playlists",
    "practice_playlist_clips",
    "practice_plan_items",
]

EXPECTED_COLUMNS = {
    "events": ["id", "game_id", "player", "event_type", "shot_result",
                "timestamp_ms", "details_json", "source_video", "source_frame",
                "human_verified", "confidence", "created_at"],
    "seasons": ["id", "name", "start_date", "end_date", "created_at"],
    "scheduled_games": ["id", "season_id", "program_name", "gender", "level",
                        "game_date", "game_time", "location_type", "opponent_name",
                        "tournament_name", "status", "notes", "created_at", "updated_at"],
    "players": ["id", "name", "jersey_number", "position", "grade",
                "program_name", "gender", "level", "season_id", "tracker_id", "created_at"],
    "stats": ["id", "game_id", "player_id", "player_name", "pts", "fgm", "fga",
              "threes_made", "threes_att", "ast", "reb", "tov", "stl", "blk"],
}


def get_tables(db):
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def get_columns(db, table):
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_all_tables_exist(db):
    tables = get_tables(db)
    for table in EXPECTED_TABLES:
        assert table in tables, f"Missing table: {table}"


def test_events_columns(db):
    cols = get_columns(db, "events")
    for col in EXPECTED_COLUMNS["events"]:
        assert col in cols, f"events missing column: {col}"


def test_seasons_columns(db):
    cols = get_columns(db, "seasons")
    for col in EXPECTED_COLUMNS["seasons"]:
        assert col in cols, f"seasons missing column: {col}"


def test_scheduled_games_columns(db):
    cols = get_columns(db, "scheduled_games")
    for col in EXPECTED_COLUMNS["scheduled_games"]:
        assert col in cols, f"scheduled_games missing column: {col}"


def test_players_columns(db):
    cols = get_columns(db, "players")
    for col in EXPECTED_COLUMNS["players"]:
        assert col in cols, f"players missing column: {col}"


def test_stats_columns(db):
    cols = get_columns(db, "stats")
    for col in EXPECTED_COLUMNS["stats"]:
        assert col in cols, f"stats missing column: {col}"
