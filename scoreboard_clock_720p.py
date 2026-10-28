"""Read the 720p scoreboard overlay burned into the Notus NFHS films.

The Notus board is a fixed bottom-right overlay on a 1280x720 frame. Its scores
are red and its clock is yellow, so this module reuses the masks and digit
readers from :mod:`scoreboard_clock` instead of copying them. The digit boxes
come from ``data/roi/notus_scoreboard_rois.json``, measured on Notus frames by
``scripts/measure_notus_rois.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import cv2

from scoreboard_clock import (
    _digit_groups,
    _red_mask,
    _score_value,
    _SEGMENT_ON,
    _SEVEN_SEGMENT,
    _warm_mask,
    read_scoreboard,
)

ROOT = Path(__file__).resolve().parent
ROI_FILE = ROOT / "data" / "roi" / "notus_scoreboard_rois.json"
SEGMENT_GEOMETRY_FILE = ROOT / "data" / "roi" / "notus_segment_geometry.json"
TRACK_DIR = ROOT / "data" / "scoreboard_tracks"

_NOTUS_THRESHOLDS_A1: dict | None = None
_NOTUS_THRESHOLDS_A: dict | None = None
_NOTUS_GEOMETRY_A1: dict | None = None
_NOTUS_GEOMETRY_A: dict | None = None

def _load_notus_thresholds_A1() -> dict:
    global _NOTUS_THRESHOLDS_A1
    if _NOTUS_THRESHOLDS_A1 is not None:
        return _NOTUS_THRESHOLDS_A1
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_red_thresholds_A1.json"
    _NOTUS_THRESHOLDS_A1 = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_THRESHOLDS_A1

def _load_notus_thresholds_A() -> dict:
    global _NOTUS_THRESHOLDS_A
    if _NOTUS_THRESHOLDS_A is not None:
        return _NOTUS_THRESHOLDS_A
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_red_thresholds_A.json"
    _NOTUS_THRESHOLDS_A = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_THRESHOLDS_A

def _load_notus_geometry_A1() -> dict:
    global _NOTUS_GEOMETRY_A1
    if _NOTUS_GEOMETRY_A1 is not None:
        return _NOTUS_GEOMETRY_A1
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_segment_geometry_A1.json"
    _NOTUS_GEOMETRY_A1 = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_GEOMETRY_A1

def _load_notus_geometry_A() -> dict:
    global _NOTUS_GEOMETRY_A
    if _NOTUS_GEOMETRY_A is not None:
        return _NOTUS_GEOMETRY_A
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_segment_geometry_A.json"
    _NOTUS_GEOMETRY_A = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_GEOMETRY_A

def _notus_red_mask(crop: np.ndarray, game_key: str = "default") -> np.ndarray:
    """Red mask for Notus 720p board using frozen thresholds from notus_red_thresholds.json."""
    if game_key == "A1":
        thresholds = _load_notus_thresholds_A1()
    elif game_key == "A":
        thresholds = _load_notus_thresholds_A()
    else:
        # Fallback to original single file if requested
        try:
            thresholds = _load_notus_thresholds()
        except:
            return np.zeros((crop.shape[0], crop.shape[1]), dtype=np.uint8)
            
    h_min = thresholds["h_min"]
    h_max = thresholds["h_max"]
    s_min = thresholds["s_min"]
    v_min = thresholds["v_min"]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if h_min <= h_max:
        mask = cv2.inRange(hsv, (h_min, s_min, v_min), (h_max, 255, 255))
    else:
        low = cv2.inRange(hsv, (0, s_min, v_min), (h_max, 255, 255))
        high = cv2.inRange(hsv, (h_min, s_min, v_min), (179, 255, 255))
        mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def load_rois(path: str | Path | None = None) -> dict[str, Any]:
    """Load measured ROI boxes. Raises when the measurement has not been run."""
    roi_path = Path(path) if path else ROI_FILE
    if not roi_path.is_file():
        raise FileNotFoundError(f"run scripts/measure_notus_rois.py first: {roi_path}")
    data = json.loads(roi_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"ROI file is not an object: {roi_path}")
    return data


def game_rois(rois: dict[str, Any], game_id: str) -> dict[str, Any]:
    games = rois.get("games") or {}
    if game_id in games:
        return games[game_id]
    if "default" in rois:
        return rois["default"]
    raise KeyError(f"no ROI boxes for {game_id}")


def _crop(frame: np.ndarray, box: list[int] | tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = (int(value) for value in box)
    return frame[max(0, y) : max(0, y) + h, max(0, x) : max(0, x) + w]


def _load_segment_geometry() -> dict[str, tuple[float, float, float, float]]:
    """The measured Notus segment boxes, as fractions of a tens/ones slot."""
    global _GEOMETRY
    if _GEOMETRY is not None:
        return _GEOMETRY
    if not SEGMENT_GEOMETRY_FILE.is_file():
        raise FileNotFoundError(f"run scripts/fit_notus_segments.py first: {SEGMENT_GEOMETRY_FILE}")
    data = json.loads(SEGMENT_GEOMETRY_FILE.read_text(encoding="utf-8"))
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, dict):
        raise ValueError(f"segment geometry has no 'segments' object: {SEGMENT_GEOMETRY_FILE}")
    geometry: dict[str, tuple[float, float, float, float]] = {}
    for name in ("a", "b", "c", "d", "e", "f", "g"):
        rect = segments.get(name)
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise ValueError(f"segment {name!r} is not a four-value box: {SEGMENT_GEOMETRY_FILE}")
        geometry[name] = tuple(float(value) for value in rect)
    _GEOMETRY = geometry
    return geometry


def _read_notus_digit(mask: np.ndarray) -> str | None:
    """A digit from which seven segments are lit, "" for a blank slot, None if unknown."""
    geometry = _load_segment_geometry()
    height, width = mask.shape[:2]
    lit = ""
    for name, (fx0, fy0, fx1, fy1) in geometry.items():
        sx0 = int(fx0 * width)
        sx1 = max(int(fx1 * width), sx0 + 1)
        sy0 = int(fy0 * height)
        sy1 = max(int(fy1 * height), sy0 + 1)
        cell = mask[sy0:sy1, sx0:sx1]
        if cell.size and float((cell > 0).mean()) >= _SEGMENT_ON:
            lit += name
    if not lit:
        return ""
    return _SEVEN_SEGMENT.get(lit)


def _read_score(frame: np.ndarray, cell: dict[str, Any]) -> int | None:
    """Read the tens and ones slots of one red score cell."""
    tens_box = cell.get("tens")
    ones_box = cell.get("ones")
    if not tens_box or not ones_box:
        return None
    tens = _read_notus_digit(_notus_red_mask(_crop(frame, tens_box)))
    ones = _read_notus_digit(_notus_red_mask(_crop(frame, ones_box)))
    if tens == "" and ones == "":
        return None
    if ones == "":
        ones = None
    text = ("?" if tens is None else tens) + ("?" if ones is None else ones)
    return _score_value([text])


def _clock_text(groups: list[str]) -> str | None:
    """M:SS or MM:SS from the clock field's digit groups."""
    if any("?" in part for part in groups):
        return None
    digits = "".join(part for part in groups if part.isdigit())
    if len(digits) == 3:
        return f"{digits[0]}:{digits[1:]}"
    if len(digits) == 4:
        return f"{digits[:2]}:{digits[2:]}"
    return None


def read_scoreboard_720p(frame_bgr: np.ndarray, rois: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Read one 720p Notus frame. Missing digits stay None; nothing is guessed."""
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    height, width = frame_bgr.shape[:2]
    if height >= 1000 and width >= 1800:
        return read_scoreboard(frame_bgr)
    config = rois if rois is not None else game_rois(load_rois(), "default")
    clock_box = config.get("clock_field") or config.get("clock")
    if not clock_box:
        return None
    clock_groups = _digit_groups(_warm_mask(_crop(frame_bgr, clock_box))) if clock_box else []
    cells = config.get("scores") or {}
    home = _read_score(frame_bgr, cells.get("home") or {})
    away = _read_score(frame_bgr, cells.get("away") or {})
    return {
        "clock": _clock_text(clock_groups),
        "home_score": home,
        "away_score": away,
        "raw": {"clock": clock_groups, "home": cells.get("home"), "away": cells.get("away")},
    }


def _safe_name(game_id: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", (game_id or "").strip())[:180] or "unknown"


def load_scoreboard_track(game_id: str) -> list[dict[str, Any]]:
    path = TRACK_DIR / f"{_safe_name(game_id)}.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return list(data.get("samples") or [])
    if isinstance(data, list):
        return data
    return []


def scoreboard_at(samples: list[dict[str, Any]], timestamp_ms: int, max_dt_ms: int = 1500) -> dict[str, Any] | None:
    """The board reading nearest this video time, or None when there is none."""
    best = None
    best_dt = None
    for row in samples or []:
        dt = abs(int(row.get("timestamp_ms") or 0) - int(timestamp_ms))
        if dt > max_dt_ms:
            continue
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = row
    return best
