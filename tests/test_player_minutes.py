"""
test_player_minutes.py — Focused tests for Stage 4D Player Minutes Foundation.

Covers:
1. Schema existence (table + columns).
2. Backfill produces correct minute totals from detection frames.
3. Idempotency: re-running backfill does not duplicate rows.
4. Per-game and per-player query paths.
5. Regression: stats.py can read backfilled player_minutes.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def populated_db(app, db):
    """DB with games, players, and detections for 2 games."""
    # Create games
    db.execute(
        "INSERT INTO games (source_type, source_key) VALUES ('manual', 'game-one')"
    )
    db.execute(
        "INSERT INTO games (source_type, source_key) VALUES ('manual', 'game-two')"
    )

    # Create players with tracker_ids
    db.execute(
        """INSERT INTO players (name, jersey_number, tracker_id, program_name, gender, level)
           VALUES ('Alice', 10, 1, 'Liberty', 'boys', 'jr_high')"""
    )
    db.execute(
        """INSERT INTO players (name, jersey_number, tracker_id, program_name, gender, level)
           VALUES ('Bob', 20, 2, 'Liberty', 'boys', 'jr_high')"""
    )

    # Game-one detections:
    # tracker_id=1: frames 1,2,3,...,30 (30 distinct frames)
    # tracker_id=2: frames 1,2,3,...,60 (60 distinct frames)
    for i in range(1, 31):
        db.execute(
            """INSERT INTO detections
               (game_id, frame_number, timestamp_ms, object_class, confidence,
                x_center, y_center, width, height, tracker_id)
               VALUES ('game-one', ?, ?, 'person', 0.9, 100, 200, 50, 100, 1)""",
            (i, i * 33),
        )
    for i in range(1, 61):
        db.execute(
            """INSERT INTO detections
               (game_id, frame_number, timestamp_ms, object_class, confidence,
                x_center, y_center, width, height, tracker_id)
               VALUES ('game-one', ?, ?, 'person', 0.9, 300, 400, 50, 100, 2)""",
            (i, i * 33),
        )

    # Game-two detections: tracker_id=1 only, 90 frames
    for i in range(1, 91):
        db.execute(
            """INSERT INTO detections
               (game_id, frame_number, timestamp_ms, object_class, confidence,
                x_center, y_center, width, height, tracker_id)
               VALUES ('game-two', ?, ?, 'person', 0.9, 100, 200, 50, 100, 1)""",
            (i, i * 33),
        )

    db.commit()
    return db


# ── Schema tests ─────────────────────────────────────────────

def test_player_minutes_table_exists(app, db):
    tables = {
        r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "player_minutes" in tables


def test_player_minutes_columns(app, db):
    cols = {
        r[1] for r in db.execute("PRAGMA table_info(player_minutes)").fetchall()
    }
    required = {
        "id", "game_id", "relational_game_id", "tracker_id", "jersey_number", "player_name",
        "first_frame", "last_frame", "total_frames", "minutes_played", "created_at",
    }
    assert required.issubset(cols), f"Missing columns: {required - cols}"


# ── Backfill computation tests ───────────────────────────────

def test_backfill_computes_minutes(app, populated_db):
    from player_minutes import backfill_player_minutes

    results = backfill_player_minutes(populated_db, "game-one", fps=30.0, detect_stride=1)
    assert len(results) == 2

    # tracker_id=2 has 60 frames at 30 fps → 2.0 seconds → 0.03 min
    by_tracker = {r["tracker_id"]: r for r in results}
    assert by_tracker[1]["total_frames"] == 30
    assert by_tracker[1]["minutes_played"] == pytest.approx(30 / 30.0 / 60.0, abs=0.01)
    assert by_tracker[2]["total_frames"] == 60
    assert by_tracker[2]["minutes_played"] == pytest.approx(60 / 30.0 / 60.0, abs=0.01)


def test_backfill_records_persisted(app, populated_db):
    from player_minutes import backfill_player_minutes

    backfill_player_minutes(populated_db, "game-one")

    rows = populated_db.execute(
        "SELECT tracker_id, total_frames, minutes_played FROM player_minutes WHERE game_id='game-one' ORDER BY tracker_id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["tracker_id"] == 1
    assert rows[0]["total_frames"] == 30
    assert rows[1]["tracker_id"] == 2
    assert rows[1]["total_frames"] == 60


# ── Idempotency test ─────────────────────────────────────────

def test_backfill_is_idempotent(app, populated_db):
    from player_minutes import backfill_player_minutes

    backfill_player_minutes(populated_db, "game-one")
    first_count = populated_db.execute(
        "SELECT COUNT(*) FROM player_minutes WHERE game_id='game-one'"
    ).fetchone()[0]

    backfill_player_minutes(populated_db, "game-one")
    second_count = populated_db.execute(
        "SELECT COUNT(*) FROM player_minutes WHERE game_id='game-one'"
    ).fetchone()[0]

    assert first_count == second_count == 2


# ── Per-player query tests ───────────────────────────────────

def test_get_player_minutes_per_game(app, populated_db):
    from player_minutes import backfill_player_minutes, get_player_minutes

    backfill_player_minutes(populated_db, "game-one")
    rows = get_player_minutes(populated_db, "game-one")

    assert len(rows) == 2
    # Should be sorted by minutes_played DESC
    assert rows[0]["tracker_id"] == 2  # 60 frames > 30 frames
    assert rows[0]["minutes_played"] > rows[1]["minutes_played"]


def test_get_player_minutes_for_player(app, populated_db):
    from player_minutes import backfill_player_minutes, backfill_all_games, get_player_minutes_for_player

    backfill_all_games(populated_db)
    rows = get_player_minutes_for_player(populated_db, 1)

    # tracker_id=1 appears in both game-one (30 frames) and game-two (90 frames)
    assert len(rows) == 2
    game_ids = {r["game_id"] for r in rows}
    assert game_ids == {"game-one", "game-two"}


def test_backfill_sets_relational_game_id_for_numeric_game_ids(app, db):
    from player_minutes import backfill_player_minutes, get_player_minutes

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'stage5a-minutes-game')")
    game_id = db.execute(
        "SELECT id FROM games WHERE source_key='stage5a-minutes-game'"
    ).fetchone()[0]
    for i in range(1, 31):
        db.execute(
            """INSERT INTO detections
               (game_id, frame_number, timestamp_ms, object_class, confidence,
                x_center, y_center, width, height, tracker_id)
               VALUES (?, ?, ?, 'person', 0.9, 100, 200, 50, 100, 7)""",
            (str(game_id), i, i * 33),
        )
    db.commit()

    backfill_player_minutes(db, str(game_id))

    row = db.execute(
        "SELECT game_id, relational_game_id FROM player_minutes WHERE tracker_id=7"
    ).fetchone()
    assert row["game_id"] == str(game_id)
    assert row["relational_game_id"] == game_id

    rows = get_player_minutes(db, game_id)
    assert len(rows) == 1
    assert rows[0]["tracker_id"] == 7


# ── Stats integration test ───────────────────────────────────

def test_stats_reads_player_minutes(app, populated_db):
    """Verify that stats.py can consume backfilled player_minutes data."""
    from player_minutes import backfill_player_minutes

    backfill_player_minutes(populated_db, "game-one")

    rows = populated_db.execute(
        "SELECT tracker_id, minutes_played FROM player_minutes WHERE game_id='game-one' ORDER BY tracker_id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["minutes_played"] > 0


def test_refresh_stats_sets_relational_game_id_for_manual_games(app, db):
    from stats import refresh_stats

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'stage5a-stats-game')")
    game_id = db.execute(
        "SELECT id FROM games WHERE source_key='stage5a-stats-game'"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, event_type, event_type_id, shot_result,
               timestamp_ms, review_status, source_type)
           SELECT ?, ?, 'made_two', id, 'made', 1000, 'accepted', 'manual'
           FROM event_types WHERE code='made_two'"""
        ,
        (str(game_id), game_id),
    )
    db.commit()

    refresh_stats(db, game_id)

    row = db.execute(
        "SELECT game_id, relational_game_id, pts, fgm, fga FROM stats WHERE relational_game_id=?",
        (game_id,),
    ).fetchone()
    assert row is not None
    assert row["game_id"] == str(game_id)
    assert row["relational_game_id"] == game_id
    assert row["pts"] == 2
    assert row["fgm"] == 1
    assert row["fga"] == 1


# ── Empty-data safety test ──────────────────────────────────

def test_backfill_no_detections_returns_empty(app, db):
    from player_minutes import backfill_player_minutes

    results = backfill_player_minutes(db, "empty-game")
    assert results == []
