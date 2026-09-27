"""Turn Film Tool manual tags into ground truth the AI pass can keep.

Coach tags are stored as events (source_type=manual, human_verified=1) so
event_generator.persist_events will not wipe them. Nearby AI events in the
tagged window are corrected or rejected, and human_corrections is written.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from helpers import is_foul_event, normalize_analysis_game_id
from review_actions import reject_event

TEACH_NOTE = "Film Tool teach"
MATCH_TOLERANCE_MS = 8000
STAT_EVENTTYPES = {
    "2PT",
    "3PT",
    "FT",
    "Assist",
    "Steal",
    "Turnover",
    "Foul",
    "Block",
    "OffRebound",
    "DefRebound",
}
AI_SHOT_TYPES = {
    "shot",
    "make",
    "miss",
    "made_two",
    "missed_two",
    "made_three",
    "missed_three",
    "made_free_throw",
    "missed_free_throw",
    "free_throw",
}
AI_REBOUND_TYPES = {
    "rebound",
    "offensive_rebound",
    "defensive_rebound",
    "rebound_offensive",
    "rebound_defensive",
}


# Film Tool: category Foul, event type is the subcategory.
# A plain "Foul" tag is the category itself (older tags, before the split).
_FILM_FOUL_CODES = {
    "Foul": "foul",
    "Shooting": "foul_shooting",
    "Personal": "foul_personal",
    "Technical": "foul_technical",
}


def _film_foul_code(row: dict) -> str | None:
    eventtype = str(row.get("eventtype") or "").strip()
    category = str(row.get("category") or "").strip()
    if eventtype == "Foul":
        return "foul"
    if category == "Foul" and eventtype in _FILM_FOUL_CODES:
        return _FILM_FOUL_CODES[eventtype]
    return None


def _stat_code(item: dict) -> str:
    """Box-score code for a tag. The stored event_type for shots stays ``shot``."""
    shot_type = item.get("shot_type")
    make = item.get("shot_result") == "make"
    if shot_type == "2pt":
        return "made_two" if make else "missed_two"
    if shot_type == "3pt":
        return "made_three" if make else "missed_three"
    if shot_type == "ft":
        return "made_free_throw" if make else "missed_free_throw"
    return item["event_type"]


def _lookup_event_type_id(db, code: str):
    try:
        row = db.execute(
            "SELECT id FROM event_types WHERE lower(code) = lower(?)",
            (code,),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        return row["id"]
    except (KeyError, TypeError, IndexError):
        return row[0]


def time_to_ms(value) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return int(round(float(parts[0]) * 1000))
        return int(round(((int(parts[0]) or 0) * 60 + float(parts[1] or 0)) * 1000))
    except (TypeError, ValueError):
        return 0


def map_manual_row(row: dict) -> dict | None:
    eventtype = str(row.get("eventtype") or "").strip()
    foul_code = _film_foul_code(row)
    if eventtype not in STAT_EVENTTYPES and not foul_code:
        return None
    result = str(row.get("result") or "NA").strip()
    player = str(row.get("player") or "").strip()
    team = str(row.get("team") or "").strip()
    ms = time_to_ms(row.get("start"))
    if eventtype in {"2PT", "3PT", "FT"}:
        shot_type = {"2PT": "2pt", "3PT": "3pt", "FT": "ft"}[eventtype]
        shot_result = "make" if result == "Make" else "miss"
        return {
            "event_type": "shot",
            "shot_result": shot_result,
            "player": player,
            "team": team,
            "timestamp_ms": ms,
            "label": row.get("label") or f"{eventtype} {result}",
            "shot_type": shot_type,
            "family": "shot",
        }
    mapped = {
        "Assist": ("assist", "assist"),
        "Steal": ("steal", "steal"),
        "Turnover": ("turnover", "turnover"),
        "Foul": ("foul", "foul"),
        "Shooting": ("foul_shooting", "foul"),
        "Personal": ("foul_personal", "foul"),
        "Technical": ("foul_technical", "foul"),
        "Block": ("block", "block"),
        "OffRebound": ("rebound_offensive", "rebound"),
        "DefRebound": ("rebound_defensive", "rebound"),
    }[eventtype]
    return {
        "event_type": mapped[0],
        "shot_result": None,
        "player": player,
        "team": team,
        "timestamp_ms": ms,
        "label": row.get("label") or eventtype,
        "shot_type": "offensive" if eventtype == "OffRebound" else ("defensive" if eventtype == "DefRebound" else None),
        "foul_type": {
            "foul_shooting": "shooting",
            "foul_personal": "personal",
            "foul_technical": "technical",
        }.get(mapped[0]),
        "family": mapped[1],
    }


def _ai_family(event_type: str, details: dict | None = None) -> str | None:
    et = str(event_type or "").lower()
    if et in AI_SHOT_TYPES:
        return "shot"
    if et in AI_REBOUND_TYPES:
        return "rebound"
    if is_foul_event(et):
        return "foul"
    if et in {"assist", "steal", "turnover", "block"}:
        return et
    return None


def _details(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _row_get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def teach_from_film_tool_rows(db, game_id: str, rows: list[dict]) -> dict[str, Any]:
    """Replace prior Film Tool teach rows for this analysis key and grade AI events."""
    game_id = normalize_analysis_game_id(game_id)
    mapped = [item for item in (map_manual_row(row or {}) for row in rows or []) if item]
    if not game_id:
        return {"ok": False, "error": "game_id required", "manual_saved": 0}
    if not mapped:
        return {
            "ok": True,
            "game_id": game_id,
            "manual_saved": 0,
            "corrected": 0,
            "rejected": 0,
            "unmatched_manual": 0,
            "window_ms": None,
            "replaced": 0,
        }

    prior = db.execute(
        """SELECT id, event_type, timestamp_ms FROM events
            WHERE game_id=? AND source_type='manual'
              AND COALESCE(details_json,'') LIKE '%film_tool_teach%'
            ORDER BY timestamp_ms, id""",
        (game_id,),
    ).fetchall()
    prior_ids = [int(_row_get(r, "id")) for r in prior]

    # Re-saving replaces the tag set, but prior rows are rewritten in place rather
    # than deleted: highlight clips (clips / player_development_clips) may point at
    # them and a DELETE would fail the foreign key.
    reuse: list[int | None] = [None] * len(mapped)
    free = list(prior)
    for i, item in enumerate(mapped):
        for row in free:
            if (_row_get(row, "event_type"), int(_row_get(row, "timestamp_ms") or 0)) == (
                item["event_type"], item["timestamp_ms"]
            ):
                reuse[i] = int(_row_get(row, "id"))
                free.remove(row)
                break
    for i in range(len(mapped)):
        if reuse[i] is None and free:
            reuse[i] = int(_row_get(free.pop(0), "id"))
    surplus = [int(_row_get(r, "id")) for r in free]
    if surplus:
        marks = ",".join("?" * len(surplus))
        for table in ("clips", "player_development_clips"):
            try:
                db.execute(f"UPDATE {table} SET event_id=NULL WHERE event_id IN ({marks})", surplus)
            except sqlite3.OperationalError:  # table absent on slim DBs
                pass
        db.execute(f"DELETE FROM events WHERE id IN ({marks})", surplus)

    inserted = 0
    for item, event_id in zip(mapped, reuse):
        details = {
            "film_tool_teach": True,
            "label": item["label"],
            "team": item["team"],
            "shot_type": item["shot_type"],
            "foul_type": item.get("foul_type"),
        }
        event_type_id = _lookup_event_type_id(db, _stat_code(item))
        if event_id is None:
            cur = db.execute(
                """INSERT INTO events
                      (game_id, player, event_type, event_type_id, shot_result, timestamp_ms, details_json,
                       human_verified, confidence, review_status, source_type, review_notes, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1.0, 'accepted', 'manual', ?, CURRENT_TIMESTAMP)""",
                (
                    game_id,
                    item["player"] or None,
                    item["event_type"],
                    event_type_id,
                    item["shot_result"],
                    item["timestamp_ms"],
                    json.dumps(details),
                    TEACH_NOTE,
                ),
            )
            event_id = cur.lastrowid
        else:
            db.execute(
                """UPDATE events
                      SET player=?, event_type=?, event_type_id=?, shot_result=?, timestamp_ms=?,
                          details_json=?, human_verified=1, confidence=1.0, review_status='accepted',
                          review_notes=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                (
                    item["player"] or None,
                    item["event_type"],
                    event_type_id,
                    item["shot_result"],
                    item["timestamp_ms"],
                    json.dumps(details),
                    TEACH_NOTE,
                    event_id,
                ),
            )
        inserted += 1
        db.execute(
            """INSERT INTO human_corrections
                  (game_id, event_id, correction_type, original_value, corrected_value,
                   field_changed, timestamp_ms, notes)
               VALUES (?, ?, 'add_event', '', ?, 'event_type', ?, ?)""",
            (game_id, event_id, item["event_type"], item["timestamp_ms"], TEACH_NOTE),
        )

    applied = apply_saved_manual_teach(db, game_id, commit=False)
    db.commit()
    applied.update({"ok": True, "game_id": game_id, "manual_saved": inserted, "replaced": len(prior_ids)})
    return applied


def apply_saved_manual_teach(
    db, game_id: str, *, commit: bool = True, pending_only: bool = False
) -> dict[str, Any]:
    """Grade AI events in the window covered by saved Film Tool teach rows.

    pending_only=True (event rebuilds) grades only fresh drafts, so rows a coach
    already accepted, corrected or rejected are left alone.
    """
    game_id = normalize_analysis_game_id(game_id)
    manuals = db.execute(
        """SELECT id, event_type, shot_result, player, timestamp_ms, details_json
             FROM events
            WHERE game_id=? AND source_type='manual'
              AND COALESCE(details_json,'') LIKE '%film_tool_teach%'
            ORDER BY timestamp_ms""",
        (game_id,),
    ).fetchall()
    if not manuals:
        return {"corrected": 0, "rejected": 0, "unmatched_manual": 0, "window_ms": None}

    times = [int(_row_get(r, "timestamp_ms") or 0) for r in manuals]
    start_ms = max(0, min(times) - MATCH_TOLERANCE_MS)
    end_ms = max(times) + MATCH_TOLERANCE_MS

    ai_rows = db.execute(
        """SELECT id, game_id, event_type, shot_result, player, timestamp_ms, details_json, review_status
             FROM events
            WHERE game_id=?
              AND COALESCE(source_type,'ai')='ai'
              AND timestamp_ms BETWEEN ? AND ?
              AND (? = 0 OR review_status = 'pending')
            ORDER BY timestamp_ms""",
        (game_id, start_ms, end_ms, 1 if pending_only else 0),
    ).fetchall()

    used_ai: set[int] = set()
    corrected = 0
    unmatched_manual = 0

    for manual in manuals:
        details = _details(_row_get(manual, "details_json"))
        family = _ai_family(_row_get(manual, "event_type"), details)
        if not family:
            continue
        want_ms = int(_row_get(manual, "timestamp_ms") or 0)
        best = None
        best_dt = None
        for ai in ai_rows:
            ai_id = int(_row_get(ai, "id"))
            if ai_id in used_ai:
                continue
            if _ai_family(_row_get(ai, "event_type"), _details(_row_get(ai, "details_json"))) != family:
                continue
            dt = abs(int(_row_get(ai, "timestamp_ms") or 0) - want_ms)
            if dt > MATCH_TOLERANCE_MS:
                continue
            if best_dt is None or dt < best_dt:
                best, best_dt = ai, dt
        if best is None:
            unmatched_manual += 1
            continue
        used_ai.add(int(_row_get(best, "id")))
        _correct_ai_from_manual(db, game_id, best, manual, details)
        corrected += 1

    rejected = 0
    for ai in ai_rows:
        ai_id = int(_row_get(ai, "id"))
        if ai_id in used_ai:
            continue
        family = _ai_family(_row_get(ai, "event_type"))
        if family not in {"shot", "rebound", "assist", "steal", "turnover", "foul", "block"}:
            continue
        result = reject_event(
            db,
            ai_id,
            notes=f"{TEACH_NOTE}: extra AI event in tagged window",
            commit=False,
        )
        if result:
            rejected += 1

    if commit:
        db.commit()
    return {
        "corrected": corrected,
        "rejected": rejected,
        "unmatched_manual": unmatched_manual,
        "window_ms": [start_ms, end_ms],
    }


def _correct_ai_from_manual(db, game_id, ai_row, manual_row, manual_details: dict) -> None:
    ai_id = int(_row_get(ai_row, "id"))
    new_player = str(_row_get(manual_row, "player") or "").strip()
    new_type = _row_get(manual_row, "event_type")
    new_result = _row_get(manual_row, "shot_result")
    details = _details(_row_get(ai_row, "details_json"))
    if manual_details.get("shot_type"):
        details["shot_type"] = manual_details["shot_type"]
    if manual_details.get("team"):
        details["team"] = manual_details["team"]
    details["film_tool_teach"] = True
    old_player = _row_get(ai_row, "player")
    db.execute(
        """UPDATE events
              SET player=?,
                  event_type=?,
                  shot_result=?,
                  details_json=?,
                  review_status='corrected',
                  human_verified=1,
                  review_notes=?,
                  reviewed_at=CURRENT_TIMESTAMP
            WHERE id=?""",
        (
            new_player or old_player,
            new_type,
            new_result,
            json.dumps(details),
            TEACH_NOTE,
            ai_id,
        ),
    )
    db.execute(
        """INSERT INTO human_corrections
              (game_id, event_id, correction_type, original_value, corrected_value,
               field_changed, timestamp_ms, notes)
           VALUES (?, ?, 'change_event', ?, ?, 'player', ?, ?)""",
        (
            str(_row_get(ai_row, "game_id") or game_id),
            ai_id,
            str(old_player or ""),
            new_player,
            int(_row_get(manual_row, "timestamp_ms") or 0),
            TEACH_NOTE,
        ),
    )
