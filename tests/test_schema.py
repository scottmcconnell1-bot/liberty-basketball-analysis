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
    "possessions",
    "event_types",
    "event_participants",
    "provenance_records",
    "review_items",
    "module_entitlements",
    "clips",
    "clip_tags",
    "player_development_clips",
    "practice_playlists",
    "practice_playlist_clips",
    "practice_plan_items",
    "player_minutes",
    "shot_classifications",
    "play_recognitions",
    "player_effect",
    "human_corrections",
]

EXPECTED_COLUMNS = {
    "analysis_runs": ["id", "game_id", "analysis_key", "video_path", "source_video_id",
                    "base_game_id", "base_analysis_key", "run_label", "settings_json",
                    "run_kind", "status", "started_at", "completed_at", "error_message"],
    "events": ["id", "game_id", "player", "event_type", "shot_result",
                "timestamp_ms", "details_json", "source_video", "source_frame",
                "human_verified", "confidence", "review_status", "source_type",
                "possession_id", "relational_game_id", "event_type_id", "team_id",
                "primary_player_id", "primary_roster_membership_id",
                "reviewed_by_user_id", "reviewed_at", "review_notes",
                "created_by_user_id", "created_at", "updated_at"],
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
    "stats": ["id", "game_id", "relational_game_id", "player_id", "player_name", "pts", "fgm", "fga",
              "threes_made", "threes_att", "ast", "reb", "tov", "stl", "blk"],
    "video_assets": ["id", "game_id", "source_id", "original_filename", "stored_filename",
                     "file_path", "source_type", "camera_label", "angle_label",
                     "file_size_bytes", "duration_ms", "frame_rate", "width", "height",
                     "checksum", "transcode_status", "sync_group_id", "primary_asset",
                     "created_at", "updated_at"],
    "possessions": ["id", "game_id", "team_id", "opponent_team_id", "period",
                    "start_timestamp_ms", "end_timestamp_ms", "start_event_id",
                    "end_event_id", "outcome", "points_for", "source",
                    "review_status", "confidence", "notes", "created_at",
                    "updated_at"],
    "event_types": ["id", "code", "label", "category", "counts_for_stats",
                    "is_scoring_event", "is_possession_boundary", "created_at", "updated_at"],
    "event_participants": ["id", "event_id", "player_id", "roster_membership_id",
                           "team_id", "role", "tracker_id", "confidence",
                           "source", "created_at"],
    "provenance_records": ["id", "entity_type", "entity_id", "source_type", "source_id",
                           "source_path", "source_frame", "source_timestamp_ms",
                           "model_name", "model_version", "confidence", "created_by_user_id",
                           "created_at", "details_json"],
    "review_items": ["id", "entity_type", "entity_id", "game_id", "relational_game_id", "review_status",
                     "priority", "reason", "assigned_to_user_id", "reviewed_by_user_id",
                     "reviewed_at", "notes", "created_at", "updated_at"],
    "module_entitlements": ["id", "team_id", "module_key", "enabled", "starts_at",
                            "ends_at", "notes", "created_at", "updated_at"],
    "clips": ["id", "game_id", "video_asset_id", "event_id", "possession_id",
              "clip_type", "title", "start_timestamp_ms", "end_timestamp_ms",
              "created_by_user_id", "source", "review_status", "confidence",
              "notes", "created_at", "updated_at"],
    "clip_tags": ["id", "clip_id", "tag", "category", "created_by_user_id",
                  "created_at"],
    "player_development_clips": ["id", "player_id", "game_id", "event_id",
                                 "canonical_clip_id", "relational_game_id",
                                 "clip_start_ms", "clip_end_ms", "clip_label",
                                 "clip_category", "season_id", "notes",
                                 "created_at", "updated_at"],
    "player_minutes": ["id", "game_id", "relational_game_id", "tracker_id", "jersey_number",
                       "player_name", "first_frame", "last_frame",
                       "total_frames", "minutes_played", "created_at"],
    "shot_classifications": ["id", "event_id", "game_id", "relational_game_id", "tracker_id",
                             "jersey_number", "shot_type", "shot_result", "court_x",
                             "court_y", "confidence", "timestamp_ms", "details_json",
                             "created_at"],
    "play_recognitions": ["id", "game_id", "relational_game_id", "play_type", "play_subtype",
                          "start_frame", "end_frame", "start_timestamp_ms", "end_timestamp_ms",
                          "primary_tracker_id", "secondary_tracker_id", "confidence",
                          "details_json", "created_at"],
    "player_effect": ["id", "game_id", "relational_game_id", "tracker_id", "jersey_number",
                      "plus_minus", "possessions_on", "possessions_off", "points_for",
                      "points_against", "ortg", "drtg", "net_rating", "created_at"],
    "human_corrections": ["id", "game_id", "relational_game_id", "event_id", "correction_type",
                          "original_value", "corrected_value", "field_changed", "timestamp_ms",
                          "notes", "applied_to_model", "created_at"],
    "detections": ["id", "game_id", "relational_game_id", "frame_number", "timestamp_ms",
                   "object_class", "confidence", "x_center", "y_center", "width", "height",
                   "tracker_id", "created_at"],
    "videos": ["id", "original_filename", "stored_filename", "file_path", "file_size_bytes",
               "opponent", "game_id", "relational_game_id", "upload_timestamp",
               "is_duplicate", "duplicate_of_id", "created_at"],
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
    "clips",
    "clip_tags",
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


def test_stage3c_possession_clip_foundation_tables(db):
    for table in ["possessions", "clips", "clip_tags", "player_development_clips"]:
        cols = get_columns(db, table)
        for col in EXPECTED_COLUMNS[table]:
            assert col in cols, f"{table} missing column: {col}"

    event_cols = get_columns(db, "events")
    assert "possession_id" in event_cols


def test_stage3c_possession_clip_foundation_is_idempotent(app, db):
    before = {
        table: table_count(db, table)
        for table in ["possessions", "clips", "clip_tags"]
    }

    with app.app_context():
        import app as app_module

        app_module.init_db()

    after = {
        table: table_count(db, table)
        for table in before
    }
    assert after == before


def test_stage3c_manual_possession_and_clip_can_link_to_event(db):
    db.execute(
        """INSERT INTO games (source_type, source_key)
           VALUES ('manual', 'stage3c-foundation-game')"""
    )
    game_id = db.execute(
        "SELECT id FROM games WHERE source_key='stage3c-foundation-game'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO events
              (game_id, event_type, timestamp_ms, review_status, source_type)
           VALUES (?, 'shot', 12000, 'accepted', 'manual')""",
        (str(game_id),),
    )
    event_id = db.execute(
        "SELECT id FROM events WHERE game_id=? AND event_type='shot'",
        (str(game_id),),
    ).fetchone()[0]
    db.execute(
        """INSERT INTO possessions
              (game_id, period, start_timestamp_ms, end_timestamp_ms,
               start_event_id, end_event_id, outcome, points_for,
               source, review_status)
           VALUES (?, 1, 10000, 18000, ?, ?, 'made_two', 2,
                   'manual', 'reviewed')""",
        (game_id, event_id, event_id),
    )
    possession_id = db.execute(
        "SELECT id FROM possessions WHERE game_id=?",
        (game_id,),
    ).fetchone()[0]
    db.execute(
        "UPDATE events SET possession_id=? WHERE id=?",
        (possession_id, event_id),
    )
    db.execute(
        """INSERT INTO clips
              (game_id, event_id, possession_id, clip_type, title,
               start_timestamp_ms, end_timestamp_ms, source, review_status)
           VALUES (?, ?, ?, 'possession', 'Opening possession',
                   9000, 19000, 'manual', 'reviewed')""",
        (game_id, event_id, possession_id),
    )
    clip_id = db.execute(
        "SELECT id FROM clips WHERE possession_id=?",
        (possession_id,),
    ).fetchone()[0]
    db.execute(
        """INSERT INTO clip_tags (clip_id, tag, category)
           VALUES (?, 'transition', 'phase')""",
        (clip_id,),
    )
    db.commit()

    event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    clip = db.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    tag = db.execute("SELECT * FROM clip_tags WHERE clip_id=?", (clip_id,)).fetchone()

    assert event["possession_id"] == possession_id
    assert clip["event_id"] == event_id
    assert clip["clip_type"] == "possession"
    assert tag["tag"] == "transition"

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


def test_stage4a_event_ledger_participant_foundation_tables(db):
    event_cols = get_columns(db, "events")
    for col in [
        "relational_game_id",
        "event_type_id",
        "team_id",
        "primary_player_id",
        "primary_roster_membership_id",
        "created_by_user_id",
        "updated_at",
    ]:
        assert col in event_cols, f"events missing Stage 4A column: {col}"

    participant_cols = get_columns(db, "event_participants")
    for col in EXPECTED_COLUMNS["event_participants"]:
        assert col in participant_cols, f"event_participants missing column: {col}"


def test_stage4a_event_participants_backfill_is_idempotent(app, db):
    team_id = db.execute(
        "SELECT id FROM teams WHERE team_name='Liberty' ORDER BY id LIMIT 1"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO players
              (name, jersey_number, position, grade, tracker_id)
           VALUES ('Stage Four Player', 4, 'G', 8, 44)"""
    )
    player_id = db.execute(
        "SELECT id FROM players WHERE name='Stage Four Player'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO roster_memberships
              (player_id, team_id, jersey_number, position, grade)
           VALUES (?, ?, 4, 'G', 8)""",
        (player_id, team_id),
    )
    membership_id = db.execute(
        "SELECT id FROM roster_memberships WHERE player_id=? AND team_id=?",
        (player_id, team_id),
    ).fetchone()[0]
    db.execute(
        """INSERT INTO events
              (game_id, player, event_type, timestamp_ms, confidence, source_type)
           VALUES ('stage4a-analysis-key', 'Stage Four Player', 'made_two',
                   22000, 0.91, 'ai')"""
    )
    event_id = db.execute(
        "SELECT id FROM events WHERE game_id='stage4a-analysis-key'"
    ).fetchone()[0]
    db.commit()

    with app.app_context():
        import app as app_module

        app_module.init_db()

    participant = db.execute(
        """SELECT * FROM event_participants
           WHERE event_id=? AND role='primary'""",
        (event_id,),
    ).fetchone()
    assert participant is not None
    assert participant["player_id"] == player_id
    assert participant["roster_membership_id"] == membership_id
    assert participant["team_id"] == team_id
    assert participant["tracker_id"] == 44
    assert participant["source"] == "ai"

    event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    assert event["primary_player_id"] == player_id
    assert event["primary_roster_membership_id"] == membership_id
    assert event["team_id"] == team_id

    before = table_count(db, "event_participants")
    with app.app_context():
        import app as app_module

        app_module.init_db()
    assert table_count(db, "event_participants") == before


def test_stage4a_manual_event_can_store_multiple_participants(db):
    team_id = db.execute(
        "SELECT id FROM teams WHERE team_name='Liberty' ORDER BY id LIMIT 1"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO players (name, jersey_number, position)
           VALUES ('Shooter', 10, 'G')"""
    )
    db.execute(
        """INSERT INTO players (name, jersey_number, position)
           VALUES ('Assister', 11, 'G')"""
    )
    shooter_id = db.execute(
        "SELECT id FROM players WHERE name='Shooter'"
    ).fetchone()[0]
    assister_id = db.execute(
        "SELECT id FROM players WHERE name='Assister'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO events
              (game_id, event_type, timestamp_ms, review_status, source_type,
               team_id, primary_player_id)
           VALUES ('stage4a-manual-key', 'made_three', 33000, 'reviewed',
                   'manual', ?, ?)""",
        (team_id, shooter_id),
    )
    event_id = db.execute(
        "SELECT id FROM events WHERE game_id='stage4a-manual-key'"
    ).fetchone()[0]
    db.executemany(
        """INSERT INTO event_participants
              (event_id, player_id, team_id, role, source)
           VALUES (?, ?, ?, ?, 'manual')""",
        [
            (event_id, shooter_id, team_id, "shooter"),
            (event_id, assister_id, team_id, "assister"),
            (event_id, None, team_id, "defender"),
        ],
    )
    db.commit()

    roles = {
        row["role"]
        for row in db.execute(
            "SELECT role FROM event_participants WHERE event_id=?",
            (event_id,),
        ).fetchall()
    }
    assert roles == {"shooter", "assister", "defender"}


def test_stats_columns(db):
    cols = get_columns(db, "stats")
    for col in EXPECTED_COLUMNS["stats"]:
        assert col in cols, f"stats missing column: {col}"


# ── Stage 5B: player_development_clips relational_game_id ─────────────


def test_stage5b_player_development_clips_has_relational_game_id(db):
    cols = get_columns(db, "player_development_clips")
    assert "relational_game_id" in cols, "player_development_clips missing relational_game_id"
    types = get_column_types(db, "player_development_clips")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5b_legacy_game_id_is_still_text(db):
    """Legacy TEXT game_id column must remain TEXT (analysis-key separation)."""
    types = get_column_types(db, "player_development_clips")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5b_relational_game_id_is_idempotent(app, db):
    """Running init_db twice must not raise or duplicate the column."""
    with app.app_context():
        import app as app_module

        app_module.init_db()
        # Second run must not raise (CREATE TABLE IF NOT EXISTS + ADD COLUMN guard)
        app_module.init_db()
    cols = get_columns(db, "player_development_clips")
    assert "relational_game_id" in cols


def test_stage5b_create_clip_with_relational_game_id(db):
    """create_clip accepts and persists relational_game_id."""
    import player_development as pd

    # Create a valid game first for FK reference
    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'test-game')")
    db.commit()
    game_id = db.execute("SELECT id FROM games WHERE source_key='test-game'").fetchone()[0]

    clip = pd.create_clip(
        db,
        "Test clip",
        10000,
        15000,
        player_id=None,
        game_id="game_001",
        relational_game_id=game_id,
    )
    assert clip["relational_game_id"] == game_id


def test_stage5b_update_clip_can_set_relational_game_id(db):
    """update_clip can set relational_game_id."""
    import player_development as pd

    # Create a valid game first for FK reference
    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'upd-game')")
    db.commit()
    game_id = db.execute("SELECT id FROM games WHERE source_key='upd-game'").fetchone()[0]

    clip = pd.create_clip(
        db,
        "Update test",
        10000,
        15000,
        player_id=None,
        game_id="game_001",
    )
    assert clip["relational_game_id"] is None

    updated = pd.update_clip(db, clip["id"], relational_game_id=game_id)
    assert updated["relational_game_id"] == game_id


def test_stage5b_get_clips_filters_by_relational_game_id(db):
    """get_clips supports relational_game_id filter."""
    import player_development as pd

    # Create a valid game first for FK reference
    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'filter-game')")
    db.commit()
    game_id = db.execute("SELECT id FROM games WHERE source_key='filter-game'").fetchone()[0]

    pd.create_clip(db, "Clip A", 1000, 2000, game_id="g1", relational_game_id=game_id)
    pd.create_clip(db, "Clip B", 3000, 4000, game_id="g2", relational_game_id=None)
    pd.create_clip(db, "Clip C", 5000, 6000, game_id="g3", relational_game_id=game_id)

    clips = pd.get_clips(db, relational_game_id=game_id)
    assert len(clips) == 2
    labels = {c["clip_label"] for c in clips}
    assert labels == {"Clip A", "Clip C"}


def test_stage5b_legacy_game_id_preserved(db):
    """Legacy TEXT game_id still works alongside relational_game_id."""
    import player_development as pd

    clip = pd.create_clip(
        db,
        "Legacy test",
        1000,
        2000,
        game_id="legacy_game_123",
        relational_game_id=None,
    )
    assert clip["game_id"] == "legacy_game_123"
    assert clip["relational_game_id"] is None

    # Query by legacy game_id still works
    clips = pd.get_clips(db, game_id="legacy_game_123")
    assert len(clips) == 1
    assert clips[0]["clip_label"] == "Legacy test"


# ── Stage 5C: shot_classifications relational_game_id ───────────────────


def test_stage5c_shot_classifications_has_relational_game_id(db):
    cols = get_columns(db, "shot_classifications")
    assert "relational_game_id" in cols, "shot_classifications missing relational_game_id"
    types = get_column_types(db, "shot_classifications")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5c_legacy_game_id_is_still_text(db):
    types = get_column_types(db, "shot_classifications")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5c_relational_game_id_is_idempotent(app, db):
    with app.app_context():
        import app as app_module

        app_module.init_db()
        app_module.init_db()
    cols = get_columns(db, "shot_classifications")
    assert "relational_game_id" in cols


def test_stage5c_get_enhanced_stats_uses_relational_shot_classifications(db):
    import stats

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'stage5c-game')")
    db.commit()
    game_id = db.execute("SELECT id FROM games WHERE source_key='stage5c-game'").fetchone()[0]

    db.execute(
        """INSERT INTO shot_classifications
           (game_id, relational_game_id, tracker_id, shot_type, shot_result, timestamp_ms)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("legacy-mismatch", game_id, 7, "3pt", "make", 12345),
    )
    db.commit()

    enhanced = stats.get_enhanced_stats(db, game_id)
    assert enhanced["shot_breakdown"] == [{
        "tracker_id": 7,
        "shot_type": "3pt",
        "shot_result": "make",
        "cnt": 1,
    }]


# ── Stage 5D: play_recognitions relational_game_id ───────────────────────


def test_stage5d_play_recognitions_has_relational_game_id(db):
    cols = get_columns(db, "play_recognitions")
    assert "relational_game_id" in cols, "play_recognitions missing relational_game_id"
    types = get_column_types(db, "play_recognitions")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5d_legacy_game_id_is_still_text(db):
    types = get_column_types(db, "play_recognitions")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5d_relational_game_id_is_idempotent(app, db):
    with app.app_context():
        import app as app_module

        app_module.init_db()
        app_module.init_db()
    cols = get_columns(db, "play_recognitions")
    assert "relational_game_id" in cols


def test_stage5d_get_enhanced_stats_uses_relational_play_recognitions(db):
    import stats

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'stage5d-game')")
    db.commit()
    game_id = db.execute("SELECT id FROM games WHERE source_key='stage5d-game'").fetchone()[0]

    db.execute(
        """INSERT INTO play_recognitions
           (game_id, relational_game_id, play_type, start_frame, end_frame, start_timestamp_ms, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("legacy-mismatch", game_id, "pick_and_roll", 10, 20, 1000, 0.9),
    )
    db.commit()

    enhanced = stats.get_enhanced_stats(db, game_id)
    assert enhanced["plays_summary"] == [{
        "play_type": "pick_and_roll",
        "cnt": 1,
    }]


# ── Stage 5E: player_effect relational_game_id ───────────────────────────


def test_stage5e_player_effect_has_relational_game_id(db):
    cols = get_columns(db, "player_effect")
    assert "relational_game_id" in cols, "player_effect missing relational_game_id"
    types = get_column_types(db, "player_effect")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5e_legacy_game_id_is_still_text(db):
    types = get_column_types(db, "player_effect")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5e_relational_game_id_is_idempotent(app, db):
    with app.app_context():
        import app as app_module

        app_module.init_db()
        app_module.init_db()
    cols = get_columns(db, "player_effect")
    assert "relational_game_id" in cols


def test_stage5e_get_enhanced_stats_uses_relational_player_effect(db):
    import stats

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'stage5e-game')")
    db.commit()
    game_id = db.execute("SELECT id FROM games WHERE source_key='stage5e-game'").fetchone()[0]

    db.execute(
        """INSERT INTO player_minutes
           (game_id, relational_game_id, tracker_id, minutes_played, total_frames, first_frame, last_frame)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("minutes-legacy", game_id, 7, 12.5, 100, 1, 100),
    )
    db.execute(
        """INSERT INTO player_effect
           (game_id, relational_game_id, tracker_id, possessions_on, points_for, ortg)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("effect-legacy", game_id, 7, 11, 9, 81.8),
    )
    db.commit()

    enhanced = stats.get_enhanced_stats(db, game_id)
    assert enhanced["player_effect"] == [{
        "tracker_id": 7,
        "possessions": 11,
        "points_scored": 9,
        "ortg": 81.8,
        "drtg": None,
        "net_rating": None,
        "minutes_played": 12.5,
        "name": None,
    }]


# ── Stage 5F: human_corrections relational_game_id ───────────────────────


def test_stage5f_human_corrections_has_relational_game_id(db):
    cols = get_columns(db, "human_corrections")
    assert "relational_game_id" in cols, "human_corrections missing relational_game_id"
    types = get_column_types(db, "human_corrections")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5f_legacy_game_id_is_still_text(db):
    types = get_column_types(db, "human_corrections")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5f_relational_game_id_is_idempotent(app, db):
    with app.app_context():
        import app as app_module

        app_module.init_db()
        app_module.init_db()
    cols = get_columns(db, "human_corrections")
    assert "relational_game_id" in cols


# ── Stage 5G: detections relational_game_id ───────────────────────


def test_stage5g_detections_has_relational_game_id(db):
    cols = get_columns(db, "detections")
    assert "relational_game_id" in cols, "detections missing relational_game_id"
    types = get_column_types(db, "detections")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5g_legacy_game_id_is_still_text(db):
    types = get_column_types(db, "detections")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5g_relational_game_id_is_idempotent(app, db):
    with app.app_context():
        import app as app_module

        app_module.init_db()
        app_module.init_db()
    cols = get_columns(db, "detections")
    assert "relational_game_id" in cols


# ── Stage 5H: videos relational_game_id ───────────────────────


def test_stage5h_videos_has_relational_game_id(db):
    cols = get_columns(db, "videos")
    assert "relational_game_id" in cols, "videos missing relational_game_id"
    types = get_column_types(db, "videos")
    assert types["relational_game_id"] == "INTEGER", (
        f"Expected relational_game_id INTEGER, got {types['relational_game_id']}"
    )


def test_stage5h_legacy_game_id_is_still_text(db):
    types = get_column_types(db, "videos")
    assert types["game_id"] == "TEXT", (
        f"Expected game_id TEXT, got {types['game_id']}"
    )


def test_stage5h_relational_game_id_is_idempotent(app, db):
    with app.app_context():
        import app as app_module

        app_module.init_db()
        app_module.init_db()
    cols = get_columns(db, "videos")
    assert "relational_game_id" in cols
