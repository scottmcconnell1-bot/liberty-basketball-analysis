"""Collect hoop and ball boxes for the 18 fourth-quarter tags.

This follows collect_bodd.py and the track builder in score_v6_make.py.
It appends rows to bodd_shots.json in that file's existing list layout.
It does not import score_v6_make.py, because that file rewrites
v6_tracks.json when it is imported. The 111-row track file is left as it is.
The 18 new tracks go to v6_tracks_q4.json.

is_make is the older half/drop/gap test from score_v6_make.py
(half 0.55, drop 180, gap 8). It is not run_saved_v6_rule.
"""
import json
import shutil
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
VIDEO = ROOT / "uploads/nfhs_gam0a66d85e12.mp4"
BODD = Path(r"C:\Users\scott\AppData\Local\Temp\BODD_yolov8n_0001.pt")
V6 = Path(r"C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt")
SHOTS = Path(r"C:\Users\scott\AppData\Local\Temp\bodd_shots.json")
BACKUP = Path(r"C:\Users\scott\AppData\Local\Temp\bodd_shots_before_q4_20261013.json")
Q4_TRACKS = Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks_q4.json")
KIND = {"2PT", "3PT", "FT"}
Q4_MS = int(round((55 * 60 + 17.1) * 1000))


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def groups(samples):
    hoops = [h for s in samples for h in s["hoops"]]
    buckets = {}
    for h in hoops:
        buckets.setdefault(int(h["x"] // 80), []).append(h)
    out = []
    for group in buckets.values():
        if len(group) < 4:
            continue
        out.append(tuple(sorted(h[k] for h in group)[len(group) // 2] for k in ("x", "y", "w", "h")))
    return out


def is_make(ball, hoop, half, drop_px, gap):
    hx, hy, hw, hh = hoop
    above = None
    cross_i = None
    for i, (f, x, y) in enumerate(ball):
        if abs(x - hx) > hw * 2.2:
            continue
        if y < hy - 6:
            above = (x, y, i)
        elif above is not None and y > hy + 10 and abs(x - hx) <= hw * half:
            if above[2] < i and i - above[2] <= gap:
                cross_i = i
                break
    if cross_i is None:
        return False
    fell = 0.0
    for f, x, y in ball[cross_i:]:
        if abs(x - hx) < hw * 0.9 and y < hy + 20 and fell > 30:
            return False
        if y - hy > fell and abs(x - hx) < hw * 1.3:
            fell = y - hy
        if fell >= drop_px:
            return True
    return False


def collect_samples(model, cap, start):
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    for _ in range(80):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    preds = model.predict(frames, conf=0.12, imgsz=960, verbose=False)
    samples = []
    for offset, pred in enumerate(preds):
        balls, hoops = [], []
        if pred.boxes is None:
            continue
        for box in pred.boxes:
            name = model.names[int(box.cls[0])]
            if name not in ("basketball", "hoop"):
                continue
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            item = {
                "x": round((x1 + x2) / 2, 1),
                "y": round((y1 + y2) / 2, 1),
                "w": round(x2 - x1, 1),
                "h": round(y2 - y1, 1),
                "c": round(float(box.conf[0]), 3),
            }
            if name == "basketball":
                balls.append(item)
            else:
                hoops.append(item)
        if balls or hoops:
            samples.append({"f": offset, "balls": balls, "hoops": hoops})
    return samples


def v6_ball(model, cap, fps, row, hoop):
    hx, hy = hoop[0], hoop[1]
    tag = int(round(row["t"] / 1000.0 * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, tag)
    prev = None
    series = []
    for f in range(80):
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        x0 = int(max(0, hx - 260))
        y0 = int(max(0, hy - 200))
        x1 = int(min(w, hx + 260))
        y1 = int(min(h, hy + 240))
        pred = model.predict(frame[y0:y1, x0:x1], conf=0.28, imgsz=640, verbose=False)[0]
        if pred.boxes is None or len(pred.boxes) == 0:
            prev = None
            continue
        picks = []
        for box in pred.boxes:
            a, b, c, d = [float(v) for v in box.xyxy[0]]
            cx, cy = x0 + (a + c) / 2, y0 + (b + d) / 2
            if abs(cx - hx) > 220 or abs(cy - hy) > 220:
                continue
            dist = (cx - hx) ** 2 + (cy - hy) ** 2
            if prev is not None:
                dist += ((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) * 0.35
            picks.append((dist, cx, cy))
        if not picks:
            prev = None
            continue
        picks.sort()
        _d, cx, cy = picks[0]
        prev = (cx, cy)
        series.append((f, cx, cy))
    return series


def main():
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = []
    for row in data["rows"]:
        if row.get("quarter") != "Q4" or row.get("eventtype") not in KIND:
            continue
        result = str(row.get("result") or "")
        if result not in ("Make", "Miss"):
            continue
        ms = clock_ms(row["start"])
        if ms <= Q4_MS:
            continue
        tags.append(
            {
                "t": ms,
                "result": "make" if result == "Make" else "miss",
                "start": row["start"],
                "player": row.get("player") or "",
            }
        )
    print(f"tags {len(tags)}", flush=True)

    bodd_model = YOLO(str(BODD))
    print("bodd classes", bodd_model.names, flush=True)
    if "hoop" not in bodd_model.names.values():
        raise SystemExit("BODD model has no hoop class")

    cap = cv2.VideoCapture(str(VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    new_rows = []
    for index, tag in enumerate(tags):
        start = int(round(tag["t"] / 1000.0 * fps))
        samples = collect_samples(bodd_model, cap, start)
        hoop_n = sum(len(s["hoops"]) for s in samples)
        ball_n = sum(len(s["balls"]) for s in samples)
        print(f"bodd {tag['start']} hoop boxes {hoop_n} ball boxes {ball_n}", flush=True)
        new_rows.append({"t": tag["t"], "result": tag["result"], "samples": samples, "start": tag["start"], "player": tag["player"]})
        del index
    cap.release()

    existing = json.loads(SHOTS.read_text(encoding="utf-8"))
    if not isinstance(existing, list):
        raise SystemExit("bodd_shots.json is not a list; refused to rewrite it")
    have = {int(row["t"]) for row in existing}
    add = [row for row in new_rows if row["t"] not in have]
    if not BACKUP.exists():
        shutil.copyfile(SHOTS, BACKUP)
    stored = []
    for row in add:
        stored.append({"t": row["t"], "result": row["result"], "samples": row["samples"]})
    SHOTS.write_text(json.dumps(existing + stored), encoding="utf-8")
    print(f"bodd_shots.json {len(existing)} plus {len(stored)}", flush=True)

    v6_model = YOLO(str(V6))
    cap = cv2.VideoCapture(str(VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    tracks = []
    print(f"{'Time':<10} {'Player':<16} {'Tag':<6} {'Hoop':<28} {'Ball':<6} {'is_make'}")
    for row in new_rows:
        cands = groups(row["samples"])
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
        series = v6_ball(v6_model, cap, fps, row, hoop) if hoop is not None else []
        made = is_make(series, hoop, 0.55, 180, 8) if series and hoop is not None else None
        hoop_text = "none" if hoop is None else f"{hoop[0]:.0f},{hoop[1]:.0f} {hoop[2]:.0f}x{hoop[3]:.0f}"
        if hoop is None:
            call = "no hoop"
        elif not series:
            call = "no ball"
        else:
            call = "make" if made else "miss"
        print(
            f"{row['start']:<10} {row['player']:<16} {row['result']:<6} {hoop_text:<28} {len(series):<6} {call}",
            flush=True,
        )
        tracks.append(
            {
                "t": row["t"],
                "result": row["result"],
                "hoop": list(hoop) if hoop is not None else None,
                "ball": series,
                "bodd": bodd,
                "is_make": call,
            }
        )
    cap.release()
    Q4_TRACKS.write_text(json.dumps(tracks), encoding="utf-8")
    print(f"wrote {Q4_TRACKS}", flush=True)
    print("v6_tracks.json was not changed")


if __name__ == "__main__":
    main()
