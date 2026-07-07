"""Tests for jersey OCR parsing and track identity aggregation."""


def test_parse_jersey_text_single_digit():
    from jersey_ocr import _parse_jersey_text

    number, conf = _parse_jersey_text("7")
    assert number == 7
    assert conf > 0


def test_parse_jersey_text_two_digit():
    from jersey_ocr import _parse_jersey_text

    number, conf = _parse_jersey_text("12")
    assert number == 12


def test_aggregate_cluster_jersey_votes(db):
    from track_identity import aggregate_cluster_jersey_votes

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'track-id-test')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_track_identity"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/track.mp4"),
    )
    rows = [
        (analysis_key, game_id, 10, 100, "person", 0.9, 100, 200, 40, 80, 1, 3, 12, 0.82),
        (analysis_key, game_id, 11, 133, "person", 0.9, 102, 202, 40, 80, 1, 3, 12, 0.80),
        (analysis_key, game_id, 12, 166, "person", 0.9, 101, 201, 40, 80, 1, 3, 12, 0.78),
        (analysis_key, game_id, 13, 199, "person", 0.9, 500, 200, 40, 80, 2, 7, 7, 0.75),
        (analysis_key, game_id, 14, 232, "person", 0.9, 502, 202, 40, 80, 2, 7, 7, 0.77),
        (analysis_key, game_id, 15, 265, "person", 0.9, 501, 201, 40, 80, 2, 7, 7, 0.76),
    ]
    for row in rows:
        db.execute(
            """INSERT INTO detections
                  (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                   confidence, x_center, y_center, width, height, tracker_id,
                   player_cluster, jersey_read, jersey_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row,
        )
    db.commit()

    suggestions = aggregate_cluster_jersey_votes(db, analysis_key, min_confidence=0.5, min_samples=3)
    by_slot = {item["tracker_id"]: item for item in suggestions}
    assert by_slot[3]["jersey_number"] == 12
    assert by_slot[7]["jersey_number"] == 7


def test_auto_apply_cluster_jerseys_updates_events(db):
    from track_identity import auto_apply_cluster_jerseys

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'auto-apply')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_auto_apply"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/auto.mp4"),
    )
    db.execute(
        """INSERT INTO players (name, jersey_number, program_name, gender, level)
           VALUES ('Sam Reed', 12, 'Liberty', 'boys', 'jr_high')"""
    )
    db.execute(
        """INSERT INTO player_minutes
              (game_id, relational_game_id, tracker_id, first_frame, last_frame,
               total_frames, minutes_played)
           VALUES (?, ?, 3, 0, 100, 50, 10.0)""",
        (analysis_key, game_id),
    )
    for i in range(10):
        db.execute(
            """INSERT INTO detections
                  (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                   confidence, x_center, y_center, width, height, tracker_id,
                   player_cluster, jersey_read, jersey_confidence)
               VALUES (?, ?, ?, ?, 'person', 0.9, 100, 200, 40, 80, 1, 3, 12, 0.85)""",
            (analysis_key, game_id, i, i * 100),
        )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status, source_type)
           VALUES (?, ?, '3', 'make', 500, 'pending', 'ai')""",
        (analysis_key, game_id),
    )
    db.commit()

    result = auto_apply_cluster_jerseys(
        db,
        analysis_key,
        {
            "jersey_ocr_min_confidence": 0.5,
            "identity_auto_apply_min_confidence": 0.7,
            "identity_auto_apply_min_samples": 8,
        },
    )
    assert result["applied"] >= 1
    row = db.execute("SELECT player FROM events WHERE player LIKE '#12%'").fetchone()
    assert row is not None
