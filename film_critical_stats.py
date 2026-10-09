"""Write film-tool steals, fouls, and steal-linked turnovers onto one run.

Scott (2026-10-08): those tags are truth and belong on the counting card.
``teach_from_film_tool_rows`` is not used here. That helper saves every shot
and rebound tag and then rejects nearby AI rows. This writer only inserts or
updates the critical families, and it leaves every other event alone.
"""

from __future__ import annotations

import json
from typing import Any

from helpers import normalize_analysis_game_id
from manual_tag_teach import TEACH_NOTE, _lookup_event_type_id, map_manual_row

LINKED_STEAL_NOTE = "Linked to steal"


def _row_id(row) -> int:
    try:
        return int(row["id"])
    except (KeyError, TypeError, IndexError):
        return int(row[0])


def _team_side(team: str, scorebook: dict | None) -> str | None:
    """Home or away, so the box can place a jersey that both teams wear.

    The tag already names Liberty or Adrian. The scorebook only says which of
    those names is home. Stat totals are not copied from the book.
    """
    if not scorebook:
        return None
    name = str(team or "").strip().lower()
    if not name:
        return None
    home = str(scorebook.get("home_team") or "").strip().lower()
    away = str(scorebook.get("away_team") or "").strip().lower()
    if name == home:
        return "home"
    if name == away:
        return "away"
    return None


def critical_film_tags(rows: list[dict] | None) -> list[tuple[dict, dict]]:
    """Steal tags, foul-family tags, and turnovers whose notes start with the steal link."""
    kept: list[tuple[dict, dict]] = []
    for row in rows or []:
        raw = row or {}
        eventtype = str(raw.get("eventtype") or "").strip()
        notes = str(raw.get("notes") or "")
        mapped = map_manual_row(raw)
        if not mapped:
            continue
        family = mapped.get("family")
        if family in {"steal", "foul"}:
            kept.append((raw, mapped))
        elif eventtype == "Turnover" and notes.startswith(LINKED_STEAL_NOTE):
            kept.append((raw, mapped))
    return kept


def write_film_tool_critical_stats(db, game_id: str, rows: list[dict] | None) -> dict[str, Any]:
    """Insert or update manual film-tool rows for steals, fouls, and linked turnovers.

    A second call with the same event type and timestamp updates that row.
    Other events on the game are not deleted.
    """
    game_id = normalize_analysis_game_id(game_id)
    selected = critical_film_tags(rows)
    if not game_id:
        return {"ok": False, "error": "game_id required", "inserted": 0, "updated": 0}

    scorebook = None
    try:
        from program_mode import load_scorebook

        scorebook = load_scorebook(game_id)
    except Exception:
        scorebook = None

    inserted = 0
    updated = 0
    written: list[dict[str, Any]] = []
    used_ids: set[int] = set()

    for raw, item in selected:
        side = _team_side(item.get("team") or "", scorebook)
        details = {
            "film_tool_teach": True,
            "label": item["label"],
            "player": item["player"],
            "team": item["team"],
            "shot_type": item.get("shot_type"),
            "foul_type": item.get("foul_type"),
            "start": str(raw.get("start") or ""),
        }
        if side:
            details["team_side"] = side
        event_type_id = _lookup_event_type_id(db, item["event_type"])
        existing = db.execute(
            """SELECT id FROM events
                WHERE game_id=? AND source_type='manual'
                  AND event_type=? AND timestamp_ms=?
                  AND COALESCE(details_json,'') LIKE '%film_tool_teach%'
                ORDER BY id""",
            (game_id, item["event_type"], item["timestamp_ms"]),
        ).fetchall()
        event_id = None
        for row in existing:
            candidate = _row_id(row)
            if candidate not in used_ids:
                event_id = candidate
                break
        payload = (
            item["player"] or None,
            item["event_type"],
            event_type_id,
            item["shot_result"],
            item["timestamp_ms"],
            json.dumps(details),
            TEACH_NOTE,
        )
        if event_id is None:
            cur = db.execute(
                """INSERT INTO events
                      (game_id, player, event_type, event_type_id, shot_result, timestamp_ms, details_json,
                       human_verified, confidence, review_status, source_type, review_notes, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1.0, 'accepted', 'manual', ?, CURRENT_TIMESTAMP)""",
                (game_id, *payload),
            )
            event_id = int(cur.lastrowid)
            inserted += 1
        else:
            db.execute(
                """UPDATE events
                      SET player=?, event_type=?, event_type_id=?, shot_result=?, timestamp_ms=?,
                          details_json=?, human_verified=1, confidence=1.0, review_status='accepted',
                          source_type='manual', review_notes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                (*payload, event_id),
            )
            updated += 1
        used_ids.add(event_id)
        written.append({
            "id": event_id,
            "event_type": item["event_type"],
            "player": item["player"],
            "team": item["team"],
            "start": str(raw.get("start") or ""),
            "timestamp_ms": item["timestamp_ms"],
            "label": item["label"],
        })

    db.commit()
    return {
        "ok": True,
        "game_id": game_id,
        "inserted": inserted,
        "updated": updated,
        "events": written,
    }


def _live_main() -> int:
    import sqlite3 as _sqlite
    from pathlib import Path

    root = Path(__file__).resolve().parent
    tag_path = root / "data" / "film_tags" / "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
    run_id = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941"
    doc = json.loads(tag_path.read_text(encoding="utf-8"))
    db = _sqlite.connect(root / "film_analysis.db", timeout=30)
    db.row_factory = _sqlite.Row
    result = write_film_tool_critical_stats(db, run_id, doc.get("rows") or [])
    print(json.dumps({"inserted": result["inserted"], "updated": result["updated"], "n": len(result["events"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_live_main())
