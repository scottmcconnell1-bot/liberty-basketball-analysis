"""Manual vs AI Q1 comparison for Wilder (video 8), mirroring Film Tool logic."""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8080"
CLIENT_GAME_ID = "game-1784304093435"
Q1_COMPARE_END_SEC = 871
Q1_COMPARE_END_MS = Q1_COMPARE_END_SEC * 1000
Q1_COMPARE_LABEL = "Q1 0:00–14:31"
MATCH_TOLERANCE_MS = 8000  # ±8s for event-level matching
OUT_MD = Path(__file__).resolve().parent / "manual_vs_ai_q1_wilder_report.md"
OUT_JSON = Path(__file__).resolve().parent / "manual_vs_ai_q1_wilder_report.json"
DB_PATH = Path(__file__).resolve().parent.parent / "film_analysis.db"

COMPARE_STATS = ["PTS", "FGM", "FGA", "3PM", "3PA", "FTM", "FTA", "Reb", "Ast", "Stl", "Blk", "TO", "PF"]
TEAM_STAT_KEY_MAP = {
    "PTS": "Points",
    "FGM": "FGM",
    "FGA": "FGA",
    "3PM": "3PM",
    "3PA": "3PA",
    "FTM": "FTM",
    "FTA": "FTA",
    "OReb": "OReb",
    "DReb": "DReb",
    "Reb": "Reb",
    "Ast": "Assists",
    "Stl": "Steals",
    "Blk": "Blocks",
    "TO": "Turnovers",
    "PF": "Fouls",
}
STAT_EVENTTYPES = {
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


def get_json(path: str):
    with urllib.request.urlopen(BASE + path, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def time_to_seconds(value) -> float:
    s = str(value or "").strip()
    if not s:
        return 0.0
    parts = s.split(":")
    if len(parts) == 1:
        try:
            return float(parts[0])
        except ValueError:
            return 0.0
    try:
        return (int(parts[0]) or 0) * 60 + float(parts[1] or 0)
    except ValueError:
        return 0.0


def fmt_mmss(sec: float) -> str:
    total = int(round(sec))
    return f"{total // 60}:{total % 60:02d}"


def normalize_player_name(player) -> str:
    value = str(player or "").strip()
    if not value or value.lower() in {"unknown", "unknown / team only"}:
        return "Unknown"
    return value


def filter_manual_q1_rows(rows):
    out = []
    for row in rows:
        if row.get("quarter") and row.get("quarter") != "Q1":
            continue
        seconds = time_to_seconds(row.get("start"))
        if seconds > Q1_COMPARE_END_SEC:
            continue
        category = str(row.get("category") or "")
        eventtype = str(row.get("eventtype") or "")
        if eventtype in {"EndQTR", "StartQTR"}:
            continue
        if category == "Quarter" and eventtype not in STAT_EVENTTYPES:
            continue
        out.append(row)
    return out


def filter_ai_events_to_window(events):
    out = []
    for event in events or []:
        if (event.get("source_type") or "ai") != "ai":
            continue
        ts = int(event.get("timestamp_ms") or 0)
        if 0 <= ts <= Q1_COMPARE_END_MS:
            out.append(event)
    return out


def convert_ai_events_to_stat_rows(events, team_name="Liberty"):
    skip = {"make", "miss", "possession_change", "bookmark"}
    rows = []
    for event in events:
        event_type = str(event.get("event_type") or "").lower()
        if event_type in skip:
            continue
        shot_result = str(event.get("shot_result") or "").lower()
        player = normalize_player_name(event.get("player"))
        start = str((int(event.get("timestamp_ms") or 0)) / 1000)
        details = {}
        try:
            details = json.loads(event.get("details_json") or "{}")
        except Exception:
            details = {}
        if event_type == "shot":
            is_make = shot_result in {"make", "made"}
            shot_kind = str(details.get("shot_type") or details.get("shotType") or "2pt").lower()
            manual_type = "2PT"
            if "3" in shot_kind:
                manual_type = "3PT"
            elif "ft" in shot_kind or "free" in shot_kind:
                manual_type = "FT"
            rows.append(
                {
                    "eventtype": manual_type,
                    "result": "Make" if is_make else "Miss",
                    "player": player,
                    "team": team_name,
                    "start": start,
                    "source_event_id": event.get("id"),
                    "timestamp_ms": int(event.get("timestamp_ms") or 0),
                    "label": f"{manual_type} {'Make' if is_make else 'Miss'}",
                }
            )
            continue
        if event_type == "rebound":
            rebound_kind = str(details.get("rebound_type") or details.get("reboundType") or "").lower()
            mapped = "OffRebound" if "off" in rebound_kind else "DefRebound"
        else:
            mapped = {
                "assist": "Assist",
                "steal": "Steal",
                "turnover": "Turnover",
                "block": "Block",
                "foul": "Foul",
            }.get(event_type)
        if not mapped:
            continue
        rows.append(
            {
                "eventtype": mapped,
                "result": "NA",
                "player": player,
                "team": team_name,
                "start": start,
                "source_event_id": event.get("id"),
                "timestamp_ms": int(event.get("timestamp_ms") or 0),
            }
        )
    return rows


def empty_stats():
    return {
        "Points": 0,
        "FGM": 0,
        "FGA": 0,
        "3PM": 0,
        "3PA": 0,
        "FTM": 0,
        "FTA": 0,
        "OReb": 0,
        "DReb": 0,
        "Reb": 0,
        "Assists": 0,
        "Steals": 0,
        "Blocks": 0,
        "Turnovers": 0,
        "Fouls": 0,
    }


def stat_accumulator(rows):
    by_team = {}
    by_player = {}
    for r in rows:
        team = r.get("team") or "Unknown"
        player = normalize_player_name(r.get("player"))
        key = f"{team}__{player}"
        if team not in by_team:
            by_team[team] = empty_stats()
        if key not in by_player:
            by_player[key] = {"Team": team, "Player": player, **empty_stats()}
        t = by_team[team]
        p = by_player[key]
        et = r.get("eventtype")
        res = r.get("result")
        if et == "2PT":
            t["FGA"] += 1
            p["FGA"] += 1
            if res == "Make":
                t["FGM"] += 1
                p["FGM"] += 1
                t["Points"] += 2
                p["Points"] += 2
        elif et == "3PT":
            t["FGA"] += 1
            t["3PA"] += 1
            p["FGA"] += 1
            p["3PA"] += 1
            if res == "Make":
                t["FGM"] += 1
                t["3PM"] += 1
                p["FGM"] += 1
                p["3PM"] += 1
                t["Points"] += 3
                p["Points"] += 3
        elif et == "FT":
            t["FTA"] += 1
            p["FTA"] += 1
            if res == "Make":
                t["FTM"] += 1
                p["FTM"] += 1
                t["Points"] += 1
                p["Points"] += 1
        elif et == "Assist":
            t["Assists"] += 1
            p["Assists"] += 1
        elif et == "OffRebound":
            t["OReb"] += 1
            t["Reb"] += 1
            p["OReb"] += 1
            p["Reb"] += 1
        elif et == "DefRebound":
            t["DReb"] += 1
            t["Reb"] += 1
            p["DReb"] += 1
            p["Reb"] += 1
        elif et == "Steal":
            t["Steals"] += 1
            p["Steals"] += 1
        elif et == "Block":
            t["Blocks"] += 1
            p["Blocks"] += 1
        elif et == "Turnover":
            t["Turnovers"] += 1
            p["Turnovers"] += 1
        elif et == "Foul":
            t["Fouls"] += 1
            p["Fouls"] += 1
    return {"byTeam": by_team, "byPlayer": by_player}


def category_counts(rows):
    counts = Counter()
    for r in rows:
        et = r.get("eventtype") or "?"
        res = r.get("result") or "NA"
        if et in {"2PT", "3PT", "FT"}:
            key = f"{et} {res}"
        else:
            key = et
        counts[key] += 1
    return counts


def match_key(row):
    """Coarse type key for event matching (result-aware for shots)."""
    et = row.get("eventtype")
    if et in {"2PT", "3PT", "FT"}:
        return f"{et}|{row.get('result') or 'Miss'}"
    if et in {"OffRebound", "DefRebound"}:
        return "Rebound"
    return et or "?"


def coarse_type(row):
    et = row.get("eventtype")
    if et in {"2PT", "3PT", "FT"}:
        return "Shot"
    if et in {"OffRebound", "DefRebound"}:
        return "Rebound"
    return et or "?"


def event_level_match(manual_rows, ai_rows, tolerance_ms=MATCH_TOLERANCE_MS):
    """Greedy nearest-neighbor match by type + time (manual = ground truth)."""
    manual = []
    for i, r in enumerate(manual_rows):
        ts = int(round(time_to_seconds(r.get("start")) * 1000))
        manual.append({**r, "_i": i, "_ts": ts, "_key": match_key(r), "_coarse": coarse_type(r)})
    ai = []
    for j, r in enumerate(ai_rows):
        ts = int(r.get("timestamp_ms") or round(float(r.get("start") or 0) * 1000))
        ai.append({**r, "_j": j, "_ts": ts, "_key": match_key(r), "_coarse": coarse_type(r)})

    used_ai = set()
    matches = []
    disagreements = []
    misses = []

    # Pass 1: exact type+result key
    for m in sorted(manual, key=lambda x: x["_ts"]):
        best = None
        best_dt = None
        for a in ai:
            if a["_j"] in used_ai:
                continue
            if a["_key"] != m["_key"]:
                continue
            dt = abs(a["_ts"] - m["_ts"])
            if dt <= tolerance_ms and (best_dt is None or dt < best_dt):
                best = a
                best_dt = dt
        if best is not None:
            used_ai.add(best["_j"])
            matches.append({"manual": m, "ai": best, "dt_ms": best_dt, "kind": "exact_type"})
        else:
            # Pass 2 candidate: same coarse family (shot/rebound/etc) — disagreement
            best2 = None
            best2_dt = None
            for a in ai:
                if a["_j"] in used_ai:
                    continue
                if a["_coarse"] != m["_coarse"]:
                    continue
                dt = abs(a["_ts"] - m["_ts"])
                if dt <= tolerance_ms and (best2_dt is None or dt < best2_dt):
                    best2 = a
                    best2_dt = dt
            if best2 is not None:
                used_ai.add(best2["_j"])
                disagreements.append({"manual": m, "ai": best2, "dt_ms": best2_dt})
            else:
                misses.append(m)

    extras = [a for a in ai if a["_j"] not in used_ai]
    return matches, extras, misses, disagreements


def pr_summary(matches, extras, misses, disagreements):
    tp = len(matches)
    # disagreements count as partial: still a detection near a manual event, but wrong label/result
    fp = len(extras)
    fn = len(misses)
    # Treat disagreements as neither full TP nor full FN for strict metrics;
    # also report a "loose" recall that counts disagreements as found.
    denom_p = tp + fp
    denom_r = tp + fn + len(disagreements)
    precision = (tp / denom_p) if denom_p else 0.0
    recall_strict = (tp / (tp + fn + len(disagreements))) if (tp + fn + len(disagreements)) else 0.0
    recall_loose = ((tp + len(disagreements)) / (tp + fn + len(disagreements))) if (tp + fn + len(disagreements)) else 0.0
    f1 = (2 * precision * recall_strict / (precision + recall_strict)) if (precision + recall_strict) else 0.0
    return {
        "true_positives": tp,
        "false_positives_ai_extras": fp,
        "false_negatives_ai_misses": fn,
        "disagreements_near_but_wrong_label": len(disagreements),
        "precision_exact": round(precision, 4),
        "recall_exact": round(recall_strict, 4),
        "recall_loose_includes_disagreements": round(recall_loose, 4),
        "f1_exact": round(f1, 4),
        "match_tolerance_ms": MATCH_TOLERANCE_MS,
    }


def load_events_for_analysis_key(analysis_key: str) -> list[dict]:
    """Load AI events for one analysis_key only (avoid API relational_game_id merge)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE game_id = ? ORDER BY timestamp_ms ASC, id ASC",
        (analysis_key,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pick_best_analysis_key(primary_key: str) -> tuple[str, dict]:
    """Prefer completed video-8 run with most events (99/2875 rerun)."""
    info = {"selected": primary_key, "candidates": []}
    if not DB_PATH.exists():
        return primary_key, info
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, analysis_key, status, started_at, completed_at, base_analysis_key,
               source_video_id, run_label, run_kind
        FROM analysis_runs
        WHERE source_video_id = 8
           OR analysis_key LIKE ?
           OR base_analysis_key LIKE ?
        ORDER BY id DESC
        """,
        ("%gam30b09cbb4f%", "%gam30b09cbb4f%"),
    )
    runs = [dict(r) for r in cur.fetchall()]
    for run in runs:
        ak = run["analysis_key"]
        cur.execute("SELECT COUNT(*) AS c FROM events WHERE game_id = ?", (ak,))
        ec = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM detections WHERE game_id = ?", (ak,))
        dc = cur.fetchone()["c"]
        cur.execute(
            "SELECT MIN(timestamp_ms) AS mn, MAX(timestamp_ms) AS mx FROM events WHERE game_id = ?",
            (ak,),
        )
        span = cur.fetchone()
        run["event_count"] = ec
        run["detection_count"] = dc
        run["event_ts_min_ms"] = span["mn"]
        run["event_ts_max_ms"] = span["mx"]
        info["candidates"].append(run)
    conn.close()
    completed = [r for r in info["candidates"] if (r.get("status") or "").lower() == "completed"]
    pool = [r for r in completed if (r.get("event_count") or 0) > 0] or completed or info["candidates"]
    if pool:
        best = max(pool, key=lambda r: (r.get("event_count") or 0, r.get("detection_count") or 0, r.get("id") or 0))
        info["selected"] = best["analysis_key"]
        info["reason"] = "max events then detections among completed video-8 runs"
        return best["analysis_key"], info
    return primary_key, info


def row_brief(r):
    return {
        "time": fmt_mmss(time_to_seconds(r.get("start"))),
        "team": r.get("team"),
        "player": normalize_player_name(r.get("player")),
        "eventtype": r.get("eventtype"),
        "result": r.get("result"),
        "label": r.get("label"),
    }


def ai_brief(r):
    return {
        "time": fmt_mmss((r.get("_ts") or int(float(r.get("start") or 0) * 1000)) / 1000),
        "player": normalize_player_name(r.get("player")),
        "eventtype": r.get("eventtype"),
        "result": r.get("result"),
        "source_event_id": r.get("source_event_id"),
    }


def count_based_surplus_deficit(manual_rows, ai_rows):
    """Bag-of-labels comparison when timestamps cannot align."""
    man = category_counts(manual_rows)
    ai = category_counts(ai_rows)
    keys = sorted(set(man) | set(ai))
    rows = []
    ai_extra_total = 0
    ai_miss_total = 0
    overlap = 0
    for k in keys:
        m = man.get(k, 0)
        a = ai.get(k, 0)
        matched = min(m, a)
        extra = max(0, a - m)
        miss = max(0, m - a)
        overlap += matched
        ai_extra_total += extra
        ai_miss_total += miss
        rows.append(
            {
                "Category": k,
                "Manual": m,
                "AI": a,
                "Matched_by_count": matched,
                "AI_extra": extra,
                "AI_miss": miss,
            }
        )
    total_m = sum(man.values())
    total_a = sum(ai.values())
    precision = (overlap / total_a) if total_a else 0.0
    recall = (overlap / total_m) if total_m else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "by_category": rows,
        "matched_by_count": overlap,
        "ai_extras_by_count": ai_extra_total,
        "ai_misses_by_count": ai_miss_total,
        "precision_count_bag": round(precision, 4),
        "recall_count_bag": round(recall, 4),
        "f1_count_bag": round(f1, 4),
        "note": (
            "Count-bag metrics ignore time/player identity: "
            "min(manual, AI) per category counts as matched."
        ),
    }


def main():
    videos = get_json("/api/videos")
    vlist = videos if isinstance(videos, list) else videos.get("videos", [])
    v8 = next(v for v in vlist if v.get("id") == 8)
    primary_key = v8.get("analysis_key")
    analysis_key, run_info = pick_best_analysis_key(primary_key)

    ft = get_json("/api/film-tool-games")
    games = ft.get("games") if isinstance(ft, dict) else ft
    game = next(g for g in games if g.get("id") == CLIENT_GAME_ID)
    all_manual = game.get("rows") or []
    liberty = (game.get("ourTeam") or "Liberty").strip() or "Liberty"

    manual_q1 = filter_manual_q1_rows(all_manual)
    events = load_events_for_analysis_key(analysis_key)
    ai_q1_raw = filter_ai_events_to_window(events)
    # Because this run's timestamps only span ~22s, the Q1 window keeps ALL of them.
    ai_rows = convert_ai_events_to_stat_rows(ai_q1_raw, team_name=liberty)

    manual_for_box = [r for r in manual_q1 if r.get("eventtype") in STAT_EVENTTYPES]

    # Many Liberty tags have empty team=""; treat non-Opponent as Liberty for attribution.
    def normalize_manual_team(row):
        team = (row.get("team") or "").strip()
        if team in {liberty, "Our Team"}:
            return liberty
        if team == "Opponent":
            return "Opponent"
        if not team:
            return liberty  # blank team on this game = Liberty side
        return team

    manual_norm = [{**r, "team": normalize_manual_team(r)} for r in manual_for_box]

    man_acc = stat_accumulator(manual_norm)
    ai_acc = stat_accumulator(ai_rows)

    man_all = empty_stats()
    for team_stats in man_acc["byTeam"].values():
        for k, v in team_stats.items():
            man_all[k] = man_all.get(k, 0) + v
    ai_team = ai_acc["byTeam"].get(liberty) or ai_acc["byTeam"].get("Our Team") or empty_stats()

    team_compare_all_manual = []
    for stat in COMPARE_STATS:
        key = TEAM_STAT_KEY_MAP[stat]
        mv = man_all.get(key, 0)
        av = ai_team.get(key, 0)
        team_compare_all_manual.append(
            {"Stat": stat, "Manual_all_teams": mv, "AI": av, "Delta_manual_minus_ai": mv - av}
        )

    team_compare_liberty_only = []
    man_lib_stats = man_acc["byTeam"].get(liberty) or man_acc["byTeam"].get("Our Team") or empty_stats()
    for stat in COMPARE_STATS:
        key = TEAM_STAT_KEY_MAP[stat]
        mv = man_lib_stats.get(key, 0)
        av = ai_team.get(key, 0)
        team_compare_liberty_only.append(
            {"Stat": stat, "Manual_Liberty": mv, "AI": av, "Delta": mv - av}
        )

    man_cat = category_counts(manual_norm)
    ai_cat = category_counts(ai_rows)
    all_cat_keys = sorted(set(man_cat) | set(ai_cat))
    category_compare = [
        {
            "Category": k,
            "Manual": man_cat.get(k, 0),
            "AI": ai_cat.get(k, 0),
            "Delta": man_cat.get(k, 0) - ai_cat.get(k, 0),
        }
        for k in all_cat_keys
    ]

    matches, extras, misses, disagreements = event_level_match(manual_norm, ai_rows)
    metrics_time = pr_summary(matches, extras, misses, disagreements)
    metrics_bag = count_based_surplus_deficit(manual_norm, ai_rows)

    ai_ts_vals = [int(e.get("timestamp_ms") or 0) for e in events]
    ai_ts_min = min(ai_ts_vals) if ai_ts_vals else None
    ai_ts_max = max(ai_ts_vals) if ai_ts_vals else None
    time_align_ok = bool(ai_ts_max and ai_ts_max >= 60_000)  # at least 1 minute of span

    manual_by_team = Counter(r.get("team") for r in manual_norm)
    manual_by_team_raw = Counter((r.get("team") or "(blank)") for r in manual_for_box)
    manual_by_quarter = Counter((r.get("quarter") or "?") for r in all_manual)
    ai_raw_types = Counter(str(e.get("event_type") or "?") for e in events)

    # Manual Liberty vs Opponent category split (after blank→Liberty)
    man_liberty_rows = [r for r in manual_norm if r.get("team") == liberty]
    man_opp_rows = [r for r in manual_norm if r.get("team") == "Opponent"]

    selected_run = next(
        (c for c in run_info.get("candidates", []) if c.get("analysis_key") == analysis_key),
        {},
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "empty_pdf_note": (
            "Empty.pdf is a 1-page essentially blank Chrome print (no readable table/body text). "
            "It documents an empty UI state (likely Film Tool Reports / compare with nothing rendered)."
        ),
        "game": {
            "client_game_id": CLIENT_GAME_ID,
            "opponent": game.get("opponent"),
            "our_team": liberty,
            "analysis_game_id": game.get("analysisGameId"),
            "video_id": 8,
            "video_analysis_key": primary_key,
            "selected_analysis_key": analysis_key,
            "selected_run_event_count": selected_run.get("event_count"),
            "selected_run_detection_count": selected_run.get("detection_count"),
            "run_selection": run_info,
        },
        "window": {
            "label": Q1_COMPARE_LABEL,
            "end_sec": Q1_COMPARE_END_SEC,
            "end_ms": Q1_COMPARE_END_MS,
        },
        "timestamp_alignment": {
            "usable_for_time_matching": time_align_ok,
            "ai_event_ts_min_ms": ai_ts_min,
            "ai_event_ts_max_ms": ai_ts_max,
            "ai_span_sec": round((ai_ts_max - ai_ts_min) / 1000, 2) if ai_ts_min is not None else None,
            "manual_q1_span_sec": Q1_COMPARE_END_SEC,
            "warning": (
                "AI timestamps for the preferred 99-event / 2875-det rerun only span ~22s "
                "(not a full Q1 timeline). Film Tool Q1 window (0–871s) therefore includes "
                "all AI events, but event-level time matching vs manual tags is not meaningful. "
                "Prefer count-bag precision/recall below. "
                "Also: GET /api/events/<key> merges relational_game_id across reruns (40+99=139); "
                "this report uses DB rows for the selected analysis_key only."
            ),
        },
        "counts": {
            "manual_total_tags_saved": len(all_manual),
            "manual_q1_filtered_stat_tags": len(manual_for_box),
            "manual_q1_including_non_stat": len(manual_q1),
            "manual_liberty_stat_tags": len(man_liberty_rows),
            "manual_opponent_stat_tags": len(man_opp_rows),
            "manual_by_team": dict(manual_by_team),
            "manual_by_team_raw_before_blank_fill": dict(manual_by_team_raw),
            "manual_all_tags_by_quarter": dict(manual_by_quarter),
            "ai_events_total_for_run": len(events),
            "ai_events_in_q1_window": len(ai_q1_raw),
            "ai_stat_rows_after_convert": len(ai_rows),
            "ai_raw_types_full_run": dict(ai_raw_types),
        },
        "team_totals_manual_all_teams_vs_ai": team_compare_all_manual,
        "team_totals_manual_liberty_only_vs_ai": team_compare_liberty_only,
        "category_counts": category_compare,
        "event_match_metrics_time_based": metrics_time,
        "event_match_metrics_count_bag": metrics_bag,
        "matches_sample": [
            {
                "manual": row_brief(m["manual"]),
                "ai": ai_brief(m["ai"]),
                "dt_ms": m["dt_ms"],
            }
            for m in matches[:25]
        ],
        "ai_misses_manual_truth_not_found_time_based": [row_brief(m) for m in misses],
        "ai_extras_no_manual_nearby_time_based": [ai_brief(a) for a in extras],
        "disagreements_time_based": [
            {
                "manual": row_brief(d["manual"]),
                "ai": ai_brief(d["ai"]),
                "dt_ms": d["dt_ms"],
            }
            for d in disagreements
        ],
        "method": {
            "source": "Film Tool generateManualVsAiQ1Report filters + converters",
            "ai_event_source": "film_analysis.db events WHERE game_id = selected analysis_key",
            "match_algorithm_time": (
                f"Greedy nearest neighbor within ±{MATCH_TOLERANCE_MS}ms "
                "(not usable when AI timeline collapsed)"
            ),
            "match_algorithm_count_bag": metrics_bag["note"],
            "notes": [
                "Many Liberty tags have blank team; report maps blank→Liberty for attribution.",
                "Manual tags are ground truth.",
                "AI rebounds map to DefRebound in Film Tool converter (no O/D split).",
                "AI make/miss/possession_change events are skipped (duplicates of shot rows).",
                "AI has no quarter field; Q1 filter is time window 0–871s.",
            ],
        },
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = []
    lines.append("# Manual vs AI — Q1 Comparison (Wilder)")
    lines.append("")
    lines.append(f"Generated: {payload['generated_at']}")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(
        f"**Manual (truth):** {len(all_manual)} saved tags on `{CLIENT_GAME_ID}` "
        f"(vs Wilder), of which **{len(manual_norm)}** are Q1 action/stat tags "
        f"({len(man_liberty_rows)} Liberty / {len(man_opp_rows)} Opponent; blank team→Liberty) "
        f"after Film Tool Q1 filters "
        f"(drops Start/End QTR; window `{Q1_COMPARE_LABEL}`)."
    )
    lines.append("")
    lines.append(
        f"**AI (selected run):** `{analysis_key}` — "
        f"**{selected_run.get('event_count')} events / {selected_run.get('detection_count')} dets** "
        f"(2026-07-11 rerun). After Film Tool conversion: **{len(ai_rows)}** comparable stat rows "
        f"(skipped make/miss/possession_change)."
    )
    lines.append("")
    lines.append(
        f"**Alignment caveat:** AI `timestamp_ms` only spans "
        f"**{(ai_ts_min or 0)/1000:.1f}s–{(ai_ts_max or 0)/1000:.1f}s** (~{payload['timestamp_alignment']['ai_span_sec']}s), "
        "not a full Q1. Time-based match P/R is **not usable**. "
        "Primary quality metrics below are **count-bag** (category totals)."
    )
    lines.append("")
    bag = metrics_bag
    lines.append(
        f"**Count-bag summary:** matched **{bag['matched_by_count']}**, "
        f"AI extras **{bag['ai_extras_by_count']}**, "
        f"AI misses **{bag['ai_misses_by_count']}** → "
        f"precision **{bag['precision_count_bag']:.1%}**, "
        f"recall **{bag['recall_count_bag']:.1%}**, "
        f"F1 **{bag['f1_count_bag']:.1%}**."
    )
    lines.append("")
    lines.append("### Empty.pdf")
    lines.append("")
    lines.append(payload["empty_pdf_note"])
    lines.append("")
    lines.append("## Counts by category (manual truth vs AI)")
    lines.append("")
    lines.append("| Category | Manual | AI | Matched | AI extra | AI miss |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in bag["by_category"]:
        lines.append(
            f"| {row['Category']} | {row['Manual']} | {row['AI']} | "
            f"{row['Matched_by_count']} | {row['AI_extra']} | {row['AI_miss']} |"
        )
    lines.append("")
    lines.append("## Team box totals (manual = all teams in Q1 tags)")
    lines.append("")
    lines.append("| Stat | Manual (all) | AI | Delta (M−AI) |")
    lines.append("|---|---:|---:|---:|")
    for row in team_compare_all_manual:
        lines.append(
            f"| {row['Stat']} | {row['Manual_all_teams']} | {row['AI']} | {row['Delta_manual_minus_ai']} |"
        )
    lines.append("")
    lines.append("## Team box totals (Film Tool UI style: Liberty-only manual)")
    lines.append("")
    lines.append(
        "_Note: Film Tool assigns all converted AI rows to Our Team, so Liberty-only "
        "manual understates AI if opponent actions are in the AI stream._"
    )
    lines.append("")
    lines.append("| Stat | Manual (Liberty) | AI | Delta |")
    lines.append("|---|---:|---:|---:|")
    for row in team_compare_liberty_only:
        lines.append(
            f"| {row['Stat']} | {row['Manual_Liberty']} | {row['AI']} | {row['Delta']} |"
        )
    lines.append("")
    lines.append("## Precision / recall")
    lines.append("")
    lines.append("### Count-bag (preferred given broken AI timeline)")
    lines.append("")
    lines.append("```")
    lines.append(json.dumps({k: v for k, v in bag.items() if k != "by_category"}, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("### Time-based (±8s) — diagnostic only")
    lines.append("")
    lines.append("```")
    lines.append(json.dumps(metrics_time, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(
        f"Time-based found {metrics_time['true_positives']} matches / "
        f"{metrics_time['false_negatives_ai_misses']} misses / "
        f"{metrics_time['false_positives_ai_extras']} extras — expected near-zero overlap "
        "because AI clocks stop around 22s while manual Q1 runs to 14:31."
    )
    lines.append("")
    lines.append("## Method notes")
    lines.append("")
    for n in payload["method"]["notes"]:
        lines.append(f"- {n}")
    lines.append(f"- {payload['timestamp_alignment']['warning']}")
    lines.append(f"- Count-bag: {payload['method']['match_algorithm_count_bag']}")
    lines.append("")
    lines.append(f"JSON twin: `{OUT_JSON.name}`")
    lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    print(
        json.dumps(
            {
                "manual_q1_stat_tags": len(manual_for_box),
                "ai_q1_stat_rows": len(ai_rows),
                "ai_run_events": len(events),
                "ai_run_dets": selected_run.get("detection_count"),
                "count_bag_matched": bag["matched_by_count"],
                "count_bag_ai_extras": bag["ai_extras_by_count"],
                "count_bag_ai_misses": bag["ai_misses_by_count"],
                "precision": bag["precision_count_bag"],
                "recall": bag["recall_count_bag"],
                "f1": bag["f1_count_bag"],
                "time_align_ok": time_align_ok,
                "analysis_key": analysis_key,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
