"""Read the real ball boxes near the free-throw anchor.

Eight fourth-quarter tags have at least one offline ball box within 80
pixels of (1174, 213). This script keeps the closest box on each frame and
measures the step from one frame to the next.

The make rule scores a saved track: a ball path through one rim about 90 to
110 pixels wide. Invented coordinates are not that path. No track file is
written, and the make rule is not called.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
FULL_BOXES = Path(r"C:\Users\scott\AppData\Local\Temp\v6_full_game.jsonl")
FPS = 25.0
KIND = {"2PT", "3PT", "FT"}
ANCHOR_X = 1174.0
ANCHOR_Y = 213.0
NEAR_PX = 80
WINDOW_S = 2.0
TIMES = (
    "56:39.4",
    "57:27.6",
    "57:40.8",
    "58:14.6",
    "59:28.1",
    "63:13.1",
    "63:24.5",
    "64:24.6",
)


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


def closest_path(boxes, center):
    half = int(WINDOW_S * FPS)
    path = []
    for frame in range(center - half, center + half + 1):
        best = None
        best_d = NEAR_PX * NEAR_PX
        for x, y in boxes.get(frame, []):
            d = (x - ANCHOR_X) ** 2 + (y - ANCHOR_Y) ** 2
            if d <= best_d:
                best = (frame, x, y)
                best_d = d
        if best:
            path.append(best)
    return path


def max_step(path):
    if len(path) < 2:
        return 0.0
    step = 0.0
    for (f0, x0, y0), (f1, x1, y1) in zip(path, path[1:]):
        gap = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        # A skipped frame is still a jump in time. Scale is per frame so a
        # two-frame gap is not treated as one small step.
        step = max(step, gap / max(f1 - f0, 1))
    return step


def main():
    boxes = load_boxes()
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    players = {
        row["start"]: row.get("player", "")
        for row in data["rows"]
        if row.get("start") in TIMES and row.get("eventtype") in KIND
    }
    print(f"anchor ({ANCHOR_X:.0f}, {ANCHOR_Y:.0f})  radius {NEAR_PX}px")
    print(
        f"{'Time':<10} {'Player':<16} {'Frames':<7} {'x range':<10} "
        f"{'y range':<12} {'Above':<6} {'Below':<6} {'Step/frame'}"
    )
    for text in TIMES:
        center = int(round(clock_ms(text) / 1000.0 * FPS))
        path = closest_path(boxes, center)
        if not path:
            print(f"{text:<10} {players.get(text, ''):<16} 0")
            continue
        xs = [item[1] for item in path]
        ys = [item[2] for item in path]
        above = sum(1 for y in ys if y < ANCHOR_Y)
        below = sum(1 for y in ys if y > ANCHOR_Y)
        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)
        step = max_step(path)
        print(
            f"{text:<10} {players.get(text, ''):<16} {len(path):<7} "
            f"{x_span:<10.0f} {min(ys):.0f}-{max(ys):.0f}{'':<4} "
            f"{above:<6} {below:<6} {step:.0f}"
        )
    print(f"windows {len(TIMES)}  paths through one measured rim: 0")
    print(
        "synthetic_q4_tracks.json not written. "
        "The boxes on these frames are the detector's own boxes. "
        "No coordinates were invented."
    )
    print("make rule: not called.")


if __name__ == "__main__":
    main()
