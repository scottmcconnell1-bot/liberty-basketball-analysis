"""
Blueprints: Clips / Events / Players
=====================================
This blueprint covers all API routes related to:

  - Player Development Clips
      GET    /api/clips              — list clips (filterable by player_id, season_id, category, game_id)
      POST   /api/clips              — create a new clip
      GET    /api/clips/<clip_id>    — retrieve a single clip
      PUT    /api/clips/<clip_id>    — update a clip
      DELETE /api/clips/<clip_id>    — delete a clip

  - Game Events (manual tagging)
      POST   /api/save_event                    — save a new event
      GET    /api/events/<game_id>              — list events for a game (optionally filtered by event_type)
      PUT    /api/events/<event_id>             — update an event
      DELETE /api/events/<event_id>             — delete an event

  - Players
      GET    /api/players            — list players (optionally filtered by season_id)
      POST   /api/players            — create a new player

All route logic is extracted verbatim from app.py.
"""

import sqlite3

from flask import (
    Blueprint, abort, current_app, g, jsonify, request,
)

import player_development as pd_helpers

from helpers import get_db, refresh_game_stats, require_feature

clips_bp = Blueprint("clips", __name__)


# ── API: Events ───────────────────────────────────────────

@clips_bp.route("/api/save_event", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
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
    refresh_game_stats(db, data.get("game_id", "default_game"))
    return jsonify({"status": "success", "id": cur.lastrowid})


@clips_bp.route("/api/events/<game_id>", methods=["GET"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def get_events(game_id):
    db = get_db()
    event_type = (request.args.get("event_type") or "").strip()
    if event_type:
        rows = db.execute(
            "SELECT * FROM events WHERE game_id=? AND event_type=? ORDER BY timestamp_ms ASC",
            (game_id, event_type),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM events WHERE game_id=? ORDER BY timestamp_ms ASC",
            (game_id,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@clips_bp.route("/api/events/<int:event_id>", methods=["PUT"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
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
    refresh_game_stats(db, row["game_id"])
    return jsonify(dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()))


@clips_bp.route("/api/events/<int:event_id>", methods=["DELETE"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def delete_event(event_id):
    db = get_db()
    row = db.execute("SELECT game_id FROM events WHERE id=?", (event_id,)).fetchone()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    if row:
        refresh_game_stats(db, row["game_id"])
    return jsonify({"deleted": True})


# ── API: Players ──────────────────────────────────────────

@clips_bp.route("/api/players", methods=["GET"])
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


@clips_bp.route("/api/players", methods=["POST"])
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


# ── API: Clips ────────────────────────────────────────────

@clips_bp.route("/api/clips")
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_list():
    db = get_db()
    player_id = request.args.get("player_id", type=int)
    season_id = request.args.get("season_id", type=int)
    category = request.args.get("category")
    game_id = request.args.get("game_id")
    clips = pd_helpers.get_clips(db, player_id=player_id, season_id=season_id,
                                  category=category, game_id=game_id)
    return jsonify(clips)


@clips_bp.route("/api/clips", methods=["POST"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_create():
    db = get_db()
    data = request.get_json(force=True)
    try:
        clip = pd_helpers.create_clip(
            db,
            clip_label=data["clip_label"],
            clip_start_ms=int(data["clip_start_ms"]),
            clip_end_ms=int(data["clip_end_ms"]),
            player_id=data.get("player_id"),
            game_id=data.get("game_id"),
            event_id=data.get("event_id"),
            clip_category=data.get("clip_category", "general"),
            season_id=data.get("season_id"),
            notes=data.get("notes"),
        )
        return jsonify(clip), 201
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@clips_bp.route("/api/clips/<int:clip_id>")
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_get(clip_id):
    db = get_db()
    row = db.execute("SELECT * FROM player_development_clips WHERE id=?", (clip_id,)).fetchone()
    if not row:
        abort(404)
    return jsonify(dict(row))


@clips_bp.route("/api/clips/<int:clip_id>", methods=["PUT"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_update(clip_id):
    db = get_db()
    data = request.get_json(force=True)
    try:
        clip = pd_helpers.update_clip(db, clip_id, **data)
        return jsonify(clip)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clips_bp.route("/api/clips/<int:clip_id>", methods=["DELETE"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_delete(clip_id):
    db = get_db()
    pd_helpers.delete_clip(db, clip_id)
    return jsonify({"status": "deleted"})
