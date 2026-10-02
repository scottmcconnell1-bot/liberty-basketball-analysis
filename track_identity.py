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
    min_samples = int(ai_settings.get("identity_auto_apply_min_samples", 4))
    relational_game_id, analysis_key = _game_scope(db, game_id)
    scope_sql, scope_params = _detection_scope_sql(relational_game_id, analysis_key)

    cluster_suggestions = aggregate_cluster_jersey_votes(
        db, game_id, min_confidence=min_conf, min_samples=max(3, min_samples // 2)
    )
    track_suggestions = aggregate_track_jersey_votes(
        db, game_id, min_confidence=min_conf, min_samples=max(3, min_samples // 2)
    )
    persist_identity_labels(db, game_id, cluster_suggestions, source="ocr_cluster_votes")
    persist_identity_labels(db, game_id, track_suggestions, source="ocr_track_votes")

    ocr_read_count = db.execute(
        f"""
        SELECT COUNT(*) AS c FROM detections d
         WHERE {scope_sql}
           AND d.jersey_read IS NOT NULL
        """,
        scope_params,
    ).fetchone()["c"]

    return {
        "ocr_read_count": ocr_read_count,
        "cluster_suggestions": cluster_suggestions,
        "track_suggestions": track_suggestions,
        "applied_labels": get_identity_labels(db, game_id),
    }


def _roster_jersey_index(db, game_id):
    from analysis_helpers import get_analysis_roster_players

    payload = get_analysis_roster_players(db, game_id)
    by_jersey: dict[int, list] = {}
    for player in payload["players"]:
        jersey = player.get("jersey_number")
        if jersey in (None, ""):
            continue
        try:
            jersey_int = int(jersey)
        except (TypeError, ValueError):
            continue
        by_jersey.setdefault(jersey_int, []).append(player)
    return by_jersey, payload["source"]


def _shade_roster_side(shade_side: str | None, liberty_is_home: bool | None) -> str | None:
    """Map a home/away jersey shade onto the scorebook's liberty/opponent side."""
    if shade_side not in ("home", "away") or liberty_is_home is None:
        return None
    if shade_side == "home":
        return "liberty" if liberty_is_home else "opponent"
    return "opponent" if liberty_is_home else "liberty"


def _pick_roster_player(candidates, shade_side, liberty_is_home):
    """One roster person for this jersey. A shared number needs the jersey shade."""
    people = [player for player in (candidates or []) if player]
    if not people:
        return None
    if len(people) == 1:
        person = people[0]
        wanted = _shade_roster_side(shade_side, liberty_is_home)
        person_side = person.get("side")
        if wanted and person_side and person_side != wanted:
            return None
        return person
    wanted = _shade_roster_side(shade_side, liberty_is_home)
    if not wanted:
        return None
    matched = [player for player in people if player.get("side") == wanted]
    if len(matched) == 1:
        return matched[0]
    return None


def _events_use_raw_cluster_ids(db, game_id):
    relational_game_id, analysis_key = _game_scope(db, game_id)
    if relational_game_id is not None:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
              FROM events
             WHERE (relational_game_id = ? OR game_id = ?)
               AND source_type = 'ai'
               AND player GLOB '[0-9]'
            """,
            (relational_game_id, analysis_key),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
              FROM events
             WHERE game_id = ?
               AND source_type = 'ai'
               AND player GLOB '[0-9]'
            """,
            (analysis_key,),
        ).fetchone()
    return int(row["c"] or 0)


def _build_auto_apply_mappings(
    suggestions,
    *,
    roster_by_jersey,
    use_roster_whitelist,
    min_conf,
    min_samples,
    shade_by_tracker=None,
    liberty_is_home=None,
):
    mappings = []
    shades = shade_by_tracker or {}
    roster_loaded = bool(roster_by_jersey)
    for item in suggestions:
        if item["confidence"] < min_conf or item["sample_count"] < min_samples:
            continue
        jersey = int(item["jersey_number"])
        candidates = (roster_by_jersey or {}).get(jersey) or []
        if use_roster_whitelist and not candidates:
            continue
        shade_side = (shades.get(int(item["tracker_id"])) or {}).get("side")
        roster_player = _pick_roster_player(candidates, shade_side, liberty_is_home)
        if roster_loaded and not roster_player:
            continue
        name = None
        if roster_player:
            name = roster_player.get("name") or roster_player.get("label")
        mappings.append({
            "tracker_id": item["tracker_id"],
            "jersey_number": jersey,
            "player_name": name,
            "lock_name": True,
        })
    return mappings


def auto_apply_cluster_jerseys(db, game_id, ai_settings=None):
    """Auto-map court clusters to jerseys when OCR confidence is high enough."""
    from court_slot_mapping import (
        apply_court_slot_mappings,
        save_court_slot_mappings,
        stamp_scorebook_links,
    )

    ai_settings = ai_settings or {}
    min_conf = float(ai_settings.get("identity_auto_apply_min_confidence", 0.60))
    min_samples = int(ai_settings.get("identity_auto_apply_min_samples", 4))

    suggestions = aggregate_cluster_jersey_votes(
        db,
        game_id,
        min_confidence=float(ai_settings.get("jersey_ocr_min_confidence", 0.55)),
        min_samples=min_samples,
    )
    roster_by_jersey, roster_source = _roster_jersey_index(db, game_id)
    use_roster_whitelist = roster_source == "film_roster" and bool(roster_by_jersey)
    try:
        from jersey_shade import load_cached_shades
        shades = load_cached_shades(str(game_id))
    except Exception:
        shades = {}
    try:
        from program_mode import _liberty_is_home, load_scorebook
        liberty_is_home = _liberty_is_home(load_scorebook(str(game_id)))
    except Exception:
        liberty_is_home = None

    mapping_kwargs = {
        "roster_by_jersey": roster_by_jersey,
        "min_conf": min_conf,
        "min_samples": min_samples,
        "shade_by_tracker": shades,
        "liberty_is_home": liberty_is_home,
    }
    mappings = _build_auto_apply_mappings(
        suggestions,
        use_roster_whitelist=use_roster_whitelist,
        **mapping_kwargs,
    )
    if not mappings and use_roster_whitelist and suggestions:
        mappings = _build_auto_apply_mappings(
            suggestions,
            use_roster_whitelist=False,
            **mapping_kwargs,
        )

    if not mappings:
        linked = stamp_scorebook_links(db, game_id)
        db.commit()
        return {"applied": 0, "mappings": [], "events_updated": linked}

    save_court_slot_mappings(db, game_id, mappings, apply_to_events=False)
    result = apply_court_slot_mappings(
        db,
        game_id,
        tracker_ids=[item["tracker_id"] for item in mappings],
        mark_reviewed=False,
    )
    linked = stamp_scorebook_links(db, game_id)
    db.commit()
    return {
        "applied": len(mappings),
        "mappings": mappings,
        "events_updated": result.get("events_updated", 0) + linked,
    }


def run_identity_postprocess(db, game_id, ai_settings=None):
    """Build OCR identity report and auto-apply jersey mappings when enabled."""
    ai_settings = ai_settings or {}
    report = build_identity_report(db, game_id, ai_settings)
    applied = {"applied": 0, "mappings": [], "events_updated": 0}
    if ai_settings.get("auto_apply_jersey_mapping", True):
        applied = auto_apply_cluster_jerseys(db, game_id, ai_settings)
    return {
        **report,
        "auto_apply": applied,
        "slots_mapped": applied.get("applied", 0),
        "events_updated": applied.get("events_updated", 0),
    }


def _ocr_backed_trackers(db, game_id) -> set[tuple[int, int]]:
    """Cluster/tracker ids whose jersey was read on this analysis key."""
    try:
        rows = db.execute(
            """SELECT tracker_id, jersey_number
                 FROM track_identity_labels
                WHERE game_id = ?
                  AND jersey_number IS NOT NULL
                  AND sample_count >= 2
                  AND confidence >= 0.55
                  AND source LIKE 'ocr%'""",
            (game_id,),
        ).fetchall()
    except Exception:
        return set()
    backed = set()
    for row in rows:
        tracker = row["tracker_id"] if hasattr(row, "keys") else row[0]
        jersey = row["jersey_number"] if hasattr(row, "keys") else row[1]
        backed.add((int(tracker), int(jersey)))
    return backed


def ensure_identity_applied(db, game_id, ai_settings=None):
    """Auto-apply jersey mappings when AI events still use raw cluster ids."""
    ai_settings = ai_settings or {}
    if not ai_settings.get("auto_apply_jersey_mapping", True):
        return {"skipped": True, "reason": "auto_apply_disabled"}

    raw_cluster_events = _events_use_raw_cluster_ids(db, game_id)
    if raw_cluster_events == 0:
        return {"skipped": True, "reason": "already_mapped", "raw_cluster_events": 0}

    from court_slot_mapping import apply_court_slot_mappings, get_court_slots

    slots = get_court_slots(db, game_id)
    ocr_backed = _ocr_backed_trackers(db, game_id)
    mapped = [
        slot for slot in slots
        if slot.get("is_mapped")
        and slot.get("jersey_number") is not None
        and (int(slot["tracker_id"]), int(slot["jersey_number"])) in ocr_backed
    ]
    if mapped:
        result = apply_court_slot_mappings(
            db,
            game_id,
            tracker_ids=[slot["tracker_id"] for slot in mapped],
            mark_reviewed=False,
        )
        if _events_use_raw_cluster_ids(db, game_id) == 0:
            return {
                "skipped": False,
                "reason": "applied_saved_slots",
                "raw_cluster_events": raw_cluster_events,
                "events_updated": result.get("events_updated", 0),
                "slots_mapped": result.get("slots_mapped", 0),
                "applied": result.get("slots_mapped", 0),
            }

    report = build_identity_report(db, game_id, ai_settings)
    if not report.get("cluster_suggestions"):
        return {
            "skipped": True,
            "reason": "no_cluster_suggestions",
            "raw_cluster_events": raw_cluster_events,
            "ocr_read_count": report.get("ocr_read_count", 0),
        }

    applied = auto_apply_cluster_jerseys(db, game_id, ai_settings)
    return {
        "skipped": False,
        "raw_cluster_events": raw_cluster_events,
        "ocr_read_count": report.get("ocr_read_count", 0),
        "cluster_suggestions": len(report.get("cluster_suggestions") or []),
        **applied,
    }
