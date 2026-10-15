"""See whether the stable free-throw windows can anchor both baskets.

Those windows are the only places the afternoon hoop stays inside 110 pixels.
This script measures their x and y, looks for a second stable window at the
other end, and counts offline ball boxes within 80 pixels of the measured
anchor during each of the 18 tags.

The make rule reads a ball path through one rim about 90 to 110 pixels wide.
A single forced coordinate is not that path. No track file is written, and
the make rule is not called.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
FULL_BOXES = Path(r"C:\Users\scott\AppData\Local\Temp\v6_full_game.jsonl")
HOOP = ROOT / "data/hoop_tracks/q4_blind_rerun_20261013.json"
FPS = 25.0
CLIP_START_S = 56 * 60 + 26.7
KIND = {"2PT", "3PT", "FT"}
RIM_PX = 110
NEAR_PX = 80
OTHER_END_PX = 400
WINDOW_S = 2.0
STABLE_TIMES = ("57:27.6", "57:40.8", "64:24.6")


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def load_boxes():
    boxes = {}
    with FULL_BOXES.open(encoding="utf-8") as handle:
        for line in handle:
            frame, found = json.loads(line)
            if found:
                boxes[frame] = [(item[0], item[1]) for item in found]
    return boxes


def window_samples(hoop, clip_frame):
    span = int(6 * FPS)
    local = [sample for sample in hoop if abs(sample["frame"] - clip_frame) <= span]
    if not local:
        local = [min(hoop, key=lambda sample: abs(sample["frame"] - clip_frame))]
    return local


def summarize(local):
    return {
        "x": statistics.median(sample["x"] for sample in local),
        "y": statistics.median(sample["y"] for sample in local),
        "x_spread": max(sample["x"] for sample in local) - min(sample["x"] for sample in local),
        "y_spread": max(sample["y"] for sample in local) - min(sample["y"] for sample in local),
    }


def main():
    hoop = json.loads(HOOP.read_text(encoding="utf-8"))["samples"]
    boxes = load_boxes()
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and (row.get("result") or "").lower() in ("make", "miss")
    ]

    print("stable windows (hoop spread at most 110px)")
    anchors = []
    for text in STABLE_TIMES:
        film_s = clock_ms(text) / 1000.0
        clip_frame = int(round(film_s * FPS)) - int(round(CLIP_START_S * FPS))
        info = summarize(window_samples(hoop, clip_frame))
        anchors.append(info)
        print(
            f"{text}  median ({info['x']:.0f}, {info['y']:.0f})  "
            f"x spread {info['x_spread']:.0f}  y spread {info['y_spread']:.0f}"
        )

    anchor_x = statistics.median(item["x"] for item in anchors)
    anchor_y = statistics.median(item["y"] for item in anchors)
    anchor_spread = max(item["x"] for item in anchors) - min(item["x"] for item in anchors)
    print(f"anchor from those three: ({anchor_x:.0f}, {anchor_y:.0f})  x spread among them {anchor_spread:.0f}")

    other = []
    for row in tags:
        if row["start"] in STABLE_TIMES:
            continue
        film_s = clock_ms(row["start"]) / 1000.0
        clip_frame = int(round(film_s * FPS)) - int(round(CLIP_START_S * FPS))
        info = summarize(window_samples(hoop, clip_frame))
        if info["x_spread"] <= RIM_PX and abs(info["x"] - anchor_x) >= OTHER_END_PX:
            other.append((row["start"], info))
    print(f"other tag windows stable and at least {OTHER_END_PX}px away: {len(other)}")

    half = int(WINDOW_S * FPS)
    print(f"{'Time':<10} {'Player':<16} {'Boxes near anchor':<18} {'Any box'}")
    near_tags = 0
    for row in tags:
        film_s = clock_ms(row["start"]) / 1000.0
        center = int(round(film_s * FPS))
        points = []
        for frame in range(center - half, center + half + 1):
            points.extend(boxes.get(frame, []))
        near = 0
        for x, y in points:
            if (x - anchor_x) ** 2 + (y - anchor_y) ** 2 <= NEAR_PX ** 2:
                near += 1
        if near:
            near_tags += 1
        print(f"{row['start']:<10} {row.get('player',''):<16} {near:<18} {len(points)}")
    print(f"tags {len(tags)}  with a ball box within {NEAR_PX}px of the anchor: {near_tags}")
    print(
        "q4_forced_tracks.json not written. "
        "The three stable windows are one basket, and a forced coordinate is not a ball path through that rim."
    )
    print("make rule: not called.")


if __name__ == "__main__":
    main()
