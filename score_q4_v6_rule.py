"""Score the 18 fourth-quarter tracks with run_saved_v6_rule.

The function lives in ai_bridge.py. It reads a track file and looks up each
tag time. It does not take a ball path and a hoop as two arguments.
score_v6_make.py is not imported: loading that file reruns detection and
rewrites v6_tracks.json.

Player names come from the live tags. This script does not write them into
the track file.
"""
import json
from pathlib import Path

from ai_bridge import run_saved_v6_rule

ROOT = Path(__file__).resolve().parent
TAGS = ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
TRACKS = Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks_q4.json")
KIND = {"2PT", "3PT", "FT"}


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def show(ms):
    total = ms / 1000.0
    return f"{int(total // 60)}:{total % 60:04.1f}"


def main():
    tracks = json.loads(TRACKS.read_text(encoding="utf-8"))
    by_t = {int(row["t"]): row for row in tracks}
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = [
        row
        for row in data["rows"]
        if row.get("quarter") == "Q4"
        and row.get("eventtype") in KIND
        and (row.get("result") or "") in ("Make", "Miss")
        and clock_ms(row["start"]) in by_t
    ]
    times = [clock_ms(row["start"]) for row in tags]
    scored = run_saved_v6_rule(times, str(TRACKS))
    by_ts = {int(row["tag_ts"]): row for row in scored["results"]}
    print(
        f"{'Time':<10} {'Player':<16} {'Tag':<6} {'is_make':<8} {'v6 rule':<8} Reason"
    )
    match = 0
    for row in tags:
        ts = clock_ms(row["start"])
        item = by_ts[ts]
        pred = "make" if item["pred"] else "miss"
        truth = "make" if item["true"] else "miss"
        if pred == truth:
            match += 1
        details = item["details"]
        reason = details.get("veto_reason") or details.get("reason") or ""
        older = by_t[ts].get("is_make", "")
        print(
            f"{row['start']:<10} {row.get('player',''):<16} {truth:<6} "
            f"{older:<8} {pred:<8} {reason}"
        )
    print(
        f"tracks {scored['total_tags']}  right {scored['right']}  "
        f"makes missed {scored['makes_missed']}  "
        f"misses called makes {scored['misses_called_makes']}"
    )
    print(f"same as the tag {match}")
    print("v6_tracks.json was not changed")


if __name__ == "__main__":
    main()
