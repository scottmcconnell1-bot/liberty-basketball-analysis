"""See whether the full-game file has a hoop box to filter.

Each line is [frame, [[center_x, center_y, width, height, confidence], ...]].
The weights that wrote it have one class, basketball. A line has no class
name and no hoop. This script counts that, and it does not add rows to
v6_tracks.json or call is_make.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
BOXES = Path(r"C:\Users\scott\AppData\Local\Temp\v6_full_game.jsonl")
KIND = {"2PT", "3PT", "FT"}
Q4_MS = int(round((55 * 60 + 17.1) * 1000))


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def main():
    lines = 0
    dict_lines = 0
    hoop_labels = 0
    ball_boxes = 0
    with BOXES.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            lines += 1
            record = json.loads(line)
            if isinstance(record, dict):
                dict_lines += 1
                for det in record.get("detections") or []:
                    if det.get("class") == "hoop":
                        hoop_labels += 1
                continue
            frame, found = record
            del frame
            ball_boxes += len(found)
    print(f"lines {lines}")
    print(f"lines shaped as a detection dict {dict_lines}")
    print(f"hoop labels {hoop_labels}")
    print(f"ball boxes {ball_boxes}")

    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row["start"]
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and clock_ms(row.get("start")) > Q4_MS
        and (row.get("result") or "").lower() in ("make", "miss")
    ]
    print(f"fourth-quarter tags {len(tags)}")
    print("v6_tracks.json was not changed")
    print("is_make: not called")


if __name__ == "__main__":
    main()
