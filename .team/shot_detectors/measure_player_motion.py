"""Player motion measurement for 140 build shots (measure only, changes no call).

Runs BODD on 3-second windows around each shot's anchor frame, computes:
(a) players within 3 hoop widths (median over first/last 1s, change)
(b) median player distance to hoop in hoop widths (median over first/last 1s, change)

Output: per-shot JSON+MD and summary JSON+MD under player_motion/ directory.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keep_ball_detections import (  # noqa: E402
    FILMS,
    BUILD_QUARTERS,
    EXPECTED_BUILD,
    FPS_FALLBACK,
    ZONE_HOOP_WIDTHS_H,
    load_build_shot_list,
    load_shot_tags,
    load_tracks,
    resolve_film_tracks,
)

BODD_MODEL_NAME = "BODD_yolov8n_0001.pt"
BODD_CONF = 0.12
BODD_IMGSZ = 960
BODD_CLASSES = {"basketball": 0, "hoop": 1, "player": 2, "referee": 3}
PLAYER_CLASS_ID = 2
HOOP_CLASS_ID = 1
WINDOW_SECONDS = 3.0
MEASURE_WINDOW_SECONDS = 1.0
MAX_HOOP_DIST_WIDTHS = 2.0


def find_bodd_model() -> Path:
    """Locate the BODD model file."""
    candidates = [
        Path(rf"C:\Users\scott\AppData\Local\Temp\{BODD_MODEL_NAME}"),
        Path(f"/mnt/c/Users/scott/AppData/Local/Temp/{BODD_MODEL_NAME}"),
        ROOT / BODD_MODEL_NAME,
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"BODD model not found. Tried: {candidates}")


def default_out_dir() -> Path:
    base = Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs")
    if not base.exists():
        base = Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs")
    return base / "player_motion"


def load_d1_results(d1_results_path: Path) -> Dict[int, Dict[str, Any]]:
    """Load D1 results and return a mapping of (film, t) -> anchor_frame."""
    data = json.loads(d1_results_path.read_text(encoding="utf-8"))
    mapping: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for shot in data.get("shots", []):
        key = (shot["film"], int(shot["t"]))
        mapping[key] = shot
    return mapping


def get_anchor_frame(
    shot: Dict[str, Any],
    d1_map: Dict[Tuple[str, int], Dict[str, Any]],
    fps: float,
) -> int:
    """Get anchor frame for a shot: D1 anchor_frame if available, else tag_frame."""
    key = (shot["film"], int(shot["t"]))
    if key in d1_map and d1_map[key].get("anchor_frame") is not None:
        return int(d1_map[key]["anchor_frame"])
    # Fallback to tag frame
    t_ms = int(shot["t"])
    return int(round(t_ms / 1000.0 * fps))


def compute_hoop_center_width(hoop_box: List[float]) -> Tuple[float, float, float]:
    """Return (hx, hy, hw) from hoop box [x, y, w, h] (center format from BODD)."""
    hx, hy, hw, hh = hoop_box
    return float(hx), float(hy), float(hw)


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def median_of_list(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return float(np.median(vals))


def process_shot(
    shot: Dict[str, Any],
    track: Dict[str, Any],
    video_path: Path,
    bodd_model: YOLO,
    d1_map: Dict[Tuple[str, int], Dict[str, Any]],
    fps: float,
) -> Dict[str, Any]:
    """Process a single shot's 3-second window, return per-frame measures."""
    hoop_init = track["hoop"]
    hx0, hy0, hw0 = compute_hoop_center_width(hoop_init)
    prev_hoop_center = (hx0, hy0)
    prev_hoop_width = hw0

    anchor = get_anchor_frame(shot, d1_map, fps)
    window_end = anchor + round(WINDOW_SECONDS * fps)
    measure_end_first = anchor + round(MEASURE_WINDOW_SECONDS * fps)
    measure_start_last = window_end - round(MEASURE_WINDOW_SECONDS * fps)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    per_frame_players_within: List[Optional[int]] = []
    per_frame_median_dist: List[Optional[float]] = []
    hoop_missing_count = 0
    frames_with_hoop = 0

    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, anchor)
        for fr in range(anchor, window_end + 1):
            ok, frame = cap.read()
            if not ok or frame is None:
                # Frame decode failed - treat as hoop missing
                hoop_missing_count += 1
                per_frame_players_within.append(None)
                per_frame_median_dist.append(None)
                continue

            preds = bodd_model.predict(frame, conf=BODD_CONF, imgsz=BODD_IMGSZ, verbose=False)[0]
            if preds.boxes is None:
                hoop_missing_count += 1
                per_frame_players_within.append(None)
                per_frame_median_dist.append(None)
                continue

            # Extract player boxes (class 2) and hoop boxes (class 1)
            player_boxes = []
            hoop_boxes = []
            for box in preds.boxes:
                cls_id = int(box.cls[0])
                if cls_id == PLAYER_CLASS_ID:
                    x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                    player_boxes.append((x1, y1, x2, y2))
                elif cls_id == HOOP_CLASS_ID:
                    x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                    hoop_boxes.append((x1, y1, x2, y2))

            # Choose hoop: nearest to previous hoop center, within 2 hoop widths
            chosen_hoop = None
            if hoop_boxes:
                best_dist = float("inf")
                for hb in hoop_boxes:
                    hx, hy, hw = (hb[0] + hb[2]) / 2.0, (hb[1] + hb[3]) / 2.0, hb[2] - hb[0]
                    dist = distance((hx, hy), prev_hoop_center)
                    if dist < best_dist:
                        best_dist = dist
                        chosen_hoop = (hx, hy, hw)
                # Accept only if within 2 hoop widths of previous
                if chosen_hoop and best_dist > MAX_HOOP_DIST_WIDTHS * prev_hoop_width:
                    chosen_hoop = None

            if chosen_hoop is None:
                hoop_missing_count += 1
                per_frame_players_within.append(None)
                per_frame_median_dist.append(None)
                continue

            # Frame has valid hoop
            frames_with_hoop += 1
            hx, hy, hw = chosen_hoop
            prev_hoop_center = (hx, hy)
            prev_hoop_width = hw

            # Compute player distances to hoop in hoop-width units
            player_distances_hw: List[float] = []
            for pb in player_boxes:
                px = (pb[0] + pb[2]) / 2.0
                py = (pb[1] + pb[3]) / 2.0
                dist = distance((px, py), (hx, hy))
                dist_hw = dist / hw if hw > 0 else float("inf")
                player_distances_hw.append(dist_hw)

            # Measure (a): players within 3 hoop widths
            within_3hw = sum(1 for d in player_distances_hw if d <= ZONE_HOOP_WIDTHS_H)
            per_frame_players_within.append(within_3hw)

            # Measure (b): median player distance in hoop widths
            med_dist = median_of_list(player_distances_hw) if player_distances_hw else None
            per_frame_median_dist.append(med_dist)

    finally:
        cap.release()

    # Compute medians over first 1s and last 1s
    first_1s_players = per_frame_players_within[: round(MEASURE_WINDOW_SECONDS * fps)]
    last_1s_players = per_frame_players_within[-round(MEASURE_WINDOW_SECONDS * fps) :]

    first_1s_dists = [d for d in per_frame_median_dist[: round(MEASURE_WINDOW_SECONDS * fps)] if d is not None]
    last_1s_dists = [d for d in per_frame_median_dist[-round(MEASURE_WINDOW_SECONDS * fps) :] if d is not None]

    median_players_first = median_of_list([float(x) for x in first_1s_players if x is not None])
    median_players_last = median_of_list([float(x) for x in last_1s_players if x is not None])
    change_players = (median_players_last - median_players_first) if (median_players_first is not None and median_players_last is not None) else None

    median_dist_first = median_of_list(first_1s_dists)
    median_dist_last = median_of_list(last_1s_dists)
    change_dist = (median_dist_last - median_dist_first) if (median_dist_first is not None and median_dist_last is not None) else None

    return {
        "shot_key": {
            "film": shot["film"],
            "t": int(shot["t"]),
            "quarter": shot["quarter"],
            "label": shot["label"],
            "player": shot["player"],
            "gt_make": shot["gt_make"],
        },
        "window_frames": [anchor, window_end],
        "hoop_missing_frames": hoop_missing_count,
        "frames_with_hoop": frames_with_hoop,
        "players_within_3hw": {
            "per_frame": per_frame_players_within,
            "median_first_1s": median_players_first,
            "median_last_1s": median_players_last,
            "change": change_players,
        },
        "median_player_distance_hw": {
            "median_first_1s": median_dist_first,
            "median_last_1s": median_dist_last,
            "change": change_dist,
        },
    }


def write_per_shot_outputs(out_dir: Path, film: str, t: int, result: Dict[str, Any]) -> None:
    """Write per-shot JSON and markdown."""
    json_path = out_dir / f"{film}_t{t}_player_motion.json"
    md_path = out_dir / f"{film}_t{t}_player_motion.md"

    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    sk = result["shot_key"]
    lines = [
        f"# Player Motion: {film} t={t}",
        "",
        f"**Quarter:** {sk['quarter']}  **Label:** {sk['label']}  **Player:** {sk['player']}  **GT:** {'Make' if sk['gt_make'] else 'Miss'}",
        "",
        f"**Window frames:** {result['window_frames'][0]} .. {result['window_frames'][1]}",
        f"**Hoop missing frames:** {result['hoop_missing_frames']}  **Frames with hoop:** {result['frames_with_hoop']}",
        "",
        "## Players within 3 hoop widths",
        "",
        f"- Median first 1s: {result['players_within_3hw']['median_first_1s']}",
        f"- Median last 1s: {result['players_within_3hw']['median_last_1s']}",
        f"- Change (last - first): {result['players_within_3hw']['change']}",
        "",
        "## Median player distance (hoop widths)",
        "",
        f"- Median first 1s: {result['median_player_distance_hw']['median_first_1s']}",
        f"- Median last 1s: {result['median_player_distance_hw']['median_last_1s']}",
        f"- Change (last - first): {result['median_player_distance_hw']['change']}",
        "",
        "## Per-frame players within 3hw",
        "",
        str(result["players_within_3hw"]["per_frame"]),
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def compute_summary_stats(
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute makes vs misses summary statistics."""
    makes = [r for r in results if r["shot_key"]["gt_make"]]
    misses = [r for r in results if not r["shot_key"]["gt_make"]]

    def stat_block(group: List[Dict[str, Any]], prefix: str) -> Dict[str, Any]:
        pw_first = [r["players_within_3hw"]["median_first_1s"] for r in group if r["players_within_3hw"]["median_first_1s"] is not None]
        pw_last = [r["players_within_3hw"]["median_last_1s"] for r in group if r["players_within_3hw"]["median_last_1s"] is not None]
        pw_change = [r["players_within_3hw"]["change"] for r in group if r["players_within_3hw"]["change"] is not None]
        md_first = [r["median_player_distance_hw"]["median_first_1s"] for r in group if r["median_player_distance_hw"]["median_first_1s"] is not None]
        md_last = [r["median_player_distance_hw"]["median_last_1s"] for r in group if r["median_player_distance_hw"]["median_last_1s"] is not None]
        md_change = [r["median_player_distance_hw"]["change"] for r in group if r["median_player_distance_hw"]["change"] is not None]

        return {
            f"{prefix}_players_within_3hw_first_1s": {
                "median": median_of_list(pw_first),
                "min": min(pw_first) if pw_first else None,
                "max": max(pw_first) if pw_first else None,
            },
            f"{prefix}_players_within_3hw_last_1s": {
                "median": median_of_list(pw_last),
                "min": min(pw_last) if pw_last else None,
                "max": max(pw_last) if pw_last else None,
            },
            f"{prefix}_players_within_3hw_change": {
                "median": median_of_list(pw_change),
                "min": min(pw_change) if pw_change else None,
                "max": max(pw_change) if pw_change else None,
            },
            f"{prefix}_median_player_distance_hw_first_1s": {
                "median": median_of_list(md_first),
                "min": min(md_first) if md_first else None,
                "max": max(md_first) if md_first else None,
            },
            f"{prefix}_median_player_distance_hw_last_1s": {
                "median": median_of_list(md_last),
                "min": min(md_last) if md_last else None,
                "max": max(md_last) if md_last else None,
            },
            f"{prefix}_median_player_distance_hw_change": {
                "median": median_of_list(md_change),
                "min": min(md_change) if md_change else None,
                "max": max(md_change) if md_change else None,
            },
        }

    out = {}
    out.update(stat_block(makes, "makes"))
    out.update(stat_block(misses, "misses"))
    return out


def write_summary_outputs(out_dir: Path, summary: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    """Write summary JSON and markdown."""
    json_path = out_dir / "summary_player_motion.json"
    md_path = out_dir / "summary_player_motion.md"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Player Motion Summary (140 build shots)",
        "",
        "| Metric | Makes (median, min, max) | Misses (median, min, max) |",
        "|--------|--------------------------|---------------------------|",
    ]

    metrics = [
        ("players_within_3hw_first_1s", "Players within 3hw (first 1s)"),
        ("players_within_3hw_last_1s", "Players within 3hw (last 1s)"),
        ("players_within_3hw_change", "Players within 3hw (change)"),
        ("median_player_distance_hw_first_1s", "Median player distance hw (first 1s)"),
        ("median_player_distance_hw_last_1s", "Median player distance hw (last 1s)"),
        ("median_player_distance_hw_change", "Median player distance hw (change)"),
    ]

    for key, label in metrics:
        mk = summary.get(f"makes_{key}", {})
        ms = summary.get(f"misses_{key}", {})
        mk_str = f"{mk.get('median')}, {mk.get('min')}, {mk.get('max')}"
        ms_str = f"{ms.get('median')}, {ms.get('min')}, {ms.get('max')}"
        lines.append(f"| {label} | {mk_str} | {ms_str} |")

    lines.append("")
    lines.append("**NO threshold, NO rule, NO call change** — this is measurement only.")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure player motion around shots (140 build shots)")
    parser.add_argument("--d1-results", type=Path, required=True, help="Path to d1_results.json")
    parser.add_argument("--tracks-dir", type=Path, required=True, help="Directory containing track JSON files")
    parser.add_argument("--bodd-weights", type=Path, default=None, help="Path to BODD model (default: auto-find)")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory (will refuse if exists and non-empty)")
    args = parser.parse_args()

    out_dir = args.out_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"Refusing to run: output directory {out_dir} exists and is non-empty")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load D1 results for anchor frames
    d1_map = load_d1_results(args.d1_results)

    # Load build shots (140 shots, Q1-Q3)
    shots, tracks_by_film, _ = load_build_shot_list(args.tracks_dir)
    if len(shots) != EXPECTED_BUILD:
        raise SystemExit(f"Expected {EXPECTED_BUILD} build shots, got {len(shots)}")

    # Load BODD model
    bodd_path = args.bodd_weights if args.bodd_weights else find_bodd_model()
    print(f"Loading BODD model from {bodd_path}")
    bodd_model = YOLO(str(bodd_path))
    print(f"BODD classes: {bodd_model.names}")

    all_results: List[Dict[str, Any]] = []

    for film in FILMS:
        film_name = film["name"]
        video_path = ROOT / film["video_rel"]
        if not video_path.exists():
            raise SystemExit(f"Missing video: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        fps_v = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = fps_v if fps_v > 1e-6 else FPS_FALLBACK
        cap.release()

        film_shots = [s for s in shots if s["film"] == film_name]
        print(f"Processing {film_name}: {len(film_shots)} shots at {fps:.2f} fps")

        for shot in film_shots:
            t = int(shot["t"])
            track = tracks_by_film[film_name][t]
            result = process_shot(shot, track, video_path, bodd_model, d1_map, fps)
            all_results.append(result)
            write_per_shot_outputs(out_dir, film_name, t, result)
            print(f"  {film_name} t={t}: done")

    # Summary
    summary = compute_summary_stats(all_results)
    write_summary_outputs(out_dir, summary, all_results)
    print(f"Wrote summary to {out_dir / 'summary_player_motion.json'}")
    print(f"Wrote summary to {out_dir / 'summary_player_motion.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())