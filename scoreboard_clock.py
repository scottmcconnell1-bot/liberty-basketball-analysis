"""Read the scoreboard burned into an NFHS frame.

The board sits in the bottom-right corner. It shows the game clock, the
period, Mustangs and Guest scores, team fouls, and the player-foul pair.
Those pixels are the clock. A quarter is not guessed from the length of the file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent
TRACK_DIR = ROOT / "data" / "scoreboard_tracks"

# Fixed on this 1920x1080 sideline film. Orange digits stay inside this box.
_BOARD = (1535, 840, 1880, 1030)
_CELLS = {
    "clock": (100, 0, 260, 52),
    "home_score": (5, 65, 105, 135),
    "period": (145, 55, 200, 115),
    "guest_score": (250, 65, 345, 135),
    "home_fouls": (15, 125, 70, 175),
    "player_foul": (115, 120, 240, 180),
    "guest_fouls": (270, 125, 340, 180),
}

# The red scores are two fixed seven-segment slots (tens, ones) inside each score cell.
# Splitting on blank columns cut a 4 at its thin crossbar and read the upright as a 1.
_SCORE_CELLS = ("home_score", "guest_score")
_SCORE_SLOTS = ((12, 20, 43, 57), (50, 20, 80, 57))
_SEGMENTS = {
    "a": (0.25, 0.00, 0.75, 0.14),
    "b": (0.72, 0.10, 1.00, 0.45),
    "c": (0.72, 0.55, 1.00, 0.90),
    "d": (0.25, 0.86, 0.75, 1.00),
    "e": (0.00, 0.55, 0.28, 0.90),
    "f": (0.00, 0.10, 0.28, 0.45),
    "g": (0.25, 0.43, 0.75, 0.57),
}
# Lit segments measured >= 0.18 of their pixels on this film, unlit <= 0.05.
_SEGMENT_ON = 0.12
_SEVEN_SEGMENT = {
    "abcdef": "0", "bc": "1", "abdeg": "2", "abcdg": "3", "bcfg": "4",
    "acdfg": "5", "acdefg": "6", "abc": "7", "abcdefg": "8", "abcdfg": "9",
    "abcf": "7", "cdefg": "6", "abcfg": "9",
}

_DIGIT_FILE = ROOT / "data" / "scoreboard_digits.npz"
_TEMPLATES: np.ndarray | None = None
_TEMPLATE_PRESENT: np.ndarray | None = None


def _safe_name(game_id: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", (game_id or "").strip())[:180] or "unknown"


def track_path(game_id: str) -> Path:
    return TRACK_DIR / f"{_safe_name(game_id)}.json"


def _warm_mask(crop: np.ndarray) -> np.ndarray:
    import cv2

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 150)).astype(np.uint8)


def _red_mask(crop: np.ndarray) -> np.ndarray:
    import cv2

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    low = cv2.inRange(hsv, (0, 90, 120), (12, 255, 255))
    high = cv2.inRange(hsv, (165, 90, 120), (180, 255, 255))
    mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def _slot_digit(mask: np.ndarray, slot: tuple[int, int, int, int]) -> str | None:
    """One seven-segment slot: a digit, "" when dark, None for a pattern that is no digit."""
    x0, y0, x1, y1 = slot
    width = x1 - x0
    height = y1 - y0
    lit = ""
    for name, (fx0, fy0, fx1, fy1) in _SEGMENTS.items():
        sx0 = x0 + int(fx0 * width)
        sx1 = max(x0 + int(fx1 * width), sx0 + 1)
        sy0 = y0 + int(fy0 * height)
        sy1 = max(y0 + int(fy1 * height), sy0 + 1)
        cell = mask[sy0:sy1, sx0:sx1]
        if cell.size and float((cell > 0).mean()) > _SEGMENT_ON:
            lit += name
    if not lit:
        return ""
    return _SEVEN_SEGMENT.get(lit)


def _score_text(board: np.ndarray, box: tuple[int, int, int, int]) -> list[str]:
    x0, y0, x1, y1 = box
    crop = board[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    mask = _red_mask(crop)
    tens, ones = (_slot_digit(mask, slot) for slot in _SCORE_SLOTS)
    if tens == "" and ones == "":
        return []
    if ones == "":
        ones = None
    return [("?" if tens is None else tens) + ("?" if ones is None else ones)]


def _score_value(groups: list[str]) -> int | None:
    """A dark tens slot is a one-digit score. A lit tens 0 or any unread slot is no score."""
    if len(groups) != 1 or "?" in groups[0]:
        return None
    text = groups[0]
    if len(text) == 2 and text[0] == "0":
        return None
    return _as_int(text)


def _load_templates() -> tuple[np.ndarray, np.ndarray] | None:
    global _TEMPLATES, _TEMPLATE_PRESENT
    if _TEMPLATES is not None and _TEMPLATE_PRESENT is not None:
        return _TEMPLATES, _TEMPLATE_PRESENT
    if not _DIGIT_FILE.is_file():
        return None
    data = np.load(_DIGIT_FILE)
    _TEMPLATES = data["templates"]
    _TEMPLATE_PRESENT = data["present"]
    return _TEMPLATES, _TEMPLATE_PRESENT


def _segment_digit(mask: np.ndarray) -> str | None:
    """Match one LED digit to a glyph taken from this film's scoreboard."""
    loaded = _load_templates()
    if loaded is None:
        return None
    templates, present = loaded
    ys, xs = np.where(mask > 0)
    if len(xs) < 6:
        return None
    digit = mask[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    if digit.shape[0] < 8:
        return None
    import cv2

    sample = cv2.resize(digit.astype(np.float32), (16, 24), interpolation=cv2.INTER_AREA)
    sample = sample / max(float(sample.max()), 1.0)
    flat = sample.ravel()
    norm = float(np.linalg.norm(flat))
    if norm < 1e-6:
        return None
    best_digit = None
    best_score = -1.0
    second = -1.0
    for digit_value in range(10):
        if not present[digit_value]:
            continue
        tmpl = templates[digit_value].ravel()
        score = float(np.dot(flat, tmpl) / (norm * float(np.linalg.norm(tmpl)) + 1e-6))
        if score > best_score:
            second = best_score
            best_score = score
            best_digit = digit_value
        elif score > second:
            second = score
    if best_digit is None or best_score < 0.55 or best_score - second < 0.04:
        return None
    return str(best_digit)


def _digit_groups(mask: np.ndarray) -> list[str]:
    """Digits left to right. A wide gap starts a new group (player, then his fouls)."""
    height, width = mask.shape[:2]
    if width < 2 or height < 2:
        return []
    columns = mask.sum(axis=0)
    runs: list[tuple[int, int]] = []
    active = False
    start = 0
    for index, value in enumerate(columns):
        if value > 1 and not active:
            active = True
            start = index
        elif value <= 1 and active:
            active = False
            if index - start >= 2:
                runs.append((start, index))
    if active and width - start >= 2:
        runs.append((start, width))
    merged: list[tuple[int, int]] = []
    for run in runs:
        if merged and run[0] - merged[-1][1] <= 2:
            merged[-1] = (merged[-1][0], run[1])
        else:
            merged.append(run)
    groups: list[str] = []
    current = ""
    previous_end = None
    for run_start, run_end in merged:
        piece = mask[:, run_start:run_end]
        if int(piece.sum()) < 8:
            continue
        if previous_end is not None and run_start - previous_end > 6 and current:
            groups.append(current)
            current = ""
        digit = _segment_digit(piece)
        # Keep a placeholder for a glyph we cannot read: dropping it silently turned
        # 10:59 into "105" -> a legal-looking 1:05 that then set the quarter.
        current += digit if digit else "?"
        previous_end = run_end
    if current:
        groups.append(current)
    return groups


def _cell_text(board: np.ndarray, box: tuple[int, int, int, int]) -> list[str]:
    x0, y0, x1, y1 = box
    crop = board[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    return _digit_groups(_warm_mask(crop))


def _as_int(text: str | None) -> int | None:
    if text and text.isdigit():
        return int(text)
    return None


def _joined_digits(groups: list[str]) -> str:
    return "".join(part for part in groups if part.isdigit())


def _clock_text(groups: list[str]) -> str | None:
    """M:SS or MM:SS. A partial read is not a clock."""
    if any("?" in part for part in groups):
        return None
    digits = _joined_digits(groups)
    if len(digits) == 3:
        return f"{digits[0]}:{digits[1:]}"
    if len(digits) == 4:
        return f"{digits[:2]}:{digits[2:]}"
    return None


_CLOCK_RE = re.compile(r"^(\d{1,2}):([0-5]\d)$")


def legal_clock(clock: str | None) -> bool:
    """A full game clock. Seconds are 0–59. A partial read or 7:62 is not a clock."""
    if not isinstance(clock, str):
        return False
    match = _CLOCK_RE.fullmatch(clock.strip())
    if not match:
        return False
    return 0 <= int(match.group(1)) <= 12


def quarter_from_scoreboard(sample: dict[str, Any] | None) -> int | None:
    """Period 1–5 only when this sample also has a legal clock. The digit alone is not a quarter."""
    if not sample or not legal_clock(sample.get("clock")):
        return None
    try:
        period = int(sample.get("period"))
    except (TypeError, ValueError):
        return None
    if period not in (1, 2, 3, 4, 5):
        return None
    return period


def read_scoreboard(frame_bgr: np.ndarray) -> dict[str, Any] | None:
    """Read one frame's board. Missing digits stay None. Nothing is guessed."""
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    height, width = frame_bgr.shape[:2]
    if height < 1000 or width < 1800:
        return None
    x0, y0, x1, y1 = _BOARD
    board = frame_bgr[y0:y1, x0:x1]
    cells = {
        name: (_score_text if name in _SCORE_CELLS else _cell_text)(board, box) for name, box in _CELLS.items()
    }
    period = _as_int(_joined_digits(cells.get("period") or []))
    if period is not None and period not in (1, 2, 3, 4, 5):
        period = None
    player_groups = [part for part in (cells.get("player_foul") or []) if part.isdigit()]
    return {
        "clock": _clock_text(cells.get("clock") or []),
        "period": period,
        "mustangs": _score_value(cells.get("home_score") or []),
        "guest": _score_value(cells.get("guest_score") or []),
        "mustangs_fouls": _as_int(_joined_digits(cells.get("home_fouls") or [])),
        "guest_fouls": _as_int(_joined_digits(cells.get("guest_fouls") or [])),
        "foul_jersey": _as_int(player_groups[0]) if player_groups else None,
        "foul_count": _as_int(player_groups[1]) if len(player_groups) > 1 else None,
        "raw": cells,
    }


def load_scoreboard_track(game_id: str) -> list[dict[str, Any]]:
    path = track_path(game_id)
    if not path.is_file() and "__rerun_" in str(game_id or ""):
        path = track_path(str(game_id).split("__rerun_", 1)[0])
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
    """The board reading nearest this video time. No reading, no quarter."""
    if not samples:
        return None
    best = None
    best_dt = None
    for row in samples:
        dt = abs(int(row.get("timestamp_ms") or 0) - int(timestamp_ms))
        if dt > max_dt_ms:
            continue
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = row
    return best
