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

  - Highlight clips (reviewed ledger)
      GET    /highlights                   — filter jersey/type → generate clips
      GET    /api/highlights/games         — games with reviewed event counts
      GET    /api/highlights/moments       — reviewed moments + seek links
      POST   /api/highlights/generate      — save clips + optional ffmpeg cuts

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
    Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, session, url_for,
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


USEFUL_REVIEW_EVENT_TYPES = (
    "shot",
    "miss",
    "make",
    "missed_two",
    "made_two",
    "missed_three",
    "made_three",
    "missed_free_throw",
    "made_free_throw",
    "rebound",
    "assist",
    "turnover",
    "steal",
    "block",
    "foul",
)


@clips_bp.route("/api/review/events", methods=["GET"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def review_events():
    db = get_db()
    clauses = []
    params = []

    review_status = (request.args.get("review_status") or "pending").strip()
    if review_status in ("ledger", "trusted"):
        # Official MVP ledger = coach-accepted or corrected events only.
        clauses.append("e.review_status IN ('accepted', 'corrected')")
    elif review_status and review_status != "all":
        clauses.append("e.review_status = ?")
        params.append(review_status)

    for key in ["event_type", "source_type", "player"]:
        value = (request.args.get(key) or "").strip()
        if value:
            clauses.append(f"e.{key} = ?")
            params.append(value)

    # Prefer the canonical event key (base, not empty __rerun_ copies).
    game_id_value = (request.args.get("game_id") or "").strip()
    if game_id_value:
        try:
            from program_mode import canonical_event_key

            game_id_value = canonical_event_key(db, game_id_value)
        except Exception:
            if "__rerun_" in game_id_value:
                game_id_value = game_id_value.split("__rerun_", 1)[0]
        clauses.append("e.game_id = ?")
        params.append(game_id_value)

    useful_only = (request.args.get("useful_only") or "").strip().lower() in ("1", "true", "yes")
    if useful_only and not (request.args.get("event_type") or "").strip():
        placeholders = ",".join("?" for _ in USEFUL_REVIEW_EVENT_TYPES)
        clauses.append(f"e.event_type IN ({placeholders})")
        params.extend(USEFUL_REVIEW_EVENT_TYPES)

    exclude_raw = (request.args.get("exclude_types") or "").strip()
    if exclude_raw:
        excluded = [part.strip() for part in exclude_raw.split(",") if part.strip()]
        if excluded:
            placeholders = ",".join("?" for _ in excluded)
            clauses.append(f"e.event_type NOT IN ({placeholders})")
            params.extend(excluded)

    min_conf = request.args.get("min_confidence")
    if min_conf not in (None, ""):
        clauses.append("e.confidence >= ?")
        params.append(float(min_conf))
    max_conf = request.args.get("max_confidence")
    if max_conf not in (None, ""):
        clauses.append("e.confidence <= ?")
        params.append(float(max_conf))

    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    if (request.args.get("count_only") or "").strip().lower() in ("1", "true", "yes"):
        count = db.execute(
            f"SELECT COUNT(*) AS c FROM events e {where}",
            params,
        ).fetchone()["c"]
        return jsonify({"count": int(count or 0)})

    around_ms = request.args.get("around_ms", type=int)
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", type=int) or 0
    if limit is not None and limit <= 0:
        limit = None
    if offset < 0:
        offset = 0

    select_cols = """e.*,
                  ri.id AS review_item_id,
                  ri.priority AS review_priority,
                  ri.reason AS review_reason,
                  ri.notes AS queue_notes"""
    join_sql = """FROM events e
             LEFT JOIN review_items ri
               ON ri.entity_type='event' AND ri.entity_id=e.id"""
    where_sql = where if where else "WHERE 1=1"

    # Near playhead: window of events around current video time.
    if around_ms is not None and limit:
        half = max(limit // 2, 1)
        window_ms = request.args.get("window_ms", type=int)
        if window_ms is None or window_ms <= 0:
            window_ms = 45_000
        lo = max(0, around_ms - window_ms)
        hi = around_ms + window_ms
        before_rows = db.execute(
            f"""SELECT {select_cols}
                 {join_sql}
                 {where_sql}
                   AND e.timestamp_ms <= ?
                   AND e.timestamp_ms >= ?
                ORDER BY e.timestamp_ms DESC, e.id DESC
                LIMIT ?""",
            (*params, around_ms, lo, half + (limit % 2)),
        ).fetchall()
        after_rows = db.execute(
            f"""SELECT {select_cols}
                 {join_sql}
                 {where_sql}
                   AND e.timestamp_ms > ?
                   AND e.timestamp_ms <= ?
                ORDER BY e.timestamp_ms ASC, e.id ASC
                LIMIT ?""",
            (*params, around_ms, hi, half),
        ).fetchall()
        rows = list(reversed(before_rows)) + list(after_rows)
        # If nothing in the short window, return nearest events in the game
        # (Adrian quality keeps are often clustered early — mid-film must still list).
        if not rows:
            nearest = db.execute(
                f"""SELECT {select_cols}
                     {join_sql}
                     {where_sql}
                    ORDER BY ABS(e.timestamp_ms - ?) ASC, e.id ASC
                    LIMIT ?""",
                (*params, around_ms, limit),
            ).fetchall()
            rows = sorted(
                nearest,
                key=lambda r: (int(r["timestamp_ms"] or 0), int(r["id"] or 0)),
            )
        return jsonify([dict(r) for r in rows])

    order_sql = "ORDER BY e.timestamp_ms ASC, e.id ASC"
    limit_sql = ""
    limit_params: list = []
    if limit is not None:
        limit_sql = " LIMIT ? OFFSET ?"
        limit_params = [limit, offset]

    rows = db.execute(
        f"""SELECT {select_cols}
             {join_sql}
             {where}
            {order_sql}{limit_sql}""",
        (*params, *limit_params),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@clips_bp.route("/api/review/events", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def create_reviewed_event():
    """Coach-added ledger event at a video timestamp (string analysis game_id OK)."""
    data = request.get_json(silent=True) or {}
    game_id = str(data.get("game_id") or "").strip()
    event_type = str(data.get("event_type") or "").strip()
    if not game_id:
        return jsonify({"error": "game_id required"}), 400
    if not event_type:
        return jsonify({"error": "event_type required"}), 400
    try:
        timestamp_ms = int(data.get("timestamp_ms"))
    except (TypeError, ValueError):
        return jsonify({"error": "timestamp_ms must be an integer"}), 400

    player = str(data.get("player") or "").strip()[:128] or None
    notes = str(data.get("notes") or "").strip() or None
    details = {"source": "film_tool_add", "notes": notes} if notes else {"source": "film_tool_add"}
    shot_result = str(data.get("shot_result") or "").strip()[:32] or None
    source_video = str(data.get("source_video") or "").strip()[:256] or None
    user_id = _current_review_user_id()

    db = get_db()
    cur = db.execute(
        """INSERT INTO events
           (game_id, player, event_type, shot_result, timestamp_ms, details_json,
            source_video, human_verified, confidence, review_status, source_type,
            reviewed_at, created_by_user_id, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?, CURRENT_TIMESTAMP)""",
        (
            game_id,
            player,
            event_type,
            shot_result,
            timestamp_ms,
            json.dumps(details),
            source_video,
            1,
            1.0,
            "accepted",
            "manual",
            user_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM events WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@clips_bp.route("/api/program/<path:game_id>/summary", methods=["GET"])
@require_feature("ENABLE_AUTO_STATS_M1")
def program_summary_api(game_id):
    """Season-ops view: ledger box, scorebook exceptions, pending counts."""
    from program_mode import program_summary

    db = get_db()
    return jsonify(program_summary(db, game_id))


@clips_bp.route("/api/film-sync/<path:game_id>", methods=["GET"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def film_sync_get(game_id):
    """Return analysis→review timestamp offset for this game (ms)."""
    from film_sync import load_film_sync

    data = load_film_sync(game_id) or {
        "game_id": (game_id or "").split("__rerun_", 1)[0],
        "offset_ms": 0,
        "method": "none",
        "notes": "No sync file — review_ms = analysis timestamp_ms.",
    }
    return jsonify(data)


@clips_bp.route("/api/film-sync/<path:game_id>", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def film_sync_set(game_id):
    """Set analysis→review offset. Body: {offset_ms, notes?, method?}."""
    from datetime import datetime, timezone

    from film_sync import (
        ADRIAN_ANALYSIS_VIDEO,
        ADRIAN_BASE,
        ADRIAN_REVIEW_VIDEO,
        save_film_sync,
    )

    body = request.get_json(silent=True) or {}
    try:
        offset_ms = int(body.get("offset_ms") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "offset_ms must be an integer"}), 400
    base = (game_id or "").split("__rerun_", 1)[0]
    payload = {
        "offset_ms": offset_ms,
        "method": (body.get("method") or "manual").strip() or "manual",
        "notes": (body.get("notes") or "").strip(),
        "calibrated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_video": body.get("analysis_video")
        or (ADRIAN_ANALYSIS_VIDEO if base == ADRIAN_BASE else ""),
        "review_video": body.get("review_video")
        or (ADRIAN_REVIEW_VIDEO if base == ADRIAN_BASE else ""),
    }
    saved = save_film_sync(base, payload)
    return jsonify(saved)


@clips_bp.route("/api/program/<path:game_id>/auto-ledger", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def program_auto_ledger_api(game_id):
    """Promote useful AI drafts → program ledger; reject noise types.

    Distinct from confidence auto-accept (still locked at 0).
    Adrian games run scorebook quality refine first.
    """
    from adrian_quality import is_adrian_game, apply_quality_to_db
    from program_mode import program_summary, promote_useful_events_to_ledger

    db = get_db()
    quality = None
    if is_adrian_game(game_id):
        quality = apply_quality_to_db(db, game_id)
        # Quality already set accepted/rejected; skip blind promote.
        summary = program_summary(db, game_id)
        return jsonify({"ok": True, "quality": quality, "promote": None, "summary": summary})

    result = promote_useful_events_to_ledger(db, game_id, commit=True)
    summary = program_summary(db, game_id)
    return jsonify({"ok": True, "promote": result, "summary": summary})


@clips_bp.route("/api/program/<path:game_id>/refine", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def program_refine_api(game_id):
    """Adrian-only scorebook quality refine."""
    from adrian_quality import apply_quality_to_db, is_adrian_game
    from program_mode import program_summary

    if not is_adrian_game(game_id):
        return jsonify({"error": "refine is Adrian-only for now"}), 400
    db = get_db()
    quality = apply_quality_to_db(db, game_id)
    return jsonify({"ok": True, "quality": quality, "summary": program_summary(db, game_id)})


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

    # Adrian: coach name/jersey → stamp scorebook jersey + team on details
    # so Film Tool does not keep showing "player unlinked".
    try:
        from adrian_quality import is_adrian_game, resolve_adrian_teams, load_adrian_scorebook, _details
        from adrian_identity import resolve_label_to_scorebook, enrich_details_with_identity

        game_key = row["game_id"] if "game_id" in row.keys() else None
        if is_adrian_game(game_key) and values.get("player"):
            identity = resolve_label_to_scorebook(values["player"])
            if identity:
                details = _details({"details_json": values.get("details_json")})
                details = enrich_details_with_identity(
                    details, identity, teams=resolve_adrian_teams(load_adrian_scorebook())
                )
                values["details_json"] = json.dumps(details)
                # Prefer canonical scorebook jersey as player id for ledger alignment
                values["player"] = str(identity.get("jersey") or values["player"])
                if "details_json" not in changed:
                    changed["details_json"] = values["details_json"]
                changed["player"] = values["player"]
    except Exception:
        pass

    user_id = _current_review_user_id()
    correction_notes = notes or "Corrected in Film Tool"
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
                  review_notes=?
            WHERE id=?""",
        (
            values["player"],
            values["event_type"],
            values["shot_result"],
            values["timestamp_ms"],
            values["details_json"],
            values["confidence"],
            user_id,
            correction_notes,
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
    # Skip full stats rebuild on single corrections — same cost issue as accept/reject.
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


# ── Highlight clips (reviewed ledger → cut/export) ─────────

@clips_bp.route("/highlights")
@require_feature("ENABLE_MANUAL_TAG_MVP")
def highlights_page():
    """Filter reviewed events by jersey/type and generate highlight clips."""
    from video_trim import ffmpeg_available

    return render_template(
        "highlights.html",
        ffmpeg_available=ffmpeg_available(),
    )


@clips_bp.route("/api/highlights/games")
@require_feature("ENABLE_MANUAL_TAG_MVP")
def api_highlights_games():
    from highlight_clips import REVIEW_SCOPE, list_highlight_games

    db = get_db()
    return jsonify({
        "review_scope": REVIEW_SCOPE,
        "games": list_highlight_games(db),
    })


@clips_bp.route("/api/highlights/moments")
@require_feature("ENABLE_MANUAL_TAG_MVP")
def api_highlights_moments():
    from highlight_clips import (
        DEFAULT_PAD_AFTER_MS,
        DEFAULT_PAD_BEFORE_MS,
        list_highlight_moments,
    )

    game_id = (request.args.get("game_id") or "").strip()
    if not game_id:
        return jsonify({"error": "game_id is required"}), 400

    try:
        pad_before = int(request.args.get("pad_before_ms") or DEFAULT_PAD_BEFORE_MS)
        pad_after = int(request.args.get("pad_after_ms") or DEFAULT_PAD_AFTER_MS)
    except (TypeError, ValueError):
        return jsonify({"error": "pad_before_ms/pad_after_ms must be integers"}), 400

    payload = list_highlight_moments(
        get_db(),
        game_id,
        jersey=(request.args.get("jersey") or "").strip() or None,
        player=(request.args.get("player") or "").strip() or None,
        event_type=(request.args.get("event_type") or "").strip() or None,
        pad_before_ms=pad_before,
        pad_after_ms=pad_after,
    )
    return jsonify(payload)


@clips_bp.route("/api/highlights/generate", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def api_highlights_generate():
    from highlight_clips import (
        DEFAULT_PAD_AFTER_MS,
        DEFAULT_PAD_BEFORE_MS,
        generate_highlight_clips,
    )

    data = request.get_json(silent=True) or {}
    game_id = data.get("game_id")
    if game_id in (None, ""):
        return jsonify({"error": "game_id is required"}), 400

    event_ids = data.get("event_ids") or []
    if not isinstance(event_ids, list) or not event_ids:
        return jsonify({"error": "event_ids must be a non-empty list"}), 400

    try:
        pad_before = int(data.get("pad_before_ms") or DEFAULT_PAD_BEFORE_MS)
        pad_after = int(data.get("pad_after_ms") or DEFAULT_PAD_AFTER_MS)
    except (TypeError, ValueError):
        return jsonify({"error": "pad_before_ms/pad_after_ms must be integers"}), 400

    save_clips = str(data.get("save_clips", "true")).lower() not in ("0", "false", "no")
    cut_video = str(data.get("cut_video", "true")).lower() not in ("0", "false", "no")

    result = generate_highlight_clips(
        get_db(),
        game_id,
        event_ids,
        pad_before_ms=pad_before,
        pad_after_ms=pad_after,
        save_clips=save_clips,
        cut_video=cut_video,
        app=current_app._get_current_object(),
    )
    if result.get("error"):
        return jsonify({"error": result["error"]}), int(result.get("status") or 400)
    return jsonify(result), 201
