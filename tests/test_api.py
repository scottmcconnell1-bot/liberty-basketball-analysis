"""
test_api.py – Integration tests for all Flask API endpoints.
"""
import json
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


# ── Events ────────────────────────────────────────────────────────────

def test_save_event(client):
    r = post_json(client, "/api/save_event", {
        "game_id": "game1",
        "event_type": "shot",
        "timestamp_ms": 5000,
        "player": "Player1",
        "shot_result": "made",
    })
    assert r.status_code == 200
    assert r.get_json()["status"] == "success"


def test_save_event_missing_timestamp(client):
    r = post_json(client, "/api/save_event", {"game_id": "game1", "event_type": "shot"})
    assert r.status_code == 400


def test_get_events(client):
    post_json(client, "/api/save_event", {"game_id": "gX", "event_type": "assist", "timestamp_ms": 1000})
    post_json(client, "/api/save_event", {"game_id": "gX", "event_type": "rebound", "timestamp_ms": 2000})
    r = client.get("/api/events/gX")
    events = r.get_json()
    assert len(events) == 2
    assert events[0]["timestamp_ms"] < events[1]["timestamp_ms"]


def test_update_event(client):
    r = post_json(client, "/api/save_event", {
        "game_id": "g1", "event_type": "shot", "timestamp_ms": 1000
    })
    eid = r.get_json()["id"]
    r2 = put_json(client, f"/api/events/{eid}", {"event_type": "block"})
    assert r2.status_code == 200
    assert r2.get_json()["event_type"] == "block"


def test_delete_event(client):
    r = post_json(client, "/api/save_event", {
        "game_id": "g1", "event_type": "steal", "timestamp_ms": 500
    })
    eid = r.get_json()["id"]
    r2 = client.delete(f"/api/events/{eid}")
    assert r2.status_code == 200
    r3 = client.get("/api/events/g1")
    assert not any(e["id"] == eid for e in r3.get_json())


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


def test_film_page(client):
    r = client.get("/film")
    assert r.status_code == 200


# ── Stats ─────────────────────────────────────────────────────────────

def test_stats_empty_game(client):
    r = client.get("/api/stats/no_such_game")
    assert r.status_code == 200
    assert r.get_json() == []


def test_stats_aggregation(client):
    for _ in range(3):
        post_json(client, "/api/save_event", {
            "game_id": "sg1", "player": "Alice",
            "event_type": "two_attempt", "shot_result": "made", "timestamp_ms": 1000
        })
    post_json(client, "/api/save_event", {
        "game_id": "sg1", "player": "Alice",
        "event_type": "assist", "timestamp_ms": 2000
    })
    r = client.get("/api/stats/sg1")
    stats = r.get_json()
    alice = next(s for s in stats if s["player"] == "Alice")
    assert alice["pts"] == 6
    assert alice["fgm"] == 3
    assert alice["ast"] == 1
