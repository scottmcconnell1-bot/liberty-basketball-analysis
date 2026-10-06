"""Per-film Film Tool tags on disk so Funnel/school Chrome can resume (no schema change)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from helpers import normalize_analysis_game_id

TAGS_ROOT = Path(__file__).resolve().parent / "data" / "film_tags"
_GAME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._,\-]{0,239}$")


def sanitize_tag_game_id(game_id: str) -> str:
    text = normalize_analysis_game_id(game_id)
    if "__rerun_" in text:
        text = text.split("__rerun_", 1)[0]
    if not _GAME_ID_RE.match(text) or ".." in text:
        raise ValueError("Invalid game_id")
    return text


def tag_path(game_id: str) -> Path:
    return TAGS_ROOT / f"{sanitize_tag_game_id(game_id)}.json"


def load_manual_tags(game_id: str) -> dict[str, Any] | None:
    path = tag_path(game_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    rows = data.get("rows")
    if not isinstance(rows, list):
        return None
    data["analysisGameId"] = sanitize_tag_game_id(game_id)
    data["rows"] = rows
    return data


class TagClearRefused(ValueError):
    """An empty list must not replace tags already saved for this film."""


def save_manual_tags(
    game_id: str,
    payload: dict[str, Any] | None,
    *,
    allow_clear: bool = False,
) -> dict[str, Any]:
    gid = sanitize_tag_game_id(game_id)
    data = dict(payload or {})
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    if not rows and not allow_clear:
        existing = load_manual_tags(gid)
        kept = existing.get("rows") if isinstance(existing, dict) else None
        if kept:
            raise TagClearRefused(
                "Saved tags were kept. An empty list cannot replace them."
            )
    data["analysisGameId"] = gid
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    TAGS_ROOT.mkdir(parents=True, exist_ok=True)
    tag_path(gid).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
