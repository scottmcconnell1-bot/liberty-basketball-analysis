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


@app.route("/schedule")
def schedule():
    """Render the simple schedule UI for coaches."""
    return render_template("schedule.html")

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


# --- Seasons DB helpers ---
def create_season(name, start_date=None, end_date=None):
    """Create a new season row and return its id."""
    db = get_db()
    cur = db.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?, ?, ?)",
        (name, start_date, end_date),
    )
    db.commit()
    return cur.lastrowid


def get_season(season_id):
    """Return a season dict by id, or None if not found."""
    db = get_db()
    row = db.execute("SELECT * FROM seasons WHERE id = ?", (season_id,)).fetchone()
    return dict(row) if row is not None else None


def list_seasons():
    """Return all seasons as a list of dicts, most recent first."""
    db = get_db()
    rows = db.execute("SELECT * FROM seasons ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_season(season_id, name, start_date=None, end_date=None):
    """Update season fields. name is required for simplicity."""
    db = get_db()
    db.execute(
        "UPDATE seasons SET name = ?, start_date = ?, end_date = ? WHERE id = ?",
        (name, start_date, end_date, season_id),
    )
    db.commit()


def delete_season(season_id):
    """Delete a season by id."""
    db = get_db()
    db.execute("DELETE FROM seasons WHERE id = ?", (season_id,))
    db.commit()

# --- Scheduled Games DB helpers ---
def create_scheduled_game(
    season_id,
    program_name=None,
    gender=None,
    level=None,
    game_date=None,
    game_time=None,
    location_type=None,
    opponent_name=None,
    tournament_name=None,
    status="scheduled",
    notes=None,
):
    """Create a scheduled_game row and return its id."""
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO scheduled_games (
            season_id, program_name, gender, level, game_date, game_time,
            location_type, opponent_name, tournament_name, status, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            season_id,
            program_name,
            gender,
            level,
            game_date,
            game_time,
            location_type,
            opponent_name,
            tournament_name,
            status,
            notes,
            None,
        ),
    )
    db.commit()
    return cur.lastrowid


def get_scheduled_game(sg_id):
    """Return a scheduled_game dict by id, or None if not found."""
    db = get_db()
    row = db.execute("SELECT * FROM scheduled_games WHERE id = ?", (sg_id,)).fetchone()
    return dict(row) if row is not None else None


def list_scheduled_games(season_id=None, level=None, gender=None):
    """Return scheduled games with optional filters (season, level, gender)."""
    db = get_db()
    query = "SELECT * FROM scheduled_games"
    clauses = []
    params = []
    if season_id is not None:
        clauses.append("season_id = ?")
        params.append(season_id)
    if level:
        clauses.append("level = ?")
        params.append(level)
    if gender:
        clauses.append("gender = ?")
        params.append(gender)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY game_date ASC, game_time ASC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_scheduled_game(sg_id, **fields):
    """Update allowed fields on a scheduled_game. Pass keyword args for columns to update."""
    allowed = [
        "season_id",
        "program_name",
        "gender",
        "level",
        "game_date",
        "game_time",
        "location_type",
        "opponent_name",
        "tournament_name",
        "status",
        "notes",
    ]
    set_clauses = []
    params = []
    for k in allowed:
        if k in fields:
            set_clauses.append(f"{k} = ?")
            params.append(fields[k])
    if not set_clauses:
        return
    # update the updated_at timestamp
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    sql = "UPDATE scheduled_games SET " + ", ".join(set_clauses) + " WHERE id = ?"
    params.append(sg_id)
    db = get_db()
    db.execute(sql, params)
    db.commit()


def delete_scheduled_game(sg_id):
    """Delete a scheduled_game by id."""
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE id = ?", (sg_id,))
    db.commit()


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


# --- Seasons API routes ---
@app.route("/api/seasons", methods=["POST"])
def api_create_season():
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"status": "error", "message": "name is required"}), 400
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    sid = create_season(name, start_date, end_date)
    season = get_season(sid)
    return jsonify({"status": "success", "season": season}), 201


@app.route("/api/seasons")
def api_list_seasons():
    seasons = list_seasons()
    return jsonify(seasons)


@app.route("/api/seasons/<int:season_id>")
def api_get_season(season_id):
    season = get_season(season_id)
    if season is None:
        return jsonify({"status": "error", "message": "not found"}), 404
    return jsonify(season)


@app.route("/api/seasons/<int:season_id>", methods=["PUT", "PATCH"])
def api_update_season(season_id):
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"status": "error", "message": "name is required"}), 400
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    update_season(season_id, name, start_date, end_date)
    return jsonify({"status": "success", "season": get_season(season_id)})


@app.route("/api/seasons/<int:season_id>", methods=["DELETE"])
def api_delete_season(season_id):
    if get_season(season_id) is None:
        return jsonify({"status": "error", "message": "not found"}), 404
    delete_season(season_id)
    return jsonify({"status": "success"})


@app.route("/api/scheduled_games", methods=["POST"])
def api_create_scheduled_game():
    data = request.json or {}
    season_id = data.get("season_id")
    if season_id is None:
        return jsonify({"status": "error", "message": "season_id is required"}), 400
    sg_id = create_scheduled_game(
        season_id=season_id,
        program_name=data.get("program_name"),
        gender=data.get("gender"),
        level=data.get("level"),
        game_date=data.get("game_date"),
        game_time=data.get("game_time"),
        location_type=data.get("location_type"),
        opponent_name=data.get("opponent_name"),
        tournament_name=data.get("tournament_name"),
        status=data.get("status", "scheduled"),
        notes=data.get("notes"),
    )
    return jsonify({"status": "success", "scheduled_game": get_scheduled_game(sg_id)}), 201


@app.route("/api/scheduled_games")
def api_list_scheduled_games():
    # Supports query params: season_id, level, gender
    season_id = request.args.get("season_id")
    level = request.args.get("level")
    gender = request.args.get("gender")
    try:
        season_id_int = int(season_id) if season_id is not None else None
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "season_id must be an integer"}), 400
    games = list_scheduled_games(season_id=season_id_int, level=level, gender=gender)
    return jsonify(games)


@app.route("/api/scheduled_games/<int:sg_id>")
def api_get_scheduled_game(sg_id):
    sg = get_scheduled_game(sg_id)
    if sg is None:
        return jsonify({"status": "error", "message": "not found"}), 404
    return jsonify(sg)


@app.route("/api/scheduled_games/<int:sg_id>", methods=["PUT", "PATCH"])
def api_update_scheduled_game(sg_id):
    data = request.json or {}
    # Validate season_id if provided
    if "season_id" in data:
        try:
            data["season_id"] = int(data["season_id"]) if data["season_id"] is not None else None
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "season_id must be an integer"}), 400
    allowed = [
        "season_id",
        "program_name",
        "gender",
        "level",
        "game_date",
        "game_time",
        "location_type",
        "opponent_name",
        "tournament_name",
        "status",
        "notes",
    ]
    fields = {k: data[k] for k in allowed if k in data}
    if not fields:
        return jsonify({"status": "error", "message": "no updatable fields provided"}), 400
    # Perform update
    update_scheduled_game(sg_id, **fields)
    sg = get_scheduled_game(sg_id)
    if sg is None:
        return jsonify({"status": "error", "message": "not found"}), 404
    return jsonify({"status": "success", "scheduled_game": sg})


@app.route("/api/scheduled_games/<int:sg_id>", methods=["DELETE"])
def api_delete_scheduled_game(sg_id):
    if get_scheduled_game(sg_id) is None:
        return jsonify({"status": "error", "message": "not found"}), 404
    delete_scheduled_game(sg_id)
    return jsonify({"status": "success"})


print(app.url_map)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
