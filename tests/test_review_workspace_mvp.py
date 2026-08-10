"""Review workspace MVP: accept/correct/reject → ledger, auto-accept off."""

from review_actions import auto_accept_high_confidence_events
from settings_store import AI_DEFAULTS, load_all_settings


def post_json(client, url, payload):
    return client.post(url, json=payload)


def _create_game(client, source_key="review-workspace-game"):
    r = post_json(client, "/api/games", {
        "source_type": "manual",
        "source_key": source_key,
    })
    assert r.status_code == 201
    return r.get_json()["id"]


def test_auto_accept_default_is_zero():
    assert float(AI_DEFAULTS["auto_accept_event_confidence"]) == 0.0


def test_auto_accept_load_forces_zero_even_if_stored(app, db):
    db.execute(
        """INSERT INTO app_settings (key, value)
           VALUES ('ai.auto_accept_event_confidence', '0.85')
           ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
    )
    db.commit()
    with app.app_context():
        loaded = load_all_settings({}, {}, AI_DEFAULTS, db=db)
        assert loaded["ai"]["auto_accept_event_confidence"] == 0.0


def test_auto_accept_noop_uses_settings_threshold_zero(app):
    game_id = "auto-accept-settings-off"
    with app.app_context():
        from helpers import get_db

        db = get_db()
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status, human_verified)
               VALUES (?, 'made_two', 1000, 'ai', 0.99, 'pending', 0)""",
            (game_id,),
        )
        db.commit()
        accepted = auto_accept_high_confidence_events(db, game_id)
        assert accepted == 0
        row = db.execute(
            "SELECT review_status FROM events WHERE game_id=?",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "pending"


def test_settings_hides_auto_accept_control(client, monkeypatch):
    monkeypatch.setattr("helpers.list_ollama_models", lambda: [])
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"ai-auto-accept-disabled-notice" in r.data
    assert b'id="ai_auto_accept_event_confidence"' not in r.data
    assert b"Disabled for the review workspace MVP" in r.data


def test_settings_save_forces_auto_accept_zero(client, db, monkeypatch):
    monkeypatch.setattr("helpers.list_ollama_models", lambda: [])
    r = client.post(
        "/settings",
        data={
            "feature_ENABLE_MANUAL_TAG_MVP": "on",
            "feature_ENABLE_AUTO_STATS_M1": "on",
            "ai_detector_model": "yolov8n.pt",
            "ai_ball_detector_model": "models/ball_detector.pt",
            "ai_ball_class_id": "0",
            "ai_ball_confidence": "0.25",
            "ai_person_confidence": "0.5",
            "ai_inference_device": "auto",
            "ai_event_generator_mode": "expanded",
            "ai_frame_stride": "1",
            "ai_tracker_max_distance": "80",
            "ai_tracker_max_frame_gap": "5",
            "ai_llm_provider": "none",
            "ai_llm_model": "",
            "ai_auto_accept_event_confidence": "0.90",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    stored = {
        row["key"]: row["value"]
        for row in db.execute("SELECT key, value FROM app_settings").fetchall()
    }
    assert float(stored["ai.auto_accept_event_confidence"]) == 0.0


def test_review_ledger_filter_accept_correct_reject(client, db):
    game_id = _create_game(client, "ledger-filter-game")

    pending = post_json(
        client,
        "/api/save_event",
        {
            "game_id": game_id,
            "event_type": "shot",
            "player": "AI Player",
            "timestamp_ms": 1000,
            "human_verified": False,
            "source_type": "ai",
            "confidence": 0.77,
        },
    )
    assert pending.status_code == 200
    eid = pending.get_json()["id"]

    listed = client.get(f"/api/review/events?game_id={game_id}&review_status=pending")
    assert listed.status_code == 200
    assert any(row["id"] == eid for row in listed.get_json())

    ledger_before = client.get(f"/api/review/events?game_id={game_id}&review_status=ledger")
    assert ledger_before.status_code == 200
    assert all(row["id"] != eid for row in ledger_before.get_json())

    accepted = post_json(client, f"/api/review/events/{eid}/accept", {"notes": "ok"})
    assert accepted.status_code == 200
    assert accepted.get_json()["review_status"] == "accepted"
    assert accepted.get_json()["human_verified"] == 1

    ledger_after_accept = client.get(
        f"/api/review/events?game_id={game_id}&review_status=ledger"
    ).get_json()
    assert any(row["id"] == eid for row in ledger_after_accept)

    pending2 = post_json(
        client,
        "/api/save_event",
        {
            "game_id": game_id,
            "event_type": "foul",
            "player": "Wrong",
            "timestamp_ms": 2000,
            "human_verified": False,
            "source_type": "ai",
        },
    )
    eid2 = pending2.get_json()["id"]
    corrected = post_json(
        client,
        f"/api/review/events/{eid2}/correct",
        {
            "player": "Right",
            "event_type": "steal",
            "notes": "coach fix",
        },
    )
    assert corrected.status_code == 200
    assert corrected.get_json()["review_status"] == "corrected"
    assert corrected.get_json()["human_verified"] == 1
    fields = {
        row["field_changed"]
        for row in db.execute(
            "SELECT field_changed FROM human_corrections WHERE event_id=?",
            (eid2,),
        ).fetchall()
    }
    assert {"player", "event_type"} <= fields
    ledger = client.get(
        f"/api/review/events?game_id={game_id}&review_status=ledger"
    ).get_json()
    assert {row["id"] for row in ledger} >= {eid, eid2}

    pending3 = post_json(
        client,
        "/api/save_event",
        {
            "game_id": game_id,
            "event_type": "turnover",
            "timestamp_ms": 3000,
            "human_verified": False,
            "source_type": "ai",
        },
    )
    eid3 = pending3.get_json()["id"]
    rejected = post_json(
        client, f"/api/review/events/{eid3}/reject", {"notes": "junk"}
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["review_status"] == "rejected"
    ledger_final = {
        row["id"]
        for row in client.get(
            f"/api/review/events?game_id={game_id}&review_status=ledger"
        ).get_json()
    }
    assert eid3 not in ledger_final
    assert {eid, eid2} <= ledger_final


def test_film_review_workspace_route_and_ui(client):
    r = client.get("/film/demo.mp4/review?game_id=demo_game", follow_redirects=True)
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "Review workspace" in html
    assert 'id="aiCorrectDialog"' in html
    assert 'data-ai-filter="pending"' in html
    assert 'data-ai-filter="ledger"' in html
    assert "FILM_TOOL_REVIEW_MODE = true" in html
    assert 'id="aiCorrectAddPlayerBtn"' in html


def test_review_players_add_delete_for_tagging(client):
    created = post_json(
        client, "/api/players", {"name": "Review Tag Player", "jersey_number": 7}
    )
    assert created.status_code == 201
    player_id = created.get_json()["id"]
    listed = client.get("/api/players")
    assert listed.status_code == 200
    assert any(row["id"] == player_id for row in listed.get_json())
    deleted = client.delete(f"/api/players/{player_id}")
    assert deleted.status_code == 200
    remaining = {row["id"] for row in client.get("/api/players").get_json()}
    assert player_id not in remaining
