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
    "teams",
    "players",
    "roster_memberships",
    "stats",
    "practices",
    "video_assets",
    "event_types",
    "provenance_records",
    "module_entitlements",
    "player_development_clips",
    "practice_playlists",
    "practice_playlist_clips",
    "practice_plan_items",
]

EXPECTED_COLUMNS = {
    "analysis_runs": ["id", "game_id", "analysis_key", "video_path", "source_video_id",
                    "base_game_id", "base_analysis_key", "run_label", "settings_json",
                    "run_kind", "status", "started_at", "completed_at", "error_message"],
    "events": ["id", "game_id", "player", "event_type", "shot_result",
                "timestamp_ms", "details_json", "source_video", "source_frame",
                "human_verified", "confidence", "created_at"],
    "seasons": ["id", "name", "start_date", "end_date", "created_at"],
    "scheduled_games": ["id", "season_id", "program_name", "gender", "level",
                        "game_date", "game_time", "location_type", "opponent_name",
                        "tournament_name", "status", "notes", "created_at", "updated_at"],
    "players": ["id", "name", "jersey_number", "position", "grade",
                "program_name", "gender", "level", "season_id", "tracker_id", "created_at"],
    "teams": ["id", "organization_name", "team_name", "program_name", "gender",
              "level", "season_default_id", "created_at", "updated_at"],
    "roster_memberships": ["id", "player_id", "team_id", "season_id", "jersey_number",
                           "position", "grade", "status", "start_date", "end_date",
                           "created_at", "updated_at"],
    "stats": ["id", "game_id", "player_id", "player_name", "pts", "fgm", "fga",
              "threes_made", "threes_att", "ast", "reb", "tov", "stl", "blk"],
    "video_assets": ["id", "game_id", "source_id", "original_filename", "stored_filename",
                     "file_path", "source_type", "camera_label", "angle_label",
                     "file_size_bytes", "duration_ms", "frame_rate", "width", "height",
                     "checksum", "transcode_status", "sync_group_id", "primary_asset",
                     "created_at", "updated_at"],
    "event_types": ["id", "code", "label", "category", "counts_for_stats",
                    "is_scoring_event", "is_possession_boundary", "created_at", "updated_at"],
    "provenance_records": ["id", "entity_type", "entity_id", "source_type", "source_id",
                           "source_path", "source_frame", "source_timestamp_ms",
                           "model_name", "model_version", "confidence", "created_by_user_id",
                           "created_at", "details_json"],
    "module_entitlements": ["id", "team_id", "module_key", "enabled", "starts_at",
                            "ends_at", "notes", "created_at", "updated_at"],
}


def get_tables(db):
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def get_columns(db, table):
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def get_column_types(db, table):
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1]: (r[2] or "").upper() for r in rows}


def test_all_tables_exist(db):
    tables = get_tables(db)
    for table in EXPECTED_TABLES:
        assert table in tables, f"Missing table: {table}"


def test_analysis_runs_identity_columns(db):
    cols = get_columns(db, "analysis_runs")
    for col in EXPECTED_COLUMNS["analysis_runs"]:
        assert col in cols, f"analysis_runs missing column: {col}"
    types = get_column_types(db, "analysis_runs")
    assert types["game_id"] == "INTEGER"
    assert types["analysis_key"] == "TEXT"


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


def test_stage1_platform_core_tables(db):
    for table in [
        "teams",
        "roster_memberships",
        "video_assets",
        "event_types",
        "provenance_records",
        "module_entitlements",
    ]:
        cols = get_columns(db, table)
        for col in EXPECTED_COLUMNS[table]:
            assert col in cols, f"{table} missing column: {col}"


def test_stats_columns(db):
    cols = get_columns(db, "stats")
    for col in EXPECTED_COLUMNS["stats"]:
        assert col in cols, f"stats missing column: {col}"
