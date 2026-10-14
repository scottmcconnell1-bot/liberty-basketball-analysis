"""Show why the full-game ball file cannot be scored by the make rule.

v6_full_game.py writes one JSON line per film frame:
[frame, [[center_x, center_y, width, height, confidence], ...]]

Those are ball boxes only. is_make() and run_saved_v6_rule() both need a
hoop as well. This script counts ball boxes in the 80 frames after each
fourth-quarter tag and does not call either function.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
BOXES = Path(r"C:\Users\scott\AppData\Local\Temp\v6_full_game.jsonl")
FPS = 25.0
KIND = {"2PT", "3PT", "FT"}
Q4_MS = int(round((55 * 60 + 17.1) * 1000))
WINDOW = 80


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def main():
    print(f"box file {BOXES}")
    sample = None
    by_frame = {}
    with BOXES.open(encoding="utf-8") as handle:
        for line in handle:
            frame, found = json.loads(line)
            if sample is None and found:
                sample = found[0]
            if found:
                by_frame[frame] = found
    print(f"one ball box is {len(sample)} numbers: center x, center y, width, height, confidence")
    print("no hoop on a line")

    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and clock_ms(row.get("start")) > Q4_MS
        and (row.get("result") or "").lower() in ("make", "miss")
    ]
    print(f"{'Time':<10} {'Player':<16} {'Tag':<6} {'Ball boxes in 80 frames'}")
    for row in tags:
        start = int(round(clock_ms(row["start"]) / 1000.0 * FPS))
        count = sum(len(by_frame.get(frame, [])) for frame in range(start, start + WINDOW))
        print(
            f"{row['start']:<10} {row.get('player',''):<16} "
            f"{row['result'].lower():<6} {count}"
        )
    print(f"tags {len(tags)}")
    print("make rule: not called. A saved track also needs the grouped hoop.")


if __name__ == "__main__":
    main()
