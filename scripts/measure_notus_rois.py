#!/usr/bin/env python3
"""Measure the Notus 720p scoreboard digit boxes and save eye-check crops.

    python scripts/measure_notus_rois.py

Non-interactive: no prompts and no GUI windows. For each Notus game it samples
ten frames spread across the film, finds the red score digits and yellow clock
digits in search windows, and writes:

    data/roi/notus_scoreboard_rois.json
    data/roi/notus_crops/<game>_<index>_<seconds>s.png   (10 per game, 20 total)
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from scoreboard_clock import _red_mask  # noqa: E402

ROI_FILE = ROOT / "data" / "roi" / "notus_scoreboard_rois.json"
CROP_DIR = ROOT / "data" / "roi" / "notus_crops"

GAMES = (
    {
        "game_id": "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
        "label": "notus_A1",
        "video": "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
    },
    {
        "game_id": "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334",
        "label": "notus_A",
        "video": "uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4",
    },
)

HOME_SEARCH = (1018, 608, 1092, 650)
AWAY_SEARCH = (1185, 608, 1260, 650)
CLOCK_SEARCH = (1062, 556, 1202, 596)
BOARD_CROP = (1000, 540, 1280, 700)
CROP_SCALE = 4
SAMPLES = 10
MIN_AREA = 20
MIN_CLUSTER_AREA = 40
MERGE_GAP = 2
NOMINAL_CLOCK_MIN_X = 1090


def _components(mask: np.ndarray, x0: int, y0: int) -> list[tuple[int, int, int, int, int]]:
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    boxes = []
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        if area >= MIN_AREA:
            boxes.append((x + x0, y + y0, w, h, area))
    return sorted(boxes)


def _merge(a: tuple[int, int, int, int, int], b: tuple[int, int, int, int, int]) -> tuple[int, int, int, int, int]:
    x0 = min(a[0], b[0])
    y0 = min(a[1], b[1])
    x1 = max(a[0] + a[2], b[0] + b[2])
    y1 = max(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1 - x0, y1 - y0, a[4] + b[4])


def _clusters(
    boxes: list[tuple[int, int, int, int, int]], limit: int | None = 2
) -> list[tuple[int, int, int, int, int]]:
    merged: list[tuple[int, int, int, int, int]] = []
    for box in boxes:
        if merged and box[0] <= merged[-1][0] + merged[-1][2] + MERGE_GAP:
            merged[-1] = _merge(merged[-1], box)
        else:
            merged.append(box)
    merged = [box for box in merged if box[4] >= MIN_CLUSTER_AREA]
    while limit is not None and len(merged) > limit:
        gaps = [merged[index + 1][0] - (merged[index][0] + merged[index][2]) for index in range(len(merged) - 1)]
        index = min(range(len(gaps)), key=lambda i: gaps[i])
        merged[index] = _merge(merged[index], merged[index + 1])
        del merged[index + 1]
    return merged


def _score_boxes(frame: np.ndarray, window: tuple[int, int, int, int]) -> list[tuple[int, int, int, int, int]]:
    x0, y0, x1, y1 = window
    return _components(_red_mask(frame[y0:y1, x0:x1]), x0, y0)


def _measure_scores(frame: np.ndarray) -> dict[str, list[int] | None]:
    result: dict[str, list[int] | None] = {
        "home_tens": None,
        "home_ones": None,
        "away_tens": None,
        "away_ones": None,
    }
    for prefix, window in (("home", HOME_SEARCH), ("away", AWAY_SEARCH)):
        clusters = _clusters(_score_boxes(frame, window))
        clusters = [box for box in clusters if box[3] >= 12]
        if len(clusters) >= 2:
            result[f"{prefix}_tens"] = list(clusters[0][:4])
            result[f"{prefix}_ones"] = list(clusters[-1][:4])
        elif len(clusters) == 1:
            result[f"{prefix}_ones"] = list(clusters[0][:4])
    return result


def _measure_clock(frame: np.ndarray) -> dict[str, list[int] | None]:
    x0, y0, x1, y1 = CLOCK_SEARCH
    crop = frame[y0:y1, x0:x1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 40) & (hsv[:, :, 1] >= 45) & (hsv[:, :, 2] >= 140)
    ).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    clusters = [box for box in _clusters(_components(mask, x0, y0), limit=None) if box[3] >= 10]
    field = None
    if clusters:
        fx0 = min(box[0] for box in clusters)
        fy0 = min(box[1] for box in clusters)
        fx1 = max(box[0] + box[2] for box in clusters)
        fy1 = max(box[1] + box[3] for box in clusters)
        field = [fx0, fy0, fx1 - fx0, fy1 - fy0]
    minutes = None
    seconds = None
    if len(clusters) >= 2 and clusters[0][0] >= NOMINAL_CLOCK_MIN_X:
        minutes = list(clusters[0][:4])
        sx0 = min(box[0] for box in clusters[1:])
        sy0 = min(box[1] for box in clusters[1:])
        sx1 = max(box[0] + box[2] for box in clusters[1:])
        sy1 = max(box[1] + box[3] for box in clusters[1:])
        seconds = [sx0, sy0, sx1 - sx0, sy1 - sy0]
    return {"clock_field": field, "clock_minutes": minutes, "clock_seconds": seconds}


def _read_frame(cap: cv2.VideoCapture, timestamp_s: float, fps: float) -> np.ndarray:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(timestamp_s * fps)))
    ok, frame = cap.read()
    if not ok or frame is None:
        raise RuntimeError(f"cannot read frame at {timestamp_s:.1f}s")
    return frame


def _union(boxes: list[list[int]], pad: int = 1) -> list[int] | None:
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    x0 = min(box[0] for box in boxes) - pad
    y0 = min(box[1] for box in boxes) - pad
    x1 = max(box[0] + box[2] for box in boxes) + pad
    y1 = max(box[1] + box[3] for box in boxes) + pad
    return [x0, y0, x1 - x0, y1 - y0]


def _infer_missing(observed: dict[str, list[list[int]]], pitch: int) -> tuple[list[int] | None, list[int] | None, bool]:
    tens = _union(observed["tens"])
    ones = _union(observed["ones"])
    inferred = False
    if ones and not tens:
        tens = [ones[0] - pitch, ones[1], max(18, ones[2]), ones[3]]
        inferred = True
    if tens and not ones:
        ones = [tens[0] + pitch, tens[1], max(18, tens[2]), tens[3]]
        inferred = True
    return tens, ones, inferred


def _score_pitch(events: list[dict], game: str) -> int:
    deltas = []
    for event in events:
        tens = event["measure"].get(f"{game}_tens")
        ones = event["measure"].get(f"{game}_ones")
        if tens and ones:
            deltas.append(ones[0] - tens[0])
    return int(round(statistics.median(deltas))) if deltas else 26


def _aggregate(events: list[dict]) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    result: dict = {"scores": {}, "clock": {}}
    for side in ("home", "away"):
        pitch = _score_pitch(events, side)
        observed = {
            "tens": [event["measure"].get(f"{side}_tens") for event in events],
            "ones": [event["measure"].get(f"{side}_ones") for event in events],
        }
        tens, ones, inferred = _infer_missing(observed, pitch)
        if inferred:
            warnings.append(f"{side} score slot inferred from the other slot (pitch {pitch}px)")
        if tens is None or ones is None:
            warnings.append(f"{side} score slots were not measured")
            continue
        result["scores"][side] = {"tens": tens, "ones": ones, "cell": _union([tens, ones], pad=2)}
    result["clock"]["clock_field"] = _union([event["measure"].get("clock_field") for event in events])
    minutes = _union([event["measure"].get("clock_minutes") for event in events])
    seconds = _union([event["measure"].get("clock_seconds") for event in events])
    if minutes is None or seconds is None:
        field = result["clock"]["clock_field"]
        if field:
            split = field[0] + int(field[2] * 0.42)
            minutes = [field[0], field[1], split - field[0], field[3]]
            seconds = [split, field[1], field[0] + field[2] - split, field[3]]
            warnings.append("clock minutes/seconds boxes inferred from the clock field")
    result["clock"]["clock_minutes"] = minutes
    result["clock"]["clock_seconds"] = seconds
    return result, warnings


_COLORS = {
    "HT": (0, 255, 0),
    "HO": (0, 180, 0),
    "AT": (255, 255, 0),
    "AO": (255, 180, 0),
    "CLK": (0, 165, 255),
    "CM": (255, 0, 255),
    "CS": (180, 0, 180),
}


def _annotate(frame: np.ndarray, rois: dict, label: str, timestamp_s: float) -> np.ndarray:
    bx0, by0, bx1, by1 = BOARD_CROP
    crop = frame[by0:by1, bx0:bx1]
    big = cv2.resize(crop, None, fx=CROP_SCALE, fy=CROP_SCALE, interpolation=cv2.INTER_NEAREST)
    boxes = []
    home = rois["scores"].get("home") or {}
    away = rois["scores"].get("away") or {}
    if home.get("tens"):
        boxes.append(("HT", home["tens"]))
    if home.get("ones"):
        boxes.append(("HO", home["ones"]))
    if away.get("tens"):
        boxes.append(("AT", away["tens"]))
    if away.get("ones"):
        boxes.append(("AO", away["ones"]))
    if rois["clock"].get("clock_field"):
        boxes.append(("CLK", rois["clock"]["clock_field"]))
    if rois["clock"].get("clock_minutes"):
        boxes.append(("CM", rois["clock"]["clock_minutes"]))
    if rois["clock"].get("clock_seconds"):
        boxes.append(("CS", rois["clock"]["clock_seconds"]))
    for tag, box in boxes:
        x, y, w, h = box
        x0 = (x - bx0) * CROP_SCALE
        y0 = (y - by0) * CROP_SCALE
        x1 = x0 + w * CROP_SCALE
        y1 = y0 + h * CROP_SCALE
        cv2.rectangle(big, (x0, y0), (x1, y1), _COLORS[tag], 2)
        cv2.putText(big, tag, (x0, max(12, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, _COLORS[tag], 1, cv2.LINE_AA)
    cv2.putText(big, f"{label} {timestamp_s:.0f}s", (8, big.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return big


def _default_rois(games: dict[str, dict]) -> dict:
    scores = {}
    for side in ("home", "away"):
        tens = _union([game["scores"][side]["tens"] for game in games.values() if side in game["scores"]], pad=0)
        ones = _union([game["scores"][side]["ones"] for game in games.values() if side in game["scores"]], pad=0)
        if tens and ones:
            scores[side] = {"tens": tens, "ones": ones, "cell": _union([tens, ones], pad=2)}
    clock = {}
    field = _union([game["clock"]["clock_field"] for game in games.values() if game["clock"].get("clock_field")], pad=0)
    minutes = _union([game["clock"]["clock_minutes"] for game in games.values() if game["clock"].get("clock_minutes")], pad=0)
    seconds = _union([game["clock"]["clock_seconds"] for game in games.values() if game["clock"].get("clock_seconds")], pad=0)
    if field:
        clock["clock_field"] = field
    if minutes:
        clock["clock_minutes"] = minutes
    if seconds:
        clock["clock_seconds"] = seconds
    return {"scores": scores, "clock": clock}


def measure_game(game: dict) -> dict:
    video = ROOT / game["video"]
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_s = frames / fps if frames else 0.0
    events = []
    for index in range(SAMPLES):
        timestamp_s = duration_s * (index + 0.5) / SAMPLES
        frame = _read_frame(cap, timestamp_s, fps)
        measure = _measure_scores(frame)
        measure.update(_measure_clock(frame))
        events.append({"index": index, "timestamp_s": timestamp_s, "frame": frame, "measure": measure})
    cap.release()
    aggregate, warnings = _aggregate(events)
    CROP_DIR.mkdir(parents=True, exist_ok=True)
    sample_rows = []
    for event in events:
        crop = _annotate(event["frame"], aggregate, game["label"], event["timestamp_s"])
        name = f"{game['label']}_{event['index']:02d}_{int(round(event['timestamp_s']))}s.png"
        path = CROP_DIR / name
        cv2.imwrite(str(path), crop)
        sample_rows.append(
            {
                "timestamp_ms": int(round(event["timestamp_s"] * 1000)),
                "crop": str(path.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    return {
        "game_id": game["game_id"],
        "video": game["video"],
        "width": 1280,
        "height": 720,
        "fps": round(fps, 3),
        "warnings": warnings,
        "samples": sample_rows,
        **_flatten(aggregate),
    }


def _flatten(aggregate: dict) -> dict:
    scores = aggregate["scores"]
    clock = aggregate["clock"]
    flat = {
        "home_score_tens": scores.get("home", {}).get("tens"),
        "home_score_ones": scores.get("home", {}).get("ones"),
        "away_score_tens": scores.get("away", {}).get("tens"),
        "away_score_ones": scores.get("away", {}).get("ones"),
        "home_score_cell": scores.get("home", {}).get("cell"),
        "away_score_cell": scores.get("away", {}).get("cell"),
        "clock_field": clock.get("clock_field"),
        "clock_minutes": clock.get("clock_minutes"),
        "clock_seconds": clock.get("clock_seconds"),
        "scores": scores,
        "clock": clock,
    }
    return flat


def main() -> int:
    games = {}
    for game in GAMES:
        print(f"measuring {game['game_id']} ...")
        result = measure_game(game)
        games[game["game_id"]] = result
        for warning in result["warnings"]:
            print(f"  warning: {warning}")
    payload = {
        "generated_by": "scripts/measure_notus_rois.py",
        "method": (
            "Ten frames per game sampled evenly across the film; red score digit components in "
            "home/away search windows clustered into tens/ones slots; yellow clock components "
            "clustered into the clock field and the nominal M:SS minute/second boxes. Clock digits "
            "are located with a measurement-only yellow mask because Notus A's clock is dimmer than "
            "_warm_mask accepts. Boxes are the union across samples plus one pixel of padding."
        ),
        "video_size": {"width": 1280, "height": 720},
        "games": games,
        "default": _default_rois(games),
    }
    ROI_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROI_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {ROI_FILE.relative_to(ROOT)}")
    print(f"wrote {len(games) * SAMPLES} crops to {CROP_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
