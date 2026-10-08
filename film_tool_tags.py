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
    for control in ("baseUpdatedAt", "force", "serverBase"):
        data.pop(control, None)
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    TAGS_ROOT.mkdir(parents=True, exist_ok=True)
    _keep_history(gid, len(rows))
    tag_path(gid).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


HISTORY_KEEP = 120
HISTORY_EVERY_SECONDS = 120
HISTORY_HOURLY_HOURS = 72


def _history_stamp(path: Path) -> datetime | None:
    """The UTC time written in a history copy's name, or None."""
    try:
        text = path.stem.rsplit("__", 2)[1]
        return datetime.strptime(text[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except (IndexError, ValueError):
        return None


def _prune_history(existing: list[Path]) -> None:
    """Keep every recent copy, then one per hour for the last few days."""
    older = existing[:-HISTORY_KEEP]
    seen_hours: set[str] = set()
    now = datetime.now(timezone.utc)
    for old in reversed(older):  # newest first
        stamp = _history_stamp(old)
        keep = False
        if stamp is not None and (now - stamp).total_seconds() <= HISTORY_HOURLY_HOURS * 3600:
            hour = stamp.strftime("%Y%m%d%H")
            if hour not in seen_hours:
                seen_hours.add(hour)
                keep = True
        if not keep:
            try:
                old.unlink()
            except OSError:
                pass


def _keep_history(gid: str, incoming_rows: int) -> None:
    """Keep a dated copy of the saved tags before they are replaced.

    A copy is made when the new list is shorter than the saved one, and
    otherwise at most every two minutes, so a bad save never costs more than
    a couple of minutes of tags. The newest HISTORY_KEEP copies stay, plus one
    copy per hour for HISTORY_HOURLY_HOURS hours.
    """
    path = tag_path(gid)
    if not path.is_file():
        return
    folder = TAGS_ROOT / "_history"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved_rows = len(saved.get("rows") or [])
    except (OSError, json.JSONDecodeError, AttributeError):
        saved_rows = 0
    if not saved_rows:
        return
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob(f"{gid}__*.json"))
    shrinking = incoming_rows < saved_rows
    if existing and not shrinking:
        age = datetime.now(timezone.utc).timestamp() - existing[-1].stat().st_mtime
        if age < HISTORY_EVERY_SECONDS:
            return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (folder / f"{gid}__{stamp}__{saved_rows}rows.json").write_bytes(path.read_bytes())
    _prune_history(sorted(folder.glob(f"{gid}__*.json")))


class StaleTags(ValueError):
    """The save was built on an older copy than the one on the server."""


def _parse_stamp(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def check_not_stale(game_id: str, payload: dict[str, Any] | None) -> None:
    """Refuse a save that was not built on the copy now on the server.

    A tab sends the updatedAt of the server copy it loaded (baseUpdatedAt).
    If the server copy is newer, or the tab sent nothing (a tab opened before
    this check existed), the save is refused and the server copy is kept.
    force=true skips the check for scripts that mean to replace the copy.
    """
    data = payload or {}
    if data.get("force") is True:
        return
    existing = load_manual_tags(game_id)
    if not existing or not existing.get("rows"):
        return
    saved_at = _parse_stamp(existing.get("updatedAt"))
    if saved_at is None:
        return
    base = _parse_stamp(data.get("baseUpdatedAt"))
    if base is None or base < saved_at:
        raise StaleTags(
            "A newer copy of these tags is on the server. Reload the page to get it. "
            "Nothing was overwritten."
        )