"""Shared event review actions used by the review API, pipeline, and UIs."""

import json


def _stringify_review_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _insert_review_provenance(db, event_id, action, user_id, details):
    db.execute(
        """INSERT INTO provenance_records
              (entity_type, entity_id, source_type, source_id, confidence,
               created_by_user_id, details_json)
           VALUES ('event', ?, 'review', ?, 1.0, ?, ?)""",
        (event_id, action, user_id, json.dumps(details or {}, sort_keys=True)),
    )


def _record_human_correction(
    db,
    row,
    correction_type,
    field_changed,
    original_value,
    corrected_value,
    notes=None,
):
    db.execute(
        """INSERT INTO human_corrections
              (game_id, relational_game_id, event_id, correction_type, original_value,
               corrected_value, field_changed, timestamp_ms, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row["game_id"],
            row["relational_game_id"],
            row["id"],
            correction_type,
            _stringify_review_value(original_value),
            _stringify_review_value(corrected_value),
            field_changed,
            row["timestamp_ms"],
            notes,
        ),
    )


def _sync_event_review_item(db, event_id, status, user_id=None, notes=None):
    row = db.execute(
        "SELECT id, game_id, relational_game_id FROM events WHERE id=?",
        (event_id,),
    ).fetchone()
    if not row:
        return
    db.execute(
        """INSERT OR IGNORE INTO review_items
              (entity_type, entity_id, game_id, relational_game_id, review_status, reason)
           VALUES ('event', ?, ?, ?, ?, 'Event needs coach review')""",
        (event_id, row["game_id"], row["relational_game_id"], status),
    )
    db.execute(
        """UPDATE review_items
              SET review_status=?,
                  reviewed_by_user_id=?,
                  reviewed_at=CASE
                      WHEN ? IN ('accepted', 'corrected', 'rejected') THEN CURRENT_TIMESTAMP
                      ELSE reviewed_at
                  END,
                  notes=COALESCE(?, notes),
                  updated_at=CURRENT_TIMESTAMP
            WHERE entity_type='event' AND entity_id=?""",
        (status, user_id, status, notes, event_id),
    )


def accept_event(
    db,
    event_id,
    *,
    user_id=None,
    notes=None,
    provenance_action="accept_event",
    commit=True,
):
    from helpers import refresh_game_stats

    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return None
    if row["review_status"] in ("accepted", "corrected"):
        return dict(row)

    db.execute(
        """UPDATE events
              SET review_status='accepted',
                  human_verified=1,
                  reviewed_by_user_id=?,
                  reviewed_at=CURRENT_TIMESTAMP,
                  review_notes=COALESCE(?, review_notes)
            WHERE id=?""",
        (user_id, notes, event_id),
    )
    _sync_event_review_item(db, event_id, "accepted", user_id, notes)
    _insert_review_provenance(
        db,
        event_id,
        provenance_action,
        user_id,
        {"previous_review_status": row["review_status"], "notes": notes},
    )
    if commit:
        db.commit()
        refresh_game_stats(db, row["game_id"])
    return dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())


def reject_event(db, event_id, *, user_id=None, notes=None, commit=True):
    from helpers import refresh_game_stats

    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return None
    if row["review_status"] == "rejected":
        return dict(row)

    db.execute(
        """UPDATE events
              SET review_status='rejected',
                  human_verified=0,
                  reviewed_by_user_id=?,
                  reviewed_at=CURRENT_TIMESTAMP,
                  review_notes=COALESCE(?, review_notes)
            WHERE id=?""",
        (user_id, notes, event_id),
    )
    _record_human_correction(
        db,
        row,
        "remove_event",
        "review_status",
        row["review_status"],
        "rejected",
        notes,
    )
    _sync_event_review_item(db, event_id, "rejected", user_id, notes)
    _insert_review_provenance(
        db,
        event_id,
        "reject_event",
        user_id,
        {"previous_review_status": row["review_status"], "notes": notes},
    )
    if commit:
        db.commit()
        refresh_game_stats(db, row["game_id"])
    return dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())


def auto_accept_high_confidence_events(
    db,
    game_id,
    *,
    relational_game_id=None,
    threshold=None,
):
    """Auto-accept pending AI events at or above the confidence threshold."""
    from settings_store import AI_DEFAULTS, load_all_settings

    if threshold is None:
        ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
        threshold = float(ai_settings.get("auto_accept_event_confidence", 0.50))

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 0.50

    if threshold <= 0:
        return 0

    if relational_game_id is not None:
        rows = db.execute(
            """
            SELECT id FROM events
             WHERE source_type = 'ai'
               AND review_status = 'pending'
               AND confidence IS NOT NULL
               AND confidence >= ?
               AND (
                     relational_game_id = ?
                     OR (relational_game_id IS NULL AND game_id = ?)
                   )
            """,
            (threshold, relational_game_id, game_id),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT id FROM events
             WHERE game_id = ?
               AND source_type = 'ai'
               AND review_status = 'pending'
               AND confidence IS NOT NULL
               AND confidence >= ?
            """,
            (game_id, threshold),
        ).fetchall()

    if not rows:
        return 0

    accepted = 0
    for row in rows:
        result = accept_event(
            db,
            row["id"],
            notes="Auto-accepted (high confidence)",
            provenance_action="auto_accept_event",
            commit=False,
        )
        if result:
            accepted += 1

    if accepted:
        from helpers import refresh_game_stats

        db.commit()
        # AI worker subprocess may have no Flask app context.
        try:
            refresh_game_stats(db, game_id)
        except RuntimeError as exc:
            if "application context" not in str(exc).lower():
                raise
    return accepted
