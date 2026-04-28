import os
import sqlite3
import sys
import subprocess

print("[DEBUG] Starting app.py...")
print("[DEBUG] os imported.")
print("[DEBUG] sqlite3 imported.")
print("[DEBUG] subprocess imported.")

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
print("[DEBUG] flask imported.")

from werkzeug.utils import secure_filename
print("[DEBUG] werkzeug imported.")

app = Flask(__name__)

# --- App and DB Configuration ---
DATABASE = "film_analysis.db"
UPLOAD_FOLDER = "uploads"

app.config["DATABASE"] = DATABASE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
@app.route("/video/<filename>")
def index(filename=None):
    return render_template("film-tool-v2026-04-23-Tagger_Finished.html", filename=filename)

# --- Database Functions ---
def get_db():
    """Connect to the application's database."""
    db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    with app.open_resource("schema.sql", mode="r") as f:
        db.cursor().executescript(f.read())
    db.commit()

@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Initialized the database.")

@app.before_request
def before_first_request_func():
    if not os.path.exists(DATABASE):
        with app.app_context():
            init_db()

# --- API Routes ---
@app.route("/api/save_event", methods=["POST"])
def save_event():
    event_data = request.json
    if not event_data or "timestamp_ms" not in event_data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    db = get_db()
    db.execute(
        "INSERT INTO events (game_id, player, event_type, shot_result, timestamp_ms, details_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            event_data.get("game_id", "default_game"),
            event_data.get("player"),
            event_data.get("event_type"),
            event_data.get("shot_result"),
            event_data.get("timestamp_ms"),
            event_data.get("details_json"),
        ),
    )
    db.commit()
    return jsonify({"status": "success"})

@app.route("/api/analysis_status/<game_id>")
def get_analysis_status(game_id):
    """API endpoint to check AI analysis status for a game."""
    db = get_db()
    row = db.execute(
        """
        SELECT status, started_at, completed_at, error_message
        FROM analysis_runs
        WHERE game_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (game_id,),
    ).fetchone()

    if row is None:
        return jsonify({"status": "unknown"}), 404

    return jsonify(
        {
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "error_message": row["error_message"],
        }
    )

@app.route("/api/events/<game_id>")
def get_ai_events(game_id):
    """API endpoint to fetch AI-generated events."""
    db = get_db()
    events = db.execute(
        "SELECT * FROM events WHERE game_id = ? ORDER BY timestamp_ms ASC", (game_id,)
    ).fetchall()
    return jsonify([dict(row) for row in events])


@app.route("/api/tracker_summary/<game_id>")
def tracker_summary(game_id):
    """Small verification route: returns counts of detections with and without tracker_id for a game."""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN tracker_id IS NOT NULL THEN 1 ELSE 0 END) as with_tracker "
        "FROM detections WHERE game_id = ?",
        (game_id,),
    ).fetchone()
    if row is None:
        return jsonify({"error": "no data"}), 404
    return jsonify({"game_id": game_id, "total_detections": row[0], "with_tracker_id": row[1]})

print(app.url_map)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)