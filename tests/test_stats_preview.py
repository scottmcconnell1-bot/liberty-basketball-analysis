"""Tests for AI preview stats aggregation and possession scoring."""


def test_aggregate_stats_preview_counts_make_miss_events(db):
    """AI make/miss events should populate preview box score stats."""
    from stats import aggregate_stats_preview

    db.execute(
        """INSERT INTO games (source_type, source_key) VALUES ('manual', 'preview-make-miss')"""
    )
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_preview_make_miss"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/preview-make-miss.mp4"),
    )
    for event_type, player, shot_result, ts in [
        ("make", "3", None, 1000),
        ("miss", "3", None, 2000),
        ("make", "7", None, 3000),
        ("rebound", "5", None, 3100),
    ]:
        db.execute(
            """INSERT INTO events
                  (game_id, relational_game_id, player, event_type, shot_result,
                   timestamp_ms, review_status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (analysis_key, game_id, player, event_type, shot_result, ts),
        )
    db.commit()

    stats = aggregate_stats_preview(db, analysis_key)
    by_player = {row["player"]: row for row in stats}
    assert by_player["3"]["pts"] == 2
    assert by_player["3"]["fgm"] == 1
    assert by_player["3"]["fga"] == 2
    assert by_player["7"]["pts"] == 2
    assert by_player["5"]["reb"] == 1


def test_aggregate_stats_preview_dedupes_shot_and_make(db):
    """Expanded generator shot+make pairs must not double-count FGA/FGM."""
    from stats import aggregate_stats_preview

    db.execute(
        """INSERT INTO games (source_type, source_key) VALUES ('manual', 'preview-dedupe')"""
    )
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_preview_dedupe"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/preview-make-miss.mp4"),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, shot_result,
               timestamp_ms, review_status)
           VALUES (?, ?, '4', 'shot', 'make', 1000, 'pending')""",
        (analysis_key, game_id),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, shot_result,
               timestamp_ms, review_status)
           VALUES (?, ?, '4', 'make', NULL, 1000, 'pending')""",
        (analysis_key, game_id),
    )
    db.commit()

    stats = aggregate_stats_preview(db, analysis_key)
    player = next(row for row in stats if row["player"] == "4")
    assert player["fga"] == 1
    assert player["fgm"] == 1
    assert player["pts"] == 2


def test_possession_summary_uses_relational_game_id(db):
    """Possession scoring must resolve relational_game_id when passed analysis_key."""
    from helpers import assign_possessions_for_game
    from stats import get_possession_summary, score_possessions_for_game

    db.execute(
        """INSERT INTO games (source_type, source_key) VALUES ('manual', 'poss-rel')"""
    )
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_poss_relational"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/preview-make-miss.mp4"),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status)
           VALUES (?, ?, '3', 'possession_change', 0, 'pending')""",
        (analysis_key, game_id),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status)
           VALUES (?, ?, '3', 'make', 500, 'pending')""",
        (analysis_key, game_id),
    )
    db.commit()

    assign_possessions_for_game(db, game_id)
    score_possessions_for_game(db, game_id)

    summary = get_possession_summary(db, analysis_key)
    assert summary["total_possessions"] > 0
    assert summary["scoring_possessions"] > 0
    assert summary["points_per_possession"] > 0
