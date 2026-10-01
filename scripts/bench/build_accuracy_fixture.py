#!/usr/bin/env python3
"""Freeze the real analyzer's detections for a clip into an accuracy-benchmark fixture.

CI cannot run YOLO (no GPU, no CV stack, no LFS), so the benchmark scores the event
generator against frozen detections. This script makes those detections: it runs
ai_analyzer.run_ai_analysis on a video in a throwaway database and writes
<out>/detections.csv.gz plus <out>/meta.json.

Run it in the Docker image (needs OpenCV + ultralytics + the real ball model):
  docker run --rm -v $PWD:/app -v <lfs dir>:/lfs:ro -v <out>:/out -w /app \\
    -v <lfs dir>/ball_detector.pt:/app/models/ball_detector.pt:ro liberty-analysis:cpu \\
    python scripts/bench/build_accuracy_fixture.py --video /lfs/Q1_full.mp4 --out /out
Then copy detections.csv.gz / meta.json into benchmarks/accuracy/<name>/.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

COLUMNS = ["frame_number", "timestamp_ms", "object_class", "confidence",
           "x_center", "y_center", "width", "height", "tracker_id"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--key", default="bench_clip", help="analysis key used inside the temp DB")
    ap.add_argument("--commit", help="analyzer commit to record (the image has no git)")
    args = ap.parse_args(argv)

    work = Path(tempfile.mkdtemp(prefix="accuracy_fixture_"))
    db_path = work / "fixture.db"
    os.environ["LIBERTY_DATABASE"] = str(db_path)
    os.environ["LIBERTY_UPLOAD_FOLDER"] = str(work / "uploads")

    import app as app_module

    with app_module.app.app_context():
        app_module.init_db()
    conn = sqlite3.connect(db_path)
    # EasyOCR is not in the image; keep the run deterministic and say so in meta.json.
    conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('ai.jersey_ocr_enabled', '0')")
    conn.commit()
    conn.close()

    import ai_analyzer
    from settings_store import AI_DEFAULTS, load_all_settings

    started = time.time()
    ai_analyzer.run_ai_analysis(str(db_path), str(args.video), args.key)
    elapsed = time.time() - started

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM detections WHERE game_id = ? ORDER BY frame_number, id",
        (args.key,),
    ).fetchall()
    ai = load_all_settings({}, {}, AI_DEFAULTS, db_path=str(db_path))["ai"]
    conn.close()

    args.out.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out / "detections.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    try:  # the Docker image has no git; pass --commit from the host instead
        git_rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.strip() or None
    except (FileNotFoundError, OSError):
        git_rev = None
    git_rev = args.commit or git_rev
    meta = {
        "video": args.video.name,
        "video_sha256": _sha256(args.video),
        "detections": len(rows),
        "frames": (rows[-1][0] + 1) if rows else 0,
        "analyzer_commit": git_rev,
        "analyzer_seconds": round(elapsed, 1),
        "settings": {k: ai.get(k) for k in (
            "detector_model", "ball_detector_model", "ball_class_id", "ball_confidence",
            "person_confidence", "detection_stride", "tracker_enabled", "jersey_ocr_enabled")},
    }
    (args.out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
