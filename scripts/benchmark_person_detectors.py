#!/usr/bin/env python3
"""Compare person-detector YOLO weights on film frames (measured bake-off).

Does NOT touch production ball_detector.pt / ball_confidence.
Default person setting remains unchanged unless Scott flips detector_model.

Examples:
  python scripts/benchmark_person_detectors.py --video data/videos/Q1_snippet.mp4
  python scripts/benchmark_person_detectors.py --video videos/Q1.mp4 --frames 40 --stride 30
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "benchmark" / "person_detector_bakeoff"
PERSON_CLASS = 0  # COCO person


def extract_frames(video: Path, out_dir: Path, frames: int, stride: int) -> list[Path]:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {video}")
    saved: list[Path] = []
    idx = 0
    kept = 0
    while kept < frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            path = out_dir / f"frame_{kept:04d}.jpg"
            cv2.imwrite(str(path), frame)
            saved.append(path)
            kept += 1
        idx += 1
    cap.release()
    if not saved:
        raise SystemExit("No frames extracted")
    return saved


def run_model(weights: str, frame_paths: list[Path], conf: float) -> dict:
    from ultralytics import YOLO

    model = YOLO(weights)
    t0 = time.perf_counter()
    total_people = 0
    confs: list[float] = []
    for path in frame_paths:
        result = model.predict(source=str(path), conf=conf, verbose=False, classes=[PERSON_CLASS])[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue
        total_people += len(boxes)
        confs.extend(float(x) for x in boxes.conf.tolist())
    elapsed = time.perf_counter() - t0
    n = len(frame_paths)
    return {
        "weights": weights,
        "frames": n,
        "person_detections": total_people,
        "mean_people_per_frame": round(total_people / n, 3) if n else 0.0,
        "mean_confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
        "seconds": round(elapsed, 3),
        "fps": round(n / elapsed, 3) if elapsed else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, default=ROOT / "data" / "videos" / "Q1_snippet.mp4")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--stride", type=int, default=45)
    ap.add_argument("--conf", type=float, default=0.5)
    ap.add_argument(
        "--models",
        nargs="+",
        default=["yolov8n.pt", "yolo11n.pt", "yolov8s.pt", "yolo11s.pt"],
    )
    args = ap.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Video not found: {args.video}")

    frames_dir = OUT_DIR / "frames"
    frame_paths = extract_frames(args.video, frames_dir, args.frames, args.stride)
    rows = []
    for weights in args.models:
        print(f"Running {weights} on {len(frame_paths)} frames...")
        row = run_model(weights, frame_paths, args.conf)
        rows.append(row)
        print(json.dumps(row))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_path = OUT_DIR / "summary.json"
    json_path.write_text(json.dumps({"video": str(args.video), "conf": args.conf, "rows": rows}, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
