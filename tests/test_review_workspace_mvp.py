"""Review workspace MVP: accept/correct/reject → ledger; auto-accept enabled."""

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


def test_auto_accept_default_is_enabled():
    assert float(AI_DEFAULTS["auto_accept_event_confidence"]) == 0.85


def test_auto_accept_load_respects_stored_threshold(app, db):
    db.execute(
        """INSERT INTO app_settings (key, value)
           VALUES ('ai.auto_accept_event_confidence', '0.90')
           ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
    )
    db.commit()
    with app.app_context():
        loaded = load_all_settings({}, {}, AI_DEFAULTS, db=db)
        assert loaded["ai"]["auto_accept_event_confidence"] == 0.90


def test_auto_accept_promotes_high_confidence_events(app):
    game_id = "auto-accept-settings-on"
    with app.app_context():
        from helpers import get_db

        db = get_db()
        db.execute(
            """INSERT INTO app_settings (key, value)
               VALUES ('ai.auto_accept_event_confidence', '0.85')
               ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
        )
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status, human_verified)
               VALUES (?, 'made_two', 1000, 'ai', 0.99, 'pending', 0)""",
            (game_id,),
        )
        db.commit()
        accepted = auto_accept_high_confidence_events(db, game_id)
        assert accepted == 1
        row = db.execute(
            "SELECT review_status FROM events WHERE game_id=?",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "accepted"


def test_settings_shows_auto_accept_control(client, monkeypatch):
    monkeypatch.setattr("helpers.list_ollama_models", lambda: [])
    r = client.get("/settings")
    assert r.status_code == 200
    assert b'id="ai_auto_accept_event_confidence"' in r.data
    assert b"ai-auto-accept-disabled-notice" not in r.data


def test_settings_save_persists_auto_accept_threshold(client, db, monkeypatch):
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
    assert float(stored["ai.auto_accept_event_confidence"]) == 0.90
