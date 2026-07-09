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


def _broad_detection_scope(db, game_id, alias="d"):
    from helpers import detection_scope_for_analysis

    return detection_scope_for_analysis(db, game_id, alias=alias)


def jersey_ocr_engine_status() -> dict:
    """Report whether OCR backends are available in this Python environment."""
    from jersey_ocr import _get_ocr_engine, _get_paddle_engine

    return {
        "easyocr": _get_ocr_engine() is not None,
        "paddleocr": _get_paddle_engine() is not None,
    }


def suggest_cluster_jerseys(db, game_id, ai_settings=None):
    """Low-threshold OCR hints for coach review (not auto-applied)."""
    ai_settings = ai_settings or {}
    min_conf = float(ai_settings.get("jersey_ocr_suggest_min_confidence", 0.35))
    return aggregate_cluster_jersey_votes(
        db,
        game_id,
        min_confidence=min_conf,
        min_samples=1,
    )


def apply_ocr_hints_to_slots(db, game_id, ai_settings=None):
    """Apply best OCR hint per court slot when it matches the loaded roster."""
    from court_slot_mapping import apply_court_slot_mappings, get_court_slots, save_court_slot_mappings

    ai_settings = ai_settings or {}
    hints = suggest_cluster_jerseys(db, game_id, ai_settings)
    roster_by_jersey, roster_source = _roster_jersey_index(db, game_id)
    if not hints:
        return {"applied": 0, "mappings": [], "events_updated": 0, "reason": "no_hints"}

    mappings = []
    used_jerseys = set()
    for item in hints:
        jersey = int(item["jersey_number"])
        if jersey in used_jerseys:
            continue
        if roster_by_jersey and jersey not in roster_by_jersey:
            continue
        used_jerseys.add(jersey)
        roster_player = roster_by_jersey.get(jersey) if roster_by_jersey else None
        mappings.append({
            "tracker_id": int(item["tracker_id"]),
            "jersey_number": jersey,
            "player_name": (roster_player or {}).get("name") or (roster_player or {}).get("label"),
        })

    if not mappings:
        return {
            "applied": 0,
            "mappings": [],
            "events_updated": 0,
            "reason": "no_roster_matches",
            "hint_count": len(hints),
        }

    save_court_slot_mappings(db, game_id, mappings, apply_to_events=False)
    result = apply_court_slot_mappings(db, game_id)
    return {
        "applied": len(mappings),
        "mappings": mappings,
        "events_updated": result.get("events_updated", 0),
        "slots": get_court_slots(db, game_id),
        "hint_count": len(hints),
        "roster_source": roster_source,
    }


def aggregate_cluster_jersey_votes(
    db,
    game_id,
    *,
    min_confidence: float = 0.55,
    min_samples: int = 3,
):
    """Majority vote jersey per court cluster from co-located OCR reads."""
    scope_sql, scope_params = _broad_detection_scope(db, game_id)

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
    scope_sql, scope_params = _broad_detection_scope(db, game_id)

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
    min_conf = float(ai_settings.get("jersey_ocr_min_confidence", 0.50))
    min_samples = int(ai_settings.get("identity_auto_apply_min_samples", 2))

    cluster_suggestions = aggregate_cluster_jersey_votes(
        db, game_id, min_confidence=min_conf, min_samples=max(1, min_samples)
    )
    track_suggestions = aggregate_track_jersey_votes(
        db, game_id, min_confidence=min_conf, min_samples=max(1, min_samples)
    )
    persist_identity_labels(db, game_id, cluster_suggestions, source="ocr_cluster_votes")
    persist_identity_labels(db, game_id, track_suggestions, source="ocr_track_votes")

    from helpers import count_jersey_reads_for_analysis

    ocr_read_count = count_jersey_reads_for_analysis(db, game_id)

    return {
        "ocr_read_count": ocr_read_count,
        "cluster_suggestions": cluster_suggestions,
        "track_suggestions": track_suggestions,
        "applied_labels": get_identity_labels(db, game_id),
    }


def _roster_jersey_index(db, game_id):
    from analysis_helpers import get_analysis_roster_players

    payload = get_analysis_roster_players(db, game_id)
    by_jersey = {}
    for player in payload["players"]:
        jersey = player.get("jersey_number")
        if jersey in (None, ""):
            continue
        try:
            jersey_int = int(jersey)
        except (TypeError, ValueError):
            continue
        by_jersey[jersey_int] = player
    return by_jersey, payload["source"]


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


def _build_auto_apply_mappings(suggestions, *, roster_by_jersey, use_roster_whitelist, min_conf, min_samples):
    mappings = []
    used_jerseys = set()
    for item in suggestions:
        if item["confidence"] < min_conf or item["sample_count"] < min_samples:
            continue
        jersey = int(item["jersey_number"])
        if use_roster_whitelist and jersey not in roster_by_jersey:
            continue
        if jersey in used_jerseys:
            continue
        used_jerseys.add(jersey)
        roster_player = roster_by_jersey.get(jersey) if roster_by_jersey else None
        mappings.append({
            "tracker_id": item["tracker_id"],
            "jersey_number": jersey,
            "player_name": (roster_player or {}).get("name") or (roster_player or {}).get("label"),
        })
    return mappings


def auto_apply_cluster_jerseys(db, game_id, ai_settings=None):
    """Auto-map court clusters to jerseys when OCR confidence is high enough."""
    from court_slot_mapping import save_court_slot_mappings, apply_court_slot_mappings

    ai_settings = ai_settings or {}
    min_conf = float(ai_settings.get("identity_auto_apply_min_confidence", 0.55))
    min_samples = int(ai_settings.get("identity_auto_apply_min_samples", 2))

    suggestions = aggregate_cluster_jersey_votes(
        db,
        game_id,
        min_confidence=float(ai_settings.get("jersey_ocr_min_confidence", 0.55)),
        min_samples=min_samples,
    )
    roster_by_jersey, roster_source = _roster_jersey_index(db, game_id)
    use_roster_whitelist = roster_source == "film_roster" and bool(roster_by_jersey)
    if roster_by_jersey:
        min_samples = min(min_samples, 1)
        min_conf = min(min_conf, 0.45)

    mappings = _build_auto_apply_mappings(
        suggestions,
        roster_by_jersey=roster_by_jersey,
        use_roster_whitelist=use_roster_whitelist,
        min_conf=min_conf,
        min_samples=min_samples,
    )
    if not mappings and use_roster_whitelist and suggestions:
        mappings = _build_auto_apply_mappings(
            suggestions,
            roster_by_jersey=roster_by_jersey,
            use_roster_whitelist=False,
            min_conf=min_conf,
            min_samples=min_samples,
        )

    if not mappings:
        return {"applied": 0, "mappings": [], "events_updated": 0}

    save_court_slot_mappings(db, game_id, mappings, apply_to_events=False)
    result = apply_court_slot_mappings(db, game_id)
    return {
        "applied": len(mappings),
        "mappings": mappings,
        "events_updated": result.get("events_updated", 0),
    }


def _run_jersey_ocr_scan(db, game_id, ai_settings=None, video_path=None):
    """Run full jersey OCR: cluster samples + event-window crops."""
    ai_settings = ai_settings or {}
    if not ai_settings.get("jersey_ocr_enabled", True):
        return {"skipped": True, "reason": "jersey_ocr_disabled"}
    if video_path is None:
        try:
            from analysis_helpers import resolve_analysis_game_context

            context = resolve_analysis_game_context(db, game_id)
            video_path = context.get("video_path")
        except Exception:
            video_path = None
    if not video_path:
        return {"skipped": True, "reason": "no_video"}
    from jersey_ocr import ocr_jerseys_for_game

    return ocr_jerseys_for_game(db, game_id, video_path, ai_settings)


def _run_event_jersey_ocr(db, game_id, ai_settings=None, video_path=None):
    return _run_jersey_ocr_scan(db, game_id, ai_settings, video_path=video_path)


def run_identity_postprocess(db, game_id, ai_settings=None, video_path=None):
    """Build OCR identity report and auto-apply jersey mappings when enabled."""
    ai_settings = ai_settings or {}
    ocr_result = _run_jersey_ocr_scan(db, game_id, ai_settings, video_path=video_path)
    report = build_identity_report(db, game_id, ai_settings)
    applied = {"applied": 0, "mappings": [], "events_updated": 0}
    if ai_settings.get("auto_apply_jersey_mapping", True):
        applied = auto_apply_cluster_jerseys(db, game_id, ai_settings)
    return {
        **report,
        "ocr_scan": ocr_result,
        "event_ocr": ocr_result.get("event_scan") if isinstance(ocr_result, dict) else ocr_result,
        "auto_apply": applied,
        "slots_mapped": applied.get("applied", 0),
        "events_updated": applied.get("events_updated", 0),
    }


def _analysis_video_fps(db, game_id, ai_settings=None) -> float:
    ai_settings = ai_settings or {}
    detect_stride = max(1, int(ai_settings.get("detection_stride", 1)))
    from analysis_helpers import resolve_analysis_game_context

    context = resolve_analysis_game_context(db, game_id)
    video_path = context.get("video_path")
    if video_path:
        try:
            import cv2

            cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            cap.release()
            return float(fps), detect_stride
        except Exception:
            pass
    return 25.0, detect_stride


def scan_and_apply_jerseys(db, game_id, ai_settings=None, video_path=None) -> dict:
    """Run full OCR scan and auto-apply jersey mappings. Returns result dict."""
    from analysis_helpers import resolve_analysis_game_context

    ai_settings = ai_settings or {}
    engines = jersey_ocr_engine_status()
    if not engines.get("easyocr") and not engines.get("paddleocr"):
        return {
            "error": "No OCR engine installed. Run: py -3.12 -m pip install easyocr",
            "ocr_engines": engines,
            "status_code": 400,
        }

    if video_path is None:
        context = resolve_analysis_game_context(db, game_id)
        video_path = context.get("video_path")
    if not video_path:
        return {
            "error": "Video file path not found for this analysis. Re-link the video or re-run AI.",
            "game_id": game_id,
            "status_code": 400,
        }

    result = run_identity_postprocess(db, game_id, ai_settings, video_path=video_path)
    return {
        "game_id": game_id,
        "video_path": video_path,
        "ocr_engines": engines,
        **result,
    }


def ensure_analysis_player_slots(db, game_id, ai_settings=None):
    """Ensure court slots exist, then auto-apply jersey labels to AI events."""
    from court_slot_mapping import get_court_slots

    ai_settings = ai_settings or {}
    slots = get_court_slots(db, game_id)
    if not slots:
        try:
            from film_analysis import calculate_player_minutes

            fps, detect_stride = _analysis_video_fps(db, game_id, ai_settings)
            calculate_player_minutes(db, game_id, fps=fps, detect_stride=detect_stride)
        except Exception:
            pass
    return ensure_identity_applied(db, game_id, ai_settings)


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
    if any(slot.get("is_mapped") for slot in slots):
        result = apply_court_slot_mappings(db, game_id)
        if _events_use_raw_cluster_ids(db, game_id) == 0:
            return {
                "skipped": False,
                "reason": "applied_saved_slots",
                "raw_cluster_events": raw_cluster_events,
                "events_updated": result.get("events_updated", 0),
                "slots_mapped": result.get("slots_mapped", 0),
                "applied": result.get("slots_mapped", 0),
            }

    from helpers import count_jersey_reads_for_analysis

    existing_reads = count_jersey_reads_for_analysis(db, game_id)
    ocr_result = None
    if existing_reads == 0:
        ocr_result = _run_jersey_ocr_scan(db, game_id, ai_settings)
    report = build_identity_report(db, game_id, ai_settings)
    ocr_status = jersey_ocr_engine_status()
    if not report.get("cluster_suggestions"):
        return {
            "skipped": True,
            "reason": "no_cluster_suggestions",
            "raw_cluster_events": raw_cluster_events,
            "ocr_read_count": report.get("ocr_read_count", 0),
            "ocr_scan": ocr_result,
            "event_ocr": (ocr_result or {}).get("event_scan") if isinstance(ocr_result, dict) else ocr_result,
            "ocr_engines": ocr_status,
            "ocr_hints": suggest_cluster_jerseys(db, game_id, ai_settings),
        }

    applied = auto_apply_cluster_jerseys(db, game_id, ai_settings)
    return {
        "skipped": False,
        "raw_cluster_events": raw_cluster_events,
        "ocr_read_count": report.get("ocr_read_count", 0),
        "cluster_suggestions": len(report.get("cluster_suggestions") or []),
        "ocr_scan": ocr_result,
        "event_ocr": (ocr_result or {}).get("event_scan") if isinstance(ocr_result, dict) else ocr_result,
        "ocr_engines": ocr_status,
        "ocr_hints": suggest_cluster_jerseys(db, game_id, ai_settings),
        **applied,
    }
