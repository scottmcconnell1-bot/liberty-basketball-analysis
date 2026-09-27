"""Halftime scorekeeper sheet vs Film Tool tags through 32:14. Does not copy tags."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from film_tool_tags import load_manual_tags
from manual_tag_teach import time_to_ms

GAME = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
HT_MS = 32 * 60 * 1000 + 14 * 1000

# Scorekeeper listed PTS. Dayley line says 15 but 7 2PT + 1 3PT = 17;
# Scott: SK missed one Liberty 2PT (that +2 makes Liberty 27).
LIBERTY_SHEET = [
    ("0", "Sullivan", 0, 0, 0, 0, 0),
    ("3", "Kariuki", 0, 0, 0, 0, 0),
    ("5", "Bradshaw", 0, 0, 0, 0, 0),
    ("11", "Flores", 0, 0, 0, 0, 0),
    ("21", "Colman", 8, 2, 1, 1, 3),
    ("24", "Jenkins", 0, 0, 0, 0, 0),
    ("40", "Dayley", 15, 7, 1, 0, 0),
    ("41", "Leach", 0, 0, 0, 0, 0),
    ("45", "Musgrave", 0, 0, 0, 0, 0),
    ("51", "Peterson", 2, 1, 0, 0, 0),
    ("53", "Price", 0, 0, 0, 0, 0),
]
# jersey, name, pts, 2pm, 3pm, ftm, fta
ADRIAN_SHEET = [
    ("11", "Linkhart", 0, 0, 0, 0, 0),
    ("12", "Linkhart", 0, 0, 0, 0, 2),
    ("13", "Mendoza", 7, 1, 1, 2, 4),
    ("14", "Dorms", 0, 0, 0, 0, 0),
    ("15", "Allison", 0, 0, 0, 0, 0),
    ("22", "Foster", 2, 1, 0, 0, 0),
    ("23", "Rodus", 2, 0, 0, 2, 4),
    ("24", "Abel", 0, 0, 0, 0, 0),
    ("25", "Alvarez", 4, 0, 0, 4, 6),
    ("30", "Gallegos", 0, 0, 0, 0, 0),
    ("32", "Unknown", 0, 0, 0, 0, 0),
]


def jersey_of(player: str) -> str:
    text = str(player or "").strip()
    if " - " in text:
        text = text.split(" - ", 1)[0]
    return text.strip()


def team_of(row: dict) -> str:
    text = str(row.get("team") or "").strip().lower()
    if "adrian" in text or "opponent" in text or text == "home":
        return "Adrian"
    return "Liberty"


def empty():
    return {"pts": 0, "fg2": 0, "fg3": 0, "ftm": 0, "fta": 0, "player": ""}


def main() -> None:
    payload = load_manual_tags(GAME) or {}
    you = {"Liberty": defaultdict(empty), "Adrian": defaultdict(empty)}
    for row in payload.get("rows") or []:
        ts = time_to_ms(row.get("start"))
        if ts > HT_MS:
            continue
        et = str(row.get("eventtype") or "")
        result = str(row.get("result") or "")
        team = team_of(row)
        jer = jersey_of(row.get("player"))
        if et not in {"2PT", "3PT", "FT"}:
            continue
        box = you[team][jer]
        box["player"] = str(row.get("player") or jer)
        if et == "2PT":
            if result == "Make":
                box["fg2"] += 1
                box["pts"] += 2
        elif et == "3PT":
            if result == "Make":
                box["fg3"] += 1
                box["pts"] += 3
        elif et == "FT":
            box["fta"] += 1
            if result == "Make":
                box["ftm"] += 1
                box["pts"] += 1

    def rows_for(sheet, side):
        out = []
        tagged = you[side]
        used = set()
        for jer, name, pts, fg2, fg3, ftm, fta in sheet:
            t = tagged.get(jer) or empty()
            used.add(jer)
            out.append(
                {
                    "jersey": jer,
                    "name": name,
                    "book_pts": pts,
                    "you_pts": t["pts"],
                    "book": f"{fg2} 2PT, {fg3} 3PT, {ftm}-{fta} FT",
                    "you": f"{t['fg2']} 2PT, {t['fg3']} 3PT, {t['ftm']}-{t['fta']} FT",
                    "delta": t["pts"] - pts,
                }
            )
        extras = []
        for jer, t in tagged.items():
            if jer not in used and t["pts"]:
                extras.append({"jersey": jer, "player": t["player"], "you_pts": t["pts"]})
        return out, extras, sum(r["book_pts"] for r in out), sum(r["you_pts"] for r in out)

    lib, lib_x, lib_book, lib_you = rows_for(LIBERTY_SHEET, "Liberty")
    adr, adr_x, adr_book, adr_you = rows_for(ADRIAN_SHEET, "Adrian")
    print(
        json.dumps(
            {
                "halftime_gym": "Liberty 27 – Adrian 15 (Q1 16-10 + Q2 11-5)",
                "scorekeeper_listed": {"Liberty": lib_book, "Adrian": adr_book},
                "scorekeeper_plus_missed_2pt": {"Liberty": lib_book + 2, "Adrian": adr_book},
                "your_tags": {"Liberty": lib_you, "Adrian": adr_you},
                "liberty": lib,
                "liberty_unlisted_scorers": lib_x,
                "adrian": adr,
                "adrian_unlisted_scorers": adr_x,
                "dayley_note": "Sheet PTS 15; 7 twos + 1 three = 17. Missed 2PT is that +2.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
