import os
import sqlite3
import sys
import subprocess

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, abort
from werkzeug.utils import secure_filename

from config import Features

app = Flask(__name__)

# --- App and DB Configuration ---
DATABASE = "film_analysis.db"
UPLOAD_FOLDER = "uploads"

app.config["DATABASE"] = DATABASE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --- Database Functions ---
def get_db():
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


# --- Routes ---
@app.route("/")
@app.route("/video/<filename>")
def index(filename=None):
    return render_template("film-tool-v2026-04-23-Tagger_Finished.html", filename=filename)


# --- Schedule Page (Phase 2) ---
@app.route("/schedule")
def schedule_page():
    if not Features.ENABLE_SCHEDULE:
        abort(404)
    db = get_db()
    from scheduled_games import list_scheduled_games
    from season_management import list_seasons
    seasons = list_seasons(db)
    games = list_scheduled_games(db)
    db.close()
    return render_template("schedule.html", seasons=seasons, games=games)


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
    db = get_db()
    events = db.execute(
        "SELECT * FROM events WHERE game_id = ? ORDER BY timestamp_ms ASC", (game_id,)
    ).fetchall()
    return jsonify([dict(row) for row in events])


# --- Schedule API ---
@app.route("/api/scheduled_games", methods=["GET"])
def api_list_scheduled_games():
    if not Features.ENABLE_SCHEDULE:
        abort(404)
    db = get_db()
    from scheduled_games import list_scheduled_games
    season_id = request.args.get("season_id", type=int)
    level = request.args.get("level")
    gender = request.args.get("gender")
    games = list_scheduled_games(db, season_id=season_id, level=level, gender=gender)
    db.close()
    return jsonify(games)


@app.route("/api/scheduled_games", methods=["POST"])
def api_create_scheduled_game():
    if not Features.ENABLE_SCHEDULE:
        abort(404)
    data = request.json
    required = ["season_id", "program_name", "gender", "level", "game_date",
                "game_time", "location_type", "opponent_name"]
    for f in required:
        if f not in data:
            return jsonify({"status": "error", "message": f"Missing field: {f}"}), 400
    db = get_db()
    from scheduled_games import create_scheduled_game
    gid = create_scheduled_game(
        db,
        season_id=data["season_id"],
        program_name=data["program_name"],
        gender=data["gender"],
        level=data["level"],
        game_date=data["game_date"],
        game_time=data["game_time"],
        location_type=data["location_type"],
        opponent_name=data["opponent_name"],
        tournament_name=data.get("tournament_name"),
        notes=data.get("notes"),
    )
    db.close()
    return jsonify({"status": "success", "id": gid}), 201


@app.route("/api/scheduled_games/<int:game_id>", methods=["PUT"])
def api_edit_scheduled_game(game_id):
    if not Features.ENABLE_SCHEDULE:
        abort(404)
    data = request.json
    db = get_db()
    from scheduled_games import edit_scheduled_game
    ok = edit_scheduled_game(db, game_id, **data)
    db.close()
    if not ok:
        return jsonify({"status": "error", "message": "No updates applied"}), 400
    return jsonify({"status": "success"})


@app.route("/api/scheduled_games/<int:game_id>", methods=["DELETE"])
def api_delete_scheduled_game(game_id):
    if not Features.ENABLE_SCHEDULE:
        abort(404)
    db = get_db()
    from scheduled_games import delete_scheduled_game
    ok = delete_scheduled_game(db, game_id)
    db.close()
    if not ok:
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify({"status": "success"})


# --- Seasons API ---
@app.route("/api/seasons", methods=["GET"])
def api_list_seasons():
    db = get_db()
    from season_management import list_seasons
    seasons = list_seasons(db)
    db.close()
    return jsonify(seasons)


@app.route("/api/seasons", methods=["POST"])
def api_create_season():
    data = request.json
    if not data or "name" not in data or "start_date" not in data or "end_date" not in data:
        return jsonify({"status": "error", "message": "Missing name/start_date/end_date"}), 400
    db = get_db()
    from season_management import create_season
    sid = create_season(db, data["name"], data["start_date"], data["end_date"])
    db.close()
    return jsonify({"status": "success", "id": sid}), 201


print(app.url_map)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
