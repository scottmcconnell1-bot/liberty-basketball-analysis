"""
AI and Video Analysis Blueprint.

Routes:
  GET  /api/analysis_status/<game_id>  - Analysis status for an analysis key
  GET  /api/stats/<game_id>            - Stats for a game/analysis key
  POST /api/upload_video               - Upload a video file
  GET  /api/videos                     - List all videos
  GET  /videos/<int:vid_id>/compare    - Compare video analysis
  POST /videos/<int:vid_id>/rerun      - Re-run video analysis
  POST /api/videos/<int:vid_id>/analyze - Start AI analysis for an existing video
  GET  /api/check_duplicate            - Check for duplicate videos
  DELETE /api/videos/<int:vid_id>      - Delete a video
  POST /api/videos/<int:vid_id>/trim   - Trim video to start/end range
  GET  /api/videos/trim/<job_id>       - Poll trim job status
  POST /api/admin/reset                - Admin reset
  POST /upload                         - Upload and analyze
  POST /api/assistant/query            - Read-only Q&A from reviewed data (Stage 10A)
  GET  /api/assistant/workflow/games   - Guided workflow step: games (Stage 10B)
  GET  /api/assistant/workflow/games/<game_id>/players - Players with trusted stats
  GET  /api/assistant/workflow/games/<game_id>/clips   - Clips for optional player filter
  GET  /assistant                      - Guided workflow UI
"""

import json
import os
import threading
from datetime import datetime
from flask import (
    Blueprint, current_app, jsonify, redirect, render_template,
    request, url_for, abort
)
from werkzeug.utils import secure_filename

from helpers import (
    AI_DEFAULTS, ai_runtime_available, append_query_params, build_analysis_settings_snapshot,
    build_resource_status, build_rerun_game_id, build_run_summary,
    build_settings_catalog, default_run_label, display_detector_model,
    ensure_db, ensure_primary_run_metadata, extract_local_path, get_db, get_default_team_id,
    get_runtime_settings, is_superseded_analysis_run, latest_analysis_run_id_subquery,
    load_all_settings,
    queue_analysis_run, require_feature,
    resolve_analysis_run_for_progress, resolve_detector_model, safe_return_path,
    start_analysis_subprocess,
    ai_packages_install_commands, ai_packages_install_hint,
    supersede_pending_analysis_runs,
    validate_video_for_analysis,
    validate_ai_models_for_analysis,
    reconcile_stuck_analysis_run,
    heal_failed_analysis_run_with_events,
    ai_analysis_log_path,
    count_detections_for_analysis, count_events_for_analysis,
    _read_log_tail,
)

ai_bp = Blueprint("ai", __name__)


def _format_team_level_label(level, gender):
    level_labels = {"varsity": "Varsity", "jv": "JV", "jr_high": "Jr High"}
    gender_labels = {"boys": "Boys", "girls": "Girls", "coed": "Coed"}
    parts = []
    if gender:
        parts.append(gender_labels.get(str(gender).lower(), str(gender).title()))
    if level:
        parts.append(level_labels.get(str(level).lower(), str(level).replace("_", " ").title()))
    return " ".join(parts) if parts else None


def _lookup_video_schedule_context(db, *, relational_game_id=None, game_id=None):
    if relational_game_id:
        row = db.execute(
            """
            SELECT sg.opponent_name, sg.game_date, sg.level, sg.gender
              FROM games g
              LEFT JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
             WHERE g.id = ?
            """,
            (relational_game_id,),
        ).fetchone()
        if row:
            return row

    if game_id:
        row = db.execute(
            """
            SELECT sg.opponent_name, sg.game_date, sg.level, sg.gender
              FROM games g
              LEFT JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
             WHERE g.nfhs_game_id = ?
                OR g.source_key = ?
             ORDER BY g.id DESC
             LIMIT 1
            """,
            (str(game_id), str(game_id)),
        ).fetchone()
        if row:
            return row
    return None


def _enrich_video_list_row(db, row):
    payload = dict(row)
    opponent = (payload.get("opponent") or "").strip()
    if not opponent or opponent.lower() == "unknown":
        opponent = ""

    schedule = _lookup_video_schedule_context(
        db,
        relational_game_id=payload.get("relational_game_id"),
        game_id=payload.get("game_id"),
    )
    if schedule:
        if not opponent and schedule["opponent_name"]:
            opponent = schedule["opponent_name"]
        payload["game_date"] = schedule["game_date"]
        payload["team_label"] = _format_team_level_label(schedule["level"], schedule["gender"])
    else:
        payload["game_date"] = None
        payload["team_label"] = None

    payload["display_game"] = f"Liberty vs {opponent}" if opponent else "Liberty"

    clause = _video_analysis_runs_clause()
    run_row = db.execute(
        f"""SELECT * FROM analysis_runs
            WHERE {clause}
            ORDER BY id DESC LIMIT 1""",
        (payload["id"], payload.get("game_id"), payload.get("game_id"), payload.get("file_path")),
    ).fetchone()
    if run_row:
        analysis_key = run_row["analysis_key"] or payload.get("game_id")
        run_row = resolve_analysis_run_for_progress(db, analysis_key) or run_row
        payload["analysis_status"] = run_row["status"]
        payload["error_message"] = run_row["error_message"]
        payload["analysis_key"] = run_row["analysis_key"]
        count_kwargs = dict(
            analysis_key=run_row["analysis_key"],
            relational_game_id=run_row["game_id"],
            video_game_id=payload.get("game_id"),
            video_relational_game_id=payload.get("relational_game_id"),
            base_analysis_key=run_row["base_analysis_key"],
            source_video_id=payload.get("id"),
            video_path=payload.get("file_path"),
        )
        payload["detection_count"] = count_detections_for_analysis(db, **count_kwargs)
        payload["event_count"] = count_events_for_analysis(
            db,
            analysis_key=count_kwargs["analysis_key"],
            relational_game_id=count_kwargs["relational_game_id"],
            video_game_id=count_kwargs["video_game_id"],
            base_analysis_key=count_kwargs["base_analysis_key"],
        )

    return payload


def _resolve_analysis_relational_game_id(db, game_id):
    """Resolve the canonical game id for either an analysis key or a game key."""
    row = db.execute(
        "SELECT game_id FROM analysis_runs WHERE analysis_key=? AND game_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        (game_id,),
    ).fetchone()
    if row and row["game_id"] is not None:
        return row["game_id"]

    from stats import _resolve_relational_game_id
    return _resolve_relational_game_id(db, game_id)


def _resolve_video_id_for_analysis(db, game_id):
    row = db.execute(
        """SELECT v.id
             FROM videos v
             LEFT JOIN analysis_runs ar
               ON ar.source_video_id = v.id
               OR ar.analysis_key = v.game_id
               OR ar.base_analysis_key = v.game_id
               OR ar.video_path = v.file_path
            WHERE v.game_id = ?
               OR ar.analysis_key = ?
            ORDER BY v.id DESC
            LIMIT 1""",
        (game_id, game_id),
    ).fetchone()
    return row["id"] if row else None


@ai_bp.route("/api/analysis_status/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_status(game_id):
    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row is None:
        return jsonify({
            "status": "not_started",
            "detection_count": 0,
            "event_count": 0,
            "event_generation_summary": "AI analysis has not started yet.",
        })

    progress_game_id = row["analysis_key"] or game_id
    detection_count = db.execute(
        """SELECT COUNT(*) AS c FROM detections d
           WHERE (d.relational_game_id = ? AND ? IS NOT NULL)
              OR (d.relational_game_id IS NULL AND d.game_id = ?)""",
        (row["game_id"], row["game_id"], progress_game_id),
    ).fetchone()["c"]
    event_count = db.execute(
        """SELECT COUNT(*) AS c FROM events e
           WHERE e.game_id = ?
              OR (? IS NOT NULL AND e.relational_game_id = ?)""",
        (progress_game_id, row["game_id"], row["game_id"]),
    ).fetchone()["c"]

    payload = dict(row)
    payload["analysis_key"] = progress_game_id
    payload["detection_count"] = detection_count
    payload["event_count"] = event_count
    settings_snapshot = {}
    if payload.get("settings_json"):
        try:
            settings_snapshot = json.loads(payload["settings_json"])
        except json.JSONDecodeError:
            settings_snapshot = {}
    generator_mode = settings_snapshot.get("ai", {}).get("event_generator_mode", AI_DEFAULTS["event_generator_mode"])
    if generator_mode == "expanded":
        payload["event_generation_summary"] = (
            "YOLO currently detects players and the ball. The expanded heuristic generator tries to "
            "derive possession changes, shots, makes, misses, rebounds, assists, steals, turnovers, "
            "blocks, and fouls from those detections."
        )
    else:
        payload["event_generation_summary"] = (
            "YOLO currently detects players and the ball. Auto-tagged events come from the "
            "heuristic event generator."
        )
    return jsonify(payload)


# ── API: Stats ────────────────────────────────────────────

@ai_bp.route("/api/stats/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_stats(game_id):
    from stats import refresh_stats, get_enhanced_stats
    db = get_db()
    basic = refresh_stats(db, game_id)
    enhanced = get_enhanced_stats(db, game_id)

    # Wire possession inference after stats refresh
    from helpers import assign_possessions_for_game
    relational_game_id = _resolve_analysis_relational_game_id(db, game_id)
    if relational_game_id is not None:
        assign_possessions_for_game(db, relational_game_id, analysis_key=game_id)

    return jsonify({
        "basic": basic,
        "enhanced": enhanced,
    })


# ── API: Analysis Progress ──────────────────────────────────

@ai_bp.route("/api/ai/runtime")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_ai_runtime():
    """Return whether the server's Python environment can run AI analysis."""
    import sys
    from helpers import module_available

    return jsonify({
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "cv2": module_available("cv2"),
        "ultralytics": module_available("ultralytics"),
        "torch": module_available("torch"),
        "sklearn": module_available("sklearn"),
        "ai_runtime_available": ai_runtime_available(),
        "install_hint": ai_packages_install_hint(),
        "install_commands": ai_packages_install_commands(),
    })


@ai_bp.route("/api/analysis_progress/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_progress(game_id):
    """Return current analysis progress for an analysis key."""
    db = get_db()
    reconcile_stuck_analysis_run(db, game_id)
    row = resolve_analysis_run_for_progress(db, game_id)
    if row is None:
        return jsonify({"status": "not_started", "progress_pct": 0, "progress_step": ""})
    progress_game_id = row["analysis_key"] or game_id
    error_message = row["error_message"]
    if is_superseded_analysis_run(row):
        error_message = None
    return jsonify({
        "status": row["status"],
        "analysis_key": progress_game_id,
        "progress_pct": row["progress_pct"] or 0,
        "progress_step": row["progress_step"] or "",
        "error_message": error_message,
        "log_path": ai_analysis_log_path(progress_game_id),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "detection_count": db.execute(
            """SELECT COUNT(*) AS c FROM detections d
               WHERE (d.relational_game_id = ? AND ? IS NOT NULL)
                  OR (d.relational_game_id IS NULL AND d.game_id = ?)""",
            (row["game_id"], row["game_id"], progress_game_id),
        ).fetchone()["c"],
        "event_count": db.execute(
            "SELECT COUNT(*) AS c FROM events e WHERE e.game_id = ?",
            (progress_game_id,),
        ).fetchone()["c"],
    })


# ── API: Full Analysis Results ──────────────────────────────

@ai_bp.route("/api/analysis/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_results(game_id):
    """Return full analysis results: box score, shots, plays, player effect."""
    import sqlite3
    from stats import refresh_stats, get_enhanced_stats, aggregate_stats_preview, get_shot_breakdown_preview

    try:
        payload = _get_analysis_results_payload(
            game_id,
            refresh_stats=refresh_stats,
            get_enhanced_stats=get_enhanced_stats,
            aggregate_stats_preview=aggregate_stats_preview,
            get_shot_breakdown_preview=get_shot_breakdown_preview,
        )
        return jsonify(payload)
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            return jsonify({
                "error": (
                    "Database is busy while analysis is still writing. "
                    "Wait until Video Library shows Completed, then refresh."
                ),
                "code": "database_locked",
            }), 503
        raise


def _get_analysis_results_payload(
    game_id,
    *,
    refresh_stats,
    get_enhanced_stats,
    aggregate_stats_preview,
    get_shot_breakdown_preview,
):
    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    relational_game_id = _resolve_analysis_relational_game_id(db, game_id)
    analysis_running = row and row["status"] in {"running", "pending"}

    identity_status = None
    if analysis_running:
        identity_status = {
            "skipped": True,
            "reason": "analysis_running",
            "message": "Analysis is still running — open Results again when AI Status shows Completed.",
        }
    else:
        try:
            from settings_store import load_all_settings, AI_DEFAULTS
            from track_identity import ensure_analysis_player_slots

            ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
            identity_status = ensure_analysis_player_slots(
                db, game_id, ai_settings, allow_ocr=False,
            )
        except Exception as exc:
            import sqlite3

            current_app.logger.exception("Identity auto-apply failed for %s", game_id)
            if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
                identity_status = {
                    "skipped": True,
                    "reason": "database_locked",
                    "message": "Database busy (analysis may still be writing). Wait a minute and refresh.",
                }
            else:
                identity_status = {"skipped": True, "reason": "error", "error": str(exc)[:200]}

    db.execute(
        """UPDATE events
              SET event_type_id = (
                  SELECT id FROM event_types WHERE lower(code) = lower(events.event_type)
              )
            WHERE event_type_id IS NULL
              AND (
                    game_id = ?
                 OR (relational_game_id IS NOT NULL AND relational_game_id = ?)
              )""",
        (game_id, relational_game_id),
    )
    db.commit()

    from analysis_helpers import event_scope_sql
    from helpers import count_detections_for_analysis

    detection_count = count_detections_for_analysis(
        db,
        analysis_key=game_id,
        relational_game_id=relational_game_id,
    )
    event_scope, event_scope_params = event_scope_sql(db, game_id, alias="e")
    event_count = db.execute(
        f"SELECT COUNT(*) AS c FROM events e WHERE {event_scope}",
        event_scope_params,
    ).fetchone()["c"]

    basic = aggregate_stats_preview(db, game_id)
    quality_notes = []
    try:
        refresh_stats(db, game_id)
    except Exception as exc:
        current_app.logger.exception("refresh_stats failed for %s", game_id)
        quality_notes.append(f"Persisted stats refresh failed: {str(exc)[:200]}")
    enhanced = get_enhanced_stats(db, game_id)
    enhanced["shot_breakdown"] = [dict(row) for row in get_shot_breakdown_preview(db, game_id)]
    enhanced["basic_stats"] = basic

    if detection_count < 1000:
        quality_notes.append(
            "Very few detections saved for this analysis run. Re-run AI on Video Library "
            "(not just Rebuild) when no other analysis is writing to the database, then "
            "open Results again."
        )
    if detection_count > 250_000:
        quality_notes.append(
            "Very high detection count — the clip may include extra footage beyond one game, "
            "or detection_stride may be too low for a long video."
        )
    if event_count > 3000:
        quality_notes.append(
            "Event count is high for a single game. Expanded AI heuristics often over-tag "
            "shots and possession changes; treat counts as directional, not official stats."
        )
    if event_count > 0 and not enhanced["shot_breakdown"] and not any(row.get("pts") for row in basic):
        quality_notes.append(
            "Events were generated but shot classifications are empty. "
            "Try Rebuild Events on Video Library, then refresh this page."
        )
    if any((row.get("minutes_played") or 0) > 42 for row in enhanced.get("minutes", [])):
        quality_notes.append(
            "Some position clusters show more than 42 minutes — the trimmed video may still "
            "be longer than one regulation game."
        )

    # Wire possession inference after stats refresh
    from helpers import assign_possessions_for_game
    relational_game_id = _resolve_analysis_relational_game_id(db, game_id)
    if relational_game_id is not None:
        assign_possessions_for_game(db, relational_game_id, analysis_key=game_id)

    # Events summary
    events_summary = db.execute(
        f"""SELECT event_type, COUNT(*) as cnt
              FROM events e
             WHERE {event_scope}
             GROUP BY event_type
             ORDER BY cnt DESC""",
        event_scope_params,
    ).fetchall()

    recent_events = db.execute(
        f"""SELECT event_type, player, shot_result, timestamp_ms, details_json
              FROM events e
             WHERE {event_scope}
             ORDER BY timestamp_ms DESC
             LIMIT 50""",
        event_scope_params,
    ).fetchall()

    return {
        "game_id": game_id,
        "video_id": _resolve_video_id_for_analysis(db, game_id),
        "detection_count": detection_count,
        "event_count": event_count,
        "quality_notes": quality_notes,
        "basic_stats": basic,
        "enhanced": enhanced,
        "events_summary": [dict(e) for e in events_summary],
        "recent_events": [dict(e) for e in recent_events],
        "identity_status": identity_status,
        "player_labels": _analysis_player_labels(db, game_id),
        "analysis_version": "2026-07-07-analysis-v2",
        **_analysis_film_payload(db, game_id),
    }


def _analysis_player_labels(db, game_id):
    from court_slot_mapping import get_court_slots

    labels = {}
    for slot in get_court_slots(db, game_id):
        tracker_id = slot.get("tracker_id")
        label = slot.get("mapped_label")
        if tracker_id is None or not label:
            continue
        labels[str(tracker_id)] = label
    return labels


def _analysis_film_payload(db, game_id):
    from analysis_helpers import resolve_analysis_game_context, resolve_video_duration_ms

    context = resolve_analysis_game_context(db, game_id)
    stored_filename = context.get("stored_filename")
    film_url = None
    if stored_filename:
        film_url = url_for("core.film", filename=stored_filename, game_id=context["analysis_key"])
    return {
        "analysis_key": context["analysis_key"],
        "stored_filename": stored_filename,
        "film_url": film_url,
        "duration_ms": resolve_video_duration_ms(
            db,
            context["analysis_key"],
            relational_game_id=context["relational_game_id"],
            analysis_key=context["analysis_key"],
        ),
        "roster_context": {
            "season_id": context["season_id"],
            "level": context["level"],
            "gender": context["gender"],
            "side": context["side"],
            "opponent_name": context["opponent_name"],
        },
        "teams": {
            "our_team_id": context["our_team_id"],
            "our_team_name": context["our_team_name"],
            "opponent_team_name": context["opponent_team_name"],
        },
    }


@ai_bp.route("/api/analysis/<game_id>/roster")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_roster_api(game_id):
    from analysis_helpers import get_analysis_roster_players

    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]
    return jsonify(get_analysis_roster_players(db, game_id))


@ai_bp.route("/api/analysis/<game_id>/events")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_events_api(game_id):
    from analysis_helpers import list_analysis_events

    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    payload = list_analysis_events(
        db,
        game_id,
        event_type=request.args.get("event_type"),
        stat=request.args.get("stat"),
        player=request.args.get("player"),
        tracker_id=request.args.get("tracker_id"),
        team=request.args.get("team"),
        quarter=request.args.get("quarter"),
        half=request.args.get("half"),
        limit=request.args.get("limit", 500),
    )
    stored_filename = payload.get("stored_filename")
    if stored_filename:
        payload["film_url"] = url_for("core.film", filename=stored_filename, game_id=payload["game_id"])
    for event in payload.get("events", []):
        ts = event.get("timestamp_ms") or 0
        event["film_url"] = None
        if stored_filename:
            from helpers import analysis_film_clip_query

            event["film_url"] = url_for(
                "core.film",
                filename=stored_filename,
                game_id=payload["game_id"],
                **analysis_film_clip_query(ts),
            )
    return jsonify(payload)


@ai_bp.route("/api/track-identity/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_track_identity_api(game_id):
    from track_identity import build_identity_report
    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]
    settings = load_all_settings({}, {}, AI_DEFAULTS, db=db)
    report = build_identity_report(db, game_id, settings["ai"])
    return jsonify({"game_id": game_id, **report})


# ── API: Court slot → jersey mapping ─────────────────────────

@ai_bp.route("/api/court-slots/<game_id>", methods=["GET"])
@require_feature("ENABLE_AUTO_STATS_M1")
def get_court_slots_api(game_id):
    from court_slot_mapping import get_court_slots
    from track_identity import jersey_ocr_engine_status, suggest_cluster_jerseys
    from settings_store import load_all_settings, AI_DEFAULTS

    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
    hints = suggest_cluster_jerseys(db, game_id, ai_settings)
    hints_by_slot = {int(item["tracker_id"]): item for item in hints}
    slots = get_court_slots(db, game_id)
    for slot in slots:
        hint = hints_by_slot.get(int(slot["tracker_id"]))
        if not hint:
            continue
        slot["ocr_suggested_jersey"] = int(hint["jersey_number"])
        slot["ocr_confidence"] = hint.get("confidence")
        slot["ocr_samples"] = hint.get("sample_count")

    return jsonify({
        "game_id": game_id,
        "slots": slots,
        "ocr_hints": hints,
        "ocr_engines": jersey_ocr_engine_status(),
    })


@ai_bp.route("/api/court-slots/<game_id>", methods=["PUT"])
@require_feature("ENABLE_AUTO_STATS_M1")
def save_court_slots_api(game_id):
    from court_slot_mapping import save_court_slot_mappings, get_court_slots
    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    data = request.get_json(force=True) or {}
    mappings = data.get("mappings") or []
    apply_to_events = bool(data.get("apply_to_events", True))
    if not mappings:
        return jsonify({"error": "mappings required"}), 400

    applied = save_court_slot_mappings(db, game_id, mappings, apply_to_events=apply_to_events)
    return jsonify({
        "game_id": game_id,
        "applied": applied,
        "slots": get_court_slots(db, game_id),
    })


@ai_bp.route("/api/court-slots/<game_id>/apply", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def apply_court_slots_api(game_id):
    from court_slot_mapping import apply_court_slot_mappings, get_court_slots
    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    result = apply_court_slot_mappings(db, game_id)
    result["game_id"] = game_id
    result["slots"] = get_court_slots(db, game_id)
    return jsonify(result)


def _run_scan_jerseys_worker(
    app,
    *,
    run_id: int,
    analysis_key: str,
) -> None:
    """Background worker: full jersey OCR scan and auto-apply roster mappings."""
    with app.app_context():
        db = get_db()
        try:
            from settings_store import load_all_settings, AI_DEFAULTS
            from stats import refresh_stats
            from track_identity import scan_and_apply_jerseys

            db.execute(
                """UPDATE analysis_runs
                   SET progress_step='jersey_scan:running'
                   WHERE id=?""",
                (run_id,),
            )
            db.commit()

            ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
            result = scan_and_apply_jerseys(db, analysis_key, ai_settings)
            status_code = result.pop("status_code", None)
            if status_code:
                raise RuntimeError(result.get("error") or "Jersey scan failed")

            refresh_stats(db, analysis_key)
            mapped = result.get("slots_mapped") or (result.get("auto_apply") or {}).get("applied", 0)
            reads = result.get("ocr_read_count", 0)
            db.execute(
                """UPDATE analysis_runs
                   SET progress_step='jersey_scan:done',
                       error_message=NULL
                   WHERE id=?""",
                (run_id,),
            )
            db.commit()
            app.logger.info(
                "Jersey scan finished for %s: %s mapped, %s reads",
                analysis_key,
                mapped,
                reads,
            )
        except Exception as exc:
            app.logger.exception("Jersey scan failed for %s", analysis_key)
            from helpers import format_exception_message

            db.execute(
                """UPDATE analysis_runs
                   SET progress_step=?
                   WHERE id=?""",
                (f"jersey_scan:failed:{format_exception_message(exc)}"[:500], run_id),
            )
            db.commit()
        finally:
            db.close()


@ai_bp.route("/api/court-slots/<game_id>/scan-jerseys", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def scan_jerseys_api(game_id):
    """Run full jersey OCR on the video and auto-apply roster mappings."""
    try:
        from track_identity import jersey_ocr_engine_status, scan_and_apply_jerseys
        from settings_store import load_all_settings, AI_DEFAULTS

        db = get_db()
        row = resolve_analysis_run_for_progress(db, game_id)
        resolved_key = game_id
        if row and row["analysis_key"]:
            resolved_key = row["analysis_key"]

        if row is None:
            return jsonify({
                "error": "No analysis run found for this game.",
                "game_id": resolved_key,
                "code": "no_analysis_run",
            }), 404

        progress_step = (row["progress_step"] or "").strip()
        if row["status"] in {"running", "pending"}:
            return jsonify({
                "error": "Analysis is already running. Wait until it finishes, then scan jerseys.",
                "code": "analysis_running",
                "analysis_key": resolved_key,
            }), 409
        if progress_step == "jersey_scan:running":
            return jsonify({
                "status": "jersey_scan_running",
                "analysis_key": resolved_key,
                "message": "Jersey scan is already running in the background.",
            }), 202

        # Quick path for tests/small scans when explicitly requested.
        if request.args.get("sync") == "1":
            engines = jersey_ocr_engine_status()
            if not engines.get("easyocr") and not engines.get("paddleocr"):
                return jsonify({
                    "error": "No OCR engine installed. Run: py -3.12 -m pip install easyocr",
                    "ocr_engines": engines,
                    "code": "ocr_unavailable",
                }), 400
            ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
            from analysis_helpers import resolve_analysis_game_context

            context = resolve_analysis_game_context(db, resolved_key)
            video_path = context.get("video_path")
            if not video_path:
                return jsonify({
                    "error": "Video file path not found for this analysis. Re-link the video or re-run AI.",
                    "game_id": resolved_key,
                    "code": "no_video",
                }), 400
            result = scan_and_apply_jerseys(db, resolved_key, ai_settings, video_path=video_path)
            status_code = result.pop("status_code", None)
            if status_code:
                return jsonify(result), status_code
            from stats import refresh_stats
            refresh_stats(db, resolved_key)
            return jsonify(result)

        # Return immediately — EasyOCR model load + video OCR can take many minutes.
        db.execute(
            """UPDATE analysis_runs
               SET progress_step='jersey_scan:running'
               WHERE id=?""",
            (row["id"],),
        )
        db.commit()

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_run_scan_jerseys_worker,
            kwargs={
                "app": app,
                "run_id": row["id"],
                "analysis_key": resolved_key,
            },
            daemon=True,
            name=f"scan-jerseys-{row['id']}",
        )
        thread.start()

        engines = jersey_ocr_engine_status()
        return jsonify({
            "status": "jersey_scan_started",
            "analysis_key": resolved_key,
            "message": (
                "Jersey scan started in the background. Loading OCR models and scanning the video "
                "can take several minutes on long games — this page will refresh when it finishes."
            ),
            "ocr_engines": engines,
        }), 202
    except Exception as exc:
        current_app.logger.exception("Could not start jersey scan for %s", game_id)
        return jsonify({
            "error": str(exc),
            "code": "jersey_scan_start_failed",
        }), 500


@ai_bp.route("/api/videos/<int:vid_id>/scan-jerseys", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def scan_video_jerseys_api(vid_id):
    """Run full jersey OCR for a video's linked analysis."""
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    clause = _video_analysis_runs_clause()
    row = db.execute(
        f"""SELECT * FROM analysis_runs
            WHERE {clause}
            ORDER BY id DESC LIMIT 1""",
        (vid_id, video["game_id"], video["game_id"], video["file_path"]),
    ).fetchone()
    analysis_key = (row["analysis_key"] if row else None) or video["game_id"]
    return scan_jerseys_api(analysis_key)


@ai_bp.route("/api/court-slots/<game_id>/apply-ocr-hints", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def apply_ocr_hints_api(game_id):
    """Apply OCR jersey hints that match the loaded Film Tool roster."""
    from settings_store import load_all_settings, AI_DEFAULTS
    from stats import refresh_stats
    from track_identity import apply_ocr_hints_to_slots, jersey_ocr_engine_status

    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
    result = apply_ocr_hints_to_slots(db, game_id, ai_settings)
    refresh_stats(db, game_id)
    result["game_id"] = game_id
    result["ocr_engines"] = jersey_ocr_engine_status()
    return jsonify(result)


@ai_bp.route("/api/court-slots/<game_id>/auto-apply", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def auto_apply_court_slots_api(game_id):
    """Apply OCR jersey mapping and any saved court-slot corrections to events/stats."""
    from court_slot_mapping import apply_court_slot_mappings, get_court_slots
    from settings_store import load_all_settings, AI_DEFAULTS
    from stats import refresh_stats
    from track_identity import ensure_analysis_player_slots

    db = get_db()
    row = resolve_analysis_run_for_progress(db, game_id)
    if row and row["analysis_key"]:
        game_id = row["analysis_key"]

    ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
    identity_status = ensure_analysis_player_slots(db, game_id, ai_settings)
    slot_result = apply_court_slot_mappings(db, game_id)
    refresh_stats(db, game_id)
    return jsonify({
        "game_id": game_id,
        "identity_status": identity_status,
        "slots_mapped": slot_result.get("slots_mapped", 0),
        "events_updated": slot_result.get("events_updated", 0),
        "slots": get_court_slots(db, game_id),
    })


# ── API: Possessions ─────────────────────────────────────────

@ai_bp.route("/api/possessions/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_possessions(game_id):
    """Return possession summary for a game."""
    from stats import get_possession_summary
    from helpers import assign_possessions_for_game
    db = get_db()
    # Ensure possessions are assigned before returning summary
    relational_game_id = _resolve_analysis_relational_game_id(db, game_id)
    if relational_game_id is not None:
        assign_possessions_for_game(db, relational_game_id, analysis_key=game_id)
    return jsonify(get_possession_summary(db, game_id))


# ── Page: Analysis Results ──────────────────────────────────

@ai_bp.route("/analysis/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def analysis_results_page(game_id):
    """Render the analysis results dashboard for a game."""
    return render_template("analysis_results.html", game_id=game_id)


# ── API: Upload video ─────────────────────────────────────

@ai_bp.route("/api/upload_video", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def upload_video():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    filename = secure_filename(f.filename)
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    f.save(dest)
    return jsonify({"status": "uploaded", "filename": filename})


# ── Chunked Upload ──────────────────────────────────────────
# Supports large file uploads by splitting into chunks that fit
# within Cloudflare's ~100MB proxy limit per request.

import tempfile, uuid, json as _json

CHUNK_SIZE = 80 * 1024 * 1024  # 80 MB per chunk (under Cloudflare limit)


@ai_bp.route("/api/upload_chunk", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def upload_chunk():
    """Receive a single chunk of a file upload."""
    upload_id = request.form.get("upload_id")
    chunk_index = request.form.get("chunk_index", type=int)
    total_chunks = request.form.get("total_chunks", type=int)
    filename = request.form.get("filename", "video.mp4")
    opponent = request.form.get("opponent", "unknown").strip() or "unknown"
    upload_mode = (request.form.get("upload_mode") or "analyze").strip().lower()

    if not upload_id:
        return jsonify({"error": "Missing upload_id"}), 400
    if chunk_index is None or total_chunks is None:
        return jsonify({"error": "Missing chunk_index or total_chunks"}), 400
    if "file" not in request.files:
        return jsonify({"error": "No file chunk provided"}), 400

    chunk_dir = os.path.join(tempfile.gettempdir(), "liberty_uploads", upload_id)
    os.makedirs(chunk_dir, exist_ok=True)

    # Save chunk
    chunk_file = request.files["file"]
    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index:04d}")
    chunk_file.save(chunk_path)

    # Check if all chunks received
    received = len([f for f in os.listdir(chunk_dir) if f.startswith("chunk_")])

    if received == total_chunks:
        # All chunks received — reassemble
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = secure_filename(filename)
        stem, ext = os.path.splitext(safe_name)
        stored_filename = f"{stem}_{ts}{ext}"
        dest = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename)

        with open(dest, "wb") as outfile:
            for i in range(total_chunks):
                chunk_path = os.path.join(chunk_dir, f"chunk_{i:04d}")
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
                os.remove(chunk_path)

        os.rmdir(chunk_dir)

        file_size = os.path.getsize(dest)

        # Save to DB
        db = get_db()
        game_id = f"{opponent.lower().replace(' ', '_')}_{stem}_{ts}"
        prior = db.execute(
            "SELECT id, stored_filename, upload_timestamp FROM videos WHERE original_filename=? ORDER BY id DESC LIMIT 1",
            (safe_name,),
        ).fetchone()
        is_dup = prior is not None
        dup_of_id = prior["id"] if prior else None

        # Resolve relational_game_id from games table
        try:
            gid_int = int(game_id)
            row = db.execute("SELECT id FROM games WHERE id = ?", (gid_int,)).fetchone()
            relational_game_id = row[0] if row else None
        except (TypeError, ValueError):
            relational_game_id = None

        video_cur = db.execute(
            """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                                   opponent, game_id, relational_game_id, is_duplicate, duplicate_of_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (safe_name, stored_filename, dest, file_size, opponent, game_id, relational_game_id, int(is_dup), dup_of_id),
        )
        video_row = db.execute(
            "SELECT * FROM videos WHERE id=?", (video_cur.lastrowid,),
        ).fetchone()
        film_url = url_for("core.film", filename=stored_filename, game_id=game_id)

        if upload_mode == "tag_only":
            db.commit()
            return jsonify({
                "status": "complete",
                "filename": stored_filename,
                "game_id": game_id,
                "redirect_url": film_url,
            })

        runtime_settings = get_runtime_settings()
        run_payload = queue_analysis_run(
            db, video_row, runtime_settings,
            run_kind="primary", run_label="Original upload",
        )
        if ai_runtime_available():
            start_analysis_subprocess(run_payload["analysis_key"], dest)
        db.commit()

        return jsonify({
            "status": "complete",
            "filename": stored_filename,
            "game_id": game_id,
            "redirect_url": film_url,
        })

    return jsonify({"status": "chunk_received", "received": received, "total": total_chunks})


@ai_bp.route("/api/videos")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_videos():
    """Return all videos from the DB with their analysis status."""
    db = get_db()
    latest_run = latest_analysis_run_id_subquery()
    rows = db.execute(f"""
        SELECT v.*, ar.status as analysis_status, ar.error_message, ar.analysis_key,
               (SELECT COUNT(*) FROM analysis_runs ar2 WHERE ar2.source_video_id = v.id OR ar2.base_analysis_key = v.game_id OR ar2.analysis_key = v.game_id OR ar2.video_path = v.file_path) as analysis_run_count
        FROM videos v
        LEFT JOIN analysis_runs ar ON ar.id = {latest_run}
        ORDER BY v.id DESC
    """).fetchall()

    running_keys = set()
    healed_keys = set()
    for r in rows:
        game_id = r["analysis_key"] or r["game_id"]
        if not game_id:
            continue
        status = r["analysis_status"]
        if status == "failed":
            if heal_failed_analysis_run_with_events(db, game_id):
                healed_keys.add(game_id)
        elif status == "running":
            running_keys.add(game_id)
    for game_id in running_keys:
        reconcile_stuck_analysis_run(db, game_id)
    if running_keys or healed_keys:
        rows = db.execute(f"""
            SELECT v.*, ar.status as analysis_status, ar.error_message, ar.analysis_key,
                   (SELECT COUNT(*) FROM analysis_runs ar2 WHERE ar2.source_video_id = v.id OR ar2.base_analysis_key = v.game_id OR ar2.analysis_key = v.game_id OR ar2.video_path = v.file_path) as analysis_run_count
            FROM videos v
            LEFT JOIN analysis_runs ar ON ar.id = {latest_run}
            ORDER BY v.id DESC
        """).fetchall()

    return jsonify([_enrich_video_list_row(db, r) for r in rows])


@ai_bp.route("/videos/<int:vid_id>/compare")
@require_feature("ENABLE_AUTO_STATS_M1")
def compare_video_analysis(vid_id):
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        abort(404)

    ensure_primary_run_metadata(db, video)
    rows = db.execute(
        """SELECT ar.*,
                  (SELECT COUNT(*) FROM detections d WHERE (d.relational_game_id = (SELECT id FROM games WHERE game_id = ar.analysis_key) OR (d.relational_game_id IS NULL AND d.game_id = ar.analysis_key))) AS detection_count,
                  (SELECT COUNT(*) FROM events e WHERE e.game_id = ar.analysis_key) AS event_count
           FROM analysis_runs ar
           WHERE ar.source_video_id = ?
              OR ar.base_analysis_key = ?
              OR ar.analysis_key = ?
              OR ar.video_path = ?
           ORDER BY ar.id DESC""",
        (vid_id, video["game_id"], video["game_id"], video["file_path"]),
    ).fetchall()
    runs = [build_run_summary(row) for row in rows]
    primary_run = next((run for run in runs if run.get("run_kind") == "primary"), runs[-1] if runs else None)
    baseline_detection_count = primary_run["detection_count"] if primary_run else 0
    baseline_event_count = primary_run["event_count"] if primary_run else 0
    current_ai_settings = get_runtime_settings()["ai"]
    for run in runs:
        run["detection_delta"] = run["detection_count"] - baseline_detection_count
        run["event_delta"] = run["event_count"] - baseline_event_count

    return render_template(
        "analysis_compare.html",
        video=video,
        runs=runs,
        primary_run=primary_run,
        current_ai_settings=current_ai_settings,
        current_detector_model=display_detector_model(current_ai_settings),
        message=request.args.get("message"),
        error=request.args.get("error"),
        ai_runtime_available=ai_runtime_available(),
        ai_install_commands=ai_packages_install_commands(),
    )


def _video_analysis_runs_clause():
    return """(source_video_id=? OR base_analysis_key=? OR analysis_key=? OR video_path=?)"""


def _start_video_analysis_run(video, *, run_label=None):
    """Queue and optionally launch AI analysis for an existing video."""
    if not ai_runtime_available():
        return None, ai_packages_install_hint(), "ai_packages_unavailable"

    ensure_db()
    db = get_db()
    clause = _video_analysis_runs_clause()
    supersede_pending_analysis_runs(db, video)
    running = db.execute(
        f"""SELECT id FROM analysis_runs
            WHERE {clause} AND status='running'
            LIMIT 1""",
        (video["id"], video["game_id"], video["game_id"], video["file_path"]),
    ).fetchone()
    if running:
        return None, "Analysis already in progress", "already_running"

    video_ok, video_error = validate_video_for_analysis(video["file_path"])
    if not video_ok:
        return None, video_error, "invalid_video"

    runtime_settings = get_runtime_settings()
    models_ok, models_error = validate_ai_models_for_analysis(runtime_settings["ai"])
    if not models_ok:
        return None, models_error, "invalid_models"

    existing_runs = db.execute(
        f"SELECT COUNT(*) AS c FROM analysis_runs WHERE {clause}",
        (video["id"], video["game_id"], video["game_id"], video["file_path"]),
    ).fetchone()["c"]
    run_kind = "primary" if existing_runs == 0 else "rerun"
    if run_kind == "rerun":
        ensure_primary_run_metadata(db, video, build_analysis_settings_snapshot(runtime_settings))
    default_label = "NFHS / library video" if run_kind == "primary" else None
    run_payload = queue_analysis_run(
        db,
        video,
        runtime_settings,
        run_kind=run_kind,
        run_label=run_label or default_label,
    )

    try:
        start_analysis_subprocess(run_payload["analysis_key"], video["file_path"])
    except Exception as exc:
        db.execute(
            """UPDATE analysis_runs
               SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (f"Failed to start analysis worker: {exc}", run_payload["id"]),
        )
        db.commit()
        return None, f"Failed to start analysis worker: {exc}", "worker_start_failed"

    if run_kind == "rerun":
        message = f"Queued rerun '{run_payload['run_label']}'."
    else:
        message = f"AI analysis started ({run_payload['run_label']})."

    return {
        "status": "started",
        "game_id": run_payload["analysis_key"],
        "analysis_key": run_payload["analysis_key"],
        "run_label": run_payload["run_label"],
        "run_kind": run_kind,
        "message": message,
    }, None, None


@ai_bp.route("/api/videos/<int:vid_id>/analysis-debug")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_video_analysis_debug(vid_id):
    """Return latest analysis run + log tail for troubleshooting."""
    try:
        db = get_db()
        video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        clause = _video_analysis_runs_clause()
        row = db.execute(
            f"""SELECT * FROM analysis_runs
                WHERE {clause}
                ORDER BY id DESC LIMIT 1""",
            (vid_id, video["game_id"], video["game_id"], video["file_path"]),
        ).fetchone()
        game_id = video["game_id"]
        if row:
            game_id = row["analysis_key"] or video["game_id"]
            row = resolve_analysis_run_for_progress(db, game_id) or row

        if not row:
            return jsonify({
                "video_id": vid_id,
                "video_path": video["file_path"],
                "video_exists": os.path.exists(video["file_path"]),
                "run": None,
                "log_path": ai_analysis_log_path(game_id) if game_id else None,
                "log_tail": "",
            })

        game_id = row["analysis_key"] or game_id
        reconcile_stuck_analysis_run(db, game_id)
        row = db.execute("SELECT * FROM analysis_runs WHERE id=?", (row["id"],)).fetchone()
        log_path = ai_analysis_log_path(game_id)
        count_kwargs = dict(
            analysis_key=row["analysis_key"],
            relational_game_id=row["game_id"],
            video_game_id=video["game_id"],
            video_relational_game_id=video["relational_game_id"],
            base_analysis_key=row["base_analysis_key"],
            source_video_id=vid_id,
            video_path=video["file_path"],
        )
        detection_count = count_detections_for_analysis(db, **count_kwargs)
        event_count = count_events_for_analysis(
            db,
            analysis_key=count_kwargs["analysis_key"],
            relational_game_id=count_kwargs["relational_game_id"],
            video_game_id=count_kwargs["video_game_id"],
            base_analysis_key=count_kwargs["base_analysis_key"],
        )
        return jsonify({
            "video_id": vid_id,
            "video_path": video["file_path"],
            "video_exists": os.path.exists(video["file_path"]),
            "run": build_run_summary(row),
            "detection_count": detection_count,
            "event_count": event_count,
            "needs_event_regeneration": detection_count > 0 and event_count == 0,
            "log_path": log_path,
            "log_tail": _read_log_tail(log_path, 2000) if os.path.exists(log_path) else "",
        })
    except Exception as exc:
        current_app.logger.exception("analysis-debug failed for video %s", vid_id)
        return jsonify({
            "video_id": vid_id,
            "error": str(exc),
            "hint": "If analysis is still running (OCR/Rebuild), wait until Completed and try again.",
        }), 500


def _run_regenerate_events_worker(
    app,
    *,
    run_id: int,
    analysis_key: str,
    relational_game_id,
    lookup_kwargs: dict,
    video_path: str,
    db_path: str,
) -> None:
    """Background worker: rebuild events, enhanced analysis, and jersey OCR."""
    with app.app_context():
        db = get_db()
        try:
            from event_generator import main as generate_events

            db.execute(
                """UPDATE analysis_runs
                   SET progress_pct=35, progress_step='Clustering players and rebuilding events…'
                   WHERE id=?""",
                (run_id,),
            )
            db.commit()

            if generate_events(
                analysis_key,
                db_path,
                relational_game_id=relational_game_id,
                video_game_id=lookup_kwargs["video_game_id"],
                base_analysis_key=lookup_kwargs["base_analysis_key"],
                video_relational_game_id=lookup_kwargs["video_relational_game_id"],
                force_expanded=True,
            ) is False:
                raise RuntimeError(
                    "Event generation failed. Check logs for details, then click Rebuild again."
                )

            from helpers import assign_possessions_for_game
            if relational_game_id is not None:
                assign_possessions_for_game(db, relational_game_id, analysis_key=analysis_key)

            db.execute(
                """UPDATE analysis_runs
                   SET progress_pct=70, progress_step='Running enhanced analysis…'
                   WHERE id=?""",
                (run_id,),
            )
            db.commit()

            enhanced_warning = None
            try:
                import cv2
                from film_analysis import run_enhanced_analysis

                cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                cap.release()
                run_enhanced_analysis(db_path, analysis_key, fps)
            except Exception as exc:
                enhanced_warning = f"Enhanced analysis skipped: {exc}"[:500]

            db.execute(
                """UPDATE analysis_runs
                   SET progress_pct=85, progress_step='Scanning jersey numbers (OCR)…'
                   WHERE id=?""",
                (run_id,),
            )
            db.commit()

            try:
                from settings_store import load_all_settings, AI_DEFAULTS
                from track_identity import run_identity_postprocess

                ai_settings = load_all_settings({}, {}, AI_DEFAULTS, db=db).get("ai", AI_DEFAULTS)
                run_identity_postprocess(
                    db, analysis_key, ai_settings, video_path=video_path,
                )
            except Exception as exc:
                app.logger.warning("Identity postprocess after regenerate failed: %s", exc)

            db.execute(
                """UPDATE analysis_runs
                   SET status='completed', progress_pct=100, progress_step=?,
                       completed_at=CURRENT_TIMESTAMP, error_message=?
                   WHERE id=?""",
                (
                    "Done" if not enhanced_warning else "Events regenerated (enhanced analysis skipped)",
                    enhanced_warning,
                    run_id,
                ),
            )
            db.commit()
        except Exception as exc:
            app.logger.exception("Rebuild events failed for %s", analysis_key)
            from helpers import format_exception_message

            db.execute(
                """UPDATE analysis_runs
                   SET status='failed',
                       error_message=?,
                       progress_step='Event generation failed',
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (format_exception_message(exc), run_id),
            )
            db.commit()
        finally:
            db.close()


@ai_bp.route("/api/videos/<int:vid_id>/regenerate-events", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_regenerate_video_events(vid_id):
    """Rebuild events from existing detections without re-running YOLO."""
    try:
        db = get_db()
        video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404

        clause = _video_analysis_runs_clause()
        row = db.execute(
            f"""SELECT * FROM analysis_runs
                WHERE {clause}
                ORDER BY id DESC LIMIT 1""",
            (vid_id, video["game_id"], video["game_id"], video["file_path"]),
        ).fetchone()
        if not row:
            return jsonify({"error": "No analysis run found for this video"}), 404

        if row["status"] in {"running", "pending"}:
            return jsonify({
                "error": "Analysis is already running for this video.",
                "code": "already_running",
                "analysis_key": row["analysis_key"] or video["game_id"],
            }), 409

        analysis_key = row["analysis_key"] or video["game_id"]
        relational_game_id = row["game_id"]
        run_id = row["id"]
        db_path = current_app.config["DATABASE"]
        lookup_kwargs = dict(
            analysis_key=analysis_key,
            relational_game_id=relational_game_id,
            video_game_id=video["game_id"],
            video_relational_game_id=video["relational_game_id"],
            base_analysis_key=row["base_analysis_key"],
            source_video_id=vid_id,
            video_path=video["file_path"],
        )
        expected_detections = count_detections_for_analysis(db, **lookup_kwargs)
        if expected_detections == 0:
            return jsonify({
                "error": (
                    "No saved detections found for this video. "
                    "Run full AI analysis first, then use Rebuild."
                ),
                "code": "no_detections",
            }), 400

        db.execute(
            """UPDATE analysis_runs
               SET status='running', progress_pct=10, progress_step='Loading detections…',
                   error_message=NULL, completed_at=NULL
               WHERE id=?""",
            (run_id,),
        )
        db.commit()

        log_path = ai_analysis_log_path(analysis_key)
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"\n[{datetime.utcnow().isoformat()}Z] Rebuild events started in background.\n")
        except OSError:
            pass

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_run_regenerate_events_worker,
            kwargs={
                "app": app,
                "run_id": run_id,
                "analysis_key": analysis_key,
                "relational_game_id": relational_game_id,
                "lookup_kwargs": lookup_kwargs,
                "video_path": video["file_path"],
                "db_path": db_path,
            },
            daemon=True,
            name=f"rebuild-events-{vid_id}",
        )
        thread.start()

        return jsonify({
            "status": "rebuild_started",
            "analysis_key": analysis_key,
            "detection_count": expected_detections,
            "message": (
                f"Rebuild started in background from {expected_detections:,} saved detections. "
                "Watch AI Status on this page — may take several minutes on long games."
            ),
        }), 202
    except Exception as exc:
        current_app.logger.exception("Could not start rebuild for video %s", vid_id)
        return jsonify({
            "error": str(exc),
            "code": "rebuild_start_failed",
        }), 500


@ai_bp.route("/api/videos/<int:vid_id>/analyze", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_start_video_analysis(vid_id):
    """Start AI analysis for a video already in the library (e.g. NFHS download)."""
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    payload, error, error_code = _start_video_analysis_run(video)
    if error:
        status = 503 if error_code == "ai_packages_unavailable" else 409
        return jsonify({"error": error, "code": error_code}), status
    return jsonify(payload)


@ai_bp.route("/videos/<int:vid_id>/rerun", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def rerun_video_analysis(vid_id):
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        abort(404)

    run_payload, error, error_code = _start_video_analysis_run(
        video,
        run_label=request.form.get("run_label"),
    )
    if error:
        return redirect(url_for(
            "ai.compare_video_analysis",
            vid_id=vid_id,
            error=error,
        ))

    return redirect(url_for(
        "ai.compare_video_analysis",
        vid_id=vid_id,
        message=run_payload["message"],
    ))


@ai_bp.route("/api/check_duplicate")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_check_duplicate():
    """Check if a filename has been uploaded before."""
    original_filename = request.args.get("filename", "")
    if not original_filename:
        return jsonify({"is_duplicate": False})
    db = get_db()
    rows = db.execute(
        "SELECT id, stored_filename, opponent, upload_timestamp FROM videos WHERE original_filename=? ORDER BY id DESC",
        (secure_filename(original_filename),),
    ).fetchall()
    if rows:
        return jsonify({
            "is_duplicate": True,
            "previous_uploads": [dict(r) for r in rows],
        })
    return jsonify({"is_duplicate": False})


@ai_bp.route("/api/videos/<int:vid_id>", methods=["DELETE"])
@require_feature("ENABLE_AUTO_STATS_M1")
def delete_video(vid_id):
    """Delete a video record, its file on disk, and all related analysis data."""
    db = get_db()
    row = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    game_id = row["game_id"]
    file_path = row["file_path"]
    run_keys = [
        (run["analysis_key"], run["game_id"])
        for run in db.execute(
            "SELECT analysis_key, game_id FROM analysis_runs WHERE source_video_id=? OR base_analysis_key=? OR analysis_key=? OR video_path=?",
            (vid_id, game_id, game_id, file_path),
        ).fetchall()
    ] or [(game_id, None)]

    # Delete file from disk
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass  # Don't fail if file already gone

    # Null out duplicate_of_id references to this video (FK constraint)
    db.execute("UPDATE videos SET duplicate_of_id=NULL WHERE duplicate_of_id=?", (vid_id,))

    # Delete all related analysis data
    # Delete all related analysis data
    for run_game_id, relational_game_id in run_keys:
        db.execute("DELETE FROM events WHERE game_id=? AND human_verified = 0", (run_game_id,))
        db.execute(
            """DELETE FROM detections
               WHERE (relational_game_id = ?)
                  OR (relational_game_id IS NULL AND game_id = ?)""",
            (relational_game_id, run_game_id),
        )
        db.execute("DELETE FROM stats WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM stats WHERE game_id=?", (run_game_id,))
    db.execute("DELETE FROM analysis_runs WHERE source_video_id=? OR base_analysis_key=? OR analysis_key=? OR video_path=?", (vid_id, game_id, game_id, file_path))
    db.execute("DELETE FROM videos WHERE id=?", (vid_id,))
    db.commit()

    return jsonify({"success": True, "deleted_game_id": game_id})


@ai_bp.route("/api/videos/<int:vid_id>/trim", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_trim_video(vid_id):
    """Trim a saved video to a start/end range; writes a new library copy."""
    from video_trim import ffmpeg_available, ffprobe_duration_ms, parse_time_input, start_trim_job

    if not ffmpeg_available():
        return jsonify({
            "error": "ffmpeg is not installed. Install ffmpeg and restart the app.",
            "code": "ffmpeg_missing",
        }), 503

    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404

    data = request.get_json(silent=True) or {}
    start_ms = data.get("start_ms")
    end_ms = data.get("end_ms")
    if start_ms is None and data.get("start"):
        start_ms = parse_time_input(data.get("start"))
    if end_ms is None and data.get("end"):
        end_ms = parse_time_input(data.get("end"))
    try:
        start_ms = int(start_ms)
        end_ms = int(end_ms)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid start_ms/end_ms"}), 400

    if start_ms < 0 or end_ms <= start_ms:
        return jsonify({"error": "End time must be after start time"}), 400

    duration_ms = ffprobe_duration_ms(video["file_path"])
    if duration_ms is not None and end_ms > duration_ms + 1000:
        return jsonify({"error": "End time is past the end of the video"}), 400

    label = (data.get("label") or "trimmed").strip() or "trimmed"
    job_id = start_trim_job(
        app=current_app._get_current_object(),
        video_row=dict(video),
        start_ms=start_ms,
        end_ms=end_ms,
        label=label,
    )
    return jsonify({
        "status": "started",
        "job_id": job_id,
        "message": "Trim started. This may take a few minutes for long files.",
    })


@ai_bp.route("/api/videos/trim/<job_id>", methods=["GET"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_trim_video_status(job_id):
    from video_trim import get_trim_job

    job = get_trim_job(job_id)
    if not job:
        return jsonify({"error": "Trim job not found or expired"}), 404
    return jsonify(job)


@ai_bp.route("/api/videos/<int:vid_id>/meta", methods=["GET"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_video_meta(vid_id):
    """Return duration and paths for the trim editor."""
    from video_trim import ffprobe_duration_ms

    video = get_db().execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        return jsonify({"error": "Video not found"}), 404
    duration_ms = ffprobe_duration_ms(video["file_path"])
    return jsonify({
        "id": video["id"],
        "original_filename": video["original_filename"],
        "stored_filename": video["stored_filename"],
        "opponent": video["opponent"],
        "file_size_bytes": video["file_size_bytes"],
        "duration_ms": duration_ms,
        "video_url": url_for("core.uploaded_file", filename=video["stored_filename"]),
    })


@ai_bp.route("/upload", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def upload_and_analyze():
    """Handle the film tool's 'Upload and Analyze' form (posts to /upload)."""
    if "video" not in request.files:
        return "No video file provided", 400
    f = request.files["video"]
    if not f.filename:
        return "Empty filename", 400

    opponent = request.form.get("opponent", "unknown").strip() or "unknown"
    original_filename = secure_filename(f.filename)
    stem, ext = os.path.splitext(original_filename)

    # ── Timestamped stored filename ───────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_filename = f"{stem}_{ts}{ext}"
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename)
    f.save(dest)
    file_size = os.path.getsize(dest)

    # ── Duplicate detection ───────────────────────────────────
    db = get_db()
    prior = db.execute(
        "SELECT id, stored_filename, upload_timestamp FROM videos WHERE original_filename=? ORDER BY id DESC LIMIT 1",
        (original_filename,),
    ).fetchone()
    is_dup = prior is not None
    dup_of_id = prior["id"] if prior else None
    dup_msg = ""
    if is_dup:
        dup_msg = (
            f"<p style='background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;"
            f"padding:10px 14px;margin-top:12px;'>⚠️ <strong>Duplicate detected</strong> — "
            f"<em>{original_filename}</em> was previously uploaded as "
            f"<code>{prior['stored_filename']}</code> on {prior['upload_timestamp']}. "
            f"This upload has been saved with a new timestamp.</p>"
        )

    # ── game_id & DB records ─────────────────────────────────
    game_id = f"{opponent.lower().replace(' ', '_')}_{stem}_{ts}"

    # Resolve relational_game_id from games table
    try:
        gid_int = int(game_id)
        row = db.execute("SELECT id FROM games WHERE id = ?", (gid_int,)).fetchone()
        relational_game_id = row[0] if row else None
    except (TypeError, ValueError):
        relational_game_id = None

    video_cur = db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, relational_game_id, is_duplicate, duplicate_of_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (original_filename, stored_filename, dest, file_size,
         opponent, game_id, relational_game_id, int(is_dup), dup_of_id),
    )
    video_row = db.execute(
        "SELECT * FROM videos WHERE id=?",
        (video_cur.lastrowid,),
    ).fetchone()
    runtime_settings = get_runtime_settings()
    run_payload = queue_analysis_run(
        db,
        video_row,
        runtime_settings,
        run_kind="primary",
        run_label="Original upload",
    )
    run_id = run_payload["id"]

    # ── Launch AI subprocess ──────────────────────────────────
    if ai_runtime_available():
        start_analysis_subprocess(run_payload["analysis_key"], dest)
        ai_msg = "✅ AI analysis running in background — check <a href='/status'>Status page</a> for progress."
    else:
        db.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            ("Missing AI packages (cv2/ultralytics)", run_id),
        )
        db.commit()
        ai_msg = "⚠️ AI analysis unavailable — missing opencv-python or ultralytics."

    film_url = url_for("core.film", filename=stored_filename, game_id=game_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({
            "status": "uploaded",
            "stored_filename": stored_filename,
            "game_id": game_id,
            "redirect_url": film_url,
            "analysis_message": ai_msg,
        })

    return f"""<!DOCTYPE html>
    <html><head>
    <meta http-equiv="refresh" content="4;url={film_url}">
    <style>
      body{{font-family:sans-serif;padding:40px;background:#f7f6f2;max-width:640px;margin:auto;}}
      .card{{background:#fff;border:1px solid #e2e0da;border-radius:8px;padding:28px;margin-top:24px;}}
      code{{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:.9em;}}
      .nav a{{margin-right:16px;color:#01696f;text-decoration:none;font-weight:500;}}
      .report-link{{display:inline-block;padding:8px 12px;border-radius:999px;background:linear-gradient(135deg,#f59e0b,#ef4444,#ec4899);color:#fff !important;font-weight:700;box-shadow:0 8px 20px rgba(239,68,68,.25);}}
    </style>
    </head><body>
    <div class="nav"><a href="/">⬅ Dashboard</a><a href="/videos">📹 All Videos</a><a href="/status">📊 Status</a><a href="/debug">🛠 Debug / Issues</a><a href="/debug?compose=1&source=/upload" class="report-link">Report Bug / Idea</a></div>
    <div class="card">
      <h2>📹 Upload complete</h2>
      <p><strong>Original filename:</strong> {original_filename}</p>
      <p><strong>Stored as:</strong> <code>{stored_filename}</code></p>
      <p><strong>Opponent:</strong> {opponent}</p>
      <p><strong>Game ID:</strong> <code>{game_id}</code></p>
      <p><strong>File size:</strong> {file_size/1_000_000:.1f} MB</p>
      {dup_msg}
      <p style="margin-top:16px;">{ai_msg}</p>
      <p style="margin-top:20px;color:#6b7280;font-size:.9em;">
        Redirecting to film tool in 4 seconds…
        <a href="{film_url}">click here</a> to go now.
      </p>
      <p><a href="/videos">📹 View all uploaded videos</a> &nbsp;|&nbsp; <a href="/status">📊 Analysis status</a></p>
    </div>
    </body></html>
    """


@ai_bp.route("/upload_only", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def upload_only():
    """Upload a video for manual tagging only (no AI analysis)."""
    if "video" not in request.files:
        return "No video file provided", 400
    f = request.files["video"]
    if not f.filename:
        return "Empty filename", 400

    opponent = request.form.get("opponent", "unknown").strip() or "unknown"
    original_filename = secure_filename(f.filename)
    stem, ext = os.path.splitext(original_filename)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_filename = f"{stem}_{ts}{ext}"
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename)
    f.save(dest)
    file_size = os.path.getsize(dest)

    db = get_db()
    game_id = f"{opponent.lower().replace(' ', '_')}_{stem}_{ts}"

    # Resolve relational_game_id from games table
    try:
        gid_int = int(game_id)
        row = db.execute("SELECT id FROM games WHERE id = ?", (gid_int,)).fetchone()
        relational_game_id = row[0] if row else None
    except (TypeError, ValueError):
        relational_game_id = None

    db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, relational_game_id, is_duplicate, duplicate_of_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (original_filename, stored_filename, dest, file_size, opponent, game_id, relational_game_id, 0, None),
    )
    db.commit()

    film_url = url_for("core.film", filename=stored_filename, game_id=game_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({
            "status": "uploaded",
            "stored_filename": stored_filename,
            "game_id": game_id,
            "redirect_url": film_url,
            "analysis_message": None,
        })

    return f"""<!DOCTYPE html>
    <html><head>
    <meta http-equiv="refresh" content="4;url={film_url}">
    <style>
      body{{font-family:sans-serif;padding:40px;background:#f7f6f2;max-width:640px;margin:auto;}}
      .card{{background:#fff;border:1px solid #e2e0da;border-radius:8px;padding:28px;margin-top:24px;}}
      code{{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:.9em;}}
      .nav a{{margin-right:16px;color:#01696f;text-decoration:none;font-weight:500;}}
    </style>
    </head><body>
    <div class="nav"><a href="/">⬅ Dashboard</a><a href="/videos">📹 All Videos</a></div>
    <div class="card">
      <h2>📹 Upload complete</h2>
      <p><strong>Original filename:</strong> {original_filename}</p>
      <p><strong>Stored as:</strong> <code>{stored_filename}</code></p>
      <p><strong>Opponent:</strong> {opponent}</p>
      <p><strong>File size:</strong> {file_size/1_000_000:.1f} MB</p>
      <p style="margin-top:16px;">Ready for manual tagging.</p>
      <p style="margin-top:20px;color:#6b7280;font-size:.9em;">
        Redirecting to film tool in 4 seconds…
        <a href="{film_url}">click here</a> to go now.
      </p>
    </div>
    </body></html>
    """


@ai_bp.route("/api/assistant/query", methods=["POST"])
@require_feature("ENABLE_ASSISTANT_READ_ONLY")
def assistant_query_route():
    """Answer coach questions from trusted reviewed events, stats, and clips."""
    db = get_db()
    from module_entitlements import enforce_module_access
    from module_keys import AI_ASSIST
    from assistant_query import answer_question

    enforce_module_access(db, get_default_team_id(db), AI_ASSIST)

    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    game_id = data.get("game_id")
    if game_id is None:
        return jsonify({"error": "game_id is required"}), 400

    player = data.get("player")
    payload = answer_question(db, question=question, game_id=game_id, player=player)
    return jsonify(payload)


def _assistant_access(db):
    from module_entitlements import enforce_module_access
    from module_keys import AI_ASSIST

    enforce_module_access(db, get_default_team_id(db), AI_ASSIST)


@ai_bp.route("/assistant")
@require_feature("ENABLE_ASSISTANT_READ_ONLY")
def assistant_workflow_page():
    """Dropdown-guided workflow: game → player → clip list."""
    db = get_db()
    _assistant_access(db)
    return render_template("assistant_workflow.html")


@ai_bp.route("/api/assistant/workflow/games")
@require_feature("ENABLE_ASSISTANT_READ_ONLY")
def assistant_workflow_games():
    db = get_db()
    _assistant_access(db)
    from assistant_workflow import build_workflow_payload

    return jsonify(build_workflow_payload("games", db))


@ai_bp.route("/api/assistant/workflow/games/<int:game_id>/players")
@require_feature("ENABLE_ASSISTANT_READ_ONLY")
def assistant_workflow_players(game_id):
    db = get_db()
    _assistant_access(db)
    from assistant_workflow import build_workflow_payload

    payload = build_workflow_payload("players", db, game_id=game_id)
    if payload.get("error"):
        return jsonify(payload), 404
    return jsonify(payload)


@ai_bp.route("/api/assistant/workflow/games/<int:game_id>/clips")
@require_feature("ENABLE_ASSISTANT_READ_ONLY")
def assistant_workflow_clips(game_id):
    db = get_db()
    _assistant_access(db)
    from assistant_workflow import build_workflow_payload

    player = (request.args.get("player") or "").strip() or None
    payload = build_workflow_payload("clips", db, game_id=game_id, player=player)
    if payload.get("error"):
        return jsonify(payload), 404
    return jsonify(payload)

