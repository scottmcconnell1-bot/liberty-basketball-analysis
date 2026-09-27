"""Time the real ai_analyzer frame loop under different settings (run inside Docker).

Needs the real (LFS) clip and ball model, mounted at /lfs:
  docker run --rm -v $PWD/scripts/bench:/bench:ro -v <lfs dir>:/lfs:ro -v <work dir>:/work \
    -v <lfs dir>/ball_detector.pt:/app/models/ball_detector.pt:ro liberty-analysis:cpu \
    python /bench/bench_analysis_loop.py --name base --pad 3000000 --seconds 20 [--index] [--ocr] [--no-tracker] [--profile]
--pad pre-loads N detection rows for another game (the live table is tens of millions).
Prints one JSON line with the loop fps and, with --profile, the top cumulative functions.
Results for 2026-09-27: docs/validation/analysis_speed.md.
"""
import argparse
import cProfile
import json
import os
import pstats
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, "/app")

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--pad", type=int, default=0, help="rows of other games' detections to pre-load")
ap.add_argument("--seconds", type=int, default=20)
ap.add_argument("--index", action="store_true")
ap.add_argument("--ocr", action="store_true")
ap.add_argument("--no-tracker", action="store_true")
ap.add_argument("--stride", type=int, default=1)
ap.add_argument("--profile", action="store_true")
args = ap.parse_args()

work = f"/work/{args.name}"
os.makedirs(work, exist_ok=True)
db_path = f"{work}/bench.db"
if os.path.exists(db_path):
    os.remove(db_path)
os.environ["LIBERTY_DATABASE"] = db_path
os.environ["LIBERTY_UPLOAD_FOLDER"] = f"{work}/uploads"

clip = f"/work/clip_{args.seconds}s.mp4"
if not os.path.exists(clip):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", "/lfs/Q1_snippet.mp4",
                    "-t", str(args.seconds), "-c", "copy", clip], check=True)

import app as app_module  # noqa: E402

with app_module.app.app_context():
    app_module.init_db()

conn = sqlite3.connect(db_path)
if args.pad:
    row = ("other_game", None, 0, 0, "person", 0.9, 100, 100, 20, 40, None, None, None)
    batch = 50_000
    for start in range(0, args.pad, batch):
        n = min(batch, args.pad - start)
        conn.executemany(
            """INSERT INTO detections (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                   confidence, x_center, y_center, width, height, tracker_id, jersey_read, jersey_confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(row[0], row[1], start + i, row[3]) + row[4:] for i in range(n)],
        )
    conn.commit()
if args.index:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_game_frame ON detections(game_id, frame_number)")
    conn.commit()
settings = {
    "ai.inference_device": "cpu",
    "ai.jersey_ocr_enabled": "1" if args.ocr else "0",
    "ai.tracker_enabled": "0" if args.no_tracker else "1",
    "ai.detection_stride": str(args.stride),
    "ai.frame_stride": str(args.stride),
}
for k, v in settings.items():
    conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (k, v))
conn.commit()
conn.close()

import ai_analyzer  # noqa: E402

# Time only the frame loop: first and last cap.read() calls.
marks = {"first": None, "last": None, "frames": 0}
_Real = ai_analyzer.cv2.VideoCapture


class TimedCapture(_Real):
    def read(self, *a, **kw):
        ret, frame = super().read(*a, **kw)
        now = time.perf_counter()
        if marks["first"] is None:
            marks["first"] = now
        if ret:
            marks["last"] = now
            marks["frames"] += 1
        return ret, frame


ai_analyzer.cv2.VideoCapture = TimedCapture
prof = cProfile.Profile() if args.profile else None
t0 = time.perf_counter()
if prof:
    prof.enable()
try:
    ai_analyzer.run_ai_analysis(db_path, clip, "bench_game")
finally:
    if prof:
        prof.disable()
total = time.perf_counter() - t0
loop = (marks["last"] or 0) - (marks["first"] or 0)
out = {
    "name": args.name, "pad": args.pad, "index": args.index, "ocr": args.ocr,
    "tracker": not args.no_tracker, "stride": args.stride, "frames": marks["frames"],
    "loop_s": round(loop, 1), "loop_fps": round(marks["frames"] / loop, 2) if loop else None,
    "total_s": round(total, 1),
}
if prof:
    stats = pstats.Stats(prof)
    rows = sorted(stats.stats.items(), key=lambda kv: kv[1][3], reverse=True)
    top = []
    for (file, line, fn), (cc, nc, tt, ct, _) in rows[:40]:
        top.append({"fn": f"{os.path.basename(file)}:{line}:{fn}", "cum_s": round(ct, 2), "self_s": round(tt, 2), "calls": nc})
    out["top"] = top
print("BENCH " + json.dumps(out))
