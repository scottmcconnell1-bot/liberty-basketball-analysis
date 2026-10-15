"""See whether a median hoop can turn Q4 boxes into a make-rule track.

The afternoon hoop is one CV sample every two seconds. This script takes
the median of five neighboring samples, then keeps ball boxes that sit near
that median during the four seconds around each of the 18 tags.

A saved make-rule track is a ball path through one rim about 90 to 110
pixels wide. If the median series still jumps farther than that, no track
file is written and the make rule is not called.
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
ROLL = 5
RIM_PX = 110
NEAR_PX = 80
WIDE_PX = 180
JUMP_PX = 60
WINDOW_S = 2.0


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def max_step(samples):
    if len(samples) < 2:
        return 0.0
    return max(abs(b["x"] - a["x"]) for a, b in zip(samples, samples[1:]))


def rolling_median(samples, k):
    half = k // 2
    out = []
    for i, sample in enumerate(samples):
        window = samples[max(0, i - half) : i + half + 1]
        out.append(
            {
                "x": statistics.median(item["x"] for item in window),
                "y": statistics.median(item["y"] for item in window),
                "frame": sample["frame"],
                "timestamp_ms": sample["timestamp_ms"],
            }
        )
    return out


def load_boxes():
    boxes = {}
    with FULL_BOXES.open(encoding="utf-8") as handle:
        for line in handle:
            frame, found = json.loads(line)
            if found:
                boxes[frame] = [(item[0], item[1]) for item in found]
    return boxes


def near_count(points, hoop_x, hoop_y, radius):
    kept = []
    r2 = radius * radius
    for x, y in points:
        dx = x - hoop_x
        dy = y - hoop_y
        if dx * dx + dy * dy <= r2:
            kept.append((x, y))
    return kept


def continuous(points, hoop_x, hoop_y):
    """Boxes near the median that also stay within one jump of the previous box."""
    kept = []
    for x, y in near_count(points, hoop_x, hoop_y, NEAR_PX):
        if kept:
            px, py = kept[-1]
            if (x - px) ** 2 + (y - py) ** 2 > JUMP_PX * JUMP_PX:
                continue
        kept.append((x, y))
    return kept


def main():
    hoop = json.loads(HOOP.read_text(encoding="utf-8"))["samples"]
    hoop.sort(key=lambda sample: sample["timestamp_ms"])
    smoothed = rolling_median(hoop, ROLL)
    median_x = statistics.median(sample["x"] for sample in hoop)
    median_y = statistics.median(sample["y"] for sample in hoop)
    on_fixed = sum(
        1
        for sample in hoop
        if (sample["x"] - median_x) ** 2 + (sample["y"] - median_y) ** 2 <= NEAR_PX ** 2
    )
    print(f"afternoon hoop samples {len(hoop)}")
    print(f"raw x step {max_step(hoop):.0f}px")
    print(
        f"rolling median of {ROLL} samples: x step {max_step(smoothed):.0f}px  "
        f"x {min(s['x'] for s in smoothed):.0f}-{max(s['x'] for s in smoothed):.0f}"
    )
    print(
        f"one median for the quarter: ({median_x:.0f}, {median_y:.0f})  "
        f"samples within {NEAR_PX}px of it: {on_fixed} of {len(hoop)}"
    )

    boxes = load_boxes()
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and (row.get("result") or "").lower() in ("make", "miss")
    ]
    half = int(WINDOW_S * FPS)
    print(
        f"{'Time':<10} {'Median x':<9} {'Spread':<8} "
        f"{'Within 80':<11} {'Within 180':<12} {'Linked':<7} {'Any box'}"
    )
    stable_shots = 0
    for row in tags:
        film_s = clock_ms(row["start"]) / 1000.0
        center = int(round(film_s * FPS))
        clip_frame = center - int(round(CLIP_START_S * FPS))
        local = [
            sample
            for sample in hoop
            if abs(sample["frame"] - clip_frame) <= int(6 * FPS)
        ]
        if not local:
            local = [min(hoop, key=lambda sample: abs(sample["frame"] - clip_frame))]
        hx = statistics.median(sample["x"] for sample in local)
        hy = statistics.median(sample["y"] for sample in local)
        spread = max(sample["x"] for sample in local) - min(sample["x"] for sample in local)
        if spread <= RIM_PX:
            stable_shots += 1
        points = []
        for frame in range(center - half, center + half + 1):
            points.extend(boxes.get(frame, []))
        linked = continuous(points, hx, hy)
        print(
            f"{row['start']:<10} {hx:<9.0f} {spread:<8.0f} "
            f"{len(near_count(points, hx, hy, NEAR_PX)):<11} "
            f"{len(near_count(points, hx, hy, WIDE_PX)):<12} "
            f"{len(linked):<7} {len(points)}"
        )
    print(f"tags {len(tags)}  local median stays inside {RIM_PX}px: {stable_shots}")
    print(
        "candidate track file not written. "
        "The median hoop still moves farther than one rim, so these boxes are not a saved track."
    )
    print("make rule: not called.")


if __name__ == "__main__":
    main()
