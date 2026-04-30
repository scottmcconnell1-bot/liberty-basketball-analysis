import os
import sqlite3
import subprocess

from flask import (
    Flask, g, render_template, request,
    send_from_directory, jsonify, current_app,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────
app.config.setdefault("DATABASE", "film_analysis.db")
app.config.setdefault("UPLOAD_FOLDER", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Database helpers ──────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql", mode="r") as f:
        db.executescript(f.read())
    db.commit()
    _ensure_migration_columns(db)


def _ensure_migration_columns(db):
    """Add new columns to existing tables without wiping data."""
    migrations = [
        ("events", "source_video",   "ALTER TABLE events ADD COLUMN source_video TEXT"),
        ("events", "source_frame",   "ALTER TABLE events ADD COLUMN source_frame INTEGER"),
        ("events", "human_verified", "ALTER TABLE events ADD COLUMN human_verified INTEGER NOT NULL DEFAULT 0"),
        ("events", "confidence",     "ALTER TABLE events ADD COLUMN confidence REAL"),
    ]
    existing = {
        (row[1], row[2]): True
        for row in db.execute(
            "SELECT type, tbl_name, name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table, col, sql in migrations:
        try:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                db.execute(sql)
        except Exception:
            pass
    db.commit()


@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        init_db()
    print("Initialized the database.")


@app.before_request
def ensure_db():
    if not os.path.exists(current_app.config["DATABASE"]):
        init_db()


# ── Page routes ───────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/schedule")
def schedule():
    return render_template("schedule.html")


@app.route("/film")
@app.route("/film/<filename>")
def film(filename=None):
    game_id = None
    if filename:
        db = get_db()
        # Find the most recent analysis run for this video file
        row = db.execute(
            "SELECT game_id FROM analysis_runs WHERE video_path LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{filename}",),
        ).fetchone()
        if row:
            game_id = row["game_id"]
    return render_template("film_tool.html", filename=filename, game_id=game_id)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


# ── API: Dashboard ────────────────────────────────────────

@app.route("/api/dashboard")
def api_dashboard():
    db = get_db()
    seasons   = db.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
    scheduled = db.execute("SELECT COUNT(*) FROM scheduled_games").fetchone()[0]
    events    = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    players   = db.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    upcoming  = db.execute(
        """SELECT * FROM scheduled_games
           WHERE game_date >= date('now') AND status != 'cancelled'
           ORDER BY game_date, game_time LIMIT 5"""
    ).fetchall()
    recent    = db.execute(
        "SELECT * FROM events ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    return jsonify({
        "seasons":       seasons,
        "scheduled":     scheduled,
        "events":        events,
        "players":       players,
        "upcoming_games": [dict(r) for r in upcoming],
        "recent_events":  [dict(r) for r in recent],
    })


# ── API: Seasons ──────────────────────────────────────────

@app.route("/api/seasons", methods=["GET"])
def api_seasons_list():
    db = get_db()
    rows = db.execute("SELECT * FROM seasons ORDER BY start_date DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/seasons", methods=["POST"])
def api_seasons_create():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    start = data.get("start_date", "")
    end   = data.get("end_date", "")
    if not name or not start or not end:
        return jsonify({"error": "name, start_date, end_date required"}), 400
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
            (name, start, end),
        )
        db.commit()
        row = db.execute("SELECT * FROM seasons WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Season name already exists"}), 409


@app.route("/api/seasons/<int:season_id>", methods=["GET"])
def api_season_get(season_id):
    db = get_db()
    row = db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/seasons/<int:season_id>", methods=["PUT"])
def api_season_update(season_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    name  = data.get("name", row["name"])
    start = data.get("start_date", row["start_date"])
    end   = data.get("end_date", row["end_date"])
    db.execute(
        "UPDATE seasons SET name=?, start_date=?, end_date=? WHERE id=?",
        (name, start, end, season_id),
    )
    db.commit()
    return jsonify(dict(db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()))


@app.route("/api/seasons/<int:season_id>", methods=["DELETE"])
def api_season_delete(season_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE season_id=?", (season_id,))
    db.execute("DELETE FROM seasons WHERE id=?", (season_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Scheduled Games ──────────────────────────────────

@app.route("/api/scheduled_games", methods=["GET"])
def api_scheduled_games_list():
    db = get_db()
    season_id = request.args.get("season_id")
    if season_id:
        rows = db.execute(
            "SELECT * FROM scheduled_games WHERE season_id=? ORDER BY game_date, game_time",
            (season_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM scheduled_games ORDER BY game_date, game_time"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/scheduled_games", methods=["POST"])
def api_scheduled_games_create():
    data = request.get_json(force=True)
    required = ("season_id", "game_date", "opponent_name")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, gender, level, game_date, game_time,
            location_type, opponent_name, tournament_name, status, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["season_id"],
            data.get("program_name", "Liberty"),
            data.get("gender", "boys"),
            data.get("level", "jr_high"),
            data["game_date"],
            data.get("game_time"),
            data.get("location_type", "home"),
            data["opponent_name"],
            data.get("tournament_name"),
            data.get("status", "scheduled"),
            data.get("notes"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/scheduled_games/<int:game_id>", methods=["GET"])
def api_scheduled_game_get(game_id):
    db = get_db()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/scheduled_games/<int:game_id>", methods=["PUT"])
def api_scheduled_game_update(game_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        """UPDATE scheduled_games SET
           season_id=?, program_name=?, gender=?, level=?, game_date=?, game_time=?,
           location_type=?, opponent_name=?, tournament_name=?, status=?, notes=?,
           updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            data.get("season_id", row["season_id"]),
            data.get("program_name", row["program_name"]),
            data.get("gender", row["gender"]),
            data.get("level", row["level"]),
            data.get("game_date", row["game_date"]),
            data.get("game_time", row["game_time"]),
            data.get("location_type", row["location_type"]),
            data.get("opponent_name", row["opponent_name"]),
            data.get("tournament_name", row["tournament_name"]),
            data.get("status", row["status"]),
            data.get("notes", row["notes"]),
            game_id,
        ),
    )
    db.commit()
    return jsonify(dict(db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()))


@app.route("/api/scheduled_games/<int:game_id>", methods=["DELETE"])
def api_scheduled_game_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE id=?", (game_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Events (film tagger) ─────────────────────────────

@app.route("/api/save_event", methods=["POST"])
def save_event():
    data = request.get_json(force=True)
    if not data or "timestamp_ms" not in data:
        return jsonify({"status": "error", "message": "timestamp_ms required"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO events
           (game_id, player, event_type, shot_result, timestamp_ms, details_json,
            source_video, source_frame, human_verified, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("game_id", "default_game"),
            data.get("player"),
            data.get("event_type"),
            data.get("shot_result"),
            data["timestamp_ms"],
            data.get("details_json"),
            data.get("source_video"),
            data.get("source_frame"),
            int(bool(data.get("human_verified", True))),
            data.get("confidence"),
        ),
    )
    db.commit()
    return jsonify({"status": "success", "id": cur.lastrowid})


@app.route("/api/events/<game_id>", methods=["GET"])
def get_events(game_id):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM events WHERE game_id=? ORDER BY timestamp_ms ASC", (game_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/events/<int:event_id>", methods=["PUT"])
def update_event(event_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        """UPDATE events SET player=?, event_type=?, shot_result=?,
           timestamp_ms=?, details_json=?, human_verified=?, confidence=?
           WHERE id=?""",
        (
            data.get("player", row["player"]),
            data.get("event_type", row["event_type"]),
            data.get("shot_result", row["shot_result"]),
            data.get("timestamp_ms", row["timestamp_ms"]),
            data.get("details_json", row["details_json"]),
            int(bool(data.get("human_verified", row["human_verified"]))),
            data.get("confidence", row["confidence"]),
            event_id,
        ),
    )
    db.commit()
    return jsonify(dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()))


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Players ──────────────────────────────────────────

@app.route("/api/players", methods=["GET"])
def api_players_list():
    db = get_db()
    season_id = request.args.get("season_id")
    if season_id:
        rows = db.execute(
            "SELECT * FROM players WHERE season_id=? ORDER BY jersey_number", (season_id,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM players ORDER BY jersey_number").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/players", methods=["POST"])
def api_players_create():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO players (name, jersey_number, position, grade,
           program_name, gender, level, season_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            name,
            data.get("jersey_number"),
            data.get("position"),
            data.get("grade"),
            data.get("program_name", "Liberty"),
            data.get("gender", "boys"),
            data.get("level", "jr_high"),
            data.get("season_id"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM players WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


# ── API: Analysis ─────────────────────────────────────────

@app.route("/api/analysis_status/<game_id>")
def get_analysis_status(game_id):
    db = get_db()
    row = db.execute(
        """SELECT status, started_at, completed_at, error_message
           FROM analysis_runs WHERE game_id=? ORDER BY id DESC LIMIT 1""",
        (game_id,),
    ).fetchone()
    if row is None:
        return jsonify({"status": "not_started"})
    return jsonify(dict(row))


# ── API: Stats ────────────────────────────────────────────

@app.route("/api/stats/<game_id>")
def get_stats(game_id):
    from stats import aggregate_stats
    db = get_db()
    return jsonify(aggregate_stats(db, game_id))


# ── API: Upload video ─────────────────────────────────────

@app.route("/api/upload_video", methods=["POST"])
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


@app.route("/upload", methods=["POST"])
def upload_and_analyze():
    """Handle the film tool's 'Upload and Analyze' form (posts to /upload)."""
    if "video" not in request.files:
        return "No video file provided", 400
    f = request.files["video"]
    if not f.filename:
        return "Empty filename", 400
    opponent = request.form.get("opponent", "unknown").strip() or "unknown"
    filename = secure_filename(f.filename)
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    f.save(dest)

    stem = os.path.splitext(filename)[0]
    game_id = f"{opponent.lower().replace(' ', '_')}_{stem}"

    db = get_db()
    run_cur = db.execute(
        "INSERT INTO analysis_runs (game_id, video_path, status) VALUES (?,?,?)",
        (game_id, dest, "pending"),
    )
    run_id = run_cur.lastrowid
    db.commit()

    # Check AI deps before launching subprocess
    ai_available = True
    missing = []
    for mod in ("cv2", "ultralytics"):
        try:
            __import__(mod)
        except ImportError:
            ai_available = False
            missing.append("opencv-python" if mod == "cv2" else mod)

    if ai_available:
        import subprocess, sys
        subprocess.Popen(
            [sys.executable, "ai_analyzer.py",
             current_app.config["DATABASE"], dest, game_id],
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        ai_msg = "✅ AI analysis running in background — check <a href='/status'>Status page</a> for progress."
    else:
        err = f"Missing packages: {', '.join(missing)}. Run: pip install {' '.join(missing)}"
        db.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (err, run_id),
        )
        db.commit()
        ai_msg = (
            f"⚠️ <strong>AI analysis unavailable</strong> — {err}.<br>"
            "Manual tagging in the film tool still works fine."
        )

    return f"""<!DOCTYPE html>
    <html><head>
    <meta http-equiv="refresh" content="4;url=/film/{filename}">
    <style>
      body{{font-family:sans-serif;padding:40px;background:#f7f6f2;max-width:600px;margin:auto;}}
      .card{{background:#fff;border:1px solid #e2e0da;border-radius:8px;padding:28px;margin-top:24px;}}
      code{{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:.9em;}}
    </style>
    </head><body>
    <div class="card">
      <h2>📹 Upload complete</h2>
      <p><strong>File:</strong> {filename}</p>
      <p><strong>Game ID:</strong> <code>{game_id}</code></p>
      <p style="margin-top:16px;">{ai_msg}</p>
      <p style="margin-top:20px;color:#6b7280;font-size:.9em;">
        Redirecting to film tool in 4 seconds…
        <a href="/film/{filename}">click here</a> to go now.
      </p>
      <p><a href="/status">📊 View Analysis Status</a></p>
    </div>
    </body></html>
    """


@app.route("/status")
def status_page():
    """Live status page showing all analysis runs."""
    db = get_db()
    runs = db.execute(
        "SELECT * FROM analysis_runs ORDER BY id DESC"
    ).fetchall()
    rows_html = ""
    for r in runs:
        r = dict(r)
        status = r["status"]
        color = {"pending": "#f59e0b", "running": "#3b82f6",
                 "completed": "#059669", "failed": "#dc2626"}.get(status, "#6b7280")
        err = f"<br><small style='color:#dc2626'>{r['error_message']}</small>" if r.get("error_message") else ""
        rows_html += f"""<tr>
          <td>{r['id']}</td>
          <td><code>{r['game_id']}</code></td>
          <td>{r['video_path']}</td>
          <td><span style="color:{color};font-weight:600">{status}</span>{err}</td>
          <td>{r['started_at'] or '–'}</td>
          <td>{r['completed_at'] or '–'}</td>
        </tr>"""

    if not rows_html:
        rows_html = "<tr><td colspan='6' style='color:#6b7280;padding:20px'>No uploads yet.</td></tr>"

    # Count detections and events per game
    det_counts = {r[0]: r[1] for r in db.execute(
        "SELECT game_id, COUNT(*) FROM detections GROUP BY game_id"
    ).fetchall()}
    evt_counts = {r[0]: r[1] for r in db.execute(
        "SELECT game_id, COUNT(*) FROM events GROUP BY game_id"
    ).fetchall()}

    return f"""<!DOCTYPE html>
    <html><head>
    <title>Analysis Status – Liberty Basketball</title>
    <meta http-equiv="refresh" content="5">
    <style>
      body{{font-family:sans-serif;padding:32px;background:#f7f6f2;}}
      h2{{margin-bottom:6px;}} .sub{{color:#6b7280;font-size:.85rem;margin-bottom:20px;}}
      table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);}}
      th{{background:#01696f;color:#fff;padding:10px 14px;text-align:left;font-size:.8rem;text-transform:uppercase;}}
      td{{padding:10px 14px;border-bottom:1px solid #e2e0da;font-size:.875rem;}}
      tr:last-child td{{border:none;}} code{{background:#f3f4f6;padding:1px 5px;border-radius:4px;}}
      .nav a{{margin-right:16px;color:#01696f;text-decoration:none;font-weight:500;}}
    </style>
    </head><body>
    <div class="nav"><a href="/">Dashboard</a><a href="/schedule">Schedule</a><a href="/film">Film Tool</a></div>
    <h2 style="margin-top:20px;">📊 Analysis Status</h2>
    <p class="sub">Auto-refreshes every 5 seconds.</p>
    <table>
      <thead><tr><th>#</th><th>Game ID</th><th>Video</th><th>Status</th><th>Started</th><th>Completed</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <h3 style="margin-top:28px;">Detections &amp; Events per Game</h3>
    <table>
      <thead><tr><th>Game ID</th><th>Detections</th><th>Events Tagged</th></tr></thead>
      <tbody>{''.join(f"<tr><td><code>{g}</code></td><td>{det_counts.get(g,0)}</td><td>{evt_counts.get(g,0)}</td></tr>" for g in set(list(det_counts)+list(evt_counts))) or "<tr><td colspan='3' style='color:#6b7280;padding:20px'>No data yet.</td></tr>"}
      </tbody>
    </table>
    </body></html>"""


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=8080, debug=True)