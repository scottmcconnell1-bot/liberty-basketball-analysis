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
