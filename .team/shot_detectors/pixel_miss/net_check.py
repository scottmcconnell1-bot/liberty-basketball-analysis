"""Read-only net-region orange/white measurement after the rim (Task 1 step 3).

Plan: .team/specs/15_net_check_plan.md (VETTED + BINDING NOTE a).
Imports net_detector._net_box only; never edits core files. Thresholds are for
the summary table only — nothing is applied to any detector.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from net_detector import _net_box  # noqa: E402

# --- constants (no config.yaml) ---
DELTA_RATIO_THRESHOLD = 0.08
REPORT_THRESHOLDS = (0.05, 0.08, 0.10, 0.12)
BEFORE_OFFSET = -3
AFTER_OFFSETS = (1, 2, 3, 4, 5)

# HSV: BINDING NOTE a — red1/red2 match net_detector.py:74-75 (sat/val >= 70).
# Only orange (8-22) uses sat/val >= 90 (net_detector.py:76).
RED1_LO = (0, 70, 70)
RED1_HI = (14, 255, 255)
RED2_LO = (165, 70, 70)
RED2_HI = (180, 255, 255)
ORANGE_LO = (8, 90, 90)
ORANGE_HI = (22, 255, 255)

# White / gray net mesh (plan §3.3)
# white: sat < 60, val > 155  → inclusive OpenCV bounds
WHITE_LO = (0, 0, 156)
WHITE_HI = (180, 59, 255)
# gray: sat < 55, val 70–190
GRAY_LO = (0, 0, 70)
GRAY_HI = (180, 54, 190)

EXPECTED_BUILD = 140
EXPECTED_MISSED_MAKES = 19
EXPECTED_CORRECT_MAKES = 28
EXPECTED_REAL_MISSES = 93

DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/net_check"),
]

DEFAULT_RESULTS_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_build_results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/net_moved_build_results.json"),
]


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is None:
            continue
        p = Path(cand)
        if p.exists():
            return p
    return None


def resolve_path(path_str: str) -> Path:
    """Return a Path that exists, accepting Windows or /mnt/c forms."""
    raw = Path(path_str)
    if raw.exists():
        return raw
    s = str(path_str)
    if len(s) >= 3 and s[1] == ":" and s[0].isalpha():
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/").lstrip("/")
        alt = Path(f"/mnt/{drive}/{rest}")
        if alt.exists():
            return alt
    if s.startswith("/mnt/") and len(s) > 7:
        drive = s[5].upper()
        rest = s[7:].replace("/", "\\")
        alt = Path(f"{drive}:\\{rest}")
        if alt.exists():
            return alt
    return raw


def default_out_dir() -> Path:
    found = pick_existing(*DEFAULT_OUT_CANDIDATES)
    if found is not None:
        return found
    return DEFAULT_OUT_CANDIDATES[0]


def default_results_path() -> Path:
    found = pick_existing(*DEFAULT_RESULTS_CANDIDATES)
    if found is not None:
        return found
    return DEFAULT_RESULTS_CANDIDATES[0]


def dedupe_by_film_t(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the first row for each (film, t). Adrian tracks list some t twice."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (row["film"], int(row["t"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def classify_shots(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    missed = [r for r in rows if r.get("missed_make")]
    correct = [r for r in rows if r.get("gt_make") and r.get("rule_pred_make")]
    misses = [r for r in rows if not r.get("gt_make")]
    missed_sorted = sorted(
        missed, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"]))
    )
    correct_sorted = sorted(correct, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"])))
    misses_sorted = sorted(misses, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"])))
    return missed_sorted, correct_sorted, misses_sorted


def review_crop_shots(
    missed: List[Dict[str, Any]],
    correct: List[Dict[str, Any]],
    misses: List[Dict[str, Any]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """Same 39 shots as build_review_page: 19 missed + 10 correct + 10 misses."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    for i, row in enumerate(missed, start=1):
        out.append((f"missed_make_{i:02d}", row))
    correct_pick = sorted(correct, key=lambda r: int(r["t"]))[:10]
    for i, row in enumerate(correct_pick, start=1):
        out.append((f"correct_make_{i:02d}", row))
    miss_pick = sorted(misses, key=lambda r: int(r["t"]))[:10]
    for i, row in enumerate(miss_pick, start=1):
        out.append((f"miss_{i:02d}", row))
    return out


class FrameReader:
    def __init__(self, video_path: Path):
        self.path = video_path
        self.cap = cv2.VideoCapture(str(video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = float(fps) if fps and fps > 1e-6 else 25.0
        n = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self.total_frames = int(n) if n and n > 0 else 0

    def read(self, frame_idx: int):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
        ok, frame = self.cap.read()
        if not ok:
            return None
        return frame

    def close(self) -> None:
        self.cap.release()


def orange_mask(hsv: np.ndarray) -> np.ndarray:
    red1 = cv2.inRange(hsv, RED1_LO, RED1_HI)
    red2 = cv2.inRange(hsv, RED2_LO, RED2_HI)
    orange = cv2.inRange(hsv, ORANGE_LO, ORANGE_HI)
    return cv2.bitwise_or(cv2.bitwise_or(red1, red2), orange)


def measure_roi(frame, hoop_x: float, hoop_y: float, rim_r: float) -> Dict[str, float]:
    """Count orange / white / gray and largest orange blob inside the net ROI."""
    empty = {
        "orange_px": 0,
        "white_px": 0,
        "gray_px": 0,
        "max_blob": 0,
        "orange_ratio": 0.0,
    }
    if frame is None:
        return empty
    box = _net_box(frame.shape, (hoop_x, hoop_y), rim_r)
    if box is None:
        return empty
    x0, y0, x1, y1 = box
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return empty
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    o_mask = orange_mask(hsv)
    w_mask = cv2.inRange(hsv, WHITE_LO, WHITE_HI)
    g_mask = cv2.inRange(hsv, GRAY_LO, GRAY_HI)
    orange_px = int(cv2.countNonZero(o_mask))
    white_px = int(cv2.countNonZero(w_mask))
    gray_px = int(cv2.countNonZero(g_mask))
    max_blob = 0
    nlab, _labels, stats, _cents = cv2.connectedComponentsWithStats(o_mask, 8)
    for i in range(1, nlab):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area > max_blob:
            max_blob = area
    orange_ratio = orange_px / max(1, white_px + gray_px)
    return {
        "orange_px": orange_px,
        "white_px": white_px,
        "gray_px": gray_px,
        "max_blob": max_blob,
        "orange_ratio": float(orange_ratio),
    }


def crop_square(
    frame, hoop_x: float, hoop_y: float, hoop_w: float
) -> Tuple[Any, int, int, int]:
    h, w = frame.shape[:2]
    size = int(max(hoop_w * 3.0, 240.0))
    cx, cy = int(round(hoop_x)), int(round(hoop_y))
    half = size // 2
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(w, x0 + size)
    y1 = min(h, y0 + size)
    x0 = max(0, x1 - size)
    y0 = max(0, y1 - size)
    crop = frame[y0:y1, x0:x1].copy()
    return crop, x0, y0, size


def draw_net_check_crop(
    frame,
    hoop_x: float,
    hoop_y: float,
    hoop_w: float,
    rim_r: float,
) -> Any:
    """Square crop with net ROI in blue and orange pixels highlighted in red."""
    if frame is None:
        size = int(max(hoop_w * 3.0, 240.0))
        return np.zeros((size, size, 3), dtype=np.uint8)
    crop, crop_x, crop_y, _size = crop_square(frame, hoop_x, hoop_y, hoop_w)
    box = _net_box(frame.shape, (hoop_x, hoop_y), rim_r)
    if box is not None:
        x0, y0, x1, y1 = box
        roi = frame[y0:y1, x0:x1]
        if roi.size:
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            o_mask = orange_mask(hsv)
            # Map ROI mask into crop coordinates and paint orange pixels red
            cy0 = max(0, y0 - crop_y)
            cy1 = min(crop.shape[0], y1 - crop_y)
            cx0 = max(0, x0 - crop_x)
            cx1 = min(crop.shape[1], x1 - crop_x)
            my0 = cy0 - (y0 - crop_y)
            mx0 = cx0 - (x0 - crop_x)
            my1 = my0 + (cy1 - cy0)
            mx1 = mx0 + (cx1 - cx0)
            if cy1 > cy0 and cx1 > cx0:
                sub = o_mask[my0:my1, mx0:mx1] > 0
                region = crop[cy0:cy1, cx0:cx1]
                region[sub] = (0, 0, 255)
        cv2.rectangle(
            crop,
            (x0 - crop_x, y0 - crop_y),
            (x1 - crop_x, y1 - crop_y),
            (255, 0, 0),
            2,
        )
    return crop


def has_crossing_from_row(row: Dict[str, Any]) -> bool:
    reason = row.get("peak_reason") or ""
    if reason == "crossing":
        return True
    if row.get("used_no_crossing_rule"):
        return False
    return reason == "crossing"


def measure_shot(row: Dict[str, Any], reader: FrameReader) -> Dict[str, Any]:
    peak_frame = int(row["peak_frame"])
    hoop_x = float(row["hoop_x"])
    hoop_y = float(row["hoop_y"])
    hoop_w = float(row["hoop_w"])
    rim_r = float(row.get("rim_r") or (hoop_w / 2.0))
    crossing = has_crossing_from_row(row)

    before_frame = peak_frame + BEFORE_OFFSET
    before_m = measure_roi(reader.read(before_frame), hoop_x, hoop_y, rim_r)
    before_out = {
        "frame": before_frame,
        "orange_px": before_m["orange_px"],
        "white_px": before_m["white_px"],
        "gray_px": before_m["gray_px"],
        "max_blob": before_m["max_blob"],
        "orange_ratio": before_m["orange_ratio"],
    }

    frames_out: List[Dict[str, Any]] = []
    max_orange_ratio = -1.0
    max_delta_ratio = None
    max_orange_frame = peak_frame + AFTER_OFFSETS[0]
    max_delta_frame = peak_frame + AFTER_OFFSETS[0]

    for off in AFTER_OFFSETS:
        fidx = peak_frame + off
        m = measure_roi(reader.read(fidx), hoop_x, hoop_y, rim_r)
        delta_orange = m["orange_px"] - before_m["orange_px"]
        delta_ratio = m["orange_ratio"] - before_m["orange_ratio"]
        frames_out.append(
            {
                "frame": fidx,
                "orange_px": m["orange_px"],
                "white_px": m["white_px"],
                "gray_px": m["gray_px"],
                "max_blob": m["max_blob"],
                "orange_ratio": m["orange_ratio"],
                "delta_orange": delta_orange,
                "delta_ratio": float(delta_ratio),
            }
        )
        if m["orange_ratio"] > max_orange_ratio:
            max_orange_ratio = m["orange_ratio"]
            max_orange_frame = fidx
        if max_delta_ratio is None or delta_ratio > max_delta_ratio:
            max_delta_ratio = float(delta_ratio)
            max_delta_frame = fidx

    if max_delta_ratio is None:
        max_delta_ratio = 0.0

    return {
        "t": int(row["t"]),
        "film": row["film"],
        "start": row.get("start") or "",
        "quarter": row.get("quarter") or "",
        "label": row.get("label") or "",
        "player": row.get("player") or "",
        "gt_make": bool(row.get("gt_make")),
        "rule_pred_make": bool(row.get("rule_pred_make")),
        "missed_make": bool(row.get("missed_make")),
        "is_miss": bool(row.get("is_miss")) if "is_miss" in row else (not bool(row.get("gt_make"))),
        "peak_frame": peak_frame,
        "peak_reason": row.get("peak_reason") or "",
        "has_crossing": crossing,
        "hoop_x": hoop_x,
        "hoop_y": hoop_y,
        "hoop_w": hoop_w,
        "rim_r": rim_r,
        "before": before_out,
        "frames": frames_out,
        "max_orange_ratio": float(max_orange_ratio if max_orange_ratio >= 0 else 0.0),
        "max_delta_ratio": float(max_delta_ratio),
        "max_orange_frame": int(max_orange_frame),
        "max_delta_frame": int(max_delta_frame),
        "video_path": row.get("video_path") or "",
        "tracks_path": row.get("tracks_path") or "",
    }


def write_markdown_outputs(
    out_dir: Path,
    results: List[Dict[str, Any]],
    missed: List[Dict[str, Any]],
    correct: List[Dict[str, Any]],
    misses: List[Dict[str, Any]],
    thr: float,
) -> None:
    def caught(rows: List[Dict[str, Any]]) -> int:
        return sum(1 for r in rows if r["max_delta_ratio"] >= thr)

    mm_c = caught(missed)
    cm_c = caught(correct)
    miss_c = caught(misses)
    mm_cross = [r for r in missed if r["has_crossing"]]
    mm_nocross = [r for r in missed if not r["has_crossing"]]

    summary_lines = [
        "# Net Check Summary (read-only measurement)",
        "",
        f"Build shots: {len(results)}",
        f"Missed makes: {len(missed)}",
        f"  Caught (delta_ratio ≥ {thr}): {mm_c}",
        f"  Has crossing: {caught(mm_cross)} / {len(mm_cross)}",
        f"  No crossing: {caught(mm_nocross)} / {len(mm_nocross)}",
        f"Correct makes: {len(correct)}",
        f"  Caught (delta_ratio ≥ {thr}): {cm_c}",
        f"Real misses: {len(misses)}",
        f"  Fired on (delta_ratio ≥ {thr}): {miss_c}",
        "",
        "| Threshold | Real misses fired |",
        "|-----------|-------------------|",
    ]
    for t in REPORT_THRESHOLDS:
        n = sum(1 for r in misses if r["max_delta_ratio"] >= t)
        summary_lines.append(f"| {t:.2f} | {n} |")
    summary_lines.append("")
    summary_lines.append(
        "Thresholds are for this summary table only; nothing is applied to any detector."
    )
    summary_lines.append("")
    (out_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    mm_lines = [
        "# Missed makes detail",
        "",
        "| # | film | t | start | max_delta_ratio | max_delta_frame | has_crossing |",
        "|---|------|---|-------|-----------------|-----------------|--------------|",
    ]
    for i, r in enumerate(missed, start=1):
        mm_lines.append(
            f"| {i} | {r['film']} | {r['t']} | {r.get('start','')} | "
            f"{r['max_delta_ratio']:.4f} | {r['max_delta_frame']} | {r['has_crossing']} |"
        )
    mm_lines.append("")
    (out_dir / "missed_makes_detail.md").write_text(
        "\n".join(mm_lines) + "\n", encoding="utf-8"
    )

    cm_lines = [
        "# Correct makes detail (sanity check)",
        "",
        "| # | film | t | start | max_delta_ratio | max_delta_frame | has_crossing |",
        "|---|------|---|-------|-----------------|-----------------|--------------|",
    ]
    for i, r in enumerate(correct, start=1):
        cm_lines.append(
            f"| {i} | {r['film']} | {r['t']} | {r.get('start','')} | "
            f"{r['max_delta_ratio']:.4f} | {r['max_delta_frame']} | {r['has_crossing']} |"
        )
    cm_lines.append("")
    (out_dir / "correct_makes_detail.md").write_text(
        "\n".join(cm_lines) + "\n", encoding="utf-8"
    )

    fired = [r for r in misses if r["max_delta_ratio"] > 0]
    fired_lines = [
        "# Misses with max_delta_ratio > 0",
        "",
        f"Count: {len(fired)} (at report threshold {thr}: "
        f"{sum(1 for r in misses if r['max_delta_ratio'] >= thr)})",
        "",
    ]
    if not fired:
        fired_lines.append("(none)")
    else:
        fired_lines.append(
            "| film | t | start | max_delta_ratio | max_delta_frame |"
        )
        fired_lines.append("|------|---|-------|-----------------|-----------------|")
        for r in fired:
            fired_lines.append(
                f"| {r['film']} | {r['t']} | {r.get('start','')} | "
                f"{r['max_delta_ratio']:.4f} | {r['max_delta_frame']} |"
            )
    fired_lines.append("")
    (out_dir / "misses_fired_on.md").write_text(
        "\n".join(fired_lines) + "\n", encoding="utf-8"
    )


def print_console_summary(
    out_dir: Path,
    results: List[Dict[str, Any]],
    missed: List[Dict[str, Any]],
    correct: List[Dict[str, Any]],
    misses: List[Dict[str, Any]],
    crop_count: int,
) -> None:
    thr = DELTA_RATIO_THRESHOLD

    def caught(rows: List[Dict[str, Any]]) -> int:
        return sum(1 for r in rows if r["max_delta_ratio"] >= thr)

    mm_c = caught(missed)
    cm_c = caught(correct)
    miss_c = caught(misses)
    mm_cross = [r for r in missed if r["has_crossing"]]
    mm_nocross = [r for r in missed if not r["has_crossing"]]

    print("=== NET CHECK SUMMARY ===")
    print(f"Build shots: {len(results)}")
    print(f"Missed makes: {len(missed)}")
    print(f"  Caught (delta_ratio ≥ {thr}): {mm_c}")
    print("  By crossing status:")
    print(f"    Has crossing: {caught(mm_cross)} caught / {len(mm_cross)}")
    print(f"    No crossing:  {caught(mm_nocross)} caught / {len(mm_nocross)}")
    print(f"Correct makes: {len(correct)}")
    print(f"  Caught (delta_ratio ≥ {thr}): {cm_c}   <-- sanity check")
    print(f"Real misses: {len(misses)}")
    print(f"  Fired on (delta_ratio ≥ {thr}): {miss_c}   <-- MUST BE 0")
    if miss_c != 0:
        print(f"FAIL: expected 0 real misses at threshold {thr}, got {miss_c}")
    n05 = sum(1 for r in misses if r["max_delta_ratio"] >= 0.05)
    n10 = sum(1 for r in misses if r["max_delta_ratio"] >= 0.10)
    n12 = sum(1 for r in misses if r["max_delta_ratio"] >= 0.12)
    print(f"  Fired on (delta_ratio ≥ 0.05): {n05}")
    print(f"  Fired on (delta_ratio ≥ 0.10): {n10}")
    print(f"  Fired on (delta_ratio ≥ 0.12): {n12}")

    print("")
    print("Per missed make:")
    for i, r in enumerate(missed, start=1):
        print(
            f"  missed_make_{i:02d} ({r['film']} t={r['t']}):  "
            f"max_delta={r['max_delta_ratio']:.2f} at frame {r['max_delta_frame']}  "
            f"crossing={r['has_crossing']}"
        )

    print("")
    print(f"Wrote: {out_dir / 'build_results.json'}")
    print(f"Wrote: {out_dir / 'summary.md'}")
    print(f"Wrote: {out_dir / 'missed_makes_detail.md'}")
    print(f"Wrote: {out_dir / 'correct_makes_detail.md'}")
    print(f"Wrote: {out_dir / 'misses_fired_on.md'}")
    print(f"Crops: {crop_count} PNGs in crops/")
    print("STOP — measurement complete, no detector changes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output folder (default: Liberty_Shot_Outputs/net_check)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="Step-1 build results JSON (default: Liberty_Shot_Outputs/net_moved_build_results.json)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out is not None else default_out_dir()
    results_arg = Path(args.results) if args.results is not None else default_results_path()
    results_path = resolve_path(str(results_arg))
    if not results_path.exists():
        print(f"ERROR: results file not found: {results_arg} (resolved {results_path})")
        return 1

    raw_rows = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(raw_rows, list):
        print("ERROR: results JSON must be a list of shot rows")
        return 1

    rows = dedupe_by_film_t([r for r in raw_rows if r.get("set", "build") == "build"])
    missed_src, correct_src, misses_src = classify_shots(rows)

    print(
        f"Shot counts after dedupe: build={len(rows)} "
        f"missed_makes={len(missed_src)} correct_makes={len(correct_src)} "
        f"real_misses={len(misses_src)}"
    )
    if (
        len(rows) != EXPECTED_BUILD
        or len(missed_src) != EXPECTED_MISSED_MAKES
        or len(correct_src) != EXPECTED_CORRECT_MAKES
        or len(misses_src) != EXPECTED_REAL_MISSES
    ):
        print(
            "ERROR: expected "
            f"{EXPECTED_BUILD} shots = {EXPECTED_MISSED_MAKES} missed makes + "
            f"{EXPECTED_CORRECT_MAKES} correct makes + {EXPECTED_REAL_MISSES} real misses; "
            f"got {len(rows)} = {len(missed_src)} + {len(correct_src)} + {len(misses_src)}"
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    crops_root = out_dir / "crops"
    crops_root.mkdir(parents=True, exist_ok=True)

    reader_cache: Dict[str, FrameReader] = {}

    def reader_for(row: Dict[str, Any]) -> FrameReader:
        key = row["video_path"]
        if key not in reader_cache:
            vp = resolve_path(key)
            if not vp.exists():
                # Fall back to film video under repo uploads via known paths in row
                raise FileNotFoundError(f"video not found: {key} -> {vp}")
            reader_cache[key] = FrameReader(vp)
        return reader_cache[key]

    try:
        measured: List[Dict[str, Any]] = []
        by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for i, row in enumerate(rows, start=1):
            reader = reader_for(row)
            m = measure_shot(row, reader)
            measured.append(m)
            by_key[(m["film"], m["t"])] = m
            print(
                f"[{i}/{len(rows)}] {m['film']} t={m['t']} "
                f"peak={m['peak_frame']} max_delta={m['max_delta_ratio']:.4f} "
                f"crossing={m['has_crossing']}",
                flush=True,
            )

        missed = [by_key[(r["film"], int(r["t"]))] for r in missed_src]
        correct = [by_key[(r["film"], int(r["t"]))] for r in correct_src]
        misses = [by_key[(r["film"], int(r["t"]))] for r in misses_src]

        (out_dir / "build_results.json").write_text(
            json.dumps(measured, indent=2), encoding="utf-8"
        )
        write_markdown_outputs(
            out_dir, measured, missed, correct, misses, DELTA_RATIO_THRESHOLD
        )

        # Crops for the 39 review-page shots
        crop_pairs = review_crop_shots(missed_src, correct_src, misses_src)
        crop_count = 0
        for shot_id, src_row in crop_pairs:
            key = (src_row["film"], int(src_row["t"]))
            m = by_key[key]
            reader = reader_for(src_row)
            frame_idx = int(m["max_delta_frame"])
            if m["max_delta_ratio"] == 0 and all(
                f["delta_ratio"] == 0 for f in m["frames"]
            ):
                frame_idx = int(m["peak_frame"]) + 2
            frame = reader.read(frame_idx)
            crop = draw_net_check_crop(
                frame,
                m["hoop_x"],
                m["hoop_y"],
                m["hoop_w"],
                m["rim_r"],
            )
            shot_dir = crops_root / shot_id
            shot_dir.mkdir(parents=True, exist_ok=True)
            out_png = shot_dir / "net_check_010.png"
            cv2.imwrite(str(out_png), crop)
            crop_count += 1

        print("")
        print_console_summary(out_dir, measured, missed, correct, misses, crop_count)
        return 0
    finally:
        for r in reader_cache.values():
            r.close()


if __name__ == "__main__":
    raise SystemExit(main())
