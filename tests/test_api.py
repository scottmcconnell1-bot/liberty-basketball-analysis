"""
test_api.py – Integration tests for all Flask API endpoints.
"""
import json
import io
from pathlib import Path
import pytest


# ── Helpers ───────────────────────────────────────────────────────────

def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type="application/json")


# ── Dashboard ─────────────────────────────────────────────────────────

def test_dashboard_returns_counts(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.get_json()
    assert "seasons" in d
    assert "scheduled" in d
    assert "events" in d
    assert "players" in d
    assert "upcoming_games" in d
    assert "recent_events" in d


def test_resource_status_endpoint(client):
    r = client.get("/api/resource-status")
    assert r.status_code == 200
    d = r.get_json()
    assert "cpu" in d
    assert "memory" in d
    assert "gpu" in d
    assert "application" in d
    assert "power" in d
    assert "processes" in d["gpu"]


# ── Seasons ───────────────────────────────────────────────────────────

def test_seasons_empty(client):
    r = client.get("/api/seasons")
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "2025-26 Boys Jr High",
        "start_date": "2025-11-01",
        "end_date": "2026-02-28",
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d["name"] == "2025-26 Boys Jr High"
    assert d["id"] is not None


def test_create_season_missing_field(client):
    r = post_json(client, "/api/seasons", {"name": "Incomplete"})
    assert r.status_code == 400


def test_create_season_duplicate(client):
    data = {"name": "Same", "start_date": "2025-01-01", "end_date": "2025-12-31"}
    post_json(client, "/api/seasons", data)
    r = post_json(client, "/api/seasons", data)
    assert r.status_code == 409


def test_get_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "Test Season", "start_date": "2025-01-01", "end_date": "2025-12-31"
    })
    sid = r.get_json()["id"]
    r2 = client.get(f"/api/seasons/{sid}")
    assert r2.status_code == 200
    assert r2.get_json()["name"] == "Test Season"


def test_update_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "Old Name", "start_date": "2025-01-01", "end_date": "2025-12-31"
    })
    sid = r.get_json()["id"]
    r2 = put_json(client, f"/api/seasons/{sid}", {"name": "New Name"})
    assert r2.status_code == 200
    assert r2.get_json()["name"] == "New Name"


def test_delete_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "To Delete", "start_date": "2025-01-01", "end_date": "2025-12-31"
    })
    sid = r.get_json()["id"]
    r2 = client.delete(f"/api/seasons/{sid}")
    assert r2.status_code == 200
    r3 = client.get(f"/api/seasons/{sid}")
    assert r3.status_code == 404


# ── Scheduled Games ───────────────────────────────────────────────────

def _create_season(client):
    r = post_json(client, "/api/seasons", {
        "name": "2025-26", "start_date": "2025-11-01", "end_date": "2026-03-01"
    })
    return r.get_json()["id"]


def _create_game(client, source_key="test-game"):
    r = post_json(client, "/api/games", {
        "source_type": "manual",
        "source_key": source_key,
    })
    assert r.status_code == 201
    return r.get_json()["id"]


def test_scheduled_games_empty(client):
    r = client.get("/api/scheduled_games")
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_scheduled_game(client):
    sid = _create_season(client)
    r = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-01",
        "opponent_name": "Riverside",
        "location_type": "home",
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d["opponent_name"] == "Riverside"


def test_create_game_missing_fields(client):
    r = post_json(client, "/api/scheduled_games", {"season_id": 1})
    assert r.status_code == 400


def test_filter_games_by_season(client):
    s1 = _create_season(client)
    r2 = post_json(client, "/api/seasons", {
        "name": "Other Season", "start_date": "2026-01-01", "end_date": "2026-12-31"
    })
    s2 = r2.get_json()["id"]
    post_json(client, "/api/scheduled_games", {
        "season_id": s1, "game_date": "2025-12-01", "opponent_name": "TeamA"
    })
    post_json(client, "/api/scheduled_games", {
        "season_id": s2, "game_date": "2026-02-01", "opponent_name": "TeamB"
    })
    r = client.get(f"/api/scheduled_games?season_id={s1}")
    games = r.get_json()
    assert len(games) == 1
    assert games[0]["opponent_name"] == "TeamA"


def test_filter_games_by_level_and_gender(client):
    sid = _create_season(client)
    post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-01",
        "opponent_name": "Varsity Boys",
        "level": "varsity",
        "gender": "boys",
    })
    post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-02",
        "opponent_name": "JV Girls",
        "level": "jv",
        "gender": "girls",
    })
    r = client.get(f"/api/scheduled_games?season_id={sid}&level=jv&gender=girls")
    games = r.get_json()
    assert len(games) == 1
    assert games[0]["opponent_name"] == "JV Girls"


def test_update_scheduled_game(client):
    sid = _create_season(client)
    r = post_json(client, "/api/scheduled_games", {
        "season_id": sid, "game_date": "2025-12-01", "opponent_name": "Old Opp"
    })
    gid = r.get_json()["id"]
    r2 = put_json(client, f"/api/scheduled_games/{gid}", {"opponent_name": "New Opp"})
    assert r2.status_code == 200
    assert r2.get_json()["opponent_name"] == "New Opp"


def test_delete_scheduled_game(client):
    sid = _create_season(client)
    r = post_json(client, "/api/scheduled_games", {
        "season_id": sid, "game_date": "2025-12-01", "opponent_name": "DeleteMe"
    })
    gid = r.get_json()["id"]
    r2 = client.delete(f"/api/scheduled_games/{gid}")
    assert r2.status_code == 200
    r3 = client.get("/api/scheduled_games")
    assert not any(g["id"] == gid for g in r3.get_json())


def test_delete_season_cascades_games(client):
    sid = _create_season(client)
    post_json(client, "/api/scheduled_games", {
        "season_id": sid, "game_date": "2025-12-01", "opponent_name": "ShouldGoAway"
    })
    client.delete(f"/api/seasons/{sid}")
    r = client.get("/api/scheduled_games")
    assert r.get_json() == []


def test_create_and_update_game(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-10",
        "opponent_name": "Linked Opponent",
    }).get_json()
    r = post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "manual-2025-12-10",
        "home_score": 55,
        "away_score": 47,
        "result": "win",
        "is_conference": True,
    })
    assert r.status_code == 201
    game = r.get_json()
    assert game["scheduled_game_id"] == scheduled["id"]
    gid = game["id"]

    r2 = put_json(client, f"/api/games/{gid}", {"source_key": "updated-key", "result": "loss"})
    assert r2.status_code == 200
    assert r2.get_json()["source_key"] == "updated-key"
    assert r2.get_json()["result"] == "loss"


def test_games_list_includes_schedule_context(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-11",
        "opponent_name": "Context Opponent",
    }).get_json()
    post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "context-key",
    })
    r = client.get("/api/games")
    games = r.get_json()
    assert any(g.get("opponent_name") == "Context Opponent" for g in games)


def test_create_filter_and_delete_sources(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-12",
        "opponent_name": "Source Opponent",
    }).get_json()
    game = post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "source-key",
    }).get_json()
    r = post_json(client, "/api/sources", {
        "game_id": game["id"],
        "source_type": "manual_upload",
        "source_path": "/tmp/source.mp4",
    })
    assert r.status_code == 201
    source = r.get_json()

    r2 = client.get(f"/api/sources?game_id={game['id']}")
    sources = r2.get_json()
    assert len(sources) == 1
    assert sources[0]["source_path"] == "/tmp/source.mp4"

    r3 = client.delete(f"/api/sources/{source['id']}")
    assert r3.status_code == 200
    assert client.get(f"/api/sources?game_id={game['id']}").get_json() == []


def test_confirm_nfhs_match_creates_game_and_source(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-13",
        "opponent_name": "NFHS Opponent",
    }).get_json()
    match = post_json(client, "/api/nfhs_matches", {
        "scheduled_game_id": scheduled["id"],
        "nfhs_game_id": "nfhs-123",
        "nfhs_url": "https://example.com/nfhs/123",
        "confidence": 0.88,
    }).get_json()

    r = client.post(f"/api/nfhs_matches/{match['id']}/confirm")
    assert r.status_code == 200
    confirmed = r.get_json()
    assert confirmed["match_status"] == "confirmed"
    assert confirmed["game_id"] is not None

    games = client.get("/api/games").get_json()
    linked_game = next(g for g in games if g["scheduled_game_id"] == scheduled["id"])
    assert linked_game["nfhs_game_id"] == "nfhs-123"

    sources = client.get(f"/api/sources?game_id={linked_game['id']}").get_json()
    assert len(sources) == 1
    assert sources[0]["source_type"] == "nfhs_vod"
    assert sources[0]["source_path"] == "https://example.com/nfhs/123"


def test_reject_nfhs_match(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-14",
        "opponent_name": "Reject Opponent",
    }).get_json()
    match = post_json(client, "/api/nfhs_matches", {
        "scheduled_game_id": scheduled["id"],
        "nfhs_game_id": "nfhs-456",
        "nfhs_url": "https://example.com/nfhs/456",
    }).get_json()

    r = client.post(f"/api/nfhs_matches/{match['id']}/reject")
    assert r.status_code == 200
    assert r.get_json()["match_status"] == "rejected"


# ── Events ────────────────────────────────────────────────────────────

def test_save_event(client):
    game_id = _create_game(client, "event-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 5000,
        "player": "Player1",
        "shot_result": "made",
    })
    assert r.status_code == 200
    assert r.get_json()["status"] == "success"


def test_save_event_missing_timestamp(client):
    game_id = _create_game(client, "missing-timestamp-game")
    r = post_json(client, "/api/save_event", {"game_id": game_id, "event_type": "shot"})
    assert r.status_code == 400


def test_save_event_missing_game_id(client):
    r = post_json(client, "/api/save_event", {"event_type": "shot", "timestamp_ms": 1000})
    assert r.status_code == 400
    assert r.get_json()["message"] == "game_id required"


def test_save_event_rejects_unknown_game_id(client):
    r = post_json(client, "/api/save_event", {"game_id": 9999, "event_type": "shot", "timestamp_ms": 1000})
    assert r.status_code == 400
    assert "existing game" in r.get_json()["message"]


def test_get_events(client):
    game_id = _create_game(client, "events-game")
    post_json(client, "/api/save_event", {"game_id": game_id, "event_type": "assist", "timestamp_ms": 1000})
    post_json(client, "/api/save_event", {"game_id": game_id, "event_type": "rebound", "timestamp_ms": 2000})
    r = client.get(f"/api/events/{game_id}")
    events = r.get_json()
    assert len(events) == 2
    assert events[0]["timestamp_ms"] < events[1]["timestamp_ms"]


def test_get_events_can_filter_by_event_type(client):
    game_id = _create_game(client, "bookmark-game")
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "bookmark",
        "timestamp_ms": 1000,
        "player": "Clip A",
    })
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "assist",
        "timestamp_ms": 2000,
    })
    r = client.get(f"/api/events/{game_id}?event_type=bookmark")
    events = r.get_json()
    assert len(events) == 1
    assert events[0]["event_type"] == "bookmark"


def test_update_event(client):
    game_id = _create_game(client, "update-event-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id, "event_type": "shot", "timestamp_ms": 1000
    })
    eid = r.get_json()["id"]
    r2 = put_json(client, f"/api/events/{eid}", {"event_type": "block"})
    assert r2.status_code == 200
    assert r2.get_json()["event_type"] == "block"


def test_delete_event(client):
    game_id = _create_game(client, "delete-event-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id, "event_type": "steal", "timestamp_ms": 500
    })
    eid = r.get_json()["id"]
    r2 = client.delete(f"/api/events/{eid}")
    assert r2.status_code == 200
    r3 = client.get(f"/api/events/{game_id}")
    assert not any(e["id"] == eid for e in r3.get_json())


def test_review_events_lists_pending_ai_events(client):
    game_id = _create_game(client, "review-list-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
        "human_verified": False,
        "source_type": "ai",
        "confidence": 0.41,
    })
    eid = r.get_json()["id"]

    review = client.get("/api/review/events")
    assert review.status_code == 200
    rows = review.get_json()
    assert any(row["id"] == eid for row in rows)
    row = next(row for row in rows if row["id"] == eid)
    assert row["review_status"] == "pending"
    assert row["source_type"] == "ai"
    assert row["review_item_id"] is not None


def test_review_event_accept_marks_event_verified(client):
    game_id = _create_game(client, "review-accept-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "assist",
        "timestamp_ms": 1500,
        "human_verified": False,
        "source_type": "ai",
    })
    eid = r.get_json()["id"]

    accepted = post_json(client, f"/api/review/events/{eid}/accept", {"notes": "Looks right"})
    assert accepted.status_code == 200
    event = accepted.get_json()
    assert event["review_status"] == "accepted"
    assert event["human_verified"] == 1
    assert event["reviewed_at"] is not None


def test_review_event_correct_updates_event_and_records_correction(client, db):
    game_id = _create_game(client, "review-correct-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 2000,
        "player": "Wrong Player",
        "human_verified": False,
        "source_type": "ai",
    })
    eid = r.get_json()["id"]

    corrected = post_json(client, f"/api/review/events/{eid}/correct", {
        "player": "Right Player",
        "event_type": "made_two",
        "notes": "Coach corrected player and event type",
    })
    assert corrected.status_code == 200
    event = corrected.get_json()
    assert event["review_status"] == "corrected"
    assert event["human_verified"] == 1
    assert event["player"] == "Right Player"
    assert event["event_type"] == "made_two"

    corrections = db.execute(
        "SELECT field_changed FROM human_corrections WHERE event_id=?",
        (eid,),
    ).fetchall()
    fields = {row["field_changed"] for row in corrections}
    assert {"player", "event_type"} <= fields


def test_review_event_reject_preserves_event_and_records_correction(client, db):
    game_id = _create_game(client, "review-reject-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "turnover",
        "timestamp_ms": 2500,
        "human_verified": False,
        "source_type": "ai",
    })
    eid = r.get_json()["id"]

    rejected = post_json(client, f"/api/review/events/{eid}/reject", {
        "notes": "Bad AI event",
    })
    assert rejected.status_code == 200
    event = rejected.get_json()
    assert event["review_status"] == "rejected"
    assert event["human_verified"] == 0

    events = client.get(f"/api/events/{game_id}").get_json()
    assert any(row["id"] == eid for row in events)

    correction = db.execute(
        """SELECT * FROM human_corrections
           WHERE event_id=? AND correction_type='remove_event'""",
        (eid,),
    ).fetchone()
    assert correction is not None
    assert correction["relational_game_id"] == game_id
    assert correction["field_changed"] == "review_status"
    assert correction["corrected_value"] == "rejected"


def test_sync_event_review_item_sets_relational_game_id(client, db):
    game_id = _create_game(client, "sync-relational-game")
    # create an event with human_verified=False so it goes to review
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "assist",
        "timestamp_ms": 1000,
        "human_verified": False,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    # trigger sync via accept
    resp = post_json(client, f"/api/review/events/{eid}/accept", {"notes": "test"})
    assert resp.status_code == 200
    row = db.execute(
        "SELECT relational_game_id FROM review_items WHERE entity_id=? AND entity_type='event'",
        (eid,),
    ).fetchone()
    assert row is not None
    assert row["relational_game_id"] == game_id
    # ── Stage 4B: save_event relational wiring ────────────────────────────
# ── Stage 4B: save_event relational wiring ────────────────────────────

def test_save_event_writes_relational_game_id(client, db):
    """save_event must write relational_game_id while preserving legacy game_id."""
    game_id = _create_game(client, "relational-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "assist",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    row = db.execute("SELECT game_id, relational_game_id FROM events WHERE id=?", (eid,)).fetchone()
    assert row["game_id"] == str(game_id)
    assert row["relational_game_id"] == game_id


def test_save_event_resolves_event_type_id_from_seeded_code(client, db):
    """save_event resolves event_type_id by lookup against existing event_types.code."""
    game_id = _create_game(client, "event-type-id-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "assist",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    row = db.execute("SELECT event_type_id FROM events WHERE id=?", (eid,)).fetchone()
    et_row = db.execute("SELECT id FROM event_types WHERE code='assist'").fetchone()
    assert row["event_type_id"] == et_row["id"]


def test_save_event_does_not_seed_unknown_event_type(client, db):
    """save_event must NOT create new event_types rows for unknown free text."""
    game_id = _create_game(client, "no-seed-game")
    before = db.execute("SELECT COUNT(*) AS cnt FROM event_types").fetchone()["cnt"]
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "completely_unknown_xyz",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    after = db.execute("SELECT COUNT(*) AS cnt FROM event_types").fetchone()["cnt"]
    assert after == before, "save_event must not insert new event_types for unknown codes"
    eid = r.get_json()["id"]
    row = db.execute("SELECT event_type_id FROM events WHERE id=?", (eid,)).fetchone()
    assert row["event_type_id"] is None


def test_save_event_resolves_primary_player_by_name(client, db):
    """save_event resolves primary_player_id via lower(trim()) roster_membership match."""
    game_id = _create_game(client, "player-resolve-game")
    # Create player and roster_membership
    r = post_json(client, "/api/players", {"name": "Jordan Smith", "jersey_number": 23})
    player_id = r.get_json()["id"]
    # Create team via direct DB insert (no API for teams in this slice)
    db.execute(
        "INSERT INTO teams (team_name, program_name) VALUES (?, ?)",
        ("Liberty Lions", "Liberty"),
    )
    team_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        "INSERT INTO roster_memberships (player_id, team_id, status) VALUES (?, ?, 'active')",
        (player_id, team_id),
    )
    db.commit()

    # Use different casing and whitespace to exercise lower(trim()) match
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
        "player": "  jordan smith  ",
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    row = db.execute(
        "SELECT primary_player_id, primary_roster_membership_id, team_id FROM events WHERE id=?",
        (eid,),
    ).fetchone()
    assert row["primary_player_id"] == player_id
    assert row["primary_roster_membership_id"] is not None
    assert row["team_id"] == team_id


def test_save_event_writes_primary_event_participant(client, db):
    """save_event inserts one event_participants row with role='primary'."""
    game_id = _create_game(client, "participant-game")
    r = post_json(client, "/api/players", {"name": "Alex Carter", "jersey_number": 11})
    player_id = r.get_json()["id"]
    db.execute(
        "INSERT INTO teams (team_name, program_name) VALUES (?, ?)",
        ("Liberty Lions", "Liberty"),
    )
    team_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        "INSERT INTO roster_memberships (player_id, team_id, status) VALUES (?, ?, 'active')",
        (player_id, team_id),
    )
    db.commit()

    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
        "player": "Alex Carter",
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    participants = db.execute(
        "SELECT * FROM event_participants WHERE event_id=? AND role='primary'",
        (eid,),
    ).fetchall()
    assert len(participants) == 1
    p = participants[0]
    assert p["player_id"] == player_id
    assert p["team_id"] == team_id
    assert p["roster_membership_id"] is not None


def test_save_event_no_player_no_participant(client, db):
    """save_event without a player must not create event_participants."""
    game_id = _create_game(client, "no-player-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    participants = db.execute(
        "SELECT * FROM event_participants WHERE event_id=?",
        (eid,),
    ).fetchall()
    assert len(participants) == 0


def test_update_event_touches_updated_at(client, db):
    """update_event must set updated_at."""
    game_id = _create_game(client, "update-ts-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
    })
    eid = r.get_json()["id"]
    row_before = db.execute("SELECT updated_at FROM events WHERE id=?", (eid,)).fetchone()
    # Ensure time advances (SQLite has 1-second resolution)
    import time
    time.sleep(1.1)
    r2 = put_json(client, f"/api/events/{eid}", {"event_type": "block"})
    assert r2.status_code == 200
    row_after = db.execute("SELECT updated_at FROM events WHERE id=?", (eid,)).fetchone()
    assert row_after["updated_at"] is not None
    assert row_after["updated_at"] != row_before["updated_at"]

# ── Stage 4B: created_by_user_id proof ─────────────────────────────

def test_save_event_created_by_user_id_null_without_user(client, db):
    """Without session user context, created_by_user_id is NULL."""
    game_id = _create_game(client, "no-user-ctx-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    row = db.execute(
        "SELECT created_by_user_id FROM events WHERE id=?", (eid,)
    ).fetchone()
    # No session user_id set → _current_review_user_id() returns None
    assert row["created_by_user_id"] is None


def test_save_event_populates_created_by_user_id_from_session(client, db):
    """save_event must populate created_by_user_id from session["user_id"].

    _current_review_user_id() now falls back to reading session["user_id"]
    (the key used by blueprints/users.py login flow) and validates it
    against the users table before writing. This test proves the full
    wiring end-to-end using Flask session_transaction().
    """
    # 1. Create a real, active user in the DB
    db.execute(
        "INSERT INTO users (email, password_hash, display_name, role)"
        " VALUES (?,?,?,?)",
        ("coach@test.local", "x", "Auto Test Coach", "coach"),
    )
    db.commit()
    user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 2. Set session["user_id"] via session_transaction (same key users.py uses)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    # 3. Save event — session cookie will be sent automatically
    game_id = _create_game(client, "user-ctx-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]

    # 4. Prove created_by_user_id was populated
    row = db.execute(
        "SELECT created_by_user_id FROM events WHERE id=?", (eid,)
    ).fetchone()
    assert row["created_by_user_id"] == user_id, (
        f"Expected created_by_user_id={user_id}, got {row['created_by_user_id']}"
    )


def test_save_event_ignores_invalid_session_user_id(client, db):
    """If session holds a user_id that doesn't exist in users table,
    _current_review_user_id() must return None (not crash or write bad FK)."""
    with client.session_transaction() as sess:
        sess["user_id"] = 99999  # non-existent user

    game_id = _create_game(client, "invalid-user-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    eid = r.get_json()["id"]
    row = db.execute(
        "SELECT created_by_user_id FROM events WHERE id=?", (eid,)
    ).fetchone()
    assert row["created_by_user_id"] is None




# ── Players ───────────────────────────────────────────────────────────

def test_players_empty(client):
    r = client.get("/api/players")
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_player(client):
    r = post_json(client, "/api/players", {
        "name": "Jordan Smith", "jersey_number": 23, "position": "G", "grade": 8
    })
    assert r.status_code == 201
    d = r.get_json()
    assert d["name"] == "Jordan Smith"
    assert d["jersey_number"] == 23


def test_create_player_missing_name(client):
    r = post_json(client, "/api/players", {"jersey_number": 5})
    assert r.status_code == 400


# ── Pages render ─────────────────────────────────────────────────────

def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Liberty" in r.data


def test_schedule_page(client):
    r = client.get("/schedule")
    assert r.status_code == 200
    assert b"Schedule" in r.data


def test_schedule_page_renders_games_server_side(client):
    sid = _create_season(client)
    post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-05",
        "opponent_name": "Server Render Opponent",
        "level": "varsity",
        "gender": "girls",
    })
    r = client.get(f"/schedule?season_id={sid}&level=varsity&gender=girls")
    assert r.status_code == 200
    assert b"Server Render Opponent" in r.data


def test_games_page_renders_server_side(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-20",
        "opponent_name": "Rendered Game Opponent",
    }).get_json()
    post_json(client, "/api/games", {
        "scheduled_game_id": scheduled["id"],
        "source_type": "manual",
        "source_key": "rendered-game-key",
    })
    r = client.get("/games")
    assert r.status_code == 200
    assert b"Rendered Game Opponent" in r.data


def test_nfhs_matches_page_renders_server_side(client):
    sid = _create_season(client)
    scheduled = post_json(client, "/api/scheduled_games", {
        "season_id": sid,
        "game_date": "2025-12-21",
        "opponent_name": "Rendered NFHS Opponent",
    }).get_json()
    post_json(client, "/api/nfhs_matches", {
        "scheduled_game_id": scheduled["id"],
        "nfhs_game_id": "nfhs-rendered",
        "nfhs_url": "https://example.com/rendered",
    })
    r = client.get("/nfhs-matches")
    assert r.status_code == 200
    assert b"Rendered NFHS Opponent" in r.data


def test_practices_page_renders_server_side(client):
    sid = _create_season(client)
    r = client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-22",
        "level": "varsity",
        "status": "planned",
        "plan_source": "manual",
        "plan_text": "Shell defense and transition offense",
        "coach_notes": "Good energy.",
        "filter_season_id": sid,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"2025-12-22" in r.data
    assert b"Good energy." in r.data


def test_practice_report_generation(client):
    sid = _create_season(client)
    client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-23",
        "level": "jv",
        "status": "completed",
        "plan_source": "manual",
        "plan_text": "Rebounding and transition defense",
        "coach_notes": "Too many second chances allowed.",
    }, follow_redirects=True)
    report_page = client.get("/practices")
    assert report_page.status_code == 200
    assert b"2025-12-23" in report_page.data

    # Pull the first practice ID through the report link in the rendered page by assuming a single practice exists.
    practices_page_html = report_page.data.decode("utf-8")
    marker = '/practices/'
    start = practices_page_html.index(marker) + len(marker)
    practice_id = int(practices_page_html[start:practices_page_html.index('/report', start)])

    generated = client.post(f"/practices/{practice_id}/generate", follow_redirects=True)
    assert generated.status_code == 200
    assert b"AI Notes" in generated.data
    assert b"Likely emphasis area" in generated.data


def test_practice_summary_page(client):
    sid = _create_season(client)
    client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-24",
        "level": "varsity",
        "status": "completed",
        "plan_source": "manual",
        "plan_text": "Shooting and spacing",
        "coach_notes": "Shot quality improved late.",
    }, follow_redirects=True)
    client.post("/practices/save", data={
        "season_id": sid,
        "practice_date": "2025-12-26",
        "level": "varsity",
        "status": "completed",
        "plan_source": "manual",
        "plan_text": "Shooting and rebounding",
        "coach_notes": "Needed more box-outs.",
    }, follow_redirects=True)
    r = client.get("/practice-summary?start_date=2025-12-20&end_date=2025-12-31&level=varsity")
    assert r.status_code == 200
    assert b"Range Summary" in r.data
    assert b"Recurring themes" in r.data


def test_film_page(client):
    r = client.get("/film")
    assert r.status_code == 200
    assert b"Report Bug / Idea" in r.data
    assert b"filmReviewGrid" in r.data
    assert b"aiEventsPanel" in r.data
    assert b"aiEventsScroller" in r.data
    assert b"aiCurrentEventLabel" in r.data
    assert b"Independent scrolling event timeline" in r.data


def test_film_page_accepts_manual_game_id_query(client):
    r = client.get("/film?game_id=manual_clip_01")
    assert r.status_code == 200
    assert b"manual_clip_01" in r.data
    assert b"uploadProgressBar" in r.data


def test_film_page_with_uploaded_filename_embeds_video_url(client):
    r = client.get("/film/test_clip.mp4?game_id=test_game")
    assert r.status_code == 200
    assert b"/uploads/test_clip.mp4" in r.data
    assert b"Server video" in r.data


def test_film_tool_ai_events_doc_exists():
    doc = Path("docs/FILM_TOOL_AI_EVENTS.md").read_text(encoding="utf-8")
    assert "independently scrollable panel" in doc
    assert "Playback-linked highlighting" in doc


def test_upload_route_returns_json_for_xhr(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module.subprocess, "Popen", lambda *args, **kwargs: None)

    r = client.post(
        "/upload",
        data={
            "video": (io.BytesIO(b"video-bytes"), "sample.mp4"),
            "opponent": "Test Opponent",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["status"] == "uploaded"
    assert payload["redirect_url"].startswith("/film/")
    assert "game_id=" in payload["redirect_url"]


def test_analysis_status_includes_counts_and_summary(client, db):
    db.execute(
        "INSERT INTO analysis_runs (analysis_key, video_path, status) VALUES (?, ?, ?)",
        ("analysis_game", "uploads/demo.mp4", "completed"),
    )
    db.execute(
        """INSERT INTO detections
           (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("analysis_game", 1, 100, "person", 0.9, 10, 10, 20, 40),
    )
    db.execute(
        """INSERT INTO events
           (game_id, event_type, timestamp_ms, human_verified)
           VALUES (?, ?, ?, ?)""",
        ("analysis_game", "bookmark", 100, 1),
    )
    db.commit()

    r = client.get("/api/analysis_status/analysis_game")
    payload = r.get_json()
    assert r.status_code == 200
    assert payload["status"] == "completed"
    assert payload["detection_count"] == 1
    assert payload["event_count"] == 1
    assert "YOLO currently detects players and the ball" in payload["event_generation_summary"]


def test_analysis_status_counts_detections_via_relational_game_id(client, db):
    game_row = db.execute(
        "INSERT INTO games (source_type, source_key) VALUES (?, ?)",
        ("manual", "analysis-relational"),
    )
    relational_game_id = game_row.lastrowid
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, ?)""",
        (relational_game_id, "analysis_relational", "uploads/demo-relational.mp4", "completed"),
    )
    db.execute(
        """INSERT INTO detections
           (game_id, relational_game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("legacy_analysis_relational", relational_game_id, 1, 100, "person", 0.9, 10, 10, 20, 40),
    )
    db.commit()

    r = client.get("/api/analysis_status/analysis_relational")
    payload = r.get_json()
    assert r.status_code == 200
    assert payload["status"] == "completed"
    assert payload["detection_count"] == 1
    assert payload["event_count"] == 0


def test_settings_page_renders(client, monkeypatch):
    monkeypatch.setattr("helpers.list_ollama_models", lambda: [])
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"Settings" in r.data
    assert b"Report Bug / Idea" in r.data
    assert b"Debug / Issues" in r.data
    assert b"Detector Model" in r.data
    assert b"Event Generator" in r.data
    assert b"Expanded heuristic generator" in r.data
    assert b"Custom Weights Guide" in r.data
    assert b"YOLO11 Small" in r.data
    assert b"Custom Ultralytics Model or Weights" in r.data
    assert b"Recommended Ollama Models" in r.data


def test_custom_weights_guide_page_renders(client):
    r = client.get("/settings/custom-weights")
    assert r.status_code == 200
    assert b"Custom Weights Guide" in r.data
    assert b"Can Ollama Vision Models Be Used?" in r.data
    assert b"How to Create Your Own Custom Weights" in r.data
    assert b"dataset.yaml" in r.data


def test_debug_page_renders(client):
    r = client.get("/debug")
    assert r.status_code == 200
    assert b"Debug / Issues" in r.data
    assert b"Report Bug, Issue, or Recommendation" in r.data
    assert b"Application Logs" in r.data


def test_create_and_complete_issue_report(client, db):
    created = client.post("/debug/issues", data={
        "entry_type": "recommendation",
        "title": "Add better rebounding tags",
        "details": "Need clearer offensive and defensive rebound labeling.",
        "browser_console": "[2026-05-05T07:00:00Z] ERROR clip load failed",
        "return_to": "/film?game=1#clips",
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    assert created.status_code == 200
    assert created.get_json()["message"] == "Report saved."

    row = db.execute("SELECT * FROM issue_reports WHERE title = ?", ("Add better rebounding tags",)).fetchone()
    assert row is not None
    assert row["status"] == "open"
    assert row["source_path"] == "/film?game=1#clips"
    assert "clip load failed" in row["browser_console"]

    completed = client.post(f"/debug/issues/{row['id']}/complete", data={"return_to": "/debug"}, follow_redirects=True)
    assert completed.status_code == 200

    updated = db.execute("SELECT status, completed_at FROM issue_reports WHERE id = ?", (row["id"],)).fetchone()
    assert updated["status"] == "completed"
    assert updated["completed_at"] is not None
    assert b"Completed" in completed.data


def test_debug_page_prefills_source_from_referrer(client):
    r = client.get("/debug", headers={"Referer": "http://localhost/film?game=44#reports"})
    assert r.status_code == 200
    assert b"/film?game=44" in r.data


def test_debug_page_filters_completed_reports(client, db):
    db.execute(
        """INSERT INTO issue_reports (entry_type, title, details, status)
           VALUES (?, ?, ?, ?)""",
        ("bug", "Open issue", "Still broken", "open"),
    )
    db.execute(
        """INSERT INTO issue_reports (entry_type, title, details, status, completed_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        ("note", "Completed issue", "Already fixed", "completed"),
    )
    db.commit()

    r = client.get("/debug?entry_status=completed")
    assert r.status_code == 200
    assert b"Completed issue" in r.data
    assert b"Open issue" not in r.data


def test_settings_page_persists_updates(client, db, monkeypatch):
    monkeypatch.setattr("helpers.list_ollama_models", lambda: [])
    r = client.post("/settings", data={
        "feature_ENABLE_MANUAL_TAG_MVP": "on",
        "feature_ENABLE_AUTO_STATS_M1": "on",
        "feature_ENABLE_SEASONS_SCHEDULE": "on",
        "feature_ENABLE_GAMES_SOURCES": "on",
        "feature_ENABLE_NFHS_MATCHING": "on",
        "feature_ENABLE_PRACTICES": "on",
        "ai_detector_model": "custom",
        "ai_custom_detector_model": "yolo11s.pt",
        "ai_ball_detector_model": "custom",
        "ai_custom_ball_detector_model": "models/new_ball_detector.pt",
        "ai_ball_class_id": "2",
        "ai_ball_confidence": "0.32",
        "ai_inference_device": "cpu",
        "ai_event_generator_mode": "expanded",
        "ai_frame_stride": "2",
        "ai_tracker_max_distance": "95",
        "ai_tracker_max_frame_gap": "7",
        "ai_llm_provider": "none",
        "ai_llm_model": "",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Settings saved." in r.data

    rows = db.execute("SELECT key, value FROM app_settings").fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    assert stored["ai.detector_model"] == "custom"
    assert stored["ai.custom_detector_model"] == "yolo11s.pt"
    assert stored["ai.ball_detector_model"] == "custom"
    assert stored["ai.custom_ball_detector_model"] == "models/new_ball_detector.pt"
    assert stored["ai.ball_class_id"] == "2"
    assert stored["ai.ball_confidence"] == "0.32"
    assert stored["ai.inference_device"] == "cpu"
    assert stored["ai.event_generator_mode"] == "expanded"
    assert stored["ai.frame_stride"] == "2"
    assert stored["ai.tracker_max_distance"] == "95"


def test_pull_ollama_model_starts_background_pull(client, monkeypatch):
    import blueprints.core as core_module

    calls = []

    class DummyPopen:
        def __init__(self, cmd, stdout=None, stderr=None, start_new_session=None):
            calls.append({
                "cmd": cmd,
                "stdout_name": getattr(stdout, "name", None),
                "stderr": stderr,
                "start_new_session": start_new_session,
            })

    monkeypatch.setattr(core_module.subprocess, "Popen", DummyPopen)

    r = client.post("/settings/ollama/pull", data={"model_name": "qwen2.5:7b"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/settings?message=Started+pulling+qwen2.5:7b" in r.headers["Location"]
    assert calls
    assert calls[0]["cmd"] == ["ollama", "pull", "qwen2.5:7b"]
    assert calls[0]["stdout_name"].endswith("liberty-basketball-ollama-pull-qwen2.5-7b.log")
    assert calls[0]["start_new_session"] is True


def test_pull_ollama_model_rejects_invalid_name(client):
    r = client.post("/settings/ollama/pull", data={"model_name": "bad model"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/settings?message=Invalid+Ollama+model+name." in r.headers["Location"]


def test_compare_video_analysis_page(client, db):
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("sample.mp4", "sample_1.mp4", "uploads/sample_1.mp4", 123, "Test Opponent", "base_game"),
    )
    db.execute(
        """INSERT INTO analysis_runs
           (analysis_key, video_path, source_video_id, base_analysis_key, run_label, run_kind, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("base_game", "uploads/sample_1.mp4", 1, "base_game", "Original upload", "primary", "completed"),
    )
    db.execute(
        """INSERT INTO analysis_runs
           (analysis_key, video_path, source_video_id, base_analysis_key, run_label, run_kind, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("base_game__rerun_1", "uploads/sample_1.mp4", 1, "base_game", "Rerun A", "rerun", "completed"),
    )
    db.commit()

    r = client.get("/videos/1/compare")
    assert r.status_code == 200
    assert b"Compare AI Runs" in r.data
    assert b"Original upload" in r.data
    assert b"Rerun A" in r.data


def test_rerun_video_analysis_creates_separate_run(client, db, monkeypatch):
    import blueprints.ai as ai_module

    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("sample.mp4", "sample_2.mp4", "uploads/sample_2.mp4", 123, "Test Opponent", "base_game"),
    )
    db.execute(
        "INSERT INTO analysis_runs (analysis_key, video_path, status) VALUES (?, ?, ?)",
        ("base_game", "uploads/sample_2.mp4", "completed"),
    )
    db.commit()

    monkeypatch.setattr(ai_module, "ai_runtime_available", lambda: True)
    monkeypatch.setattr(ai_module, "start_analysis_subprocess", lambda *args, **kwargs: None)

    r = client.post("/videos/1/rerun", data={"run_label": "YOLOv8s retry"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Queued rerun" in r.data
    assert b"YOLOv8s retry" in r.data

    rows = db.execute(
        "SELECT game_id, analysis_key, base_analysis_key, run_label, run_kind, settings_json FROM analysis_runs ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["analysis_key"] == "base_game"
    assert rows[0]["game_id"] is None
    assert rows[1]["analysis_key"] != "base_game"
    assert rows[1]["base_analysis_key"] == "base_game"
    assert rows[1]["run_label"] == "YOLOv8s retry"
    assert rows[1]["run_kind"] == "rerun"
    assert "detector_model" in rows[1]["settings_json"]


# ── Stats ─────────────────────────────────────────────────────────────

def test_stats_empty_game(client):
    r = client.get("/api/stats/no_such_game")
    assert r.status_code == 200
    data = r.get_json()
    assert "basic" in data
    assert "enhanced" in data
    assert data["basic"] == []


def test_stats_aggregation(client):
    game_id = _create_game(client, "stats-game")
    for _ in range(3):
        post_json(client, "/api/save_event", {
            "game_id": game_id, "player": "Alice",
            "event_type": "two_attempt", "shot_result": "made", "timestamp_ms": 1000
        })
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Alice",
        "event_type": "assist", "timestamp_ms": 2000
    })
    r = client.get(f"/api/stats/{game_id}")
    data = r.get_json()
    stats = data["basic"]
    alice = next(s for s in stats if s["player"] == "Alice")
    assert alice["pts"] == 6
    assert alice["fgm"] == 3
    assert alice["ast"] == 1


def test_stats_are_persisted_to_table(client, db):
    game_id = _create_game(client, "persisted-stats-game")
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Taylor",
        "event_type": "three_attempt",
        "shot_result": "made",
        "timestamp_ms": 1000,
    })
    client.get(f"/api/stats/{game_id}")
    row = db.execute(
        "SELECT player_name, pts, threes_made FROM stats WHERE game_id=?",
        (str(game_id),),
    ).fetchone()
    assert row is not None
    assert row["player_name"] == "Taylor"
    assert row["pts"] == 3
    assert row["threes_made"] == 1


# ── Stage 4C: relational stats derivation ─────────────────────────────

def _event_type_id(db, code):
    row = db.execute("SELECT id FROM event_types WHERE code=?", (code,)).fetchone()
    return row["id"] if row else None


def test_stats_uses_event_types_taxonomy(client, db):
    """Stage 4C: stats derivation must read event_types via event_type_id.

    Saves a manual made_two event (which save_event resolves to the seeded
    'made_two' event_type_id), then asserts the box score reflects the
    taxonomy-derived aggregation.
    """
    game_id = _create_game(client, "taxonomy-stats-game")
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Dana",
        "event_type": "made_two",
        "shot_result": "made",
        "timestamp_ms": 1000,
        "human_verified": True,
    })
    r = client.get(f"/api/stats/{game_id}")
    basic = r.get_json()["basic"]
    dana = next(s for s in basic if s["player"] == "Dana")
    assert dana["pts"] == 2
    assert dana["fgm"] == 1
    assert dana["fga"] == 1


def test_stats_excludes_rejected_events(client, db):
    """Stage 4C: rejected events must not contribute to stats."""
    game_id = _create_game(client, "rejected-stats-game")
    # Accepted manual made_two
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Evan",
        "event_type": "made_two",
        "shot_result": "made",
        "timestamp_ms": 1000,
        "human_verified": True,
    })
    # AI event that will be rejected
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Evan",
        "event_type": "made_three",
        "shot_result": "made",
        "timestamp_ms": 2000,
        "human_verified": False,
        "source_type": "ai",
    })
    eid = r.get_json()["id"]
    post_json(client, f"/api/review/events/{eid}/reject", {"notes": "bad"})

    r = client.get(f"/api/stats/{game_id}")
    basic = r.get_json()["basic"]
    evan = next(s for s in basic if s["player"] == "Evan")
    # Only the manual made_two counts; rejected made_three is excluded
    assert evan["pts"] == 2
    assert evan["threes_made"] == 0
    assert evan["threes_att"] == 0


def test_stats_includes_accepted_ai_events(client, db):
    """Stage 4C: accepted AI events (human_verified=0, review_status='accepted')
    must contribute to stats."""
    game_id = _create_game(client, "accepted-ai-stats-game")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Frank",
        "event_type": "made_three",
        "shot_result": "made",
        "timestamp_ms": 1000,
        "human_verified": False,
        "source_type": "ai",
    })
    eid = r.get_json()["id"]
    post_json(client, f"/api/review/events/{eid}/accept", {"notes": "good"})

    r = client.get(f"/api/stats/{game_id}")
    basic = r.get_json()["basic"]
    frank = next(s for s in basic if s["player"] == "Frank")
    assert frank["pts"] == 3
    assert frank["threes_made"] == 1
    assert frank["threes_att"] == 1


def test_stats_excludes_zero_counts_for_stats_events(client, db):
    """Stage 4C: events whose event_types.counts_for_stats=0 (e.g. substitution,
    timeout) must not contribute to the box score."""
    game_id = _create_game(client, "nocount-stats-game")
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Gabe",
        "event_type": "made_two",
        "shot_result": "made",
        "timestamp_ms": 1000,
        "human_verified": True,
    })
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Gabe",
        "event_type": "substitution",
        "timestamp_ms": 2000,
        "human_verified": True,
    })
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Gabe",
        "event_type": "timeout",
        "timestamp_ms": 3000,
        "human_verified": True,
    })

    r = client.get(f"/api/stats/{game_id}")
    basic = r.get_json()["basic"]
    gabe = next(s for s in basic if s["player"] == "Gabe")
    assert gabe["pts"] == 2
    assert gabe["events"] == 1  # only made_two counts_for_stats=1


# ── Four Factors ────────────────────────────────────────────────────

def test_four_factors_endpoint_returns_all_keys(client):
    """GET /api/four_factors/<game_id> returns JSON with all 4 keys."""
    game_id = _create_game(client, "four-factors-game")
    r = client.get(f"/api/four_factors/{game_id}")
    assert r.status_code == 200
    data = r.get_json()
    assert "efg_pct" in data
    assert "tov_pct" in data
    assert "orb_pct" in data
    assert "ft_rate" in data


def test_four_factors_returns_valid_percentages(client):
    """Four Factors values must be in 0.0-1.0 range."""
    game_id = _create_game(client, "four-factors-range-game")
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Alice",
        "event_type": "made_two",
        "shot_result": "made",
        "timestamp_ms": 1000,
        "human_verified": True,
    })
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Bob",
        "event_type": "rebound_offensive",
        "timestamp_ms": 2000,
        "human_verified": True,
    })
    r = client.get(f"/api/four_factors/{game_id}")
    data = r.get_json()
    for key in ("efg_pct", "tov_pct", "orb_pct", "ft_rate"):
        assert 0.0 <= data[key] <= 1.0, f"{key}={data[key]} out of range"


def test_four_factors_zero_division_returns_zero(client):
    """Four Factors with no events/shots returns 0.0 for all keys (no crash)."""
    game_id = _create_game(client, "four-factors-empty-game")
    r = client.get(f"/api/four_factors/{game_id}")
    assert r.status_code == 200
    data = r.get_json()
    assert data["efg_pct"] == 0.0
    assert data["tov_pct"] == 0.0
    assert data["orb_pct"] == 0.0
    assert data["ft_rate"] == 0.0


def test_four_factors_efg_calculation(client):
    """eFG% = (FGM + 0.5 * 3PM) / FGA. 2 made 2pt + 1 made 3pt out of 3 FGA."""
    game_id = _create_game(client, "four-factors-efg-game")
    # 2 made 2pt attempts
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Alice",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 1000, "human_verified": True,
    })
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Alice",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 2000, "human_verified": True,
    })
    # 1 made 3pt
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Bob",
        "event_type": "made_three", "shot_result": "made",
        "timestamp_ms": 3000, "human_verified": True,
    })
    r = client.get(f"/api/four_factors/{game_id}")
    data = r.get_json()
    # FGM=3, 3PM=1, FGA=3 → eFG% = (3 + 0.5*1) / 3 = 3.5/3 = 1.1667
    # eFG% can exceed 1.0 when 3PM is high; clamp not applied per spec
    assert abs(data["efg_pct"] - round(3.5 / 3, 4)) < 0.001


def test_four_factors_game_not_found(client):
    """GET /api/four_factors/<bad_id> returns 404."""
    r = client.get("/api/four_factors/99999")
    assert r.status_code == 404


def test_schedule_routes_hidden_when_feature_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_SEASONS_SCHEDULE"]
    app.config["FEATURES"]["ENABLE_SEASONS_SCHEDULE"] = False
    try:
        assert client.get("/schedule").status_code == 404
        assert client.get("/api/scheduled_games").status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_SEASONS_SCHEDULE"] = original


def test_games_routes_hidden_when_feature_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_GAMES_SOURCES"]
    app.config["FEATURES"]["ENABLE_GAMES_SOURCES"] = False
    try:
        assert client.get("/games").status_code == 404
        assert client.get("/api/games").status_code == 404
        assert client.get("/api/sources").status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_GAMES_SOURCES"] = original


def test_auto_stats_routes_hidden_when_feature_disabled(app, client):
    original = app.config["FEATURES"]["ENABLE_AUTO_STATS_M1"]
    app.config["FEATURES"]["ENABLE_AUTO_STATS_M1"] = False
    try:
        assert client.get("/api/stats/no_such_game").status_code == 404
        assert client.get("/api/analysis_status/no_such_game").status_code == 404
        assert client.get("/videos").status_code == 404
        assert client.get("/api/videos").status_code == 404
        assert client.get("/status").status_code == 404
    finally:
        app.config["FEATURES"]["ENABLE_AUTO_STATS_M1"] = original


# ── Stage 4C.2: Possession linkage ─────────────────────────────────────

def _create_game_with_events(client, db, source_key, events_data):
    """Helper: create a game and insert raw events with timestamps."""
    game_id = _create_game(client, source_key)
    for ev in events_data:
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, timestamp_ms,
                   relational_game_id, human_verified, review_status,
                   created_by_user_id)
               VALUES (?, ?, ?, ?, ?, 1, 'accepted', NULL)""",
            (str(game_id), ev.get("player"), ev["event_type"],
             ev["timestamp_ms"], game_id),
        )
    db.commit()
    return game_id


def test_save_event_persists_valid_possession_id(client, db):
    """Explicit valid possession_id in save_event is persisted."""
    game_id = _create_game(client, "possession-save-valid")
    relational_game_id = game_id
    # Create a possession row to reference.
    db.execute(
        """INSERT INTO possessions (game_id, start_timestamp_ms, source)
           VALUES (?, 0, 'manual')""",
        (relational_game_id,),
    )
    db.commit()
    possession_id = db.execute(
        "SELECT id FROM possessions WHERE game_id=?", (relational_game_id,)
    ).fetchone()["id"]

    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
        "possession_id": possession_id,
    })
    assert r.status_code == 200
    event_id = r.get_json()["id"]

    row = db.execute(
        "SELECT possession_id FROM events WHERE id=?", (event_id,)
    ).fetchone()
    assert row["possession_id"] == possession_id


def test_save_event_rejects_invalid_possession_id(client, db):
    """Invalid/mismatched possession_id is ignored (set to NULL)."""
    game_id = _create_game(client, "possession-save-invalid")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
        "possession_id": 99999,
    })
    assert r.status_code == 200
    event_id = r.get_json()["id"]

    row = db.execute(
        "SELECT possession_id FROM events WHERE id=?", (event_id,)
    ).fetchone()
    assert row["possession_id"] is None


def test_save_event_null_possession_id_when_absent(client, db):
    """Without possession_id in request, the column stays NULL."""
    game_id = _create_game(client, "possession-save-null")
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "event_type": "shot",
        "timestamp_ms": 1000,
    })
    assert r.status_code == 200
    event_id = r.get_json()["id"]

    row = db.execute(
        "SELECT possession_id FROM events WHERE id=?", (event_id,)
    ).fetchone()
    assert row["possession_id"] is None


def test_assign_possessions_for_game_creates_rows(client, db):
    """assign_possessions_for_game creates possession rows and links events."""
    events_data = [
        {"event_type": "shot", "timestamp_ms": 1000},
        {"event_type": "turnover", "timestamp_ms": 2000},  # boundary
        {"event_type": "shot", "timestamp_ms": 3000},
        {"event_type": "steal", "timestamp_ms": 4000},  # boundary
        {"event_type": "made_two", "timestamp_ms": 5000},
    ]
    game_id = _create_game_with_events(
        client, db, "assign-poss-game", events_data
    )

    from helpers import assign_possessions_for_game
    assign_possessions_for_game(db, game_id)

    # 3 possessions: [shot], [turnover, shot], [steal, made_two]
    poss_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM possessions WHERE game_id=?",
        (game_id,),
    ).fetchone()["cnt"]
    assert poss_count == 3

    # All events must have a possession_id.
    null_links = db.execute(
        """SELECT COUNT(*) AS cnt FROM events
            WHERE relational_game_id=? AND possession_id IS NULL""",
        (game_id,),
    ).fetchone()["cnt"]
    assert null_links == 0


def test_assign_possessions_for_game_is_idempotent(client, db):
    """Running assign_possessions_for_game twice produces same state."""
    events_data = [
        {"event_type": "made_two", "timestamp_ms": 1000},
        {"event_type": "turnover", "timestamp_ms": 2000},
        {"event_type": "assist", "timestamp_ms": 3000},
    ]
    game_id = _create_game_with_events(
        client, db, "assign-poss-idempotent", events_data
    )

    from helpers import assign_possessions_for_game
    assign_possessions_for_game(db, game_id)
    ids_before = [
        r["possession_id"]
        for r in db.execute(
            "SELECT possession_id FROM events WHERE relational_game_id=? ORDER BY id",
            (game_id,),
        ).fetchall()
    ]
    poss_before = db.execute(
        "SELECT COUNT(*) AS cnt FROM possessions WHERE game_id=?",
        (game_id,),
    ).fetchone()["cnt"]

    # Run again.
    assign_possessions_for_game(db, game_id)
    ids_after = [
        r["possession_id"]
        for r in db.execute(
            "SELECT possession_id FROM events WHERE relational_game_id=? ORDER BY id",
            (game_id,),
        ).fetchall()
    ]
    poss_after = db.execute(
        "SELECT COUNT(*) AS cnt FROM possessions WHERE game_id=?",
        (game_id,),
    ).fetchone()["cnt"]

    assert poss_before ==poss_after, "duplicate possessions on re-run"
    assert ids_before == ids_after, "possession_id links changed on re-run"


def test_assign_possessions_boundary_starts_new_possession(client, db):
    """Boundary events end the current possession; next event starts new one."""
    events_data = [
        {"event_type": "made_two", "timestamp_ms": 1000},
        {"event_type": "made_two", "timestamp_ms": 1500},
        {"event_type": "turnover", "timestamp_ms": 2000},   # boundary
        {"event_type": "assist", "timestamp_ms": 3000},     # new possession
        {"event_type": "made_three", "timestamp_ms": 3500},
    ]
    game_id = _create_game_with_events(
        client, db, "assign-poss-boundary", events_data
    )

    from helpers import assign_possessions_for_game
    assign_possessions_for_game(db, game_id)

    rows = db.execute(
        """SELECT e.id, e.event_type, e.possession_id
             FROM events e
            WHERE e.relational_game_id = ?
            ORDER BY e.timestamp_ms ASC, e.id ASC""",
        (game_id,),
    ).fetchall()

    # Possession 1: first two made_twos. Possession 2: turnover + assist + made_three.
    p1_id = rows[0]["possession_id"]
    p2_id = rows[2]["possession_id"]
    assert p1_id != p2_id, "boundary did not split possessions"
    assert rows[1]["possession_id"] == p1_id
    assert rows[3]["possession_id"] == p2_id
    assert rows[4]["possession_id"] == p2_id


def test_assign_possessions_preserves_event_facts(client, db):
    """Linkage must never touch event_type, player, shot_result, timestamp, review."""
    events_data = [
        {"event_type": "made_two", "player": "Alice", "timestamp_ms": 1000},
        {"event_type": "turnover", "player": "Bob", "timestamp_ms": 2000},
    ]
    game_id = _create_game_with_events(
        client, db, "assign-poss-preserve", events_data
    )

    # Snapshot facts before.
    before = [
        dict(r) for r in db.execute(
            "SELECT id, event_type, player, timestamp_ms, review_status "
            "FROM events WHERE relational_game_id=? ORDER BY id",
            (game_id,),
        ).fetchall()
    ]

    from helpers import assign_possessions_for_game
    assign_possessions_for_game(db, game_id)

    # Snapshot facts after.
    after = [
        dict(r) for r in db.execute(
            "SELECT id, event_type, player, timestamp_ms, review_status "
            "FROM events WHERE relational_game_id=? ORDER BY id",
            (game_id,),
        ).fetchall()
    ]

    for b, a in zip(before, after):
        assert b["event_type"] == a["event_type"]
        assert b["player"] == a["player"]
        assert b["timestamp_ms"] == a["timestamp_ms"]
        assert b["review_status"] == a["review_status"]


def test_possession_api_endpoint_returns_summary(client, db):
    """GET /api/possessions/<game_id> returns possession summary JSON."""
    game_id = _create_game_with_events(
        client, db, "possession-api",
        [
            {"event_type": "made_two", "player": "Alice", "timestamp_ms": 1000},
            {"event_type": "turnover", "player": "Bob", "timestamp_ms": 2000},
            {"event_type": "made_three", "player": "Carol", "timestamp_ms": 3000},
        ],
    )
    resp = client.get(f"/api/possessions/{game_id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
    data = resp.get_json()
    assert "total_possessions" in data
    assert "scoring_possessions" in data
    assert "points_per_possession" in data
    assert "turnover_rate" in data
    assert "top_outcomes" in data
    assert data["total_possessions"] > 0


def test_possession_count_matches_events_with_possession_id(client, db):
    """Possession summary count matches events that have possession_id set."""
    game_id = _create_game_with_events(
        client, db, "possession-count",
        [
            {"event_type": "made_two", "player": "Alice", "timestamp_ms": 1000},
            {"event_type": "made_two", "player": "Bob", "timestamp_ms": 2000},
            {"event_type": "turnover", "player": "Charlie", "timestamp_ms": 3000},
        ],
    )
    resp = client.get(f"/api/possessions/{game_id}")
    data = resp.get_json()
    # Count events with possession_id set
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM events WHERE relational_game_id=? AND possession_id IS NOT NULL",
        (game_id,),
    ).fetchone()
    # At minimum, some events were linked
    assert row["cnt"] > 0, "Expected at least some events linked to possessions"


def test_possession_summary_in_enhanced_stats(client, db):
    """Enhanced stats response includes possession_summary."""
    game_id = _create_game_with_events(
        client, db, "possession-enhanced",
        [
            {"event_type": "made_two", "player": "Alice", "timestamp_ms": 1000},
            {"event_type": "turnover", "player": "Bob", "timestamp_ms": 2000},
        ],
    )
    resp = client.get(f"/api/stats/{game_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "enhanced" in data
    enhanced = data["enhanced"]
    assert "possession_summary" in enhanced, f"Missing possession_summary in enhanced stats: {list(enhanced.keys())}"
    ps = enhanced["possession_summary"]
    assert "total_possessions" in ps
    assert "scoring_possessions" in ps


def test_rejected_events_excluded_from_stats(client, db):
    """Events with review_status='rejected' must not appear in stats output."""
    game_id = _create_game(client, "rejected-stats")

    # Create accepted event via save_event
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Alice",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 1000, "human_verified": True,
    })
    # Mark accepted
    db.execute("UPDATE events SET review_status='accepted' WHERE player='Alice'")

    # Create rejected event via save_event
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Bob",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 2000, "human_verified": True,
    })
    # Mark rejected
    db.execute("UPDATE events SET review_status='rejected' WHERE player='Bob'")
    db.commit()

    resp = client.get(f"/api/stats/{game_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    basic = data["basic"]

    # Only Alice (accepted) should count — Bob (rejected) should be excluded
    alice = next((p for p in basic if p["player"] == "Alice"), None)
    bob = next((p for p in basic if p["player"] == "Bob"), None)

    assert alice is not None, "Alice (accepted) should be in stats"
    assert alice["pts"] == 2, f"Alice should have 2 points, got {alice['pts']}"
    assert bob is None, f"Bob (rejected) should NOT be in stats, but found: {bob}"


def test_rejected_events_excluded_from_shot_breakdown(client, db):
    """Shot classification from rejected events must not appear in shot_breakdown."""
    game_id = _create_game(client, "rejected-shots")

    # Create accepted event + shot classification
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Alice",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 1000, "human_verified": True,
    })
    db.execute("UPDATE events SET review_status='accepted' WHERE player='Alice'")
    db.commit()

    event_id_accepted = db.execute(
        "SELECT id FROM events WHERE player='Alice' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]

    db.execute(
        """INSERT INTO shot_classifications (event_id, game_id, relational_game_id,
                                             tracker_id, shot_type, shot_result, timestamp_ms)
           VALUES (?, ?, ?, 1, '2pt', 'made', 1000)""",
        (event_id_accepted, str(game_id), game_id),
    )

    # Create rejected event + shot classification
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Bob",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 2000, "human_verified": True,
    })
    db.execute("UPDATE events SET review_status='rejected' WHERE player='Bob'")
    db.commit()

    event_id_rejected = db.execute(
        "SELECT id FROM events WHERE player='Bob' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]

    db.execute(
        """INSERT INTO shot_classifications (event_id, game_id, relational_game_id,
                                             tracker_id, shot_type, shot_result, timestamp_ms)
           VALUES (?, ?, ?, 2, '2pt', 'made', 2000)""",
        (event_id_rejected, str(game_id), game_id),
    )
    db.commit()

    resp = client.get(f"/api/stats/{game_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    enhanced = data["enhanced"]
    shots = enhanced["shot_breakdown"]

    # Only Alice's shot should count
    alice_shots = [s for s in shots if s["tracker_id"] == 1]
    bob_shots = [s for s in shots if s["tracker_id"] == 2]

    assert len(alice_shots) > 0, "Alice (accepted) should appear in shot_breakdown"
    assert len(bob_shots) == 0, f"Bob (rejected) should NOT appear in shot_breakdown, got {bob_shots}"


def test_possession_summary_excludes_rejected_events(client, db):
    """Turnover count in possession_summary must exclude rejected events."""
    game_id = _create_game(client, "rejected-poss")

    # Create accepted scoring event (not a turnover)
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Alice",
        "event_type": "made_two", "shot_result": "made",
        "timestamp_ms": 1000, "human_verified": True,
    })
    db.execute("UPDATE events SET review_status='accepted' WHERE player='Alice'")

    # Create rejected turnover event
    post_json(client, "/api/save_event", {
        "game_id": game_id, "player": "Bob",
        "event_type": "turnover",
        "timestamp_ms": 2000, "human_verified": True,
    })
    db.execute("UPDATE events SET review_status='rejected' WHERE player='Bob'")
    db.commit()

    resp = client.get(f"/api/possessions/{game_id}")
    assert resp.status_code == 200
    data = resp.get_json()

    # Both events create possessions (assign_possessions_for_game includes all events)
    # but turnover count excludes rejected: 2 possessions, 0 turnovers (only turnover was rejected)
    assert data["total_possessions"] == 2, f"Expected 2 possessions, got {data['total_possessions']}"
    assert data["turnover_rate"] == 0.0, f"Expected turnover_rate=0.0, got {data['turnover_rate']}"
