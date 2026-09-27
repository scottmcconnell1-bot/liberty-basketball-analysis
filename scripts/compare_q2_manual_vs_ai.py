"""Compare Q2 Film Tool tags to persisted AI events. Does not copy tags onto AI."""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from film_tool_tags import save_manual_tags
from manual_tag_teach import time_to_ms

GAME = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
Q1_END_MS = 960700
Q2_END_MS = 32 * 60 * 1000 + 15 * 1000  # 32:15 last tag; Scott: Q2 ends 32:14
TAGS = Path("tag-exports/jrhigh_adrian_chrome_autosave.json")
DB = Path("film_analysis.db")


def empty_box():
    return {
        "PTS": 0, "FGM": 0, "FGA": 0, "2PM": 0, "2PA": 0, "3PM": 0, "3PA": 0,
        "FTM": 0, "FTA": 0, "OREB": 0, "DREB": 0, "REB": 0, "AST": 0, "STL": 0,
        "BLK": 0, "TO": 0, "PF": 0, "TOUT": 0,
    }


def team_key(name: str) -> str:
    text = str(name or "").strip().lower()
    if "adrian" in text:
        return "Adrian"
    if "liberty" in text or text in {"our team", "our", "away"}:
        return "Liberty"
    if "opponent" in text or text == "home":
        return "Adrian"
    return str(name or "Unknown")


def add_manual(box, row):
    et = str(row.get("eventtype") or "")
    result = str(row.get("result") or "")
    if et == "2PT":
        box["2PA"] += 1
        box["FGA"] += 1
        if result == "Make":
            box["2PM"] += 1
            box["FGM"] += 1
            box["PTS"] += 2
    elif et == "3PT":
        box["3PA"] += 1
        box["FGA"] += 1
        if result == "Make":
            box["3PM"] += 1
            box["FGM"] += 1
            box["PTS"] += 3
    elif et == "FT":
        box["FTA"] += 1
        if result == "Make":
            box["FTM"] += 1
            box["PTS"] += 1
    elif et == "Assist":
        box["AST"] += 1
    elif et == "OffRebound":
        box["OREB"] += 1
        box["REB"] += 1
    elif et == "DefRebound":
        box["DREB"] += 1
        box["REB"] += 1
    elif et == "Steal":
        box["STL"] += 1
    elif et == "Block":
        box["BLK"] += 1
    elif et == "Turnover":
        box["TO"] += 1
    elif et == "Foul":
        box["PF"] += 1
    elif et == "TimeOut":
        box["TOUT"] += 1


def add_ai(box, event_type, details):
    et = str(event_type or "").lower()
    if et == "shot":
        kind = str(details.get("shot_kind") or details.get("shot_type") or "2").lower()
        made = str(details.get("shot_result") or "").lower() == "make"
        # shot_result is on the event, handled by caller via details
        return
    made = et.startswith("made")
    if et in {"made_two", "missed_two"}:
        box["2PA"] += 1
        box["FGA"] += 1
        if made:
            box["2PM"] += 1
            box["FGM"] += 1
            box["PTS"] += 2
    elif et in {"made_three", "missed_three"}:
        box["3PA"] += 1
        box["FGA"] += 1
        if made:
            box["3PM"] += 1
            box["FGM"] += 1
            box["PTS"] += 3
    elif et in {"made_free_throw", "missed_free_throw"}:
        box["FTA"] += 1
        if made:
            box["FTM"] += 1
            box["PTS"] += 1
    elif et == "assist":
        box["AST"] += 1
    elif "rebound" in et:
        kind = str(details.get("rebound_kind") or details.get("rebound_type") or et)
        if "off" in kind:
            box["OREB"] += 1
        else:
            box["DREB"] += 1
        box["REB"] += 1
    elif et == "steal":
        box["STL"] += 1
    elif et == "block":
        box["BLK"] += 1
    elif et == "turnover":
        box["TO"] += 1
    elif et == "foul":
        box["PF"] += 1


def fmt(box):
    return {
        "PTS": box["PTS"],
        "FG": f"{box['FGM']}/{box['FGA']}",
        "2P": f"{box['2PM']}/{box['2PA']}",
        "3P": f"{box['3PM']}/{box['3PA']}",
        "FT": f"{box['FTM']}/{box['FTA']}",
        "REB": f"{box['REB']} ({box['OREB']}/{box['DREB']})",
        "AST": box["AST"],
        "STL": box["STL"],
        "BLK": box["BLK"],
        "TO": box["TO"],
        "PF": box["PF"],
        "TimeOut": box["TOUT"],
    }


def main() -> None:
    data = json.loads(TAGS.read_text(encoding="utf-8"))
    save_manual_tags(GAME, data)
    rows = [r for r in (data.get("rows") or []) if isinstance(r, dict)]
    q2 = []
    type_counts = defaultdict(int)
    for row in rows:
        ms = time_to_ms(row.get("start"))
        if ms <= Q1_END_MS or ms > Q2_END_MS:
            continue
        q2.append(row)
        type_counts[str(row.get("eventtype") or "")] += 1

    you = {"Liberty": empty_box(), "Adrian": empty_box()}
    for row in q2:
        team = team_key(row.get("team"))
        if team not in you:
            you[team] = empty_box()
        add_manual(you[team], row)

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    ai_rows = conn.execute(
        """
        SELECT player, event_type, shot_result, timestamp_ms, details_json, source_type
        FROM events
        WHERE game_id = ? AND timestamp_ms > ? AND timestamp_ms <= ?
        ORDER BY timestamp_ms
        """,
        (GAME, Q1_END_MS, Q2_END_MS),
    ).fetchall()
    conn.close()

    ai = {"Liberty": empty_box(), "Adrian": empty_box(), "Unknown": empty_box()}
    ai_types = defaultdict(int)
    for row in ai_rows:
        if row["source_type"] == "manual":
            continue
        ai_types[str(row["event_type"])] += 1
        try:
            details = json.loads(row["details_json"] or "{}")
        except json.JSONDecodeError:
            details = {}
        details["shot_result"] = row["shot_result"]
        et = str(row["event_type"] or "").lower()
        team = team_key(row["player"] or details.get("team") or "")
        box = ai.get(team) or ai["Unknown"]
        if et == "shot":
            kind = str(details.get("shot_kind") or details.get("shot_type") or "2").lower()
            made = str(row["shot_result"] or "").lower() == "make"
            if kind in {"3", "3pt", "three"}:
                box["3PA"] += 1
                box["FGA"] += 1
                if made:
                    box["3PM"] += 1
                    box["FGM"] += 1
                    box["PTS"] += 3
            elif kind in {"ft", "free_throw"}:
                box["FTA"] += 1
                if made:
                    box["FTM"] += 1
                    box["PTS"] += 1
            else:
                box["2PA"] += 1
                box["FGA"] += 1
                if made:
                    box["2PM"] += 1
                    box["FGM"] += 1
                    box["PTS"] += 2
            continue
        if et in {"made_two", "missed_two", "made_three", "missed_three", "made_free_throw", "missed_free_throw"}:
            continue
        add_ai(box, row["event_type"], details)

    combined_you = empty_box()
    combined_ai = empty_box()
    for side in you.values():
        for k, v in side.items():
            combined_you[k] += v
    for side in ai.values():
        for k, v in side.items():
            combined_ai[k] += v

    print(json.dumps({
        "window": "after 16:00.7 through 32:15 (Q2 end 32:14)",
        "manual_rows_q2": len(q2),
        "manual_types": dict(type_counts),
        "you": {k: fmt(v) for k, v in you.items()},
        "you_combined": fmt(combined_you),
        "ai_event_types": dict(ai_types),
        "ai_by_guessed_team": {k: fmt(v) for k, v in ai.items() if v["FGA"] or v["FTA"] or v["TO"] or v["STL"]},
        "ai_combined": fmt(combined_ai),
        "lastTaggedTime": data.get("lastTaggedTime"),
    }, indent=2))


if __name__ == "__main__":
    main()
