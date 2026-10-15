"""Compare Scott's Q4 tags to the afternoon AI rerun. Does not write the live card.

The live film_analysis.db holds the 18 tags as manual rows. This script reads
the separate AI database from the fourth-quarter rerun.
"""
import json
import sqlite3
from pathlib import Path

TAGS = Path(__file__).resolve().parent / (
    "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
)
AI_DB = Path(r"C:\Users\scott\AppData\Local\Temp\q4_rerun_20261013\q4.db")
OFFSET_MS = 3386700  # clip time 0 is film clock 56:26.7
WINDOW_MS = 8000
KIND = {"2PT": "2", "3PT": "3", "FT": "ft"}
AI_KIND = {
    "made_two": "2",
    "missed_two": "2",
    "made_three": "3",
    "missed_three": "3",
    "made_free_throw": "ft",
    "missed_free_throw": "ft",
}


def clock_ms(text):
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def clock(ms):
    seconds = ms / 1000.0
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def jersey_of(player):
    text = (player or "").strip()
    if text.startswith("#"):
        text = text[1:]
    head = text.split(" ", 1)[0]
    return int(head) if head.isdigit() else None


def main():
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    tags = []
    for row in data["rows"]:
        if row.get("quarter") != "Q4" or row.get("eventtype") not in KIND:
            continue
        result = (row.get("result") or "").lower()
        if result not in ("make", "miss"):
            continue
        tags.append(
            {
                "ms": clock_ms(row["start"]),
                "clock": row["start"],
                "player": row.get("player") or "",
                "jersey": jersey_of(row.get("player")),
                "kind": KIND[row["eventtype"]],
                "result": result,
            }
        )

    con = sqlite3.connect("file:" + str(AI_DB) + "?mode=ro", uri=True)
    ai = []
    for row in con.execute(
        """
        SELECT timestamp_ms, event_type, shot_result, player, details_json
        FROM events
        WHERE event_type IN (
          'made_two','missed_two','made_three','missed_three',
          'made_free_throw','missed_free_throw')
        ORDER BY timestamp_ms, id
        """
    ):
        details = json.loads(row[4] or "{}")
        jersey = details.get("jersey_number")
        if jersey is None and str(row[3] or "").startswith("#"):
            jersey = jersey_of(row[3])
        ai.append(
            {
                "ms": int(row[0]) + OFFSET_MS,
                "jersey": jersey,
                "kind": AI_KIND[row[1]],
                "result": row[2],
            }
        )
    con.close()

    pairs = []
    for ti, tag in enumerate(tags):
        for aj, shot in enumerate(ai):
            diff = abs(tag["ms"] - shot["ms"])
            if diff <= WINDOW_MS:
                pairs.append((diff, ti, aj))
    pairs.sort()
    used_tags, used_ai = set(), set()
    matched = {}
    for diff, ti, aj in pairs:
        if ti in used_tags or aj in used_ai:
            continue
        used_tags.add(ti)
        used_ai.add(aj)
        matched[ti] = (diff, ai[aj])

    missing = wrong_jersey = wrong_type = wrong_result = full = 0
    print("=== Q4 SHOT AUDIT ===")
    print(f"manual tags {len(tags)}  ai rows {len(ai)}")
    print("TAG | NEAREST AI | FAILURES")
    for i, tag in enumerate(tags):
        label = f"{tag['clock']} {tag['player']} {tag['kind']} {tag['result']}"
        if i not in matched:
            missing += 1
            print(f"{label} | none | missing AI row")
            continue
        diff, shot = matched[i]
        fails = []
        if tag["jersey"] != shot["jersey"]:
            fails.append("wrong jersey")
            wrong_jersey += 1
        if tag["kind"] != shot["kind"]:
            fails.append("wrong type")
            wrong_type += 1
        if tag["result"] != shot["result"]:
            fails.append("wrong make/miss")
            wrong_result += 1
        if not fails:
            full += 1
            fails.append("match")
        print(
            f"{label} | {clock(shot['ms'])} jersey {shot['jersey']} "
            f"{shot['kind']} {shot['result']} ({diff} ms) | {', '.join(fails)}"
        )

    print("---")
    print(f"full match {full}")
    print(f"missing AI row {missing}")
    print(f"paired {len(matched)}")
    print(f"wrong jersey among pairs {wrong_jersey}")
    print(f"wrong type among pairs {wrong_type}")
    print(f"wrong make/miss among pairs {wrong_result}")
    print(f"extra AI {len(ai) - len(used_ai)}")
    for j, shot in enumerate(ai):
        if j not in used_ai:
            print(f"  extra {clock(shot['ms'])} jersey {shot['jersey']} {shot['kind']} {shot['result']}")


if __name__ == "__main__":
    main()
