"""Aggregate jersey OCR reads into track/cluster → roster identity."""

from __future__ import annotations

from stats import _resolve_relational_game_id


def _game_scope(db, game_id):
    relational_game_id = _resolve_relational_game_id(db, game_id)
    return relational_game_id, str(game_id)


def _detection_scope_sql(relational_game_id, analysis_key, alias="d"):
    prefix = f"{alias}."
    if relational_game_id is not None:
        return (
            f"({prefix}relational_game_id = ? OR ({prefix}relational_game_id IS NULL AND {prefix}game_id = ?))",
            (relational_game_id, analysis_key),
        )
    return f"{prefix}game_id = ?", (analysis_key,)


def aggregate_cluster_jersey_votes(
    db,
    game_id,
    *,
    min_confidence: float = 0.55,
    min_samples: int = 3,
):
    """Majority vote jersey per court cluster from co-located OCR reads."""
    relational_game_id, analysis_key = _game_scope(db, game_id)
    scope_sql, scope_params = _detection_scope_sql(relational_game_id, analysis_key)

    rows = db.execute(
        f"""
        SELECT d.player_cluster AS slot_id,
               d.jersey_read AS jersey_number,
               COUNT(*) AS sample_count,
               AVG(d.jersey_confidence) AS avg_confidence
          FROM detections d
         WHERE {scope_sql}
           AND d.object_class = 'person'
           AND d.player_cluster IS NOT NULL
           AND d.player_cluster >= 0
           AND d.jersey_read IS NOT NULL
           AND d.jersey_confidence >= ?
         GROUP BY d.player_cluster, d.jersey_read
         ORDER BY d.player_cluster, sample_count DESC, avg_confidence DESC
        """,
        scope_params + (min_confidence,),
    ).fetchall()

    by_slot: dict[int, list] = {}
    for row in rows:
        by_slot.setdefault(int(row["slot_id"]), []).append(dict(row))

    suggestions = []
    for slot_id, votes in sorted(by_slot.items()):
        top = votes[0]
        if int(top["sample_count"]) < min_samples:
            continue
        suggestions.append({
            "tracker_id": slot_id,
            "identity_type": "cluster",
            "jersey_number": int(top["jersey_number"]),
            "sample_count": int(top["sample_count"]),
            "confidence": round(float(top["avg_confidence"]), 3),
            "alternates": [
                {
                    "jersey_number": int(v["jersey_number"]),
                    "sample_count": int(v["sample_count"]),
                    "confidence": round(float(v["avg_confidence"]), 3),
                }
                for v in votes[1:3]
            ],
        })
    return suggestions


def aggregate_track_jersey_votes(
    db,
    game_id,
    *,
    min_confidence: float = 0.55,
    min_samples: int = 3,
):
    """Majority vote jersey per ByteTrack tracker_id."""
    relational_game_id, analysis_key = _game_scope(db, game_id)
    scope_sql, scope_params = _detection_scope_sql(relational_game_id, analysis_key)

    rows = db.execute(
        f"""
        SELECT d.tracker_id AS slot_id,
               d.jersey_read AS jersey_number,
               COUNT(*) AS sample_count,
               AVG(d.jersey_confidence) AS avg_confidence
          FROM detections d
         WHERE {scope_sql}
           AND d.object_class = 'person'
           AND d.tracker_id IS NOT NULL
           AND d.jersey_read IS NOT NULL
           AND d.jersey_confidence >= ?
         GROUP BY d.tracker_id, d.jersey_read
         ORDER BY d.tracker_id, sample_count DESC, avg_confidence DESC
        """,
        scope_params + (min_confidence,),
    ).fetchall()

    by_track: dict[int, list] = {}
    for row in rows:
        by_track.setdefault(int(row["slot_id"]), []).append(dict(row))

    suggestions = []
    for track_id, votes in sorted(by_track.items()):
        top = votes[0]
        if int(top["sample_count"]) < min_samples:
            continue
        suggestions.append({
            "tracker_id": track_id,
            "identity_type": "track",
            "jersey_number": int(top["jersey_number"]),
            "sample_count": int(top["sample_count"]),
            "confidence": round(float(top["avg_confidence"]), 3),
            "alternates": [
                {
                    "jersey_number": int(v["jersey_number"]),
                    "sample_count": int(v["sample_count"]),
                    "confidence": round(float(v["avg_confidence"]), 3),
                }
                for v in votes[1:3]
            ],
        })
    return suggestions


def persist_identity_labels(db, game_id, suggestions, source="ocr_votes"):
    relational_game_id, analysis_key = _game_scope(db, game_id)
    for item in suggestions:
        db.execute(
            """
            INSERT INTO track_identity_labels
                (game_id, relational_game_id, tracker_id, identity_type,
                 jersey_number, confidence, sample_count, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, identity_type, tracker_id) DO UPDATE SET
                jersey_number = excluded.jersey_number,
                confidence = excluded.confidence,
                sample_count = excluded.sample_count,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                analysis_key,
                relational_game_id,
                int(item["tracker_id"]),
                item.get("identity_type") or "cluster",
                item.get("jersey_number"),
                item.get("confidence"),
                item.get("sample_count"),
                source,
            ),
        )
    db.commit()


def get_identity_labels(db, game_id):
    relational_game_id, analysis_key = _game_scope(db, game_id)
    if relational_game_id is not None:
        rows = db.execute(
            """
            SELECT * FROM track_identity_labels
             WHERE relational_game_id = ? OR game_id = ?
             ORDER BY identity_type, tracker_id
            """,
            (relational_game_id, analysis_key),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM track_identity_labels
             WHERE game_id = ?
             ORDER BY identity_type, tracker_id
            """,
            (analysis_key,),
        ).fetchall()
    return [dict(row) for row in rows]


def build_identity_report(db, game_id, ai_settings=None):
    ai_settings = ai_settings or {}
    min_conf = float(ai_settings.get("jersey_ocr_min_confidence", 0.55))
    min_samples = int(ai_settings.get("identity_auto_apply_min_samples", 8))

    cluster_suggestions = aggregate_cluster_jersey_votes(
        db, game_id, min_confidence=min_conf, min_samples=max(3, min_samples // 2)
    )
    track_suggestions = aggregate_track_jersey_votes(
        db, game_id, min_confidence=min_conf, min_samples=max(3, min_samples // 2)
    )
    persist_identity_labels(db, game_id, cluster_suggestions, source="ocr_cluster_votes")
    persist_identity_labels(db, game_id, track_suggestions, source="ocr_track_votes")

    ocr_read_count = db.execute(
        """
        SELECT COUNT(*) AS c FROM detections
         WHERE game_id = ? AND jersey_read IS NOT NULL
        """,
        (str(game_id),),
    ).fetchone()["c"]

    return {
        "ocr_read_count": ocr_read_count,
        "cluster_suggestions": cluster_suggestions,
        "track_suggestions": track_suggestions,
        "applied_labels": get_identity_labels(db, game_id),
    }


def auto_apply_cluster_jerseys(db, game_id, ai_settings=None):
    """Auto-map court clusters to jerseys when OCR confidence is high enough."""
    from court_slot_mapping import save_court_slot_mappings, apply_court_slot_mappings

    ai_settings = ai_settings or {}
    min_conf = float(ai_settings.get("identity_auto_apply_min_confidence", 0.70))
    min_samples = int(ai_settings.get("identity_auto_apply_min_samples", 8))

    suggestions = aggregate_cluster_jersey_votes(
        db,
        game_id,
        min_confidence=float(ai_settings.get("jersey_ocr_min_confidence", 0.55)),
        min_samples=min_samples,
    )
    mappings = []
    for item in suggestions:
        if item["confidence"] < min_conf or item["sample_count"] < min_samples:
            continue
        mappings.append({
            "tracker_id": item["tracker_id"],
            "jersey_number": item["jersey_number"],
        })

    if not mappings:
        return {"applied": 0, "mappings": [], "events_updated": 0}

    save_court_slot_mappings(db, game_id, mappings, apply_to_events=False)
    result = apply_court_slot_mappings(db, game_id)
    return {
        "applied": len(mappings),
        "mappings": mappings,
        "events_updated": result.get("events_updated", 0),
    }
