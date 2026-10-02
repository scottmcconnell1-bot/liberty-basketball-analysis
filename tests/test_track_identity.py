"""Tests for jersey OCR parsing and track identity aggregation."""


def test_shared_jersey_uses_shade_and_a_unique_number_does_not_need_it():
    from track_identity import _pick_roster_player

    shared = [
        {"name": "Dayley", "jersey_number": 11, "side": "liberty"},
        {"name": "Other", "jersey_number": 11, "side": "opponent"},
    ]
    assert _pick_roster_player(shared, "away", False)["name"] == "Dayley"
    assert _pick_roster_player(shared, "home", False)["name"] == "Other"
    assert _pick_roster_player(shared, None, False) is None
    assert _pick_roster_player([{"name": "Colman", "side": "liberty"}], None, False)["name"] == "Colman"
    assert _pick_roster_player([{"name": "Colman", "side": "liberty"}], "away", False)["name"] == "Colman"
    assert _pick_roster_player([{"name": "Colman", "side": "liberty"}], "home", False) is None


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


def test_auto_apply_leaves_an_unread_slot_and_does_not_mark_reviewed(db):
    from track_identity import auto_apply_cluster_jerseys

    db.execute("INSERT INTO games (source_type, source_key) VALUES ('manual', 'ocr-only-apply')")
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_ocr_only_apply"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/ocr-only.mp4"),
    )
    db.execute(
        """INSERT INTO player_minutes
              (game_id, relational_game_id, tracker_id, first_frame, last_frame,
               total_frames, minutes_played)
           VALUES (?, ?, 3, 0, 100, 50, 10.0)""",
        (analysis_key, game_id),
    )
    db.execute(
        """INSERT INTO player_minutes
              (game_id, relational_game_id, tracker_id, first_frame, last_frame,
               total_frames, minutes_played, jersey_number, player_name)
           VALUES (?, ?, 9, 0, 100, 50, 8.0, 4, 'Wrong Person')""",
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
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status, source_type)
           VALUES (?, ?, '9', 'rebound', 800, 'pending', 'ai')""",
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
    named = db.execute(
        "SELECT player, review_status FROM events WHERE player LIKE '#12%'"
    ).fetchone()
    assert named is not None
    assert named["review_status"] == "pending"
    untouched = db.execute(
        "SELECT player, review_status FROM events WHERE player = '9'"
    ).fetchone()
    assert untouched is not None
    assert untouched["review_status"] == "pending"


def test_both_teams_with_the_same_number_are_named_by_shade():
    """#161 review: the second #11 was dropped because duplicates were keyed by number alone."""
    from track_identity import _build_auto_apply_mappings

    roster = {11: [{"name": "Liberty Eleven", "side": "liberty"}, {"name": "Opp Eleven", "side": "opponent"}]}
    suggestions = [
        {"tracker_id": 3, "jersey_number": 11, "confidence": 0.9, "sample_count": 6},
        {"tracker_id": 8, "jersey_number": 11, "confidence": 0.8, "sample_count": 5},
    ]
    shades = {3: {"side": "home"}, 8: {"side": "away"}}
    out = _build_auto_apply_mappings(
        suggestions, roster_by_jersey=roster, use_roster_whitelist=True, min_conf=0.5,
        min_samples=2, shade_by_tracker=shades, liberty_is_home=True,
    )
    assert sorted((m["tracker_id"], m["player_name"]) for m in out) == [
        (3, "Liberty Eleven"), (8, "Opp Eleven")]


def test_same_side_shared_number_names_every_agreeing_tracker():
    """Two trackers on the same side with the same number are the same player."""
    from track_identity import _build_auto_apply_mappings

    roster = {11: [{"name": "Liberty Eleven", "side": "liberty"}, {"name": "Opp Eleven", "side": "opponent"}]}
    suggestions = [
        {"tracker_id": 3, "jersey_number": 11, "confidence": 0.9, "sample_count": 6},
        {"tracker_id": 9, "jersey_number": 11, "confidence": 0.7, "sample_count": 4},
    ]
    shades = {3: {"side": "home"}, 9: {"side": "home"}}
    out = _build_auto_apply_mappings(
        suggestions, roster_by_jersey=roster, use_roster_whitelist=True, min_conf=0.5,
        min_samples=2, shade_by_tracker=shades, liberty_is_home=True,
    )
    assert [(m["tracker_id"], m["player_name"]) for m in out] == [
        (3, "Liberty Eleven"), (9, "Liberty Eleven")]


def test_unique_number_is_still_named_once_whatever_the_shade():
    """A shirt from the other team is not named with the only person who wears that number."""
    from track_identity import _build_auto_apply_mappings

    roster = {23: [{"name": "Avery", "side": "liberty"}]}
    suggestions = [
        {"tracker_id": 4, "jersey_number": 23, "confidence": 0.9, "sample_count": 6},
        {"tracker_id": 17, "jersey_number": 23, "confidence": 0.85, "sample_count": 6},
    ]
    shades = {4: {"side": "home"}, 17: {"side": "away"}}
    out = _build_auto_apply_mappings(
        suggestions, roster_by_jersey=roster, use_roster_whitelist=True, min_conf=0.5,
        min_samples=2, shade_by_tracker=shades, liberty_is_home=True,
    )
    assert [(m["tracker_id"], m["player_name"]) for m in out] == [(4, "Avery")]


def test_unique_number_names_every_tracker_whose_shade_agrees():
    from track_identity import _build_auto_apply_mappings

    roster = {40: [{"name": "Dayley", "side": "liberty"}]}
    suggestions = [
        {"tracker_id": 6, "jersey_number": 40, "confidence": 0.9, "sample_count": 6},
        {"tracker_id": 8, "jersey_number": 40, "confidence": 0.8, "sample_count": 5},
    ]
    shades = {6: {"side": "away"}, 8: {"side": "away"}}
    out = _build_auto_apply_mappings(
        suggestions, roster_by_jersey=roster, use_roster_whitelist=True, min_conf=0.5,
        min_samples=2, shade_by_tracker=shades, liberty_is_home=False,
    )
    assert [(m["tracker_id"], m["player_name"]) for m in out] == [(6, "Dayley"), (8, "Dayley")]
