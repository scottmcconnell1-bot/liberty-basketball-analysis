"""Home = light jersey (usually white). Away = dark.

Scott 2026-09-16: same number on both teams is split by shirt color, not by
guessing Liberty first. No schema change — cache is a JSON sidecar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from helpers import normalize_analysis_game_id

ROOT = Path(__file__).resolve().parent
SHADE_DIR = ROOT / "data" / "jersey_shades"
HOME_IS_LIGHT = True
DEFAULT_SPLIT = 120.0
SAMPLES_PER_TRACK = 8


def shade_from_value(mean_v: float, split: float = DEFAULT_SPLIT) -> str:
    return "light" if float(mean_v) >= float(split) else "dark"


def shade_from_hsv(mean_s: float, mean_v: float) -> str:
    """White/light home shirts: bright and washed out. Away shirts: darker or colored."""
    if float(mean_v) >= 155 and float(mean_s) <= 85:
        return "light"
    if float(mean_v) >= 145 and float(mean_s) <= 40:
        return "light"
    return "dark"


def side_from_shade(shade: str, *, home_is_light: bool = HOME_IS_LIGHT) -> str:
    """Return scorebook team_side: home or away."""
    is_light = str(shade or "").lower() == "light"
    if home_is_light:
        return "home" if is_light else "away"
    return "away" if is_light else "home"


def side_label(side: str) -> str:
    if side == "home":
        return "Home (light)"
    if side == "away":
        return "Away (dark)"
    return side or ""


def _safe_stem(game_id: str) -> str:
    text = normalize_analysis_game_id(game_id)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)[:180]


def shade_cache_path(game_id: str) -> Path:
    SHADE_DIR.mkdir(parents=True, exist_ok=True)
    return SHADE_DIR / f"{_safe_stem(game_id)}.json"


def load_cached_shades(game_id: str) -> dict[int, dict[str, Any]]:
    path = shade_cache_path(game_id)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tracks = raw.get("tracks") if isinstance(raw, dict) else raw
    out: dict[int, dict[str, Any]] = {}
    if not isinstance(tracks, dict):
        return out
    for key, info in tracks.items():
        try:
            out[int(key)] = dict(info or {})
        except (TypeError, ValueError):
            continue
    return out


def save_cached_shades(game_id: str, tracks: dict[int, dict[str, Any]], *, split: float) -> Path:
    path = shade_cache_path(game_id)
    payload = {
        "game_id": normalize_analysis_game_id(game_id),
        "home_is_light": HOME_IS_LIGHT,
        "split": split,
        "tracks": {str(k): v for k, v in tracks.items()},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _torso_value(frame, x_center: int, y_center: int, width: int, height: int) -> float | None:
    import cv2
    import numpy as np

    h, w = frame.shape[:2]
    bw = max(int(width or 0), 8)
    bh = max(int(height or 0), 8)
    x1 = max(0, int(x_center) - bw // 2)
    y1 = max(0, int(y_center) - bh // 2)
    x2 = min(w, x1 + bw)
    y2 = min(h, y1 + bh)
    if x2 <= x1 or y2 <= y1:
        return None
    torso_y2 = y1 + max(8, int((y2 - y1) * 0.32))
    x_in = max(1, int((x2 - x1) * 0.22))
    crop = frame[y1:torso_y2, x1 + x_in:x2 - x_in]
    if crop is None or crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    return (float(np.median(hsv[:, :, 1])), float(np.median(hsv[:, :, 2])))


def _event_tracker_ids(db, game_id: str) -> list[int]:
    key = normalize_analysis_game_id(game_id)
    ids: set[int] = set()
    for row in db.execute(
        """SELECT player, details_json FROM events
            WHERE game_id=? AND review_status IN ('accepted', 'corrected')""",
        (key,),
    ):
        token = str(row[0] or "").strip()
        if token.isdigit():
            ids.add(int(token))
        extra = {}
        try:
            extra = json.loads(row[1] or "{}")
        except json.JSONDecodeError:
            extra = {}
        tracker = extra.get("tracker_id")
        if tracker is not None and str(tracker).isdigit():
            ids.add(int(tracker))
    return sorted(ids)


def _sample_rows_for_tracker(db, game_id: str, tracker_id: int, limit: int = SAMPLES_PER_TRACK):
    key = normalize_analysis_game_id(game_id)
    rows = db.execute(
        """SELECT timestamp_ms, x_center, y_center, width, height
             FROM detections
            WHERE game_id=? AND object_class='person' AND tracker_id=?
            ORDER BY timestamp_ms""",
        (key, tracker_id),
    ).fetchall()
    if not rows:
        return []
    if len(rows) <= limit:
        return rows
    step = max(1, len(rows) // limit)
    return [rows[i] for i in range(0, len(rows), step)][:limit]


def _video_path_for_game(db, game_id: str) -> str | None:
    key = normalize_analysis_game_id(game_id)
    row = db.execute(
        """SELECT video_path FROM analysis_runs
            WHERE analysis_key=? OR analysis_key=?
            ORDER BY id DESC LIMIT 1""",
        (key, game_id),
    ).fetchone()
    if not row:
        return None
    path = row["video_path"] if hasattr(row, "keys") else row[0]
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        candidate = ROOT / path
    return str(candidate) if candidate.is_file() else None


def ensure_tracker_shades(db, game_id: str, *, tracker_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    """Sample jersey brightness for event tracks. Cached. Skips if the video is missing."""
    cached = load_cached_shades(game_id)
    needed = list(tracker_ids if tracker_ids is not None else _event_tracker_ids(db, game_id))
    missing = [tid for tid in needed if tid not in cached]
    if not missing:
        return cached

    video_path = _video_path_for_game(db, game_id)
    if not video_path:
        return cached

    try:
        import cv2
    except ImportError:
        return cached

    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return cached

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    values: dict[int, list[float]] = {}
    try:
        for tracker_id in missing:
            for row in _sample_rows_for_tracker(db, game_id, tracker_id):
                ts = int(row["timestamp_ms"] if hasattr(row, "keys") else row[0] or 0)
                frame_idx = int(round((ts / 1000.0) * fps))
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                val = _torso_value(
                    frame,
                    int(row["x_center"] if hasattr(row, "keys") else row[1]),
                    int(row["y_center"] if hasattr(row, "keys") else row[2]),
                    int(row["width"] if hasattr(row, "keys") else row[3]),
                    int(row["height"] if hasattr(row, "keys") else row[4]),
                )
                if val is None:
                    continue
                values.setdefault(tracker_id, []).append(val)
    finally:
        cap.release()

    split = DEFAULT_SPLIT

    for tracker_id, series in values.items():
        mean_s = sum(pair[0] for pair in series) / len(series)
        mean_v = sum(pair[1] for pair in series) / len(series)
        shade = shade_from_hsv(mean_s, mean_v)
        cached[tracker_id] = {
            "mean_s": round(mean_s, 1),
            "mean_v": round(mean_v, 1),
            "samples": len(series),
            "shade": shade,
            "side": side_from_shade(shade),
        }
    if values:
        save_cached_shades(game_id, cached, split=split)
    return cached
