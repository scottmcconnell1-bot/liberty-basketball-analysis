"""Stage 10A read-only assistant API tests."""

import json


from assistant_query import answer_question


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


def _create_game(client, source_key="assistant-game"):
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


def test_assistant_query_requires_question_and_game_id(client):
    r = post_json(client, "/api/assistant/query", {"game_id": 1})
    assert r.status_code == 400
    assert "question" in r.get_json()["error"]

    r = post_json(client, "/api/assistant/query", {"question": "How many points?"})
    assert r.status_code == 400
    assert "game_id" in r.get_json()["error"]


def test_assistant_query_player_points_from_trusted_event(client, db):
    game_id = _create_game(client, "assistant-points")
    _save_and_accept(client, game_id, "Alice", "made_three")

    r = post_json(client, "/api/assistant/query", {
        "question": "How many points did Alice score?",
        "game_id": game_id,
        "player": "Alice",
    })
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["confidence"] == "proven"
    assert payload["review_scope"] == "accepted_and_corrected_only"
    assert "3 points" in payload["answer"]
    assert payload["citations"][0]["type"] == "stat"
    assert payload["citations"][0]["pts"] == 3


def test_assistant_query_excludes_pending_events(client, db):
    game_id = _create_game(client, "assistant-pending")
    post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": "Pending Pat",
        "event_type": "made_two",
        "shot_result": "made",
        "timestamp_ms": 1000,
        "human_verified": False,
    })
    _save_and_accept(client, game_id, "Trusted Tina", "made_two", timestamp_ms=2000)

    r = post_json(client, "/api/assistant/query", {
        "question": "Who scored the most points?",
        "game_id": game_id,
    })
    payload = r.get_json()
    assert payload["confidence"] == "proven"
    assert "Trusted Tina" in payload["answer"]
    assert "Pending Pat" not in payload["answer"]
    assert payload["citations"][0]["pts"] == 2


def test_assistant_query_turnovers(client, db):
    game_id = _create_game(client, "assistant-turnovers")
    _save_and_accept(client, game_id, "Bob", "turnover", shot_result="", timestamp_ms=1500)

    r = post_json(client, "/api/assistant/query", {
        "question": "How many turnovers did Bob have?",
        "game_id": game_id,
        "player": "Bob",
    })
    payload = r.get_json()
    assert payload["intent"] == "turnovers"
    assert payload["confidence"] == "proven"
    assert "1 reviewed turnover" in payload["answer"]
    assert payload["citations"][0]["type"] == "event"
    assert payload["citations"][0]["event_type"] == "turnover"


def test_assistant_query_team_stats(client, db):
    game_id = _create_game(client, "assistant-team")
    _save_and_accept(client, game_id, "Alice", "made_two")
    _save_and_accept(client, game_id, "Bob", "made_three", timestamp_ms=2000)

    r = post_json(client, "/api/assistant/query", {
        "question": "What are our team stats?",
        "game_id": game_id,
    })
    payload = r.get_json()
    assert payload["intent"] == "team_stats"
    assert payload["confidence"] == "proven"
    assert "5 points" in payload["answer"]
    assert payload["citations"][0]["type"] == "team_stat"
    assert payload["citations"][0]["points"] == 5


def test_assistant_query_clips_with_trusted_event(client, db):
    from player_development import create_canonical_clip

    game_id = _create_game(client, "assistant-clips")
    event_id = _save_and_accept(client, game_id, "Alice", "turnover", shot_result="", timestamp_ms=3000)
    create_canonical_clip(
        db,
        "Alice turnover clip",
        2800,
        3200,
        game_id=game_id,
        event_id=event_id,
        clip_type="turnover",
    )
    db.commit()

    r = post_json(client, "/api/assistant/query", {
        "question": "Show me film clips from this game",
        "game_id": game_id,
    })
    payload = r.get_json()
    assert payload["intent"] == "clips"
    assert payload["confidence"] == "proven"
    assert len(payload["citations"]) >= 1
    assert payload["citations"][0]["type"] == "clip"
    assert payload["citations"][0]["title"] == "Alice turnover clip"


def test_answer_question_unit_unknown_game(db):
    payload = answer_question(db, "How many points?", game_id=999999)
    assert payload["confidence"] == "unknown"
