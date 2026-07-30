#!/usr/bin/env python3
"""Compare AI events to Hoopsalytics PBP ground truth (Film Tool tags).

Teaching loop:
  1) Truth = imported PBP rows (Video Time)
  2) AI = events for an analysis_key
  3) Match within tolerance → scorecard
  4) Over/under counts feed the next teach/calibrate pass

Usage:
  py -3.12 scripts/compare_ai_to_hoops_pbp.py --film-id hoopsalytics-grace-2026-01-10 --analysis-key KEY
  py -3.12 scripts/compare_ai_to_hoops_pbp.py --film-id hoopsalytics-grace-2026-01-10 --analysis-key KEY --end-ms 980000
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tag-exports"))

from manual_vs_ai_q1_compare import (  # noqa: E402
    convert_ai_events_to_stat_rows,
    match_key,
    time_to_seconds,
)

DB_PATH = ROOT / "film_analysis.db"
STAT_TYPES = {"2PT", "3PT", "FT", "Assist", "Steal", "Turnover", "Foul", "Block", "OffRebound", "DefRebound"}


def load_truth_rows(conn: sqlite3.Connection, film_id: str) -> list[dict]:
    row = conn.execute(
        "SELECT state_json FROM film_tool_games WHERE client_game_id = ?",
        (film_id,),
    ).fetchone()
    if not row:
        raise SystemExit(f"Film Tool game not found: {film_id}")
    state = json.loads(row[0] or "{}")
    rows = state.get("rows") or []
    out = []
    for r in rows:
        et = str(r.get("eventtype") or "")
        if et not in STAT_TYPES:
            continue
        if str(r.get("team") or "") not in {"Liberty", "Our Team"}:
            # Compare Liberty side primarily; opponent optional later
            continue
        out.append(r)
    return out


def load_ai_events(conn: sqlite3.Connection, analysis_key: str) -> list[dict]:
    rows = conn.execute(
        """SELECT id, game_id, event_type, player, shot_result, timestamp_ms,
                  confidence, details_json, source_type
             FROM events
            WHERE game_id = ?
              AND COALESCE(source_type, 'ai') = 'ai'
            ORDER BY timestamp_ms, id""",
        (analysis_key,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "game_id": r[1],
            "event_type": r[2],
            "player": r[3],
            "shot_result": r[4],
            "timestamp_ms": r[5],
            "confidence": r[6],
            "details_json": r[7],
            "source_type": r[8] or "ai",
        }
        for r in rows
    ]


def filter_by_end(rows: list[dict], end_ms: int | None, *, is_truth: bool) -> list[dict]:
    if end_ms is None:
        return rows
    out = []
    for r in rows:
        if is_truth:
            ms = int(round(time_to_seconds(r.get("start")) * 1000))
        else:
            ms = int(r.get("timestamp_ms") or 0)
        if 0 <= ms <= end_ms:
            out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--film-id", required=True, help="Film Tool client id, e.g. hoopsalytics-grace-2026-01-10")
    ap.add_argument("--analysis-key", required=True)
    ap.add_argument("--end-ms", type=int, default=None)
    ap.add_argument("--tolerance-ms", type=int, default=5000)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    conn = sqlite3.connect(str(args.db))
    truth = filter_by_end(load_truth_rows(conn, args.film_id), args.end_ms, is_truth=True)
    ai_raw = filter_by_end(load_ai_events(conn, args.analysis_key), args.end_ms, is_truth=False)
    conn.close()

    ai_rows = convert_ai_events_to_stat_rows(ai_raw, team_name="Liberty")
    # Keep only Liberty-comparable types
    ai_rows = [r for r in ai_rows if r.get("eventtype") in STAT_TYPES]

    manuals = [
        {"row": r, "sec": time_to_seconds(r.get("start")), "key": match_key(r), "used": False}
        for r in truth
    ]
    ais = [
        {"row": r, "sec": time_to_seconds(r.get("start")), "key": match_key(r), "used": False}
        for r in ai_rows
    ]
    matched = 0
    disagree = 0
    for m in manuals:
        best = None
        best_d = None
        for a in ais:
            if a["used"]:
                continue
            d = abs(a["sec"] - m["sec"]) * 1000
            if d > args.tolerance_ms:
                continue
            if best_d is None or d < best_d:
                best = a
                best_d = d
        if best is None:
            continue
        best["used"] = True
        m["used"] = True
        if best["key"] == m["key"]:
            matched += 1
        else:
            disagree += 1

    miss = sum(1 for m in manuals if not m["used"])
    extra = sum(1 for a in ais if not a["used"])
    total_truth = len(manuals)
    precision = matched / max(matched + extra + disagree, 1)
    recall = matched / max(total_truth, 1)

    truth_counts = Counter(match_key(r) for r in truth)
    ai_counts = Counter(match_key(r) for r in ai_rows)

    print("=" * 60)
    print("AI vs Hoopsalytics PBP (teaching scorecard)")
    print("=" * 60)
    print(f"Film Tool truth: {args.film_id}")
    print(f"AI analysis:     {args.analysis_key}")
    if args.end_ms:
        print(f"Window:          0 .. {args.end_ms} ms")
    print(f"Tolerance:       {args.tolerance_ms} ms")
    print()
    print(f"Truth events (Liberty stats): {total_truth}")
    print(f"AI events (Liberty stats):    {len(ais)}")
    print(f"Exact matches:                {matched}")
    print(f"Near time, wrong type:        {disagree}")
    print(f"Missed by AI (truth only):    {miss}")
    print(f"Extra AI (false positives):   {extra}")
    print(f"Precision: {precision:.1%}   Recall: {recall:.1%}")
    print()
    print("If precision/recall are low, AI is wrong vs downloaded truth — that IS teaching signal.")
    print()
    print("Top truth keys:", truth_counts.most_common(8))
    print("Top AI keys:   ", ai_counts.most_common(8))

    out = ROOT / "data" / "hoopsalytics" / f"compare_{args.film_id.replace('-', '_')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "film_id": args.film_id,
        "analysis_key": args.analysis_key,
        "end_ms": args.end_ms,
        "tolerance_ms": args.tolerance_ms,
        "truth": total_truth,
        "ai": len(ais),
        "exact": matched,
        "disagree": disagree,
        "miss": miss,
        "extra": extra,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
