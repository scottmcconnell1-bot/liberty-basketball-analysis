"""Gate: the Notus seven-segment reader must match the twenty answer-key crops.

Each row re-samples the video at the exact timestamp recorded in the ROI JSON
and reads the home and away scores through ``scoreboard_clock_720p._read_score``.
The gate is run once, with no retuning after the segment geometry is fitted on
non-gate frames.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoreboard_clock_720p import _read_score, game_rois, load_rois  # noqa: E402

ROI_FILE = ROOT / "data" / "roi" / "notus_scoreboard_rois.json"
TRUTH_FILE = ROOT / ".team" / "specs" / "04_notus_crop_truth.json"


def _truth_rows() -> list[tuple[str, str, list[int]]]:
    truth = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, list[int]]] = []
    for game_id, entries in truth.items():
        if not isinstance(entries, dict):
            continue
        for crop_name, expected in entries.items():
            rows.append((game_id, crop_name, [int(value) for value in expected]))
    return rows


def _sample_for_crop(config: dict, crop_name: str) -> dict:
    for sample in config.get("samples") or []:
        if Path(str(sample.get("crop"))).stem == crop_name:
            return sample
    raise KeyError(f"no ROI sample for crop {crop_name}")


def _read_frame(capture: cv2.VideoCapture, timestamp_ms: int, fps: float):
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(round(timestamp_ms / 1000.0 * fps)))
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError(f"cannot read frame at {timestamp_ms} ms")
    return frame


def _print_table(results: list[tuple[str, int, int, int | None, int | None, bool]]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    header = (
        f"{'crop':<24} {'exp home':>8} {'exp away':>8} "
        f"{'got home':>8} {'got away':>8} {'':>2}"
    )
    print(header)
    print("-" * len(header))
    for crop_name, expected_home, expected_away, got_home, got_away, ok in results:
        mark = "✓" if ok else "✗"
        print(
            f"{crop_name:<24} {expected_home:>8} {expected_away:>8} "
            f"{str(got_home):>8} {str(got_away):>8} {mark:>2}"
        )


def test_notus_digit_gate() -> None:
    rois = load_rois(ROI_FILE)
    rows = _truth_rows()
    assert len(rows) == 20, f"expected 20 answer-key crops, found {len(rows)}"

    captures: dict[str, cv2.VideoCapture] = {}
    results: list[tuple[str, int, int, int | None, int | None, bool]] = []
    try:
        for game_id, crop_name, expected in rows:
            config = game_rois(rois, game_id)
            sample = _sample_for_crop(config, crop_name)
            capture = captures.get(game_id)
            if capture is None:
                capture = cv2.VideoCapture(str(ROOT / config["video"]))
                if not capture.isOpened():
                    raise RuntimeError(f"cannot open {config['video']}")
                captures[game_id] = capture
            frame = _read_frame(capture, int(sample["timestamp_ms"]), float(config["fps"]))
            cells = config.get("scores") or {}
            got_home = _read_score(frame, cells.get("home") or {})
            got_away = _read_score(frame, cells.get("away") or {})
            expected_home, expected_away = expected
            ok = got_home == expected_home and got_away == expected_away
            results.append((crop_name, expected_home, expected_away, got_home, got_away, ok))
    finally:
        for capture in captures.values():
            capture.release()

    _print_table(results)
    failures = [row for row in results if not row[5]]
    assert not failures, f"{len(failures)} of {len(results)} gate rows failed"
