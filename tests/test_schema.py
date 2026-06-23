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
    "review_items",
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
                "human_verified", "confidence", "review_status", "source_type",
                "reviewed_by_user_id", "reviewed_at", "review_notes", "created_at"],
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
    "review_items": ["id", "entity_type", "entity_id", "game_id", "review_status",
                     "priority", "reason", "assigned_to_user_id", "reviewed_by_user_id",
                     "reviewed_at", "notes", "created_at", "updated_at"],
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
        "review_items",
        "module_entitlements",
    ]:
        cols = get_columns(db, table)
        for col in EXPECTED_COLUMNS[table]:
            assert col in cols, f"{table} missing column: {col}"


def table_count(db, table):
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_stage2_platform_core_seed_rows(db):
    team = db.execute(
        """SELECT * FROM teams
           WHERE organization_name='Liberty'
             AND team_name='Liberty'
             AND program_name='Liberty'
             AND gender='boys'
             AND level='jr_high'"""
    ).fetchone()
    assert team is not None

    event_codes = {
        row["code"] for row in db.execute("SELECT code FROM event_types").fetchall()
    }
    assert {
        "made_two",
        "missed_two",
        "made_three",
        "missed_three",
        "turnover",
        "period_start",
        "period_end",
    }.issubset(event_codes)
    assert len(event_codes) >= 19

    entitlement = db.execute(
        """SELECT * FROM module_entitlements
           WHERE team_id=? AND module_key='base_platform'""",
        (team["id"],),
    ).fetchone()
    assert entitlement is not None
    assert entitlement["enabled"] == 1


def test_stage2_backfill_is_idempotent(app, db):
    before = {
        table: table_count(db, table)
        for table in [
            "teams",
            "event_types",
            "module_entitlements",
            "provenance_records",
        ]
    }

    with app.app_context():
        import app as app_module

        app_module.init_db()

    after = {
        table: table_count(db, table)
        for table in before
    }
    assert after == before


def test_stage2_backfills_players_videos_and_sources(app, db):
    db.execute(
        """INSERT INTO players
              (name, jersey_number, position, grade, program_name, gender, level)
           VALUES ('Test Player', 12, 'G', 10, 'Liberty', 'boys', 'jr_high')"""
    )
    player_id = db.execute("SELECT id FROM players WHERE name='Test Player'").fetchone()[0]
    db.execute(
        """INSERT INTO videos
              (original_filename, stored_filename, file_path, file_size_bytes, game_id)
           VALUES ('original.mp4', 'stored.mp4', '/tmp/stored.mp4', 123, 'analysis-key')"""
    )
    db.execute(
        """INSERT INTO games (source_type, source_key)
           VALUES ('manual', 'stage2-test-game')"""
    )
    game_id = db.execute(
        "SELECT id FROM games WHERE source_key='stage2-test-game'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO sources (game_id, source_type, source_path)
           VALUES (?, 'nfhs', '/tmp/source.mp4')""",
        (game_id,),
    )
    db.commit()

    with app.app_context():
        import app as app_module

        app_module.init_db()

    team_id = db.execute(
        "SELECT id FROM teams WHERE team_name='Liberty' ORDER BY id LIMIT 1"
    ).fetchone()[0]
    membership = db.execute(
        """SELECT * FROM roster_memberships
           WHERE player_id=? AND team_id=?""",
        (player_id, team_id),
    ).fetchone()
    assert membership is not None
    assert membership["jersey_number"] == 12
    assert membership["position"] == "G"

    uploaded_asset = db.execute(
        """SELECT * FROM video_assets
           WHERE stored_filename='stored.mp4' AND source_type='uploaded_video'"""
    ).fetchone()
    assert uploaded_asset is not None
    assert uploaded_asset["game_id"] is None
    assert uploaded_asset["primary_asset"] == 1

    source_asset = db.execute(
        """SELECT * FROM video_assets
           WHERE source_id IS NOT NULL AND source_type='nfhs'"""
    ).fetchone()
    assert source_asset is not None
    assert source_asset["game_id"] == game_id

    counts = {
        table: table_count(db, table)
        for table in ["roster_memberships", "video_assets", "provenance_records"]
    }
    with app.app_context():
        import app as app_module

        app_module.init_db()
    assert counts == {
        table: table_count(db, table)
        for table in counts
    }


def test_stage3a_review_workflow_tables(db):
    cols = get_columns(db, "review_items")
    for col in EXPECTED_COLUMNS["review_items"]:
        assert col in cols, f"review_items missing column: {col}"


def test_stage3a_review_backfill_is_idempotent(app, db):
    db.execute(
        """INSERT INTO games (source_type, source_key)
           VALUES ('manual', 'stage3-review-game')"""
    )
    game_id = db.execute(
        "SELECT id FROM games WHERE source_key='stage3-review-game'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO events
              (game_id, event_type, timestamp_ms, human_verified, confidence)
           VALUES (?, 'shot', 1000, 0, 0.42)""",
        (str(game_id),),
    )
    db.commit()

    with app.app_context():
        import app as app_module

        app_module.init_db()

    event = db.execute(
        "SELECT * FROM events WHERE game_id=? AND event_type='shot'",
        (str(game_id),),
    ).fetchone()
    assert event["review_status"] == "pending"
    assert event["source_type"] == "ai"

    review_item = db.execute(
        """SELECT * FROM review_items
           WHERE entity_type='event' AND entity_id=?""",
        (event["id"],),
    ).fetchone()
    assert review_item is not None
    assert review_item["review_status"] == "pending"

    counts = {
        table: table_count(db, table)
        for table in ["events", "review_items"]
    }
    with app.app_context():
        import app as app_module

        app_module.init_db()
    assert counts == {
        table: table_count(db, table)
        for table in counts
    }


def test_stats_columns(db):
    cols = get_columns(db, "stats")
    for col in EXPECTED_COLUMNS["stats"]:
        assert col in cols, f"stats missing column: {col}"
