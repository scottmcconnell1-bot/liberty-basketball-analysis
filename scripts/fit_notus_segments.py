#!/usr/bin/env python3
"""Fit the Notus seven-segment geometry on frames that are not in the gate.

    python scripts/fit_notus_segments.py

The gate frames are the twenty answer-key crops. This script samples both Notus
videos at timestamps at least 60 s away from every answer-key timestamp, builds
the mean red-mask occupancy inside each tens/ones slot box, finds the two dark
holes that the digits leave in the middle of the slot, and derives the seven
segment regions from those measured boundaries. The result is stored as
fractions of the fixed slot box in ``data/roi/notus_segment_geometry.json``.

Nothing here reads a gate frame and nothing here uses a digit template. The
geometry is measured once and then loaded by ``scoreboard_clock_720p``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from scoreboard_clock import _SEGMENTS, _red_mask  # noqa: E402

ROI_FILE = ROOT / "data" / "roi" / "notus_scoreboard_rois.json"
OUT_FILE = ROOT / "data" / "roi" / "notus_segment_geometry.json"

CANON_W = 100
CANON_H = 120
GATE_GAP_S = 60.0
FIT_START_S = 6.0
FIT_STEP_S = 8.0
MIN_LIT_PIXELS = 120
DARK_THRESHOLD = 0.18
MIN_HOLE_AREA = 200
CORE_SCALE = 0.46
SEGMENT_ORDER = ("a", "b", "c", "d", "e", "f", "g")


def _crop(frame: np.ndarray, box: list[int] | tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = (int(value) for value in box)
    return frame[max(0, y) : max(0, y) + h, max(0, x) : max(0, x) + w]


def _gate_timestamps(rois: dict) -> list[float]:
    """The exact timestamps of the twenty answer-key crops."""
    stamps: list[float] = []
    for game in (rois.get("games") or {}).values():
        for sample in game.get("samples") or []:
            stamps.append(float(sample["timestamp_ms"]) / 1000.0)
    return stamps


def _sample_timestamps(duration_s: float, gate_s: list[float]) -> list[float]:
    stamps: list[float] = []
    timestamp = FIT_START_S
    while timestamp < duration_s - 2.0:
        if not gate_s or min(abs(timestamp - gate) for gate in gate_s) >= GATE_GAP_S:
            stamps.append(round(timestamp, 3))
        timestamp += FIT_STEP_S
    return stamps


def _collect_masks(game: dict, timestamps: list[float]) -> list[np.ndarray]:
    video = ROOT / game["video"]
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
    masks: list[np.ndarray] = []
    try:
        for timestamp in timestamps:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(round(timestamp * fps)))
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            for side in ("home", "away"):
                cell = (game.get("scores") or {}).get(side) or {}
                for slot in ("tens", "ones"):
                    box = cell.get(slot)
                    if not box:
                        continue
                    mask = _red_mask(_crop(frame, box))
                    if int((mask > 0).sum()) < MIN_LIT_PIXELS:
                        continue
                    masks.append(
                        cv2.resize(mask.astype(np.float32), (CANON_W, CANON_H), interpolation=cv2.INTER_AREA)
                        / 255.0
                    )
    finally:
        capture.release()
    return masks


def _digit_bbox(lit: np.ndarray) -> tuple[float, float, float, float]:
    """Digit extents, ignoring one-pixel noise at the slot edges."""
    columns = lit.sum(axis=0)
    rows = lit.sum(axis=1)
    col_min = max(2, int(round(0.02 * CANON_H)))
    row_min = max(2, int(round(0.02 * CANON_W)))
    cols = np.where(columns >= col_min)[0]
    rows_keep = np.where(rows >= row_min)[0]
    if len(cols) == 0 or len(rows_keep) == 0:
        return 0.0, 0.0, 1.0, 1.0
    return (
        float(cols[0]) / CANON_W,
        float(rows_keep[0]) / CANON_H,
        float(cols[-1] + 1) / CANON_W,
        float(rows_keep[-1] + 1) / CANON_H,
    )


def _find_holes(smoothed: np.ndarray) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    dark = (smoothed < DARK_THRESHOLD).astype(np.uint8)
    region = np.zeros_like(dark)
    region[int(0.05 * CANON_H) : int(0.95 * CANON_H), int(0.12 * CANON_W) : int(0.88 * CANON_W)] = 1
    dark *= region
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(dark, 8)
    holes = []
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        if area >= MIN_HOLE_AREA:
            holes.append((x, y, w, h, area, float(centroids[index][1]) / CANON_H))
    holes.sort(key=lambda item: item[4], reverse=True)
    upper = next((hole for hole in holes if hole[5] < 0.5), None)
    lower = next((hole for hole in holes if hole[5] > 0.5), None)
    if upper is None or lower is None:
        return None
    return upper[:4], lower[:4]


def _standard_geometry() -> dict[str, list[float]]:
    """Fallback only: the shared layout, if the mean map has no holes."""
    return {name: [float(value) for value in rect] for name, rect in _SEGMENTS.items()}


def _fit_geometry(masks: list[np.ndarray]) -> dict[str, list[float]]:
    if not masks:
        raise RuntimeError("no usable non-gate slot masks were collected")
    mean = np.mean(masks, axis=0)
    smoothed = cv2.GaussianBlur(mean, (5, 5), 0)

    lit = (smoothed > DARK_THRESHOLD).astype(np.uint8)
    dx0, dy0, dx1, dy1 = _digit_bbox(lit)
    holes = _find_holes(smoothed)
    if holes is None:
        print("warning: could not find both holes; using the shared layout")
        return _standard_geometry()

    upper, lower = holes
    ux0, uy0, uw, uh = upper
    lx0, ly0, lw, lh = lower
    hx0 = max(ux0, lx0) / CANON_W
    hx1 = min(ux0 + uw, lx0 + lw) / CANON_W
    upper_top = uy0 / CANON_H
    upper_bottom = (uy0 + uh) / CANON_H
    lower_top = ly0 / CANON_H
    lower_bottom = (ly0 + lh) / CANON_H

    raw = {
        "a": (hx0, dy0, hx1, upper_top),
        "g": (hx0, upper_bottom, hx1, lower_top),
        "d": (hx0, lower_bottom, hx1, dy1),
        "b": (hx1, upper_top, dx1, upper_bottom),
        "f": (dx0, upper_top, hx0, upper_bottom),
        "c": (hx1, lower_top, dx1, lower_bottom),
        "e": (dx0, lower_top, hx0, lower_bottom),
    }

    geometry: dict[str, list[float]] = {}
    for name in SEGMENT_ORDER:
        x0, y0, x1, y1 = raw[name]
        center_x = (x0 + x1) / 2.0
        center_y = (y0 + y1) / 2.0
        half_w = (x1 - x0) * CORE_SCALE
        half_h = (y1 - y0) * CORE_SCALE
        geometry[name] = [
            round(max(0.0, center_x - half_w), 4),
            round(max(0.0, center_y - half_h), 4),
            round(min(1.0, center_x + half_w), 4),
            round(min(1.0, center_y + half_h), 4),
        ]
    return geometry


def main() -> int:
    rois = json.loads(ROI_FILE.read_text(encoding="utf-8"))
    gate_s = _gate_timestamps(rois)
    masks: list[np.ndarray] = []
    counts: dict[str, int] = {}
    for game_id, game in (rois.get("games") or {}).items():
        duration_s = float(game.get("fps") or 25.0)
        video = ROOT / game["video"]
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise RuntimeError(f"cannot open {video}")
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
        capture.release()
        duration_s = frames / fps if frames else duration_s
        timestamps = _sample_timestamps(duration_s, gate_s)
        game_masks = _collect_masks(game, timestamps)
        masks.extend(game_masks)
        counts[game_id] = len(game_masks)
        print(f"{game_id}: {len(game_masks)} non-gate slot masks from {len(timestamps)} frames")

    geometry = _fit_geometry(masks)
    payload = {
        "generated_by": "scripts/fit_notus_segments.py",
        "method": (
            "Mean red-mask occupancy of non-gate tens/ones slots, resized to "
            f"{CANON_W}x{CANON_H}; the two dark holes locate the central column band and the "
            "upper/lower stroke bands; each segment is a core rectangle inside its measured band. "
            f"Fitting frames stay at least {GATE_GAP_S:.0f} s from every answer-key timestamp."
        ),
        "gate_gap_s": GATE_GAP_S,
        "core_scale": CORE_SCALE,
        "fit_masks": counts,
        "segments": geometry,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
