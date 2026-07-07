"""Tests for Analysis Results roster + event explorer helpers."""

from film_roster import save_film_roster

from analysis_helpers import (
    get_analysis_roster_players,
    infer_period_labels,
    list_analysis_events,
    resolve_video_duration_ms,
)


def _create_season(db, name="2025-26"):
    return db.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?, ?, ?)",
        (name, "2025-11-01", "2026-03-01"),
    ).lastrowid


def test_get_analysis_roster_players_uses_film_roster(client, db):
    season_id = _create_season(db)
    scheduled_game_id = db.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, team, gender, level, game_date, opponent_name, status)
           VALUES (?, 'Liberty', 'boys_hs', 'boys', 'varsity', '2026-01-15', 'Wilder', 'scheduled')""",
        (season_id,),
    ).lastrowid
    relational_game_id = db.execute(
        "INSERT INTO games (scheduled_game_id, source_type, source_key, nfhs_game_id) VALUES (?, 'nfhs_vod', 'gam30', 'gam30')",
        (scheduled_game_id,),
    ).lastrowid
    analysis_key = "nfhs_gam30_analysis"
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (relational_game_id, analysis_key, "uploads/wilder.mp4"),
    )
    save_film_roster(
        db,
        season_id=season_id,
        level="varsity",
        gender="boys",
        side="our",
        players=[
            {"label": "0 Caleb Henrickson", "jersey_number": 0, "name": "Caleb Henrickson"},
            {"label": "3 Jonathan Kariuki", "jersey_number": 3, "name": "Jonathan Kariuki"},
        ],
        replace=True,
    )
    db.commit()

    payload = get_analysis_roster_players(db, analysis_key)
    assert payload["source"] == "film_roster"
    assert len(payload["players"]) == 2
    assert payload["players"][0]["jersey_number"] == 0
    assert payload["roster_context"]["season_id"] == season_id


def test_analysis_roster_api_endpoint(client, db):
    season_id = _create_season(db)
    scheduled_game_id = db.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, team, gender, level, game_date, opponent_name, status)
           VALUES (?, 'Liberty', 'boys_hs', 'boys', 'varsity', '2026-01-15', 'Wilder', 'scheduled')""",
        (season_id,),
    ).lastrowid
    relational_game_id = db.execute(
        "INSERT INTO games (scheduled_game_id, source_type, source_key) VALUES (?, 'manual', 'roster-api')",
        (scheduled_game_id,),
    ).lastrowid
    analysis_key = "nfhs_roster_api"
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (relational_game_id, analysis_key, "uploads/test.mp4"),
    )
    save_film_roster(
        db,
        season_id=season_id,
        level="varsity",
        gender="boys",
        side="our",
        players=[{"label": "12 Alex Player", "jersey_number": 12, "name": "Alex Player"}],
        replace=True,
    )
    db.commit()

    resp = client.get(f"/api/analysis/{analysis_key}/roster")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["source"] == "film_roster"
    assert data["players"][0]["name"] == "Alex Player"


def test_infer_period_labels_splits_video_into_quarters():
    duration = 40 * 60 * 1000
    assert infer_period_labels(5 * 60 * 1000, duration)["quarter"] == 1
    assert infer_period_labels(25 * 60 * 1000, duration)["quarter"] == 3
    assert infer_period_labels(10 * 60 * 1000, duration)["half"] == 1
    assert infer_period_labels(30 * 60 * 1000, duration)["half"] == 2


def test_list_analysis_events_filters_by_stat_and_player(client, db):
    game_row = db.execute(
        "INSERT INTO games (source_type, source_key) VALUES ('manual', 'events-filter')"
    )
    relational_game_id = game_row.lastrowid
    analysis_key = "nfhs_events_filter"
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (relational_game_id, analysis_key, "uploads/test.mp4"),
    )
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, game_id, relational_game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("test.mp4", "stored_test.mp4", "uploads/stored_test.mp4", 1000, analysis_key, relational_game_id),
    )
    events = [
        ("2", "rebound", 10 * 60 * 1000),
        ("3", "rebound", 12 * 60 * 1000),
        ("2", "assist", 11 * 60 * 1000),
        ("5", "rebound", 30 * 60 * 1000),
    ]
    for player, event_type, ts in events:
        db.execute(
            """INSERT INTO events
               (game_id, relational_game_id, player, event_type, timestamp_ms, source_type)
               VALUES (?, ?, ?, ?, ?, 'ai')""",
            (analysis_key, relational_game_id, player, event_type, ts),
        )
    db.commit()

    duration = resolve_video_duration_ms(db, analysis_key)
    assert duration == 30 * 60 * 1000

    all_rebounds = list_analysis_events(db, analysis_key, stat="reb")
    assert all_rebounds["count"] == 3
    assert all_rebounds["stored_filename"] == "stored_test.mp4"

    player_rebounds = list_analysis_events(db, analysis_key, stat="reb", player="2")
    assert player_rebounds["count"] == 1

    q1_rebounds = list_analysis_events(db, analysis_key, stat="reb", quarter=2)
    assert q1_rebounds["count"] == 2

    second_half = list_analysis_events(db, analysis_key, stat="reb", half=2)
    assert second_half["count"] == 1


def test_analysis_events_api_returns_film_links(client, db):
    game_row = db.execute(
        "INSERT INTO games (source_type, source_key) VALUES ('manual', 'events-api')"
    )
    relational_game_id = game_row.lastrowid
    analysis_key = "nfhs_events_api"
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (relational_game_id, analysis_key, "uploads/test.mp4"),
    )
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, game_id, relational_game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("test.mp4", "stored_events.mp4", "uploads/stored_events.mp4", 1000, analysis_key, relational_game_id),
    )
    db.execute(
        """INSERT INTO events
           (game_id, relational_game_id, player, event_type, timestamp_ms, source_type)
           VALUES (?, ?, ?, ?, ?, 'ai')""",
        (analysis_key, relational_game_id, "7", "rebound", 90500),
    )
    db.commit()

    resp = client.get(f"/api/analysis/{analysis_key}/events?stat=reb")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 1
    assert data["events"][0]["quarter_label"] == "Q4"
    assert "stored_events.mp4" in data["events"][0]["film_url"]
    assert "t=90" in data["events"][0]["film_url"]


def test_analysis_results_page_includes_event_explorer(client):
    resp = client.get("/analysis/test-game-key")
    assert resp.status_code == 200
    assert b"event-explorer" in resp.data
    assert b"openEventExplorer" in resp.data
    assert b"/api/analysis/" in resp.data
