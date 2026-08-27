"""Film timestamp sync between analysis video and review video.

Adrian JrHigh events were produced on the archived screencapture
(LIBERTY_A_v_ADRIAN_H_….mp4, ~3530s) but coaches review the NFHS clean
file (nfhs_gam0a66d85e12.mp4, ~3897s) under the same game_id. Without an
offset, Film Tool seeks to the wrong moment.

Store per-game sync in data/film_sync/<safe_game_id>.json.
Film Tool applies: review_ms = analysis_timestamp_ms + offset_ms.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SYNC_DIR = ROOT / "data" / "film_sync"

ADRIAN_BASE = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
ADRIAN_ANALYSIS_VIDEO = "LIBERTY_A_v_ADRIAN_H_20260809_221334.mp4"
ADRIAN_REVIEW_VIDEO = "nfhs_gam0a66d85e12.mp4"


def _safe_name(game_id: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", (game_id or "").strip())[:180] or "unknown"


def sync_path(game_id: str) -> Path:
    return SYNC_DIR / f"{_safe_name(game_id)}.json"


def load_film_sync(game_id: str) -> dict[str, Any] | None:
    path = sync_path(game_id)
    if not path.is_file():
        # Also try base key if a __rerun_ id was passed
        base = (game_id or "").split("__rerun_", 1)[0]
        if base != game_id:
            path = sync_path(base)
        if not path.is_file():
            return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def save_film_sync(game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    base = (game_id or "").split("__rerun_", 1)[0]
    out = {
        "game_id": base,
        "offset_ms": int(payload.get("offset_ms") or 0),
        "analysis_video": payload.get("analysis_video") or "",
        "review_video": payload.get("review_video") or "",
        "method": payload.get("method") or "manual",
        "notes": payload.get("notes") or "",
        "calibrated_at": payload.get("calibrated_at") or "",
    }
    path = sync_path(base)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def analysis_to_review_ms(timestamp_ms: int, offset_ms: int) -> int:
    return max(0, int(timestamp_ms) + int(offset_ms))


def review_to_analysis_ms(review_ms: int, offset_ms: int) -> int:
    return max(0, int(review_ms) - int(offset_ms))
