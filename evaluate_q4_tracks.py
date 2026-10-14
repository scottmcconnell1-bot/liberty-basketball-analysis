"""See whether the make/miss rule has a ball track for each Q4 tag.

The scored rule reads v6_tracks.json. Those rows are the first three quarters.
This script does not invent a make or a miss when that track is missing.
It does not write the live card.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
V6 = Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks.json")
AI_DB = Path(r"C:\Users\scott\AppData\Local\Temp\q4_rerun_20261013\q4.db")
HOOP = ROOT / "data/hoop_tracks/q4_blind_rerun_20261013.json"
OFFSET_MS = 3386700
KIND = {"2PT", "3PT", "FT"}


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def main():
    tracks = json.loads(V6.read_text(encoding="utf-8"))
    track_times = {int(row["t"]) for row in tracks}
    latest = max(track_times)
    print(f"saved make/miss tracks {len(tracks)}  latest {latest} ms")

    hoop = json.loads(HOOP.read_text(encoding="utf-8"))["samples"]
    print(
        f"afternoon hoop samples {len(hoop)}  "
        f"x {min(s['x'] for s in hoop):.0f}-{max(s['x'] for s in hoop):.0f}  "
        f"y {min(s['y'] for s in hoop):.0f}-{max(s['y'] for s in hoop):.0f}"
    )

    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and (row.get("result") or "").lower() in ("make", "miss")
    ]

    con = sqlite3.connect("file:" + str(AI_DB) + "?mode=ro", uri=True)
    balls = con.execute(
        """
        SELECT timestamp_ms, x_center, y_center, confidence
        FROM detections WHERE object_class='ball'
        """
    ).fetchall()
    con.close()

    print(f"{'Time':<10} {'Player':<16} {'Type':<4} {'Tag':<6} {'Saved track':<12} {'Balls near hoop'}")
    on_saved = 0
    for row in tags:
        film = clock_ms(row["start"])
        clip = film - OFFSET_MS
        saved = "yes" if film in track_times else "no"
        if saved == "yes":
            on_saved += 1
        hoop_now = min(hoop, key=lambda s: abs(s["timestamp_ms"] - clip))
        near = 0
        for ts, x, y, conf in balls:
            if abs(ts - clip) > 2000 or conf < 0.25:
                continue
            dx = x - hoop_now["x"]
            dy = y - hoop_now["y"]
            if (dx * dx + dy * dy) ** 0.5 <= 180:
                near += 1
        print(
            f"{row['start']:<10} {row.get('player',''):<16} {row['eventtype']:<4} "
            f"{row['result'].lower():<6} {saved:<12} {near}"
        )
    print(f"tags {len(tags)}  on a saved make/miss track {on_saved}")
    print("track rule result: not scored. No fourth-quarter row exists in the saved tracks.")


if __name__ == "__main__":
    main()
