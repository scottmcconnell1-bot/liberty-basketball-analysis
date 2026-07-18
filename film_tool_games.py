"""Server-side persistence for Film Tool manual tag game state."""

from __future__ import annotations

import json
from datetime import datetime, timezone

VALID_GAME_TYPES = frozenset({"my", "scout"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _seconds_to_mmss(value) -> str:
    try:
        total = int(float(value))
    except (TypeError, ValueError):
        return "0:00"
    minutes, seconds = divmod(max(0, total), 60)
    return f"{minutes}:{seconds:02d}"


def _normalize_game_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Game payload must be a JSON object")
    client_game_id = str(data.get("id") or "").strip()
    if not client_game_id:
        raise ValueError("Game id is required")
    rows = data.get("rows")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    game_type = (data.get("gameType") or data.get("game_type") or "my").strip().lower()
    if game_type not in VALID_GAME_TYPES:
        raise ValueError("gameType must be 'my' or 'scout'")
    normalized = dict(data)
    normalized["id"] = client_game_id
    normalized["gameType"] = game_type
    normalized["rows"] = rows
    normalized["updatedAt"] = data.get("updatedAt") or _utc_now_iso()
    return normalized


def _row_from_db(row) -> dict:
    try:
        state = json.loads(row["state_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    state.setdefault("id", row["client_game_id"])
    if row["analysis_key"] and not state.get("analysisGameId"):
        state["analysisGameId"] = row["analysis_key"]
    state["_serverUpdatedAt"] = row["updated_at"]
    state["_serverId"] = row["id"]
    return state


def _resolve_relational_game_id(db, analysis_key):
    if not analysis_key:
        return None
    from stats import _resolve_relational_game_id as resolve_id

    return resolve_id(db, analysis_key)


def list_film_tool_games(db, *, analysis_key=None, game_type=None) -> list[dict]:
    clauses = []
    params: list = []
    if analysis_key:
        clauses.append("analysis_key = ?")
        params.append(str(analysis_key).strip())
    if game_type:
        game_type = str(game_type).strip().lower()
        if game_type not in VALID_GAME_TYPES:
            raise ValueError("game_type must be 'my' or 'scout'")
        clauses.append("game_type = ?")
        params.append(game_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"""
        SELECT id, client_game_id, analysis_key, relational_game_id, game_type,
               game_date, our_team, opponent, tag_count, state_json, updated_at
          FROM film_tool_games
          {where}
         ORDER BY updated_at DESC, id DESC
        """,
        params,
    ).fetchall()
    return [_row_from_db(row) for row in rows]


def get_film_tool_game(db, client_game_id: str) -> dict | None:
    client_game_id = str(client_game_id or "").strip()
    if not client_game_id:
        raise ValueError("client_game_id is required")
    row = db.execute(
        """
        SELECT id, client_game_id, analysis_key, relational_game_id, game_type,
               game_date, our_team, opponent, tag_count, state_json, updated_at
          FROM film_tool_games
         WHERE client_game_id = ?
        """,
        (client_game_id,),
    ).fetchone()
    return _row_from_db(row) if row else None


def save_film_tool_game(db, data: dict, *, created_by_user_id=None) -> dict:
    payload = _normalize_game_payload(data)
    client_game_id = payload["id"]
    analysis_key = (
        str(payload.get("analysisGameId") or payload.get("analysis_key") or "").strip() or None
    )
    relational_game_id = _resolve_relational_game_id(db, analysis_key) if analysis_key else None
    tag_count = len(payload.get("rows") or [])
    state_json = json.dumps(payload, ensure_ascii=False)
    game_date = (payload.get("date") or "").strip() or None
    our_team = (payload.get("ourTeam") or "").strip() or None
    opponent = (payload.get("opponent") or "").strip() or None
    existing = db.execute(
        "SELECT id FROM film_tool_games WHERE client_game_id = ?",
        (client_game_id,),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE film_tool_games
               SET analysis_key = ?,
                   relational_game_id = ?,
                   game_type = ?,
                   game_date = ?,
                   our_team = ?,
                   opponent = ?,
                   tag_count = ?,
                   state_json = ?,
                   updated_at = CURRENT_TIMESTAMP
             WHERE client_game_id = ?
            """,
            (
                analysis_key,
                relational_game_id,
                payload["gameType"],
                game_date,
                our_team,
                opponent,
                tag_count,
                state_json,
                client_game_id,
            ),
        )
        row_id = existing["id"]
    else:
        row_id = db.execute(
            """
            INSERT INTO film_tool_games (
                client_game_id, analysis_key, relational_game_id, game_type,
                game_date, our_team, opponent, tag_count, state_json, created_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_game_id,
                analysis_key,
                relational_game_id,
                payload["gameType"],
                game_date,
                our_team,
                opponent,
                tag_count,
                state_json,
                created_by_user_id,
            ),
        ).lastrowid
    return {
        "id": row_id,
        "client_game_id": client_game_id,
        "analysis_key": analysis_key,
        "tag_count": tag_count,
        "updated_at": payload["updatedAt"],
    }


def delete_film_tool_game(db, client_game_id: str) -> bool:
    client_game_id = str(client_game_id or "").strip()
    if not client_game_id:
        raise ValueError("client_game_id is required")
    cur = db.execute(
        "DELETE FROM film_tool_games WHERE client_game_id = ?",
        (client_game_id,),
    )
    return cur.rowcount > 0


def _pick_backup_game(payload: dict) -> dict | None:
    """Normalize browser backup JSON (savedGames + autosave) to one game object."""
    if isinstance(payload.get("rows"), list):
        return payload
    autosave = payload.get("autosave")
    if isinstance(autosave, dict) and isinstance(autosave.get("rows"), list) and autosave["rows"]:
        return autosave
    saved = payload.get("savedGames")
    if isinstance(saved, list):
        candidates = [g for g in saved if isinstance(g, dict) and isinstance(g.get("rows"), list) and g["rows"]]
        if candidates:
            return max(candidates, key=lambda g: len(g.get("rows") or []))
    return None


def import_exported_events(db, payload: dict, *, created_by_user_id=None) -> dict:
    """Import Film Tool export JSON (events_*.json) or a full saved game blob."""
    if not isinstance(payload, dict):
        raise ValueError("Import payload must be a JSON object")

    backup_game = _pick_backup_game(payload)
    if backup_game is not None and backup_game is not payload:
        merged = dict(backup_game)
        if payload.get("analysisGameId") and not merged.get("analysisGameId"):
            merged["analysisGameId"] = payload["analysisGameId"]
        return save_film_tool_game(db, merged, created_by_user_id=created_by_user_id)

    if isinstance(payload.get("rows"), list):
        return save_film_tool_game(db, payload, created_by_user_id=created_by_user_id)

    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Import file must contain events[] or a saved game with rows[]")

    client_game_id = str(payload.get("id") or f"import-{int(datetime.now(timezone.utc).timestamp() * 1000)}")
    rows = []
    for event in events:
        if not isinstance(event, dict):
            continue
        start = event.get("start")
        duration = event.get("duration")
        rows.append({
            "label": event.get("label") or "",
            "player": event.get("player") or "",
            "quarter": event.get("quarter") or "",
            "team": event.get("team") or "",
            "side": event.get("side") or "",
            "category": event.get("category") or "",
            "eventtype": event.get("eventtype") or "",
            "result": event.get("result") or "",
            "start": start if isinstance(start, str) and ":" in str(start) else _seconds_to_mmss(start),
            "duration": duration if isinstance(duration, str) and ":" in str(duration) else _seconds_to_mmss(duration),
            "notes": event.get("notes") or "",
        })

    game = {
        "id": client_game_id,
        "gameType": payload.get("gametype") or payload.get("mode") or "my",
        "date": payload.get("date") or "",
        "ourTeam": payload.get("ourTeam") or "Liberty",
        "opponent": payload.get("opponent") or "",
        "analysisGameId": payload.get("analysisGameId") or payload.get("analysis_key") or "",
        "rows": rows,
        "currentStarters": payload.get("currentStarters"),
        "quarterStarters": payload.get("quarterStarters"),
        "updatedAt": _utc_now_iso(),
    }
    return save_film_tool_game(db, game, created_by_user_id=created_by_user_id)
