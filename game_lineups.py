"""Per-game starting five. Coach-picked, stored as JSON (no schema change).

Scott 2026-09-15: bench points need a starter list. Tip-off detection is later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LINEUPS_ROOT = Path(__file__).resolve().parent / "data" / "lineups"

_GAME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._,\-]{0,119}$")
_LABEL_JERSEY_RE = re.compile(r"^#?\s*(\d+)\s*[-–:]?\s*(.*)$")


def _jersey_key(value) -> str:
    text = str(value if value is not None else "").strip().lstrip("#").lstrip("0")
    return text or "0"


def sanitize_game_id(game_id: str) -> str:
    text = (game_id or "").strip()
    if "__rerun_" in text:
        text = text.split("__rerun_", 1)[0]
    if not _GAME_ID_RE.match(text) or ".." in text:
        raise ValueError("Invalid game_id")
    return text


def lineup_path(game_id: str) -> Path:
    return LINEUPS_ROOT / f"{sanitize_game_id(game_id)}.json"


def parse_starter_entry(raw: Any) -> dict[str, str] | None:
    """Accept {jersey, name, label} or a roster label like '40 - Dayley'."""
    jersey = ""
    name = ""
    label = ""
    if isinstance(raw, dict):
        jersey = str(raw.get("jersey") if raw.get("jersey") is not None else "").strip()
        name = str(raw.get("name") or "").strip()
        label = str(raw.get("label") or "").strip()
    else:
        label = str(raw or "").strip()
    if not jersey and label:
        match = _LABEL_JERSEY_RE.match(label)
        if match:
            jersey = match.group(1)
            name = name or (match.group(2) or "").strip()
    jersey = _jersey_key(jersey) if jersey else ""
    if not jersey and not name and not label:
        return None
    if not label:
        label = f"{jersey} - {name}".strip(" -") if jersey or name else ""
    return {"jersey": jersey, "name": name, "label": label}


def _normalize_side(raw_list: Any, *, required: bool) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_list or []:
        parsed = parse_starter_entry(item)
        if not parsed:
            continue
        key = parsed["jersey"] or parsed["label"].lower()
        if key in seen:
            raise ValueError("Duplicate starter on the same team")
        seen.add(key)
        entries.append(parsed)
    if len(entries) > 5:
        raise ValueError("A team can have at most 5 starters")
    if required and entries and len(entries) != 5:
        raise ValueError("Pick exactly 5 starters, or leave the list empty")
    if entries and len(entries) not in (0, 5):
        raise ValueError("Pick exactly 5 starters, or leave the list empty")
    return entries


def empty_starters(game_id: str) -> dict[str, Any]:
    gid = sanitize_game_id(game_id)
    return {
        "game_id": gid,
        "source": None,
        "liberty": [],
        "opponent": [],
        "complete": {"liberty": False, "opponent": False},
    }


def _decorate(payload: dict[str, Any]) -> dict[str, Any]:
    liberty = list(payload.get("liberty") or [])
    opponent = list(payload.get("opponent") or [])
    payload["liberty"] = liberty
    payload["opponent"] = opponent
    payload["complete"] = {
        "liberty": len(liberty) == 5,
        "opponent": len(opponent) == 5,
    }
    return payload


def load_starters(game_id: str) -> dict[str, Any]:
    path = lineup_path(game_id)
    if not path.is_file():
        return empty_starters(game_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_starters(game_id)
    if not isinstance(data, dict):
        return empty_starters(game_id)
    data["game_id"] = sanitize_game_id(game_id)
    data["liberty"] = [row for row in (_normalize_optional(data.get("liberty")) or [])]
    data["opponent"] = [row for row in (_normalize_optional(data.get("opponent")) or [])]
    return _decorate(data)


def _normalize_optional(raw_list: Any) -> list[dict[str, str]]:
    try:
        return _normalize_side(raw_list, required=False)
    except ValueError:
        return []


def save_starters(game_id: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    gid = sanitize_game_id(game_id)
    body = payload or {}
    saved = {
        "game_id": gid,
        "source": str(body.get("source") or "coach").strip() or "coach",
        "liberty": _normalize_side(body.get("liberty"), required=True),
        "opponent": _normalize_side(body.get("opponent"), required=True),
    }
    LINEUPS_ROOT.mkdir(parents=True, exist_ok=True)
    path = lineup_path(gid)
    path.write_text(json.dumps(_decorate(saved), indent=2) + "\n", encoding="utf-8")
    return load_starters(gid)


def jersey_set(entries: list[dict[str, Any]] | None) -> set[str]:
    return {_jersey_key(row.get("jersey")) for row in (entries or []) if row.get("jersey")}


def safe_load_starters(game_id: str) -> dict[str, Any]:
    try:
        return load_starters(game_id)
    except ValueError:
        return {
            "game_id": str(game_id or "").strip(),
            "source": None,
            "liberty": [],
            "opponent": [],
            "complete": {"liberty": False, "opponent": False},
        }
