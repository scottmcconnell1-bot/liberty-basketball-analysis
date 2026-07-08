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


def test_auto_apply_uses_film_roster_names(db):
    from track_identity import auto_apply_cluster_jerseys
    from film_roster import save_film_roster

    season_id = db.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?, ?, ?)",
        ("2025-26", "2025-11-01", "2026-03-01"),
    ).lastrowid
    scheduled_game_id = db.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, team, gender, level, game_date, opponent_name, status)
           VALUES (?, 'Liberty', 'boys_hs', 'boys', 'varsity', '2026-01-15', 'Wilder', 'scheduled')""",
        (season_id,),
    ).lastrowid
    game_id = db.execute(
        "INSERT INTO games (scheduled_game_id, source_type, source_key) VALUES (?, 'manual', 'film-roster-apply')",
        (scheduled_game_id,),
    ).lastrowid
    analysis_key = "nfhs_film_roster_apply"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/film-roster.mp4"),
    )
    save_film_roster(
        db,
        season_id=season_id,
        level="varsity",
        gender="boys",
        side="our",
        players=[{"label": "12 Sam Reed", "jersey_number": 12, "name": "Sam Reed"}],
        replace=True,
    )
    db.execute(
        """INSERT INTO player_minutes
              (game_id, relational_game_id, tracker_id, first_frame, last_frame,
               total_frames, minutes_played)
           VALUES (?, ?, 3, 0, 100, 50, 10.0)""",
        (analysis_key, game_id),
    )
    for i in range(6):
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
           VALUES (?, ?, '3', 'rebound', 500, 'pending', 'ai')""",
        (analysis_key, game_id),
    )
    db.commit()

    result = auto_apply_cluster_jerseys(
        db,
        analysis_key,
        {
            "jersey_ocr_min_confidence": 0.5,
            "identity_auto_apply_min_confidence": 0.6,
            "identity_auto_apply_min_samples": 4,
        },
    )
    assert result["applied"] == 1
    row = db.execute("SELECT player FROM events WHERE event_type='rebound'").fetchone()
    assert "Sam Reed" in row["player"]


def test_ensure_identity_applied_runs_when_events_use_cluster_ids(db):
    from track_identity import ensure_identity_applied

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'ensure-apply')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_ensure_apply"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/ensure.mp4"),
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
    for i in range(6):
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
           VALUES (?, ?, '3', 'rebound', 500, 'pending', 'ai')""",
        (analysis_key, game_id),
    )
    db.commit()

    result = ensure_identity_applied(
        db,
        analysis_key,
        {
            "auto_apply_jersey_mapping": True,
            "jersey_ocr_min_confidence": 0.5,
            "identity_auto_apply_min_confidence": 0.6,
            "identity_auto_apply_min_samples": 4,
        },
    )
    assert result["skipped"] is False
    assert result["applied"] >= 1
    row = db.execute("SELECT player FROM events WHERE event_type='rebound'").fetchone()
    assert row["player"].startswith("#12")


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


def test_sample_event_timestamps_spreads_samples():
    from jersey_ocr import _sample_event_timestamps

    events = [
        {"player": "3", "timestamp_ms": 1000},
        {"player": "3", "timestamp_ms": 1100},
        {"player": "3", "timestamp_ms": 5000},
        {"player": "7", "timestamp_ms": 2000},
    ]
    sampled = _sample_event_timestamps(events, max_per_cluster=10)
    assert sampled[3] == [1000, 5000]
    assert sampled[7] == [2000]


def test_ocr_jerseys_near_events_updates_detection(db, monkeypatch, tmp_path):
    from jersey_ocr import ocr_jerseys_near_events

    video_path = tmp_path / "event-ocr.mp4"
    video_path.write_bytes(b"not-a-real-video")

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'event-ocr')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_event_ocr"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, str(video_path)),
    )
    db.execute(
        """INSERT INTO events
               (game_id, relational_game_id, player, event_type, timestamp_ms, source_type)
           VALUES (?, ?, '3', 'shot', 5000, 'ai')""",
        (analysis_key, game_id),
    )
    db.execute(
        """INSERT INTO detections
               (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                confidence, x_center, y_center, width, height, tracker_id, player_cluster)
           VALUES (?, ?, 150, 5000, 'person', 0.9, 200, 300, 80, 120, 1, 3)""",
        (analysis_key, game_id),
    )
    db.commit()
    det_id = db.execute("SELECT id FROM detections").fetchone()[0]

    import sys

    class FakeCap:
        def __init__(self, path, *_args):
            self.path = path

        def isOpened(self):
            return True

        def set(self, *_args):
            return True

        def read(self):
            import numpy as np

            return True, np.zeros((1080, 1920, 3), dtype=np.uint8)

        def release(self):
            return None

    fake_cv2 = type(sys)("cv2")
    fake_cv2.VideoCapture = FakeCap
    fake_cv2.CAP_FFMPEG = 0
    fake_cv2.CAP_PROP_POS_MSEC = 0
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(
        "jersey_ocr.read_jersey_from_detection",
        lambda *_args, **_kwargs: (23, 0.88),
    )

    result = ocr_jerseys_near_events(db, analysis_key, str(video_path))
    assert result["skipped"] is False
    assert result["updated"] >= 1
    row = db.execute("SELECT jersey_read, jersey_confidence FROM detections WHERE id=?", (det_id,)).fetchone()
    assert row["jersey_read"] == 23
    assert row["jersey_confidence"] == 0.88
