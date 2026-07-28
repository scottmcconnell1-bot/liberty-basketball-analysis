"""Tests for court slot → jersey mapping."""


def _seed_game_with_slots(db):
    db.execute(
        """INSERT INTO games (source_type, source_key) VALUES ('manual', 'court-slot-test')"""
    )
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_key = "nfhs_court_slot_test"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, game_id, "/tmp/court-slot.mp4"),
    )
    db.execute(
        """INSERT INTO players (name, jersey_number, program_name, gender, level)
           VALUES ('Alex Carter', 12, 'Liberty', 'boys', 'jr_high')"""
    )
    player_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        """INSERT INTO player_minutes
              (game_id, relational_game_id, tracker_id, first_frame, last_frame,
               total_frames, minutes_played)
           VALUES (?, ?, 3, 0, 1000, 500, 18.5)""",
        (analysis_key, game_id),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status, source_type)
           VALUES (?, ?, '3', 'make', 1000, 'pending', 'ai')""",
        (analysis_key, game_id),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status, source_type)
           VALUES (?, ?, '3', 'miss', 2000, 'pending', 'ai')""",
        (analysis_key, game_id),
    )
    db.commit()
    return game_id, analysis_key, player_id


def test_get_court_slots_lists_player_minutes(db):
    from court_slot_mapping import get_court_slots

    _, analysis_key, _ = _seed_game_with_slots(db)
    slots = get_court_slots(db, analysis_key)
    assert len(slots) == 1
    assert slots[0]["tracker_id"] == 3
    assert slots[0]["minutes_played"] == 18.5
    assert slots[0]["is_mapped"] is False


def test_save_film_roster_mapping_without_player_id(db):
    """Court slot mapping should work when Film Tool roster players have no DB id."""
    from court_slot_mapping import save_court_slot_mappings
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
    relational_game_id = db.execute(
        "INSERT INTO games (scheduled_game_id, source_type, source_key) VALUES (?, 'manual', 'film-roster-map')",
        (scheduled_game_id,),
    ).lastrowid
    analysis_key = "nfhs_film_roster_map"
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, game_id, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (analysis_key, relational_game_id, "/tmp/film-roster-map.mp4"),
    )
    db.execute(
        """INSERT INTO player_minutes
              (game_id, relational_game_id, tracker_id, first_frame, last_frame,
               total_frames, minutes_played)
           VALUES (?, ?, 2, 0, 1000, 500, 12.0)""",
        (analysis_key, relational_game_id),
    )
    db.execute(
        """INSERT INTO events
              (game_id, relational_game_id, player, event_type, timestamp_ms,
               review_status, source_type)
           VALUES (?, ?, '2', 'make', 1500, 'pending', 'ai')""",
        (analysis_key, relational_game_id),
    )
    save_film_roster(
        db,
        season_id=season_id,
        level="varsity",
        gender="boys",
        side="our",
        players=[{"label": "12 Alex Carter", "jersey_number": 12, "name": "Alex Carter"}],
        replace=True,
    )
    db.commit()

    save_court_slot_mappings(
        db,
        analysis_key,
        [{"tracker_id": 2, "jersey_number": 12, "player_name": "Alex Carter"}],
        apply_to_events=True,
    )
    row = db.execute(
        "SELECT player FROM events WHERE relational_game_id = ?",
        (relational_game_id,),
    ).fetchone()
    assert row is not None
    assert row["player"] == "#12 Alex Carter"


def test_apply_mapping_rewrites_events_and_stats(db):
    from court_slot_mapping import apply_court_slot_mappings, save_court_slot_mappings
    from stats import aggregate_stats_preview

    game_id, analysis_key, player_id = _seed_game_with_slots(db)
    save_court_slot_mappings(
        db,
        analysis_key,
        [{"tracker_id": 3, "jersey_number": 12, "player_name": "Alex Carter", "player_id": player_id}],
        apply_to_events=False,
    )
    result = apply_court_slot_mappings(db, analysis_key)

    row = db.execute(
        "SELECT player, review_status, primary_player_id FROM events WHERE player LIKE '#12%'"
    ).fetchone()
    assert row is not None
    assert row["review_status"] == "corrected"
    assert row["primary_player_id"] == player_id
    assert result["events_updated"] >= 1

    stats = aggregate_stats_preview(db, analysis_key)
    labels = {s["player"] for s in stats}
    assert any(label.startswith("#12") for label in labels)
