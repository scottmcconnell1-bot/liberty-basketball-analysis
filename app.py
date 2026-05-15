import os
import sqlite3
import sys
import subprocess
import json

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, abort, g
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
    """Get a database connection with WAL mode and timeout."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=10000")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close the database connection at the end of request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    with app.open_resource("schema.sql", mode="r") as f:
        db.cursor().executescript(f.read())
    db.commit()
    db.close()


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Initialized the database.")


# --- CSP Headers (fully permissive for extensions) ---
@app.after_request
def add_csp_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src * 'unsafe-inline' 'unsafe-eval'; "
        "img-src * data: blob:; "
        "media-src * data: blob:; "
        "script-src * 'unsafe-inline' 'unsafe-eval'; "
        "style-src * 'unsafe-inline'; "
        "connect-src *; "
        "font-src * data:;"
    )
    return response


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
    return render_template("schedule.html", seasons=seasons, games=games)


# --- Games Page (Phase 3) ---
@app.route("/games")
def games_page():
    if not Features.ENABLE_GAMES:
        abort(404)
    db = get_db()
    from games import list_games
    from scheduled_games import list_scheduled_games
    from season_management import list_seasons
    seasons = list_seasons(db)
    scheduled = list_scheduled_games(db)
    game_list = list_games(db)
    return render_template("games.html", seasons=seasons, scheduled_games=scheduled, games=game_list)


# --- API Routes ---
@app.route("/api/save_event", methods=["POST"])
def save_event():
    event_data = request.json
    if not event_data or "timestamp_ms" not in event_data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    # Serialize details_json if it's a dict
    details = event_data.get("details_json")
    if isinstance(details, dict):
        details = json.dumps(details)

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
            details,
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
    return jsonify({"status": "success", "id": gid}), 201


@app.route("/api/scheduled_games/<int:game_id>", methods=["PUT"])
def api_edit_scheduled_game(game_id):
    if not Features.ENABLE_SCHEDULE:
        abort(404)
    data = request.json
    db = get_db()
    from scheduled_games import edit_scheduled_game
    ok = edit_scheduled_game(db, game_id, **data)
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
    if not ok:
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify({"status": "success"})


# --- Seasons API ---
@app.route("/api/seasons", methods=["GET"])
def api_list_seasons():
    db = get_db()
    from season_management import list_seasons
    seasons = list_seasons(db)
    return jsonify(seasons)


@app.route("/api/seasons", methods=["POST"])
def api_create_season():
    data = request.json
    if not data or "name" not in data or "start_date" not in data or "end_date" not in data:
        return jsonify({"status": "error", "message": "Missing name/start_date/end_date"}), 400
    db = get_db()
    from season_management import create_season
    sid = create_season(db, data["name"], data["start_date"], data["end_date"])
    return jsonify({"status": "success", "id": sid}), 201


# --- Games API (Phase 3) ---
@app.route("/api/games", methods=["GET"])
def api_list_games():
    if not Features.ENABLE_GAMES:
        abort(404)
    db = get_db()
    from games import list_games
    scheduled_game_id = request.args.get("scheduled_game_id", type=int)
    source_type = request.args.get("source_type")
    game_list = list_games(db, scheduled_game_id=scheduled_game_id, source_type=source_type)
    return jsonify(game_list)


@app.route("/api/games", methods=["POST"])
def api_create_game():
    if not Features.ENABLE_GAMES:
        abort(404)
    data = request.json
    required = ["source_type", "source_key"]
    for f in required:
        if f not in data:
            return jsonify({"status": "error", "message": f"Missing field: {f}"}), 400
    db = get_db()
    from games import create_game
    gid = create_game(
        db,
        source_type=data["source_type"],
        source_key=data["source_key"],
        scheduled_game_id=data.get("scheduled_game_id"),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        nfhs_game_id=data.get("nfhs_game_id"),
        nfhs_url=data.get("nfhs_url"),
        home_score=data.get("home_score", 0),
        away_score=data.get("away_score", 0),
        result=data.get("result"),
        is_conference=data.get("is_conference", 0),
    )
    return jsonify({"status": "success", "id": gid}), 201


@app.route("/api/games/<int:game_id>", methods=["GET"])
def api_get_game(game_id):
    if not Features.ENABLE_GAMES:
        abort(404)
    db = get_db()
    from games import get_game
    game = get_game(db, game_id)
    if game is None:
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify(game)


@app.route("/api/games/<int:game_id>", methods=["PUT"])
def api_edit_game(game_id):
    if not Features.ENABLE_GAMES:
        abort(404)
    data = request.json
    db = get_db()
    from games import edit_game
    ok = edit_game(db, game_id, **data)
    if not ok:
        return jsonify({"status": "error", "message": "No updates applied"}), 400
    return jsonify({"status": "success"})


@app.route("/api/games/<int:game_id>", methods=["DELETE"])
def api_delete_game(game_id):
    if not Features.ENABLE_GAMES:
        abort(404)
    db = get_db()
    from games import delete_game
    ok = delete_game(db, game_id)
    if not ok:
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify({"status": "success"})


# --- Sources API (Phase 3) ---
@app.route("/api/sources", methods=["GET"])
def api_list_sources():
    if not Features.ENABLE_GAMES:
        abort(404)
    db = get_db()
    from sources import list_sources
    game_id = request.args.get("game_id", type=int)
    src_list = list_sources(db, game_id=game_id)
    return jsonify(src_list)


@app.route("/api/sources", methods=["POST"])
def api_create_source():
    if not Features.ENABLE_GAMES:
        abort(404)
    data = request.json
    required = ["game_id", "source_type", "source_path"]
    for f in required:
        if f not in data:
            return jsonify({"status": "error", "message": f"Missing field: {f}"}), 400
    db = get_db()
    from sources import create_source
    sid = create_source(
        db,
        game_id=data["game_id"],
        source_type=data["source_type"],
        source_path=data["source_path"],
    )
    return jsonify({"status": "success", "id": sid}), 201


@app.route("/api/sources/<int:source_id>", methods=["DELETE"])
def api_delete_source(source_id):
    if not Features.ENABLE_GAMES:
        abort(404)
    db = get_db()
    from sources import delete_source
    ok = delete_source(db, source_id)
    if not ok:
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify({"status": "success"})


print(app.url_map)

if __name__ == "__main__":
    # Auto-init DB on first run
    if not os.path.exists(DATABASE):
        init_db()
    app.run(host="0.0.0.0", port=8080, debug=True)
