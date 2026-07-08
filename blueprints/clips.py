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

import json
import sqlite3

from flask import (
    Blueprint, abort, current_app, g, jsonify, redirect, request, session, url_for,
)

import player_development as pd_helpers

from helpers import get_db, refresh_game_stats, require_feature
from review_actions import accept_event, reject_event
from stats import _resolve_relational_game_id

clips_bp = Blueprint("clips", __name__)


# ── API: Events ───────────────────────────────────────────

@clips_bp.route("/api/save_event", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def save_event():
    data = request.get_json(force=True)
    if not data or "timestamp_ms" not in data:
        return jsonify({"status": "error", "message": "timestamp_ms required"}), 400

    # Validate required fields
    event_type = (data.get("event_type") or "").strip()
    if not event_type:
        return jsonify({"status": "error", "message": "event_type required"}), 400

    # Validate timestamp_ms is numeric
    try:
        timestamp_ms = int(data["timestamp_ms"])
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "timestamp_ms must be an integer"}), 400

    # Validate details_json is valid JSON if provided
    details_json = data.get("details_json")
    if details_json is not None:
        if isinstance(details_json, str):
            try:
                json.loads(details_json)
            except (json.JSONDecodeError, TypeError):
                return jsonify({"status": "error", "message": "details_json must be valid JSON"}), 400
        elif not isinstance(details_json, (dict, list)):
            return jsonify({"status": "error", "message": "details_json must be a JSON object or array"}), 400

    raw_game_id = data.get("game_id")
    if raw_game_id in (None, ""):
        return jsonify({"status": "error", "message": "game_id required"}), 400
    try:
        game_id_int = int(raw_game_id)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "game_id must be an existing game id"}), 400

    db = get_db()
    game = db.execute("SELECT id FROM games WHERE id=?", (game_id_int,)).fetchone()
    if not game:
        return jsonify({"status": "error", "message": "game_id must reference an existing game"}), 400

    # ── Stage 4B: resolve relational columns ───────────────
    game_id = str(game_id_int)
    relational_game_id = game_id_int

    # event_type_id: lookup by code (case-insensitive); leave NULL if unknown
    event_type_id = None
    et_row = db.execute(
        "SELECT id FROM event_types WHERE code=?", (event_type.lower(),)
    ).fetchone()
    if et_row:
        event_type_id = et_row["id"]

    # primary_player_id + team_id: resolve player name → roster_membership
    # Uses case-insensitive trimmed match following Stage 4A backfill pattern
    player = str(data.get("player", ""))[:128] if data.get("player") else None
    primary_player_id = None
    team_id = None
    primary_roster_membership_id = None
    if player:
        rm_row = db.execute(
            """SELECT rm.id AS rm_id, rm.player_id, rm.team_id
                 FROM roster_memberships rm
                 JOIN players p ON p.id = rm.player_id
                WHERE lower(trim(p.name)) = lower(trim(?))
                  AND rm.status = 'active'
                ORDER BY rm.created_at DESC
                LIMIT 1""",
            (player,),
        ).fetchone()
        if rm_row:
            primary_player_id = rm_row["player_id"]
            team_id = rm_row["team_id"]
            primary_roster_membership_id = rm_row["rm_id"]

    # created_by_user_id: from session
    created_by_user_id = _current_review_user_id()

    # ── remaining fields ────────────────────────────────────
    shot_result = str(data.get("shot_result", ""))[:32] if data.get("shot_result") else None
    source_video = str(data.get("source_video", ""))[:256] if data.get("source_video") else None
    human_verified = int(bool(data.get("human_verified", True)))
    review_status = "accepted" if human_verified else "pending"
    source_type = str(data.get("source_type", "manual"))[:64] if data.get("source_type") else "manual"

    # ── Stage 4C.2: explicit possession_id linkage ──────────
    possession_id = None
    raw_pid = data.get("possession_id")
    if raw_pid is not None:
        try:
            pid_int = int(raw_pid)
        except (TypeError, ValueError):
            pid_int = None
        if pid_int is not None:
            # Validate the possession exists and belongs to the same game.
            owner = db.execute(
                "SELECT id FROM possessions WHERE id=? AND game_id=?",
                (pid_int, relational_game_id),
            ).fetchone()
            if owner:
                possession_id = pid_int
            # else: silently ignore invalid/mismatched possession_id.

    try:
        cur = db.execute(
            """INSERT INTO events
               (game_id, player, event_type, shot_result, timestamp_ms, details_json,
                source_video, source_frame, human_verified, confidence,
                review_status, source_type, reviewed_at,
                possession_id,
                relational_game_id, event_type_id, team_id,
                primary_player_id, primary_roster_membership_id,
                created_by_user_id, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,
                       ?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)""",
            (
                game_id,
                player,
                event_type,
                shot_result,
                timestamp_ms,
                details_json if isinstance(details_json, str) else json.dumps(details_json) if details_json else None,
                source_video,
                data.get("source_frame"),
                human_verified,
                data.get("confidence"),
                review_status,
                source_type,
                review_status,
                possession_id,
                relational_game_id,
                event_type_id,
                team_id,
                primary_player_id,
                primary_roster_membership_id,
                created_by_user_id,
            ),
        )
        if review_status == "pending":
            db.execute(
                """INSERT OR IGNORE INTO review_items
                      (entity_type, entity_id, game_id, relational_game_id, review_status, reason)
                   VALUES ('event', ?, ?, ?, 'pending', 'Event needs coach review')""",
                (cur.lastrowid, game_id, relational_game_id),
            )

        # ── Stage 4B: write primary event_participants row ────
        if primary_player_id is not None:
            db.execute(
                """INSERT INTO event_participants
                      (event_id, player_id, roster_membership_id, team_id,
                       role, source)
                   VALUES (?, ?, ?, ?, 'primary', ?)""",
                (
                    cur.lastrowid,
                    primary_player_id,
                    primary_roster_membership_id,
                    team_id,
                    source_type,
                ),
            )

        db.commit()
        refresh_game_stats(db, game_id)
        return jsonify({"status": "success", "id": cur.lastrowid})
    except sqlite3.Error as e:
        db.rollback()
        current_app.logger.error(f"save_event DB error: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500


@clips_bp.route("/api/events/<game_id>", methods=["GET"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def get_events(game_id):
    db = get_db()
    event_type = (request.args.get("event_type") or "").strip()
    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is not None:
        if event_type:
            rows = db.execute(
                """SELECT * FROM events
                    WHERE (relational_game_id = ?
                           OR (relational_game_id IS NULL AND game_id = ?))
                      AND event_type=?
                    ORDER BY timestamp_ms ASC""",
                (relational_game_id, game_id, event_type),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT * FROM events
                    WHERE relational_game_id = ?
                       OR (relational_game_id IS NULL AND game_id = ?)
                    ORDER BY timestamp_ms ASC""",
                (relational_game_id, game_id),
            ).fetchall()
    elif event_type:
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
           timestamp_ms=?, details_json=?, human_verified=?, confidence=?,
           updated_at=CURRENT_TIMESTAMP
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


def _current_review_user_id():
    """Return the current user id from request context, or None.

    Resolution order:
      1. g.user (set by future auth middleware)
      2. session["user_id"] (set by blueprints/users.py login flow)
      3. session["current_user_id"] (alternate key)
      4. session.get("user", {}).get("id") (session stores user object)

    If a candidate id is found, it is validated against the users table
    before being returned. Invalid or missing ids yield None (keeping
    created_by_user_id NULL).
    """
    # 1. g.user (will work once auth middleware sets it)
    user = getattr(g, "user", None)
    if isinstance(user, dict):
        uid = user.get("id")
        if uid is not None:
            return _validate_user_id(uid)
    if user is not None and hasattr(user, "get"):
        uid = user.get("id")
        if uid is not None:
            return _validate_user_id(uid)

    # 2–4. Session fallback — matches keys used by blueprints/users.py
    for key in ("user_id", "current_user_id"):
        uid = session.get(key)
        if uid is not None:
            return _validate_user_id(uid)

    # session["user"]["id"] — if session stores a user dict
    user_obj = session.get("user")
    if isinstance(user_obj, dict):
        uid = user_obj.get("id")
        if uid is not None:
            return _validate_user_id(uid)

    return None


def _validate_user_id(uid):
    """Return uid if it corresponds to an active user row, else None."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT id FROM users WHERE id = ? AND is_active = 1", (int(uid),)
        ).fetchone()
        return row["id"] if row else None
    except (ValueError, TypeError):
        return None


def _stringify_review_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _insert_review_provenance(db, event_id, action, user_id, details):
    from review_actions import _insert_review_provenance as _insert

    return _insert(db, event_id, action, user_id, details)


def _record_human_correction(db, row, correction_type, field_changed,
                             original_value, corrected_value, notes=None):
    from review_actions import _record_human_correction as _record

    return _record(
        db, row, correction_type, field_changed, original_value, corrected_value, notes
    )


def _sync_event_review_item(db, event_id, status, user_id=None, notes=None):
    from review_actions import _sync_event_review_item as _sync

    return _sync(db, event_id, status, user_id=user_id, notes=notes)


@clips_bp.route("/api/review/events", methods=["GET"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def review_events():
    db = get_db()
    clauses = []
    params = []

    review_status = (request.args.get("review_status") or "pending").strip()
    if review_status and review_status != "all":
        clauses.append("e.review_status = ?")
        params.append(review_status)

    for key in ["game_id", "event_type", "source_type", "player"]:
        value = (request.args.get(key) or "").strip()
        if value:
            clauses.append(f"e.{key} = ?")
            params.append(value)

    min_conf = request.args.get("min_confidence")
    if min_conf not in (None, ""):
        clauses.append("e.confidence >= ?")
        params.append(float(min_conf))
    max_conf = request.args.get("max_confidence")
    if max_conf not in (None, ""):
        clauses.append("e.confidence <= ?")
        params.append(float(max_conf))

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.execute(
        f"""SELECT e.*,
                  ri.id AS review_item_id,
                  ri.priority AS review_priority,
                  ri.reason AS review_reason,
                  ri.notes AS queue_notes
             FROM events e
             LEFT JOIN review_items ri
               ON ri.entity_type='event' AND ri.entity_id=e.id
             {where}
            ORDER BY e.game_id, e.timestamp_ms, e.id""",
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@clips_bp.route("/api/review/events/<int:event_id>/accept", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def review_event_accept(event_id):
    data = request.get_json(silent=True) or {}
    notes = data.get("notes")
    db = get_db()
    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    user_id = _current_review_user_id()
    updated = accept_event(db, event_id, user_id=user_id, notes=notes, commit=True)
    return jsonify(updated)


@clips_bp.route("/api/review/events/<int:event_id>/reject", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def review_event_reject(event_id):
    data = request.get_json(silent=True) or {}
    notes = data.get("notes")
    db = get_db()
    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    user_id = _current_review_user_id()
    updated = reject_event(db, event_id, user_id=user_id, notes=notes, commit=True)
    return jsonify(updated)


@clips_bp.route("/api/review/events/<int:event_id>/correct", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def review_event_correct(event_id):
    data = request.get_json(force=True) or {}
    notes = data.get("notes")
    allowed_fields = {
        "player",
        "event_type",
        "shot_result",
        "timestamp_ms",
        "details_json",
        "confidence",
    }
    updates = {field: data[field] for field in allowed_fields if field in data}
    if not updates:
        return jsonify({"error": "At least one correctable field is required"}), 400

    if "timestamp_ms" in updates:
        try:
            updates["timestamp_ms"] = int(updates["timestamp_ms"])
        except (TypeError, ValueError):
            return jsonify({"error": "timestamp_ms must be an integer"}), 400
    if "event_type" in updates and not str(updates["event_type"]).strip():
        return jsonify({"error": "event_type is required"}), 400
    if "details_json" in updates and isinstance(updates["details_json"], (dict, list)):
        updates["details_json"] = json.dumps(updates["details_json"])

    db = get_db()
    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    changed = {
        field: value for field, value in updates.items()
        if _stringify_review_value(row[field]) != _stringify_review_value(value)
    }
    if not changed:
        return jsonify({"error": "No changed fields supplied"}), 400

    for field, value in changed.items():
        _record_human_correction(
            db,
            row,
            "change_event",
            field,
            row[field],
            value,
            notes,
        )

    values = {
        "player": row["player"],
        "event_type": row["event_type"],
        "shot_result": row["shot_result"],
        "timestamp_ms": row["timestamp_ms"],
        "details_json": row["details_json"],
        "confidence": row["confidence"],
    }
    values.update(changed)
    user_id = _current_review_user_id()
    db.execute(
        """UPDATE events
              SET player=?,
                  event_type=?,
                  shot_result=?,
                  timestamp_ms=?,
                  details_json=?,
                  confidence=?,
                  review_status='corrected',
                  human_verified=1,
                  reviewed_by_user_id=?,
                  reviewed_at=CURRENT_TIMESTAMP,
                  review_notes=COALESCE(?, review_notes)
            WHERE id=?""",
        (
            values["player"],
            values["event_type"],
            values["shot_result"],
            values["timestamp_ms"],
            values["details_json"],
            values["confidence"],
            user_id,
            notes,
            event_id,
        ),
    )
    _sync_event_review_item(db, event_id, "corrected", user_id, notes)
    _insert_review_provenance(
        db,
        event_id,
        "correct_event",
        user_id,
        {"fields_changed": sorted(changed.keys()), "notes": notes},
    )
    db.commit()
    refresh_game_stats(db, row["game_id"])
    return jsonify(dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()))


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


@clips_bp.route("/api/players/<int:player_id>", methods=["DELETE"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_players_delete(player_id):
    db = get_db()
    db.execute("DELETE FROM players WHERE id=?", (player_id,))
    db.commit()
    return jsonify({"status": "deleted"}), 200


@clips_bp.route("/api/rosters/import", methods=["POST"])
def api_rosters_import():
    """Parse a roster upload (CSV, Excel, PDF, or MaxPreps printable PDF)."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    roster_file = request.files["file"]
    if not roster_file or not roster_file.filename:
        return jsonify({"error": "No file selected"}), 400

    file_type = (request.form.get("file_type") or "auto").strip().lower()
    try:
        from roster_import import parse_roster_upload

        result = parse_roster_upload(roster_file, file_type=file_type)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to parse roster: {exc}"}), 500


@clips_bp.route("/api/film-rosters/summary", methods=["GET"])
def api_film_rosters_summary():
    """List non-empty Film Tool roster slots (for recovery / diagnostics)."""
    rows = get_db().execute(
        """
        SELECT frp.season_id, s.name AS season_name, frp.level, frp.gender, frp.side,
               COUNT(*) AS count
          FROM film_roster_players frp
          LEFT JOIN seasons s ON s.id = frp.season_id
         GROUP BY frp.season_id, frp.level, frp.gender, frp.side
         ORDER BY count DESC, frp.season_id DESC
        """
    ).fetchall()
    return jsonify({
        "slots": [dict(row) for row in rows],
        "total_players": sum(int(row["count"] or 0) for row in rows),
    })


@clips_bp.route("/api/film-rosters", methods=["GET"])
def api_film_rosters_get():
    """List players for a season-scoped Film Tool roster slot."""
    from film_roster import list_film_roster_players

    try:
        players = list_film_roster_players(
            get_db(),
            season_id=request.args.get("season_id"),
            level=request.args.get("level"),
            gender=request.args.get("gender"),
            side=request.args.get("side"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"players": players, "count": len(players)})


@clips_bp.route("/api/film-rosters", methods=["PUT"])
def api_film_rosters_put():
    """Replace or merge players for a season-scoped Film Tool roster slot."""
    from film_roster import save_film_roster

    data = request.get_json(force=True) or {}
    replace = str(data.get("replace", True)).lower() not in {"0", "false", "no"}
    try:
        result = save_film_roster(
            get_db(),
            season_id=data.get("season_id"),
            level=data.get("level"),
            gender=data.get("gender"),
            side=data.get("side"),
            players=data.get("players") or [],
            replace=replace,
        )
        get_db().commit()
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@clips_bp.route("/api/film-rosters", methods=["DELETE"])
def api_film_rosters_delete():
    """Mass-delete all players in a season-scoped Film Tool roster slot."""
    from film_roster import delete_film_roster

    try:
        deleted = delete_film_roster(
            get_db(),
            season_id=request.args.get("season_id"),
            level=request.args.get("level"),
            gender=request.args.get("gender"),
            side=request.args.get("side"),
        )
        get_db().commit()
        return jsonify({"deleted": deleted})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@clips_bp.route("/api/film-rosters/import", methods=["POST"])
def api_film_rosters_import():
    """Parse and save a roster upload for a specific season and team slot."""
    from film_roster import save_film_roster
    from roster_import import parse_roster_upload

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    roster_file = request.files["file"]
    if not roster_file or not roster_file.filename:
        return jsonify({"error": "No file selected"}), 400

    file_type = (request.form.get("file_type") or "auto").strip().lower()
    replace = str(request.form.get("replace", "true")).lower() not in {"0", "false", "no"}
    try:
        parsed = parse_roster_upload(roster_file, file_type=file_type)
        players = parsed.get("players") or []
        if not players:
            raise ValueError("No players found in file. Check the file type and format.")

        saved = save_film_roster(
            get_db(),
            season_id=request.form.get("season_id"),
            level=request.form.get("level"),
            gender=request.form.get("gender"),
            side=request.form.get("side"),
            players=players,
            replace=replace,
        )
        get_db().commit()
        return jsonify({
            "detected_type": parsed.get("detected_type"),
            "count": saved["count"],
            "players": saved["players"],
            "season_id": saved["season_id"],
            "level": saved["level"],
            "gender": saved["gender"],
            "side": saved["side"],
            "replaced": replace,
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to import roster: {exc}"}), 500


# ── API: Clips ────────────────────────────────────────────

@clips_bp.route("/api/clips")
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_list():
    db = get_db()
    player_id = request.args.get("player_id", type=int)
    season_id = request.args.get("season_id", type=int)
    category = request.args.get("category")
    game_id = request.args.get("game_id")
    relational_game_id = request.args.get("relational_game_id", type=int)
    clips = pd_helpers.get_clips(db, player_id=player_id, season_id=season_id,
                                  category=category, game_id=game_id,
                                  relational_game_id=relational_game_id)
    return jsonify(clips)


@clips_bp.route("/api/clips", methods=["POST"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_create():
    db = get_db()
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        canonical_clip_id = data.get("canonical_clip_id")
        if canonical_clip_id not in (None, ""):
            canonical_clip_id = int(canonical_clip_id)
        else:
            canonical_clip_id = None
        auto_link = str(data.get("auto_link_canonical", "true")).lower() not in ("0", "false", "no")
        clip = pd_helpers.create_clip(
            db,
            clip_label=data["clip_label"],
            clip_start_ms=int(data["clip_start_ms"]),
            clip_end_ms=int(data["clip_end_ms"]),
            player_id=data.get("player_id") or None,
            game_id=data.get("game_id"),
            event_id=data.get("event_id"),
            clip_category=data.get("clip_category", "general"),
            season_id=data.get("season_id") or None,
            notes=data.get("notes"),
            relational_game_id=data.get("relational_game_id"),
            canonical_clip_id=canonical_clip_id,
            auto_link_canonical=auto_link and canonical_clip_id is None,
        )
        if request.form:
            return redirect(url_for("player_dev.player_development_page", message="Clip saved"))
        return jsonify(clip), 201
    except (ValueError, KeyError) as e:
        if request.form:
            return redirect(url_for("player_dev.player_development_page", error=str(e)))
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
        if "canonical_clip_id" in data and data["canonical_clip_id"] is not None:
            data["canonical_clip_id"] = int(data["canonical_clip_id"])
        clip = pd_helpers.update_clip(db, clip_id, **data)
        return jsonify(clip)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clips_bp.route("/api/clips/<int:clip_id>/link-canonical", methods=["POST"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_link_canonical(clip_id):
    db = get_db()
    data = request.get_json(silent=True) or request.form.to_dict()
    canonical_clip_id = data.get("canonical_clip_id")
    if not canonical_clip_id:
        return jsonify({"error": "canonical_clip_id is required"}), 400
    try:
        clip = pd_helpers.link_development_clip_to_canonical(
            db, clip_id, int(canonical_clip_id)
        )
        if request.form:
            return redirect(url_for("player_dev.player_development_page", message="Canonical clip linked"))
        return jsonify(clip)
    except (KeyError, ValueError) as e:
        if request.form:
            return redirect(url_for("player_dev.player_development_page", error=str(e)))
        return jsonify({"error": str(e)}), 400


@clips_bp.route("/api/clips/<int:clip_id>", methods=["DELETE"])
@require_feature("ENABLE_PLAYER_DEVELOPMENT")
def api_clips_delete(clip_id):
    db = get_db()
    pd_helpers.delete_clip(db, clip_id)
    return jsonify({"status": "deleted"})
