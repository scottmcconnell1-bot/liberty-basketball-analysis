"""Q4 blind test with fall-through guard (opt-in).

Reads rebuilt Q4 tracks (from q4_rebuild_tracks.py), runs candidate extraction
exactly like step_extract, then runs both the v6 plain rule (old_pred) and the
new rule with optional fall_through guard (new_pred). Truth is track["result"].
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import from pixel_miss.measure_net_moved (absolute import via sys.path)
from pixel_miss.measure_net_moved import FILMS, load_tracks  # noqa: E402
# Import from keep_ball_detections (same directory)
import keep_ball_detections as kbd  # noqa: E402

# Constants from keep_ball_detections
BALL_CLASS_NAME = kbd.BALL_CLASS_NAME
BALL_CONFIDENCE = kbd.BALL_CONFIDENCE
CANDIDATE_CAP = kbd.CANDIDATE_CAP
CROP_ABOVE = kbd.CROP_ABOVE
CROP_BELOW = kbd.CROP_BELOW
CROP_LEFT_RIGHT = kbd.CROP_LEFT_RIGHT
PREDICT_IMGSZ = kbd.PREDICT_IMGSZ
ZONE_ABOVE_HOOP_WIDTHS = kbd.ZONE_ABOVE_HOOP_WIDTHS
ZONE_BELOW_PX = kbd.ZONE_BELOW_PX
ZONE_HOOP_WIDTHS_H = kbd.ZONE_HOOP_WIDTHS_H
detect_on_crop = kbd.detect_on_crop
frames_to_extract = kbd.frames_to_extract
in_near_hoop_zone = kbd.in_near_hoop_zone
peak_from_track = kbd.peak_from_track
run_arc_and_rule_on_shot = kbd.run_arc_and_rule_on_shot
zone_filter_candidates = kbd.zone_filter_candidates

EXPECTED_ADRIAN_VIDEO = "uploads/nfhs_gam0a66d85e12.mp4"


def find_adrian_film() -> Dict[str, Any]:
    for film in FILMS:
        if film["name"] == "adrian":
            return film
    raise SystemExit("ERROR: 'adrian' film not found in FILMS")


def crop_bounds(
    hoop_x: float, hoop_y: float, frame_w: int, frame_h: int
) -> tuple[int, int, int, int]:
    x0 = int(max(0, hoop_x - CROP_LEFT_RIGHT))
    y0 = int(max(0, hoop_y - CROP_ABOVE))
    x1 = int(min(frame_w, hoop_x + CROP_LEFT_RIGHT))
    y1 = int(min(frame_h, hoop_y + CROP_BELOW))
    return x0, y0, x1, y1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Q4 blind test with fall-through guard")
    parser.add_argument("--q4-tracks", type=Path, required=True, help="v6_tracks_q4.json from q4_rebuild_tracks.py")
    parser.add_argument("--weights", type=Path, required=True, help="v6 ball model weights (.pt)")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory (will create q4_results.json and q4_report.md)")
    parser.add_argument("--fall-through-guard", action="store_true", default=False)
    args = parser.parse_args(argv)

    tracks_path = Path(args.q4_tracks)
    if not tracks_path.exists():
        raise SystemExit(f"ERROR: q4 tracks file not found: {tracks_path}")

    weights_path = Path(args.weights)
    if not weights_path.exists():
        raise SystemExit(f"ERROR: weights file not found: {weights_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_json = out_dir / "q4_results.json"
    report_md = out_dir / "q4_report.md"
    if results_json.exists() or report_md.exists():
        raise SystemExit(f"ERROR: output files already exist: {results_json}, {report_md}")

    # Verify Adrian video
    adrian_film = find_adrian_film()
    video_rel = adrian_film["video_rel"]
    if video_rel != EXPECTED_ADRIAN_VIDEO:
        raise SystemExit(f"ERROR: Adrian video_rel mismatch: expected {EXPECTED_ADRIAN_VIDEO}, got {video_rel}")
    video_path = ROOT / video_rel
    if not video_path.exists():
        raise SystemExit(f"ERROR: video not found: {video_path}")

    print(f"Loading v6 model from {weights_path}")
    model = YOLO(str(weights_path))
    print(f"Model classes: {model.names}")

    tracks = load_tracks(tracks_path)
    print(f"Loaded {len(tracks)} tracks from {tracks_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"ERROR: cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)

    # Separate tracks with/without hoop
    tracks_with_hoop = [(t, tr) for t, tr in tracks.items() if tr.get("hoop") is not None]
    tracks_no_hoop = [(t, tr) for t, tr in tracks.items() if tr.get("hoop") is None]
    print(f"Tracks with hoop: {len(tracks_with_hoop)}; without hoop (scored as miss): {len(tracks_no_hoop)}")

    per_shot: List[Dict[str, Any]] = []

    # Process tracks with hoop
    for t_ms, track in sorted(tracks_with_hoop):
        hoop = track["hoop"]
        hoop_x, hoop_y, hoop_w, hoop_area = float(hoop[0]), float(hoop[1]), float(hoop[2]), float(hoop[3])
        # Same as step_extract: the answer never reaches frame picking.
        track_no_truth = {k: v for k, v in track.items() if k != "result"}
        anchor_frame, _u, _o, anchor_reason = peak_from_track(track_no_truth, t_ms, fps)
        tag_frame = int(round(t_ms / 1000.0 * fps))

        # Extract candidates (reuse step_extract logic)
        frame_list = frames_to_extract(track_no_truth, t_ms, fps, anchor_frame)
        needed = set(frame_list)
        first, last = min(frame_list), max(frame_list)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(max(0, first)))

        cands_by_frame: Dict[int, List[Dict[str, Any]]] = {}
        for abs_fr in range(max(0, first), last + 1):
            ok, frame = cap.read()
            if abs_fr not in needed:
                continue
            if not ok or frame is None:
                cands_by_frame[abs_fr] = []
                continue
            raw_dets = detect_on_crop(model, frame, hoop_x, hoop_y)
            zoned = zone_filter_candidates(raw_dets, hoop_x, hoop_y, hoop_w)
            cands_by_frame[abs_fr] = [
                {
                    "x": float(d["x_center"]),
                    "y": float(d["y_center"]),
                    "confidence": float(d["confidence"]),
                    "x1": float(d["x1"]),
                    "y1": float(d["y1"]),
                    "x2": float(d["x2"]),
                    "y2": float(d["y2"]),
                }
                for d in zoned
            ]

        # Run both rules
        outcome = run_arc_and_rule_on_shot(
            track, t_ms=t_ms, fps=fps, cands_by_frame=cands_by_frame, fall_through=args.fall_through_guard
        )

        truth = track["result"] == "make"
        per_shot.append({
            "t": t_ms,
            "start": track.get("start"),
            "truth": "make" if truth else "miss",
            "old_pred": "make" if outcome["old_pred"] else "miss",
            "old_reason": outcome["old_reason"],
            "new_pred": "make" if outcome["new_pred"] else "miss",
            "new_reason": outcome["new_reason"],
        })

    # Tracks without hoop: scored as miss calls (truth from track["result"])
    for t_ms, track in sorted(tracks_no_hoop):
        truth = track["result"] == "make"
        per_shot.append({
            "t": t_ms,
            "start": track.get("start"),
            "truth": "make" if truth else "miss",
            "old_pred": "miss",
            "old_reason": "no_hoop",
            "new_pred": "miss",
            "new_reason": "no_hoop",
        })

    cap.release()

    # Summaries
    def summarize(rows: List[Dict[str, Any]], pred_key: str) -> Dict[str, int]:
        makes_right = 0
        makes_total = 0
        misses_called_makes = 0
        for r in rows:
            gt = r["truth"] == "make"
            pred = r[pred_key] == "make"
            if gt:
                makes_total += 1
                if pred:
                    makes_right += 1
            elif pred:
                misses_called_makes += 1
        return {"makes_right": makes_right, "makes_total": makes_total, "misses_called_makes": misses_called_makes}

    old_summary = summarize(per_shot, "old_pred")
    new_summary = summarize(per_shot, "new_pred")

    # Write JSON
    payload = {
        "fall_through_guard": args.fall_through_guard,
        "per_shot": per_shot,
        "summary": {
            "v6_plain": old_summary,
            "with_guard": new_summary,
        },
        "pass": new_summary["misses_called_makes"] == 0 and new_summary["makes_right"] >= old_summary["makes_right"],
    }
    results_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {results_json}")

    # Write MD report
    lines = [
        "# Q4 Blind Test — Fall-Through Guard",
        "",
        f"Fall-through guard: {'ON' if args.fall_through_guard else 'OFF'}",
        f"Tracks file: {tracks_path}",
        f"Weights: {weights_path}",
        "",
        "## Per-Shot Results",
        "",
        "| t | start | truth | v6 plain | v6 reason | new | new reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in per_shot:
        lines.append(f"| {r['t']} | {r['start']} | {r['truth']} | {r['old_pred']} | {r['old_reason']} | {r['new_pred']} | {r['new_reason']} |")

    lines += [
        "",
        "## Summary",
        "",
        f"### v6 plain (old_pred)",
        f"- makes_right: {old_summary['makes_right']} / {old_summary['makes_total']}",
        f"- misses_called_makes: {old_summary['misses_called_makes']}",
        "",
        f"### With guard (new_pred)",
        f"- makes_right: {new_summary['makes_right']} / {new_summary['makes_total']}",
        f"- misses_called_makes: {new_summary['misses_called_makes']}",
        "",
        f"### Verdict: {'PASS' if payload['pass'] else 'FAIL'}",
        "",
        "PASS condition: new misses_called_makes == 0 AND new makes_right >= v6 plain makes_right",
    ]
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_md}")

    print(f"\n=== Q4 Blind Test ===")
    print(f"v6 plain: makes_right={old_summary['makes_right']}/{old_summary['makes_total']}, misses_called_makes={old_summary['misses_called_makes']}")
    print(f"with guard: makes_right={new_summary['makes_right']}/{new_summary['makes_total']}, misses_called_makes={new_summary['misses_called_makes']}")
    print(f"Result: {'PASS' if payload['pass'] else 'FAIL'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())