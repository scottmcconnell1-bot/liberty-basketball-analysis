"""
Stats and Seasons Blueprint.

Routes:
  GET    /api/seasons                   - List all seasons
  POST   /api/seasons                   - Create a season
  GET    /api/seasons/<int:season_id>   - Get a season
  PUT    /api/seasons/<int:season_id>   - Update a season
  DELETE /api/seasons/<int:season_id>   - Delete a season
"""

import sqlite3
from flask import Blueprint, jsonify, request

from helpers import get_db, require_feature

stats_bp = Blueprint("stats", __name__)


@stats_bp.route("/api/seasons", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_seasons_list():
    db = get_db()
    rows = db.execute("SELECT * FROM seasons ORDER BY start_date DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@stats_bp.route("/api/seasons", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
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


@stats_bp.route("/api/seasons/<int:season_id>", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_season_get(season_id):
    db = get_db()
    row = db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@stats_bp.route("/api/seasons/<int:season_id>", methods=["PUT"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
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


@stats_bp.route("/api/seasons/<int:season_id>", methods=["DELETE"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_season_delete(season_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE season_id=?", (season_id,))
    db.execute("DELETE FROM seasons WHERE id=?", (season_id,))
    db.commit()
    return jsonify({"deleted": True})
