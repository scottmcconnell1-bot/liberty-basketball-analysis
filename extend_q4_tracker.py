"""See what would have to change before the make rule can score Q4.

The scored rule looks up one saved row in v6_tracks.json per tag time.
That file ends at the last first-three-quarters tag. It has no end-frame
filter, and no code reads a hoop x bound from a config file.

Ball boxes from the offline weights already exist for every frame of the
film, including the fourth quarter. The afternoon hoop mark is a separate
sample every two seconds. Restricting its x does not build a path through
one rim.

This script does not write a config, does not call the make rule, and does
not write the database.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
V6 = Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks.json")
FULL = Path(r"C:\Users\scott\AppData\Local\Temp\v6_full_game.jsonl")
HOOP = ROOT / "data/hoop_tracks/q4_blind_rerun_20261013.json"
FPS = 25.0
KIND = {"2PT", "3PT", "FT"}
X_MIN = 300
X_MAX = 1600
WINDOW_S = 2.0


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def show_clock(ms):
    total = ms / 1000.0
    return f"{int(total // 60)}:{total % 60:04.1f}"


def main():
    tracks = json.loads(V6.read_text(encoding="utf-8"))
    times = sorted(int(row["t"]) for row in tracks)
    print(f"saved make/miss tracks {len(tracks)}")
    print(f"first {times[0]} ms ({show_clock(times[0])})")
    print(f"last  {times[-1]} ms ({show_clock(times[-1])})")
    print("no end-frame field on a track row; the rule looks up the tag time only")

    boxes = {}
    last_frame = None
    with FULL.open(encoding="utf-8") as handle:
        for line in handle:
            frame, found = json.loads(line)
            last_frame = frame
            if found:
                boxes[frame] = found
    print(
        f"offline ball boxes already run through frame {last_frame} "
        f"({show_clock(last_frame / FPS * 1000)})"
    )
    print(f"frames with at least one ball box {len(boxes)}")

    hoop = json.loads(HOOP.read_text(encoding="utf-8"))["samples"]
    outside = [s for s in hoop if s["x"] < X_MIN or s["x"] > X_MAX]
    inside = [s for s in hoop if X_MIN <= s["x"] <= X_MAX]

    def jump(samples):
        if len(samples) < 2:
            return 0.0
        return max(abs(b["x"] - a["x"]) for a, b in zip(samples, samples[1:]))

    print(
        f"afternoon hoop samples {len(hoop)}  "
        f"x {min(s['x'] for s in hoop):.0f}-{max(s['x'] for s in hoop):.0f}"
    )
    print(
        f"x outside {X_MIN}-{X_MAX}: {len(outside)}   "
        f"kept: {len(inside)}   "
        f"largest step all {jump(hoop):.0f}px   kept {jump(inside):.0f}px"
    )

    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and (row.get("result") or "").lower() in ("make", "miss")
    ]
    half = int(WINDOW_S * FPS)
    print(f"{'Time':<10} {'Player':<16} {'Boxes':<6} {'Frames hit':<11} {'Hoop x':<8} {'In 300-1600'}")
    for row in tags:
        film = clock_ms(row["start"])
        center = int(round(film / 1000.0 * FPS))
        window = range(center - half, center + half + 1)
        count = sum(len(boxes.get(frame, [])) for frame in window)
        hit = sum(1 for frame in window if boxes.get(frame))
        # Afternoon hoop frames are on the Q4 clip, which starts at 56:26.7.
        clip_frame = center - int(round(3386.7 * FPS))
        hoop_now = min(hoop, key=lambda s: abs(s["frame"] - clip_frame))
        kept = "yes" if X_MIN <= hoop_now["x"] <= X_MAX else "no"
        print(
            f"{row['start']:<10} {row.get('player',''):<16} {count:<6} {hit:<11} "
            f"{hoop_now['x']:<8.0f} {kept}"
        )
    print(f"tags {len(tags)}")
    print("config not written. Nothing in the make rule reads an end time or an x bound.")
    print("track rule result: not scored. These boxes are not a saved track through one rim.")


if __name__ == "__main__":
    main()
