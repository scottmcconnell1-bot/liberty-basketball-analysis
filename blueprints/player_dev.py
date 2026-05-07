"""
Player Development & Practice Playlists Blueprint
===================================================
Covers all player-development and practice-playlist routes for the Liberty Basketball Analysis app.

Routes:
  GET    /player-development                              — player_development_page
  GET    /practice-playlists                              — practice_playlists_page
  GET    /api/playlists                                   — api_playlists_list
  POST   /api/playlists                                   — api_playlists_create
  GET    /api/playlists/<int:playlist_id>                 — api_playlists_get
  PUT    /api/playlists/<int:playlist_id>                 — api_playlists_update
  DELETE /api/playlists/<int:playlist_id>                 — api_playlists_delete
  POST   /api/playlists/<int:playlist_id>/clips           — api_playlists_add_clip
  DELETE /api/playlists/<int:playlist_id>/clips/<int:clip_id> — api_playlists_remove_clip
"""

from flask import Blueprint, abort, render_template, request, jsonify

from helpers import require_feature, get_db, SCHEDULE_LEVEL_OPTIONS

import player_development as pd_helpers

player_dev = Blueprint("player_dev", __name__)


# ── Practice Playlists ─────────────────────────────────────────────

@player_dev.route("/api/playlists")
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_list():
    db = get_db()
    season_id = request.args.get("season_id", type=int)
    level = request.args.get("level")
    status = request.args.get("status")
    playlists = pd_helpers.get_playlists(db, season_id=season_id, level=level, status=status)
    return jsonify(playlists)


@player_dev.route("/api/playlists", methods=["POST"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_create():
    db = get_db()
    data = request.get_json(force=True)
    try:
        playlist = pd_helpers.create_playlist(
            db,
            name=data["name"],
            season_id=data.get("season_id"),
            level=data.get("level", "jr_high"),
            status=data.get("status", "draft"),
        )
        return jsonify(playlist), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@player_dev.route("/api/playlists/<int:playlist_id>")
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_get(playlist_id):
    db = get_db()
    row = db.execute("SELECT * FROM practice_playlists WHERE id=?", (playlist_id,)).fetchone()
    if not row:
        abort(404)
    clips = pd_helpers.get_playlist_clips(db, playlist_id)
    result = dict(row)
    result["clips"] = clips
    return jsonify(result)


@player_dev.route("/api/playlists/<int:playlist_id>", methods=["PUT"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_update(playlist_id):
    db = get_db()
    data = request.get_json(force=True)
    try:
        playlist = pd_helpers.update_playlist(db, playlist_id, **data)
        return jsonify(playlist)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@player_dev.route("/api/playlists/<int:playlist_id>", methods=["DELETE"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_delete(playlist_id):
    db = get_db()
    pd_helpers.delete_playlist(db, playlist_id)
    return jsonify({"status": "deleted"})


@player_dev.route("/api/playlists/<int:playlist_id>/clips", methods=["POST"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_add_clip(playlist_id):
    db = get_db()
    data = request.get_json(force=True)
    clip_id = data.get("clip_id")
    if not clip_id:
        return jsonify({"error": "clip_id is required"}), 400
    pd_helpers.add_clip_to_playlist(db, playlist_id, int(clip_id),
                                     sort_order=data.get("sort_order", 0))
    return jsonify({"status": "added"}), 201


@player_dev.route("/api/playlists/<int:playlist_id>/clips/<int:clip_id>", methods=["DELETE"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_playlists_remove_clip(playlist_id, clip_id):
    db = get_db()
    pd_helpers.remove_clip_from_playlist(db, playlist_id, clip_id)
    return jsonify({"status": "removed"})


# ── Player Development UI ──────────────────────────────────────────

@player_dev.route("/player-development")
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def player_development_page():
    db = get_db()
    seasons = db.execute("SELECT * FROM seasons ORDER BY start_date DESC, id DESC").fetchall()
    players = db.execute("SELECT * FROM players ORDER BY name").fetchall()
    player_id = request.args.get("player_id", type=int)
    season_id = request.args.get("season_id", type=int)
    category = request.args.get("category")
    game_id = request.args.get("game_id")
    clips = pd_helpers.get_clips(db, player_id=player_id, season_id=season_id,
                                  category=category, game_id=game_id)
    return render_template(
        "player_development.html",
        seasons=seasons,
        players=players,
        clips=clips,
        level_options=SCHEDULE_LEVEL_OPTIONS,
    )


@player_dev.route("/practice-playlists")
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def practice_playlists_page():
    db = get_db()
    seasons = db.execute("SELECT * FROM seasons ORDER BY start_date DESC, id DESC").fetchall()
    playlists = pd_helpers.get_playlists(db)
    view_playlist = None
    view_playlist_id = request.args.get("view_playlist_id", type=int)
    if view_playlist_id:
        row = db.execute("SELECT * FROM practice_playlists WHERE id=?", (view_playlist_id,)).fetchone()
        if row:
            clips = pd_helpers.get_playlist_clips(db, view_playlist_id)
            view_playlist = dict(row)
            view_playlist["clips"] = clips
    return render_template(
        "practice_playlists.html",
        seasons=seasons,
        playlists=playlists,
        view_playlist=view_playlist,
        level_options=SCHEDULE_LEVEL_OPTIONS,
    )
