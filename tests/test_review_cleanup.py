"""Review workflow cleanup: auto-accept and in-context review support."""

from review_actions import accept_event, auto_accept_high_confidence_events


def test_auto_accept_high_confidence_events(client, app):
    game_id = "auto-accept-test"
    with app.app_context():
        from helpers import get_db

        db = get_db()
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status, human_verified)
               VALUES (?, 'made_three', 1000, 'ai', 0.60, 'pending', 0)""",
            (game_id,),
        )
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status, human_verified)
               VALUES (?, 'foul', 2000, 'ai', 0.18, 'pending', 0)""",
            (game_id,),
        )
        db.commit()

        accepted = auto_accept_high_confidence_events(db, game_id, threshold=0.50)
        assert accepted == 1

        rows = db.execute(
            "SELECT event_type, review_status FROM events WHERE game_id = ? ORDER BY timestamp_ms",
            (game_id,),
        ).fetchall()
        assert rows[0]["review_status"] == "accepted"
        assert rows[1]["review_status"] == "pending"


def test_auto_accept_disabled_when_threshold_zero(client, app):
    game_id = "auto-accept-off"
    with app.app_context():
        from helpers import get_db

        db = get_db()
        db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status, human_verified)
               VALUES (?, 'made_two', 1000, 'ai', 0.60, 'pending', 0)""",
            (game_id,),
        )
        db.commit()

        accepted = auto_accept_high_confidence_events(db, game_id, threshold=0)
        assert accepted == 0
        row = db.execute(
            "SELECT review_status FROM events WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "pending"


def test_auto_accept_default_is_zero_and_does_not_promote(client, app):
    """Foundation: default confidence is 0; unset settings must not promote drafts."""
    from settings_store import AI_DEFAULTS

    assert float(AI_DEFAULTS["auto_accept_event_confidence"]) == 0.0

    game_id = "auto-accept-default-off"
    with app.app_context():
        from helpers import get_db

        db = get_db()
        db.execute(
            "DELETE FROM app_settings WHERE key = ?",
            ("ai.auto_accept_event_confidence",),
        )
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
            "SELECT review_status FROM events WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "pending"


def test_accept_event_helper_marks_trusted(client, app):
    with app.app_context():
        from helpers import get_db

        db = get_db()
        cur = db.execute(
            """INSERT INTO events
               (game_id, event_type, timestamp_ms, source_type, confidence, review_status, human_verified)
               VALUES ('helper-accept', 'rebound', 1500, 'ai', 0.42, 'pending', 0)"""
        )
        event_id = cur.lastrowid
        db.commit()

        updated = accept_event(db, event_id, notes="test accept", commit=True)
        assert updated["review_status"] == "accepted"
        assert updated["human_verified"] == 1
