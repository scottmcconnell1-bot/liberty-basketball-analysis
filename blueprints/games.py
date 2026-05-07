"""
Games Blueprint
===============
Covers all game-related routes for the Liberty Basketball Analysis app.

API Routes:
  - /api/games (GET, POST) - List and create completed games
  - /api/games/<int:game_id> (GET, PUT, DELETE) - Read, update, delete a game
  - /api/sources (GET, POST) - List and create film sources
  - /api/sources/<int:source_id> (GET, DELETE) - Read and delete a source
  - /api/nfhs_matches (GET, POST) - List and create NFHS match candidates
  - /api/nfhs_matches/<int:match_id>/confirm (POST) - Confirm an NFHS match
  - /api/nfhs_matches/<int:match_id>/reject (POST) - Reject an NFHS match
  - /api/scheduled_games (GET, POST) - List and create scheduled games
  - /api/scheduled_games/<int:game_id> (GET, PUT, DELETE) - Read, update, delete a scheduled game

Page Routes:
  - /games - Games management page
  - /games/save (POST) - Save (create/update) a game from form
  - /games/<int:game_id>/delete (POST) - Delete a game
  - /games/sources/save (POST) - Link a source to a game
  - /games/sources/<int:source_id>/delete (POST) - Remove a source link
  - /nfhs-matches - NFHS matches management page
  - /nfhs-matches/add (POST) - Add an NFHS match candidate
  - /nfhs-matches/<int:match_id>/confirm (POST) - Confirm an NFHS match
  - /nfhs-matches/<int:match_id>/reject (POST) - Reject an NFHS match
"""

from flask import Blueprint, redirect, render_template, request, url_for, jsonify, abort

from helpers import (
    get_db,
    require_feature,
    fetch_games_with_context,
    fetch_sources_with_context,
    fetch_nfhs_matches_with_context,
    fetch_scheduled_games,
    confirm_nfhs_match,
    render_games_page,
    render_nfhs_matches_page,
)

games_bp = Blueprint("games", __name__)


# ── API: Scheduled Games ───────────────────────────────────

@games_bp.route("/api/scheduled_games", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_games_list():
    db = get_db()
    rows = fetch_scheduled_games(
        db,
        season_id=request.args.get("season_id", type=int),
        level=(request.args.get("level") or "").strip(),
        gender=(request.args.get("gender") or "").strip(),
        status=(request.args.get("status") or "").strip(),
    )
    return jsonify([dict(r) for r in rows])


@games_bp.route("/api/scheduled_games", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
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


@games_bp.route("/api/scheduled_games/<int:game_id>", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_game_get(game_id):
    db = get_db()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@games_bp.route("/api/scheduled_games/<int:game_id>", methods=["PUT"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
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


@games_bp.route("/api/scheduled_games/<int:game_id>", methods=["DELETE"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_game_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE id=?", (game_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Games (completed games) ───────────────────────────

@games_bp.route("/api/games", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_list():
    db = get_db()
    rows = fetch_games_with_context(db)
    return jsonify([dict(r) for r in rows])


@games_bp.route("/api/games", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_create():
    data = request.get_json(force=True)
    required = ("source_type", "source_key")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO games
           (scheduled_game_id, start_time, end_time, source_type, source_key,
            nfhs_game_id, nfhs_url, home_score, away_score, result, is_conference)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("scheduled_game_id"),
            data.get("start_time"),
            data.get("end_time"),
            data["source_type"],
            data["source_key"],
            data.get("nfhs_game_id"),
            data.get("nfhs_url"),
            data.get("home_score"),
            data.get("away_score"),
            data.get("result"),
            int(bool(data.get("is_conference", False))),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM games WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@games_bp.route("/api/games/<int:game_id>", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_get(game_id):
    db = get_db()
    row = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@games_bp.route("/api/games/<int:game_id>", methods=["PUT"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_update(game_id):
    data = request.get_json(force=True)
    db = get_db()
    existing = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        """UPDATE games SET
           scheduled_game_id=?, start_time=?, end_time=?, source_type=?, source_key=?,
           nfhs_game_id=?, nfhs_url=?, home_score=?, away_score=?, result=?, is_conference=?,
           updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            data.get("scheduled_game_id", existing["scheduled_game_id"]),
            data.get("start_time", existing["start_time"]),
            data.get("end_time", existing["end_time"]),
            data.get("source_type", existing["source_type"]),
            data.get("source_key", existing["source_key"]),
            data.get("nfhs_game_id", existing["nfhs_game_id"]),
            data.get("nfhs_url", existing["nfhs_url"]),
            data.get("home_score", existing["home_score"]),
            data.get("away_score", existing["away_score"]),
            data.get("result", existing["result"]),
            int(data.get("is_conference", bool(existing["is_conference"]))),
            game_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    return jsonify(dict(row))


@games_bp.route("/api/games/<int:game_id>", methods=["DELETE"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM games WHERE id=?", (game_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Sources (film sources per game) ────────────────────

@games_bp.route("/api/sources", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_list():
    db = get_db()
    rows = fetch_sources_with_context(db, game_id=request.args.get("game_id", type=int))
    return jsonify([dict(r) for r in rows])


@games_bp.route("/api/sources", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_create():
    data = request.get_json(force=True)
    required = ("game_id", "source_type", "source_path")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO sources (game_id, source_type, source_path)
           VALUES (?,?,?)""",
        (data["game_id"], data["source_type"], data["source_path"]),
    )
    db.commit()
    row = db.execute("SELECT * FROM sources WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@games_bp.route("/api/sources/<int:source_id>", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_get(source_id):
    db = get_db()
    row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@games_bp.route("/api/sources/<int:source_id>", methods=["DELETE"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_delete(source_id):
    db = get_db()
    db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: NFHS Matches ──────────────────────────────────────

@games_bp.route("/api/nfhs_matches", methods=["GET"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_list():
    db = get_db()
    rows = fetch_nfhs_matches_with_context(db)
    return jsonify([dict(r) for r in rows])


@games_bp.route("/api/nfhs_matches", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_create():
    data = request.get_json(force=True)
    required = ("scheduled_game_id", "nfhs_game_id", "nfhs_url")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO nfhs_matches
           (scheduled_game_id, nfhs_game_id, nfhs_url, match_status, confidence)
           VALUES (?,?,?,?,?)""",
        (
            data["scheduled_game_id"],
            data["nfhs_game_id"],
            data["nfhs_url"],
            data.get("match_status", "candidate"),
            data.get("confidence"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@games_bp.route("/api/nfhs_matches/<int:match_id>/confirm", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_confirm(match_id):
    db = get_db()
    payload = confirm_nfhs_match(db, match_id)
    if not payload:
        return jsonify({"error": "Not found"}), 404
    return jsonify(payload)


@games_bp.route("/api/nfhs_matches/<int:match_id>/reject", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_reject(match_id):
    db = get_db()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (match_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute("UPDATE nfhs_matches SET match_status='rejected' WHERE id=?", (match_id,))
    db.commit()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (match_id,)).fetchone()
    return jsonify(dict(row))


# ── Page: Games ────────────────────────────────────────────

@games_bp.route("/games")
@require_feature("ENABLE_GAMES_SOURCES")
def games_page():
    return render_games_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
        edit_game_id=request.args.get("edit_game_id", type=int),
    )


@games_bp.route("/games/save", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_save():
    form = request.form
    game_id = form.get("game_id", "").strip()
    source_type = (form.get("source_type") or "").strip()
    source_key = (form.get("source_key") or "").strip()

    if not source_type or not source_key:
        return render_games_page(
            error="Source type and source key are required for each game.",
            edit_game_id=int(game_id) if game_id else None,
            game_form_data={
                "id": game_id,
                "scheduled_game_id": form.get("scheduled_game_id", "").strip(),
                "start_time": (form.get("start_time") or "").strip(),
                "end_time": (form.get("end_time") or "").strip(),
                "source_type": source_type,
                "source_key": source_key,
                "nfhs_game_id": (form.get("nfhs_game_id") or "").strip(),
                "nfhs_url": (form.get("nfhs_url") or "").strip(),
                "home_score": (form.get("home_score") or "").strip(),
                "away_score": (form.get("away_score") or "").strip(),
                "result": (form.get("result") or "").strip(),
                "is_conference": bool(form.get("is_conference")),
            },
        ), 400

    db = get_db()
    values = (
        int(form["scheduled_game_id"]) if form.get("scheduled_game_id") else None,
        (form.get("start_time") or "").strip() or None,
        (form.get("end_time") or "").strip() or None,
        source_type,
        source_key,
        (form.get("nfhs_game_id") or "").strip() or None,
        (form.get("nfhs_url") or "").strip() or None,
        int(form["home_score"]) if form.get("home_score") else None,
        int(form["away_score"]) if form.get("away_score") else None,
        (form.get("result") or "").strip() or None,
        int(bool(form.get("is_conference"))),
    )

    if game_id:
        db.execute(
            """UPDATE games SET
               scheduled_game_id=?, start_time=?, end_time=?, source_type=?, source_key=?,
               nfhs_game_id=?, nfhs_url=?, home_score=?, away_score=?, result=?, is_conference=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(game_id),),
        )
        message = "Game updated."
    else:
        db.execute(
            """INSERT INTO games
               (scheduled_game_id, start_time, end_time, source_type, source_key,
                nfhs_game_id, nfhs_url, home_score, away_score, result, is_conference)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        message = "Game created."
    db.commit()
    return redirect(url_for("games.games_page", message=message))


@games_bp.route("/games/<int:game_id>/delete", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM sources WHERE game_id=?", (game_id,))
    db.execute("DELETE FROM games WHERE id=?", (game_id,))
    db.commit()
    return redirect(url_for("games.games_page", message="Game deleted."))


@games_bp.route("/games/sources/save", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_save_source():
    form = request.form
    game_id = form.get("game_id", "").strip()
    source_type = (form.get("source_type") or "").strip()
    source_path = (form.get("source_path") or "").strip()

    if not game_id or not source_type or not source_path:
        return render_games_page(
            error="Game, source type, and source path are required to link a source.",
            source_form_data={
                "game_id": game_id,
                "source_type": source_type,
                "source_path": source_path,
            },
        ), 400

    db = get_db()
    db.execute(
        "INSERT INTO sources (game_id, source_type, source_path) VALUES (?,?,?)",
        (int(game_id), source_type, source_path),
    )
    db.commit()
    return redirect(url_for("games.games_page", message="Source linked to game."))


@games_bp.route("/games/sources/<int:source_id>/delete", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_delete_source(source_id):
    db = get_db()
    db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    db.commit()
    return redirect(url_for("games.games_page", message="Source removed."))


# ── Page: NFHS Matches ─────────────────────────────────────

@games_bp.route("/nfhs-matches")
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_page():
    return render_nfhs_matches_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@games_bp.route("/nfhs-matches/add", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_add():
    form = request.form
    scheduled_game_id = form.get("scheduled_game_id", "").strip()
    nfhs_game_id = (form.get("nfhs_game_id") or "").strip()
    nfhs_url = (form.get("nfhs_url") or "").strip()
    confidence = (form.get("confidence") or "").strip()

    if not scheduled_game_id or not nfhs_game_id or not nfhs_url:
        return render_nfhs_matches_page(
            error="Scheduled game, NFHS game ID, and NFHS URL are required.",
            form_data={
                "scheduled_game_id": scheduled_game_id,
                "nfhs_game_id": nfhs_game_id,
                "nfhs_url": nfhs_url,
                "confidence": confidence,
            },
        ), 400

    db = get_db()
    db.execute(
        """INSERT INTO nfhs_matches
           (scheduled_game_id, nfhs_game_id, nfhs_url, match_status, confidence)
           VALUES (?,?,?,?,?)""",
        (
            int(scheduled_game_id),
            nfhs_game_id,
            nfhs_url,
            "candidate",
            float(confidence) if confidence else None,
        ),
    )
    db.commit()
    return redirect(url_for("games.nfhs_matches_page", message="NFHS candidate added."))


@games_bp.route("/nfhs-matches/<int:match_id>/confirm", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_confirm_page(match_id):
    payload = confirm_nfhs_match(get_db(), match_id)
    if not payload:
        abort(404)
    return redirect(url_for("games.nfhs_matches_page", message="NFHS match confirmed and linked."))


@games_bp.route("/nfhs-matches/<int:match_id>/reject", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_reject_page(match_id):
    db = get_db()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (match_id,)).fetchone()
    if not row:
        abort(404)
    db.execute("UPDATE nfhs_matches SET match_status='rejected' WHERE id=?", (match_id,))
    db.commit()
    return redirect(url_for("games.nfhs_matches_page", message="NFHS match rejected."))
