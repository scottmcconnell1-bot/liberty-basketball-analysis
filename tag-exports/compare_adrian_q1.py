"""Compare Film Tool Q1 tags vs AI events for Liberty vs Adrian, first 16:00."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CDP = Path(r"C:\Users\scott\.cursor\browser-logs\cdp-response-Runtime.evaluate-2026-09-17T03-50-51-467Z.json")
DB = ROOT / "film_analysis.db"
GAME_ID = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
WINDOW_MS = 16 * 60 * 1000
MATCH_TOL_MS = 8000

LIBERTY_NAMES = {
    "bradshaw",
    "colman",
    "blacker",
    "xavier",
    "taylor",
    "fischer",
    "sullivan",
    "dayley",
    "musgrave",
    "peterson",
    "kariuki",
    "flores",
    "jenkins",
    "leach",
}
ADRIAN_HINTS = {
    "martinez",
    "barboza",
    "zamora",
    "bryce",
    "johnson",
    "linkhart",
    "mendoza",
    "dorms",
    "allison",
    "foster",
    "rodus",
    "abel",
}

STAT_TYPES = {
    "2PT",
    "3PT",
    "FT",
    "Assist",
    "Steal",
    "Turnover",
    "Foul",
    "Block",
    "OffRebound",
    "DefRebound",
}


def time_to_ms(value) -> int:
    s = str(value or "").strip()
    if not s:
        return 0
    parts = s.split(":")
    if len(parts) == 1:
        return int(round(float(parts[0]) * 1000))
    return int(round(((int(parts[0]) or 0) * 60 + float(parts[1] or 0)) * 1000))


def fmt(ms: int) -> str:
    sec = max(0, int(round(ms / 1000)))
    return f"{sec // 60}:{sec % 60:02d}"


def last_name(player: str) -> str:
    text = str(player or "").lower()
    text = text.replace(",", " ")
    parts = [p for p in text.replace("-", " ").split() if p and not p.isdigit() and p not in {"so", "jr", "sr", "fr", "11", "10", "12"}]
    return parts[-1] if parts else ""


def team_for(player: str, notes: str = "") -> str:
    ln = last_name(player)
    if ln in LIBERTY_NAMES:
        return "Liberty"
    if ln in ADRIAN_HINTS:
        return "Adrian"
    blob = f"{player} {notes}".lower()
    if "liberty" in blob:
        return "Liberty"
    if "adrian" in blob or "opponent" in blob:
        return "Adrian"
    return ""


def empty_box():
    return {
        "PTS": 0,
        "FGM": 0,
        "FGA": 0,
        "2PM": 0,
        "2PA": 0,
        "3PM": 0,
        "3PA": 0,
        "FTM": 0,
        "FTA": 0,
        "OREB": 0,
        "DREB": 0,
        "REB": 0,
        "AST": 0,
        "STL": 0,
        "BLK": 0,
        "TO": 0,
        "PF": 0,
    }


def add_stat(box, eventtype, result):
    if eventtype == "2PT":
        box["2PA"] += 1
        box["FGA"] += 1
        if result == "Make":
            box["2PM"] += 1
            box["FGM"] += 1
            box["PTS"] += 2
    elif eventtype == "3PT":
        box["3PA"] += 1
        box["FGA"] += 1
        if result == "Make":
            box["3PM"] += 1
            box["FGM"] += 1
            box["PTS"] += 3
    elif eventtype == "FT":
        box["FTA"] += 1
        if result == "Make":
            box["FTM"] += 1
            box["PTS"] += 1
    elif eventtype == "Assist":
        box["AST"] += 1
    elif eventtype == "Steal":
        box["STL"] += 1
    elif eventtype == "Turnover":
        box["TO"] += 1
    elif eventtype == "Foul":
        box["PF"] += 1
    elif eventtype == "Block":
        box["BLK"] += 1
    elif eventtype == "OffRebound":
        box["OREB"] += 1
        box["REB"] += 1
    elif eventtype == "DefRebound":
        box["DREB"] += 1
        box["REB"] += 1


def map_ai(event):
    et = str(event["event_type"] or "").lower()
    result = str(event["shot_result"] or "").lower()
    details = {}
    try:
        details = json.loads(event["details_json"] or "{}")
    except Exception:
        details = {}
    if et in {"make", "miss", "possession_change", "bookmark"}:
        return None
    if et == "shot":
        kind = str(details.get("shot_type") or details.get("shotType") or "2pt").lower()
        mapped = "2PT"
        if "3" in kind:
            mapped = "3PT"
        elif "ft" in kind or "free" in kind:
            mapped = "FT"
        return mapped, "Make" if result in {"make", "made"} else "Miss"
    mapped = {
        "assist": "Assist",
        "steal": "Steal",
        "turnover": "Turnover",
        "block": "Block",
        "foul": "Foul",
        "rebound": "OffRebound" if "off" in str(details.get("rebound_type") or details.get("reboundType") or "").lower() else "DefRebound",
        "offensive_rebound": "OffRebound",
        "defensive_rebound": "DefRebound",
        "free_throw": "FT",
    }.get(et)
    if not mapped:
        return None
    shot_res = "NA"
    if mapped in {"2PT", "3PT", "FT"}:
        shot_res = "Make" if result in {"make", "made"} else "Miss"
    return mapped, shot_res


def match_key(eventtype, result):
    if eventtype in {"2PT", "3PT", "FT"}:
        return f"{eventtype}|{result}"
    return eventtype


def main():
    cdp = json.loads(CDP.read_text(encoding="utf-8"))
    raw_rows = cdp["result"]["value"]["rows"]
    manual = []
    for row in raw_rows:
        ms = time_to_ms(row.get("start"))
        if ms > WINDOW_MS:
            continue
        team = team_for(row.get("player") or "", row.get("notes") or "")
        item = {
            "eventtype": row.get("eventtype") or "",
            "result": row.get("result") or "NA",
            "player": row.get("player") or "",
            "team": team,
            "start": row.get("start"),
            "ms": ms,
            "label": row.get("label") or "",
        }
        manual.append(item)

    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    keys = [r[0] for r in conn.execute("SELECT DISTINCT game_id FROM events WHERE game_id LIKE ?", ("%adrian%",)).fetchall()]
    run = conn.execute(
        """SELECT analysis_key, status, run_kind, settings_json, started_at, completed_at
           FROM analysis_runs WHERE analysis_key LIKE ? ORDER BY id DESC LIMIT 8""",
        ("%adrian%",),
    ).fetchall()
    setting = conn.execute(
        "SELECT key, value FROM app_settings WHERE key LIKE 'ai.%' OR key LIKE '%tracker%'"
    ).fetchall() if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'").fetchone() else []

    events = conn.execute(
        """SELECT id, event_type, shot_result, player, timestamp_ms, review_status, source_type, confidence, details_json
           FROM events WHERE game_id = ? AND timestamp_ms >= 0 AND timestamp_ms <= ?
           ORDER BY timestamp_ms""",
        (GAME_ID, WINDOW_MS),
    ).fetchall()
    type_counts = Counter(str(e["event_type"] or "") for e in events)
    status_counts = Counter(str(e["review_status"] or "") for e in events)

    ai_rows = []
    for event in events:
        mapped = map_ai(event)
        if not mapped:
            continue
        eventtype, result = mapped
        player = str(event["player"] or "")
        team = team_for(player)
        ai_rows.append(
            {
                "id": event["id"],
                "eventtype": eventtype,
                "result": result,
                "player": player,
                "team": team,
                "ms": int(event["timestamp_ms"] or 0),
                "start": fmt(int(event["timestamp_ms"] or 0)),
                "review_status": event["review_status"],
                "raw_type": event["event_type"],
                "confidence": event["confidence"],
            }
        )

    accepted = [r for r in ai_rows if str(r["review_status"] or "").lower() in {"accepted", "corrected"}]
    compare_ai = accepted if accepted else ai_rows

    lib_m, adr_m = empty_box(), empty_box()
    lib_a, adr_a = empty_box(), empty_box()
    man_counts = Counter()
    ai_counts = Counter()
    for row in manual:
        key = match_key(row["eventtype"], row["result"])
        if row["eventtype"] in STAT_TYPES:
            man_counts[key] += 1
            if row["team"] == "Adrian":
                add_stat(adr_m, row["eventtype"], row["result"])
            elif row["team"] == "Liberty":
                add_stat(lib_m, row["eventtype"], row["result"])
    for row in compare_ai:
        key = match_key(row["eventtype"], row["result"])
        ai_counts[key] += 1
        if row["team"] == "Adrian":
            add_stat(adr_a, row["eventtype"], row["result"])
        elif row["team"] == "Liberty":
            add_stat(lib_a, row["eventtype"], row["result"])
        else:
            add_stat(lib_a, row["eventtype"], row["result"])  # unknown player counted separately later

    # Recalculate unknown AI into a third bucket instead of dumping onto Liberty
    lib_a, adr_a, unk_a = empty_box(), empty_box(), empty_box()
    for row in compare_ai:
        bucket = unk_a
        if row["team"] == "Liberty":
            bucket = lib_a
        elif row["team"] == "Adrian":
            bucket = adr_a
        add_stat(bucket, row["eventtype"], row["result"])

    used_ai = set()
    matches = []
    only_manual = []
    for row in manual:
        if row["eventtype"] not in STAT_TYPES:
            continue
        want = match_key(row["eventtype"], row["result"])
        best = None
        best_dt = None
        for i, ai in enumerate(compare_ai):
            if i in used_ai:
                continue
            if match_key(ai["eventtype"], ai["result"]) != want:
                continue
            dt = abs(ai["ms"] - row["ms"])
            if dt > MATCH_TOL_MS:
                continue
            if best_dt is None or dt < best_dt:
                best, best_dt = i, dt
        if best is None:
            only_manual.append(row)
        else:
            used_ai.add(best)
            ai = compare_ai[best]
            matches.append(
                {
                    "type": want,
                    "manual_t": row["start"],
                    "ai_t": ai["start"],
                    "dt_s": round((ai["ms"] - row["ms"]) / 1000, 1),
                    "manual_player": row["player"],
                    "ai_player": ai["player"],
                    "player_ok": last_name(row["player"]) == last_name(ai["player"]) and bool(last_name(row["player"])),
                }
            )
    only_ai = [compare_ai[i] for i in range(len(compare_ai)) if i not in used_ai]

    flow = Counter(r["eventtype"] for r in manual if r["eventtype"] not in STAT_TYPES)

    out = {
        "game_id": GAME_ID,
        "window": "0:00–16:00 of film (960s)",
        "manual_last_tag": max((r["start"] for r in manual), default=""),
        "manual_end_ms": max((r["ms"] for r in manual), default=0),
        "manual_rows": len(manual),
        "manual_stat_rows": sum(1 for r in manual if r["eventtype"] in STAT_TYPES),
        "ai_raw_events": len(events),
        "ai_stat_rows": len(ai_rows),
        "ai_compare_rows": len(compare_ai),
        "ai_accepted": len(accepted),
        "ai_type_counts": dict(type_counts.most_common()),
        "ai_status_counts": dict(status_counts),
        "analysis_keys": keys,
        "runs": [dict(r) for r in run],
        "settings": {r["key"]: r["value"] for r in setting} if setting and hasattr(setting[0], "keys") else [tuple(r) for r in setting],
        "manual_box_liberty": lib_m,
        "manual_box_adrian": adr_m,
        "ai_box_liberty": lib_a,
        "ai_box_adrian": adr_a,
        "ai_box_unknown": unk_a,
        "manual_counts": dict(man_counts),
        "ai_counts": dict(ai_counts),
        "matched": len(matches),
        "only_manual": len(only_manual),
        "only_ai": len(only_ai),
        "player_name_matches": sum(1 for m in matches if m["player_ok"]),
        "matches": matches,
        "only_manual_rows": [
            {"t": r["start"], "type": match_key(r["eventtype"], r["result"]), "player": r["player"], "team": r["team"]}
            for r in only_manual
        ],
        "only_ai_rows": [
            {"t": r["start"], "type": match_key(r["eventtype"], r["result"]), "player": r["player"], "status": r["review_status"]}
            for r in only_ai[:80]
        ],
        "flow_manual": dict(flow),
        "liberty_pts_manual": lib_m["PTS"],
        "adrian_pts_manual": adr_m["PTS"],
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in [
        "manual_rows", "manual_stat_rows", "manual_last_tag", "ai_raw_events", "ai_stat_rows",
        "ai_accepted", "ai_status_counts", "ai_type_counts", "matched", "only_manual", "only_ai",
        "player_name_matches", "liberty_pts_manual", "adrian_pts_manual", "manual_box_liberty",
        "manual_box_adrian", "ai_box_liberty", "ai_box_adrian", "ai_box_unknown", "manual_counts",
        "ai_counts", "flow_manual", "analysis_keys",
    ]}, indent=2))
    print("---RUNS---")
    print(json.dumps(out["runs"], indent=2, default=str)[:4000])
    print("---SETTINGS---")
    print(out["settings"])


if __name__ == "__main__":
    main()
