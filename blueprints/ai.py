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
    AI_DEFAULTS, ai_runtime_available, append_query_params, build_analysis_settings_snapshot,
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
    return jsonify({
        "basic": basic,
        "enhanced": enhanced,
    })


# ── API: Analysis Progress ──────────────────────────────────

@ai_bp.route("/api/analysis_progress/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_progress(game_id):
    """Return current analysis progress for a game."""
    db = get_db()
    row = db.execute(
        """SELECT status, progress_pct, progress_step, started_at, completed_at,
                  (SELECT COUNT(*) FROM detections WHERE game_id = analysis_runs.game_id) AS detection_count,
                  (SELECT COUNT(*) FROM events WHERE game_id = analysis_runs.game_id) AS event_count
           FROM analysis_runs WHERE game_id=? ORDER BY id DESC LIMIT 1""",
        (game_id,),
    ).fetchone()
    if row is None:
        return jsonify({"status": "not_started", "progress_pct": 0, "progress_step": ""})
    return jsonify({
        "status": row["status"],
        "progress_pct": row["progress_pct"] or 0,
        "progress_step": row["progress_step"] or "",
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "detection_count": row["detection_count"],
        "event_count": row["event_count"],
    })


# ── API: Full Analysis Results ──────────────────────────────

@ai_bp.route("/api/analysis/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_results(game_id):
    """Return full analysis results: box score, shots, plays, player effect."""
    from stats import refresh_stats, get_enhanced_stats
    db = get_db()
    basic = refresh_stats(db, game_id)
    enhanced = get_enhanced_stats(db, game_id)

    # Events summary
    events_summary = db.execute("""
        SELECT event_type, COUNT(*) as cnt
        FROM events WHERE game_id=?
        GROUP BY event_type ORDER BY cnt DESC
    """, (game_id,)).fetchall()

    # Top events timeline (last 50)
    recent_events = db.execute("""
        SELECT event_type, player, shot_result, timestamp_ms, details_json
        FROM events WHERE game_id=?
        ORDER BY timestamp_ms DESC LIMIT 50
    """, (game_id,)).fetchall()

    return jsonify({
        "game_id": game_id,
        "basic_stats": basic,
        "enhanced": enhanced,
        "events_summary": [dict(e) for e in events_summary],
        "recent_events": [dict(e) for e in recent_events],
    })


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

        db.execute(
            """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                                   opponent, game_id, is_duplicate, duplicate_of_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (safe_name, stored_filename, dest, file_size, opponent, game_id, int(is_dup), dup_of_id),
        )
        db.commit()

        return jsonify({
            "status": "complete",
            "filename": stored_filename,
            "redirect_url": url_for("ai.upload_and_analyze") + f"?video={stored_filename}",
        })

    return jsonify({"status": "chunk_received", "received": received, "total": total_chunks})


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

    # Null out duplicate_of_id references to this video (FK constraint)
    db.execute("UPDATE videos SET duplicate_of_id=NULL WHERE duplicate_of_id=?", (vid_id,))

    # Delete all related analysis data
    for run_game_id in run_game_ids:
        db.execute("DELETE FROM events WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM detections WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM stats WHERE game_id=?", (run_game_id,))
    db.execute("DELETE FROM analysis_runs WHERE source_video_id=? OR base_game_id=? OR video_path=?", (vid_id, game_id, file_path))
    db.execute("DELETE FROM videos WHERE id=?", (vid_id,))
    db.commit()

    return jsonify({"success": True, "deleted_game_id": game_id})


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

    db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, is_duplicate, duplicate_of_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (original_filename, stored_filename, dest, file_size, opponent, game_id, 0, None),
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

