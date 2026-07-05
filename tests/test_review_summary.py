from helpers import build_review_workflow_summary


def _seed_review_summary_data(db):
    game_row = db.execute(
        "INSERT INTO games (source_type, source_key) VALUES (?, ?)",
        ("manual", "review-summary-game"),
    )
    relational_game_id = game_row.lastrowid
    db.execute(
        """INSERT INTO events
           (game_id, relational_game_id, event_type, timestamp_ms,
            human_verified, review_status, source_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("legacy", relational_game_id, "made_two", 1000, 1, "accepted", "manual"),
    )
    db.execute(
        """INSERT INTO events
           (game_id, relational_game_id, event_type, timestamp_ms,
            human_verified, review_status, source_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("legacy", relational_game_id, "turnover", 2000, 0, "pending", "ai"),
    )
    db.execute(
        """INSERT INTO events
           (game_id, relational_game_id, event_type, timestamp_ms,
            human_verified, review_status, source_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("legacy", relational_game_id, "missed_two", 3000, 0, "rejected", "ai"),
    )
    event_ids = [
        row["id"]
        for row in db.execute("SELECT id FROM events ORDER BY id ASC").fetchall()
    ]
    db.execute(
        """INSERT INTO review_items
           (entity_type, entity_id, game_id, relational_game_id, review_status, reason)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("event", event_ids[1], "legacy", relational_game_id, "pending", "ai event"),
    )
    db.commit()
    return relational_game_id


def test_build_review_workflow_summary_empty(db):
    summary = build_review_workflow_summary(db)
    assert summary["events_total"] == 0
    assert summary["events_accepted"] == 0
    assert summary["events_pending"] == 0
    assert summary["review_items_open"] == 0


def test_build_review_workflow_summary_counts(db):
    _seed_review_summary_data(db)
    summary = build_review_workflow_summary(db)
    assert summary["events_total"] == 3
    assert summary["events_accepted"] == 1
    assert summary["events_pending"] == 1
    assert summary["events_rejected"] == 1
    assert summary["review_items_open"] == 1


def test_status_page_shows_review_trust_summary(client, db):
    _seed_review_summary_data(db)
    r = client.get("/status")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Review &amp; Trust Summary" in html
    assert "Accepted" in html
    assert "Open Review Queue" in html


def test_preview_page_shows_review_counts(client, db):
    _seed_review_summary_data(db)
    r = client.get("/preview")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Accepted events" in html
    assert "Pending events" in html
    assert "Rejected events" in html
