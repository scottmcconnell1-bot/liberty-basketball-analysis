"""Rebuild the lost Adrian Q4 v6 track file (Scott 2026-11-02: "Rebuild the Lost Adrian Q4 Ball Tracks").

Runs the existing October builder collect_q4_bodd.py (repo root) unchanged: same tags filter,
same BODD hoop/ball sampling, same v6 ball series. Only difference: it does NOT append to
bodd_shots.json (that Temp file no longer exists) and writes the track file to an output folder.
No core file, no models/ball_detector.pt, ball_confidence 0.28 unchanged.

Usage (GPU python): python -I q4_rebuild_tracks.py <out_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from ultralytics import YOLO  # noqa: E402

import collect_q4_bodd as q4  # noqa: E402


def main(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "v6_tracks_q4.json"
    if out.exists():
        raise SystemExit(f"refused: {out} already exists")

    data = json.loads(q4.TAGS.read_text(encoding="utf-8"))
    tags = []
    for row in data["rows"]:
        if row.get("quarter") != "Q4" or row.get("eventtype") not in q4.KIND:
            continue
        result = str(row.get("result") or "")
        if result not in ("Make", "Miss"):
            continue
        ms = q4.clock_ms(row["start"])
        if ms <= q4.Q4_MS:
            continue
        tags.append({"t": ms, "result": "make" if result == "Make" else "miss",
                     "start": row["start"], "player": row.get("player") or ""})
    print(f"tags {len(tags)}", flush=True)
    if len(tags) != 18:
        raise SystemExit(f"expected 18 Q4 shot tags, got {len(tags)}")

    bodd_model = YOLO(str(q4.BODD))
    cap = cv2.VideoCapture(str(q4.VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    rows = []
    for tag in tags:
        start = int(round(tag["t"] / 1000.0 * fps))
        samples = q4.collect_samples(bodd_model, cap, start)
        print(f"bodd {tag['start']} hoops {sum(len(s['hoops']) for s in samples)} "
              f"balls {sum(len(s['balls']) for s in samples)}", flush=True)
        rows.append({**tag, "samples": samples})
    cap.release()

    v6_model = YOLO(str(q4.V6))
    cap = cv2.VideoCapture(str(q4.VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    tracks = []
    for row in rows:
        cands = q4.groups(row["samples"])
        bodd = []
        for sample in row["samples"]:
            if not sample["balls"]:
                continue
            ball = max(sample["balls"], key=lambda item: item["c"])
            if ball["c"] >= 0.28:
                bodd.append((sample["f"], ball["x"], ball["y"]))
        hoop = None
        if cands and bodd:
            hoop = min(cands, key=lambda h: min((x - h[0]) ** 2 + (y - h[1]) ** 2 for _f, x, y in bodd))
        series = q4.v6_ball(v6_model, cap, fps, row, hoop) if hoop is not None else []
        print(f"{row['start']} {row['result']} hoop={'none' if hoop is None else [round(v) for v in hoop]} "
              f"ball_pts={len(series)}", flush=True)
        tracks.append({"t": row["t"], "result": row["result"], "start": row["start"],
                       "hoop": list(hoop) if hoop is not None else None, "ball": series, "bodd": bodd})
    cap.release()
    out.write_text(json.dumps(tracks), encoding="utf-8")
    print(f"wrote {out} ({len(tracks)} tracks; {sum(1 for t in tracks if t['hoop'] is None)} without hoop)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
