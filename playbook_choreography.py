"""Sticky play choreography — authoritative positions + ink paths per play.

Competitors (CoachCanvas, HoopCoach, Tactic Board) animate from an authored
vector model. Liberty's sheet Play All starts from OCR of printed PDFs, which
re-guesses every load. This module persists a coach-correctable JSON model so
Play All can prefer sticky choreography over fresh OCR/ink traces.

Storage: data/playbook/choreography/{play_id}.json (no schema.sql change).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

CHOREOGRAPHY_VERSION = 1
_DIR_NAME = "choreography"


def choreography_dir(base: str | Path | None = None) -> Path:
    root = Path(base) if base else Path("data") / "playbook"
    d = root / _DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def choreography_path(play_id: int, base: str | Path | None = None) -> Path:
    return choreography_dir(base) / f"{int(play_id)}.json"


def load_choreography(play_id: int, base: str | Path | None = None) -> dict[str, Any] | None:
    path = choreography_path(play_id, base)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("version") or 0) != CHOREOGRAPHY_VERSION:
        return None
    return data


def save_choreography(
    play_id: int,
    payload: dict[str, Any],
    *,
    base: str | Path | None = None,
    source: str = "user_save",
) -> dict[str, Any]:
    """Persist sticky choreography. Returns the written document."""
    steps_in = payload.get("steps")
    if not isinstance(steps_in, list) or not steps_in:
        raise ValueError("steps must be a non-empty list")

    steps_out: list[dict[str, Any]] = []
    for i, raw in enumerate(steps_in):
        if not isinstance(raw, dict):
            continue
        step_index = int(raw.get("step_index", i))
        positions = _clean_positions(raw.get("positions") or {})
        ink = _clean_ink(raw.get("ink"))
        entry: dict[str, Any] = {
            "step_index": step_index,
            "source_image": (raw.get("source_image") or "") or "",
            "court_frac": raw.get("court_frac"),
            "positions": positions,
        }
        if ink is not None:
            entry["ink"] = ink
        steps_out.append(entry)

    if not steps_out:
        raise ValueError("no valid steps to save")

    doc = {
        "version": CHOREOGRAPHY_VERSION,
        "play_id": int(play_id),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(source or "user_save"),
        "sticky": True,
        "steps": steps_out,
    }
    path = choreography_path(play_id, base)
    path.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return doc


def delete_choreography(play_id: int, base: str | Path | None = None) -> bool:
    path = choreography_path(play_id, base)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _clean_positions(raw: Any) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        oid = str(key)
        if not oid.startswith("o"):
            continue
        if not isinstance(val, dict):
            continue
        try:
            x = float(val["x"])
            y = float(val["y"])
        except (KeyError, TypeError, ValueError):
            continue
        out[oid] = {"x": round(x, 2), "y": round(y, 2)}
    return out


def _clean_polyline(pts: Any) -> list[dict[str, float]] | None:
    if not isinstance(pts, list) or len(pts) < 2:
        return None
    cleaned: list[dict[str, float]] = []
    for pt in pts:
        if not isinstance(pt, dict):
            continue
        try:
            cleaned.append({"x": round(float(pt["x"]), 2), "y": round(float(pt["y"]), 2)})
        except (KeyError, TypeError, ValueError):
            continue
    return cleaned if len(cleaned) >= 2 else None


def _clean_ink(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    paths_in = raw.get("paths") or {}
    marks_in = raw.get("marks") or {}
    passes_in = raw.get("passes") or []
    paths: dict[str, list[dict[str, float]]] = {}
    if isinstance(paths_in, dict):
        for oid, poly in paths_in.items():
            cleaned = _clean_polyline(poly)
            if cleaned:
                paths[str(oid)] = cleaned
    marks: dict[str, Any] = {}
    if isinstance(marks_in, dict):
        for oid, meta in marks_in.items():
            if isinstance(meta, dict):
                marks[str(oid)] = meta
            elif isinstance(meta, str):
                marks[str(oid)] = meta
    passes: list[Any] = []
    if isinstance(passes_in, list):
        for p in passes_in:
            if isinstance(p, dict):
                item = dict(p)
                if "points" in item:
                    pts = _clean_polyline(item.get("points"))
                    if pts:
                        item["points"] = pts
                passes.append(item)
    if not paths and not marks and not passes:
        return None
    return {"paths": paths, "marks": marks, "passes": passes}
