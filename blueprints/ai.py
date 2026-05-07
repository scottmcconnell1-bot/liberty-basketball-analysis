"""
AI and Video Analysis Blueprint.

Routes:
  GET  /api/analysis_status/<game_id>  - Analysis status for a game
  GET  /api/stats/<game_id>            - Stats for a game
  POST /api/upload_video               - Upload a video file
  GET  /api/videos                     - List all videos
  GET  /videos/<int:vid_id>/compare    - Compare video analysis
  POST /videos/<int:vid_id>/rerun      - Re-run video analysis
  GET  /api/check_duplicate            - Check for duplicate videos
  DELETE /api/videos/<int:vid_id>      - Delete a video
  POST /api/admin/reset                - Admin reset
  POST /upload                         - Upload and analyze
"""

import os
from datetime import datetime
from flask import (
    Blueprint, current_app, jsonify, redirect, render_template,
    request, url_for, abort
)
from werkzeug.utils import secure_filename

from helpers import (
    AI_DEFAULTS, ai_runtime_available, analysis_option_enabled, append_query_params, build_analysis_settings_snapshot,
    build_resource_status, build_rerun_game_id, build_run_summary,
    build_settings_catalog, default_run_label, display_detector_model,
    ensure_primary_run_metadata, extract_local_path, get_db,
    get_runtime_settings, queue_analysis_run, require_feature,
    resolve_detector_model, safe_return_path, start_analysis_subprocess
)

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/analysis_status/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_status(game_id):
    db = get_db()
    row = db.execute(
        """SELECT status, started_at, completed_at, error_message, settings_json,
                  (SELECT COUNT(*) FROM detections WHERE game_id = analysis_runs.game_id) AS detection_count,
                  (SELECT COUNT(*) FROM events WHERE game_id = analysis_runs.game_id) AS event_count
           FROM analysis_runs WHERE game_id=? ORDER BY id DESC LIMIT 1""",
        (game_id,),
    ).fetchone()
    if row is None:
        return jsonify({
            "status": "not_started",
            "detection_count": 0,
            "event_count": 0,
            "event_generation_summary": "AI analysis has not started yet.",
            "auto_event_persistence_enabled": analysis_option_enabled("USE_DRIBBLE_EVENTS"),
        })

    payload = dict(row)
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
            "blocks, fouls, and dribbles from those detections."
        )
    else:
        payload["event_generation_summary"] = (
            "YOLO currently detects players and the ball. Auto-tagged events come from the legacy "
            "dribble-only heuristic, so a completed upload can still show zero tagged events."
        )
    payload["auto_event_persistence_enabled"] = analysis_option_enabled("USE_DRIBBLE_EVENTS")
    return jsonify(payload)


# ── API: Stats ────────────────────────────────────────────

@ai_bp.route("/api/stats/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_stats(game_id):
    from stats import refresh_stats
    db = get_db()
    return jsonify(refresh_stats(db, game_id))


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


@ai_bp.route("/api/videos")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_videos():
    """Return all videos from the DB with their analysis status."""
    db = get_db()
    rows = db.execute("""
        SELECT v.*, ar.status as analysis_status, ar.error_message,
               (SELECT COUNT(*) FROM detections d WHERE d.game_id = v.game_id) as detection_count,
               (SELECT COUNT(*) FROM events e WHERE e.game_id = v.game_id) as event_count,
               (SELECT COUNT(*) FROM analysis_runs ar2 WHERE ar2.source_video_id = v.id OR ar2.base_game_id = v.game_id OR ar2.video_path = v.file_path) as analysis_run_count
        FROM videos v
        LEFT JOIN analysis_runs ar ON ar.game_id = v.game_id
                                   AND ar.id = (SELECT MAX(id) FROM analysis_runs WHERE game_id = v.game_id)
        ORDER BY v.id DESC
    """).fetchall()
    return jsonify([dict(r) for r in rows])


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
                  (SELECT COUNT(*) FROM detections d WHERE d.game_id = ar.game_id) AS detection_count,
                  (SELECT COUNT(*) FROM events e WHERE e.game_id = ar.game_id) AS event_count
           FROM analysis_runs ar
           WHERE ar.source_video_id = ?
              OR ar.base_game_id = ?
              OR ar.game_id = ?
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
    )


@ai_bp.route("/videos/<int:vid_id>/rerun", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def rerun_video_analysis(vid_id):
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        abort(404)

    runtime_settings = get_runtime_settings()
    ensure_primary_run_metadata(db, video, build_analysis_settings_snapshot(runtime_settings))
    run_payload = queue_analysis_run(
        db,
        video,
        runtime_settings,
        run_kind="rerun",
        run_label=request.form.get("run_label"),
    )

    if ai_runtime_available():
        start_analysis_subprocess(run_payload["game_id"], video["file_path"])
        message = f"Queued rerun '{run_payload['run_label']}'."
    else:
        db.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            ("Missing AI packages (cv2/ultralytics)", run_payload["id"]),
        )
        db.commit()
        message = "Rerun saved, but AI packages are unavailable in the current runtime."

    return redirect(url_for("ai.compare_video_analysis", vid_id=vid_id, message=message))


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
    run_game_ids = [
        run["game_id"]
        for run in db.execute(
            "SELECT game_id FROM analysis_runs WHERE source_video_id=? OR base_game_id=? OR video_path=?",
            (vid_id, game_id, file_path),
        ).fetchall()
    ] or [game_id]

    # Delete file from disk
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass  # Don't fail if file already gone

    # Delete all related analysis data
    for run_game_id in run_game_ids:
        db.execute("DELETE FROM events WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM detections WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM stats WHERE game_id=?", (run_game_id,))
    db.execute("DELETE FROM analysis_runs WHERE source_video_id=? OR base_game_id=? OR video_path=?", (vid_id, game_id, file_path))
    db.execute("DELETE FROM videos WHERE id=?", (vid_id,))
    db.commit()

    return jsonify({"success": True, "deleted_game_id": game_id})



    # Collect file paths before deleting
    rows = db.execute("SELECT file_path FROM videos").fetchall()
    for row in rows:
        fp = row["file_path"]
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

    # Clear all analysis/video data (preserve seasons, games, players)
    db.executescript("""
        DELETE FROM events;
        DELETE FROM detections;
        DELETE FROM analysis_runs;
        DELETE FROM stats;
        DELETE FROM videos;
    """)
    db.commit()

    return jsonify({"success": True, "message": "All video data cleared."})


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

    video_cur = db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, is_duplicate, duplicate_of_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (original_filename, stored_filename, dest, file_size,
         opponent, game_id, int(is_dup), dup_of_id),
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
        start_analysis_subprocess(game_id, dest)
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

