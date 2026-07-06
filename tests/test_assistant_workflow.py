"""Navigation active-state and Stage 10B workflow tests."""

import json
import re

import pytest

from assistant_workflow import build_workflow_payload, list_workflow_clips, list_workflow_players


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _create_game(client, source_key="workflow-game"):
    r = post_json(client, "/api/games", {
        "source_type": "manual",
        "source_key": source_key,
    })
    assert r.status_code == 201
    return r.get_json()["id"]


def _save_and_accept(client, game_id, player, event_type, shot_result="made", timestamp_ms=1000):
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": player,
        "event_type": event_type,
        "shot_result": shot_result,
        "timestamp_ms": timestamp_ms,
        "human_verified": False,
        "source_type": "ai",
    })
    event_id = r.get_json()["id"]
    post_json(client, f"/api/review/events/{event_id}/accept", {"notes": "ok"})
    return event_id


@pytest.mark.parametrize(
    "path,pattern",
    [
        ("/", r'href="/"[^>]*class="active"[^>]*>Dashboard'),
        ("/preview", r'href="/preview"[^>]*class="active"'),
        ("/schedule", r'href="/schedule"[^>]*class="active"'),
        ("/games", r'href="/games"[^>]*class="active"'),
        ("/film", r'href="/film"[^>]*class="active"'),
        ("/review", r'href="/review"[^>]*class="active"'),
        ("/status", r'href="/status"[^>]*class="active"'),
        ("/assistant", r'href="/assistant"[^>]*class="active"'),
    ],
)
def test_nav_active_highlights_current_page(client, path, pattern):
    response = client.get(path)
    assert response.status_code == 200
    html = response.data.decode()
    assert re.search(pattern, html), f"Expected active nav for {path}"


def test_assistant_workflow_games_endpoint(client, db):
    game_id = _create_game(client, "workflow-games-api")
    _save_and_accept(client, game_id, "Alice", "made_two")

    response = client.get("/api/assistant/workflow/games")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["step"] == "games"
    game_row = next(row for row in payload["games"] if row["id"] == game_id)
    assert game_row["trusted_event_count"] >= 1


def test_assistant_workflow_players_endpoint(client, db):
    game_id = _create_game(client, "workflow-players-api")
    _save_and_accept(client, game_id, "Alice", "made_three")

    response = client.get(f"/api/assistant/workflow/games/{game_id}/players")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["step"] == "players"
    alice = next(row for row in payload["players"] if row["player"] == "Alice")
    assert alice["pts"] == 3


def test_assistant_workflow_clips_endpoint(client, db):
    from player_development import create_canonical_clip

    game_id = _create_game(client, "workflow-clips-api")
    event_id = _save_and_accept(
        client, game_id, "Bob", "turnover", shot_result="", timestamp_ms=4000
    )
    create_canonical_clip(
        db,
        "Bob turnover",
        3900,
        4200,
        game_id=game_id,
        event_id=event_id,
        clip_type="turnover",
    )
    db.commit()

    response = client.get(
        f"/api/assistant/workflow/games/{game_id}/clips?player=Bob"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["step"] == "clips"
    assert len(payload["clips"]) == 1
    assert payload["clips"][0]["title"] == "Bob turnover"


def test_assistant_workflow_page_loads(client):
    response = client.get("/assistant")
    assert response.status_code == 200
    assert b"Assistant Workflow" in response.data
    assert b"/api/assistant/workflow/games" in response.data


def test_build_workflow_payload_unknown_game(db):
    payload = build_workflow_payload("players", db, game_id=999999)
    assert payload["error"]
