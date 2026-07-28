#!/usr/bin/env python3
"""Teach from Hoopsalytics/MaxPreps box scores.

Principle: if AI analysis does not match the box score, the AI is wrong.
Box scores have no timestamps, but they are exact totals — that is still
teaching:

  - Overcount  → false positives; calibrator keeps top-N by confidence
  - Undercount → recall debt; lower floors / run denser detection later

Usage:
  py -3.12 scripts/teach_from_boxscore.py
  py -3.12 scripts/teach_from_boxscore.py --write-model
  py -3.12 scripts/teach_from_boxscore.py --write-model --compare-ai
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxscore_constraints import (  # noqa: E402
    DEFAULT_BOXSCORE_MODEL,
    HOOPS_DIR,
    aggregate_ai_caps,
    build_model_from_hoops_dir,
    compare_caps,
)

DB_PATH = ROOT / "film_analysis.db"
REPORT_PATH = ROOT / "data" / "hoopsalytics" / "boxscore_teach_report.json"


def _load_ai_events(conn: sqlite3.Connection, game_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT id, game_id, event_type, player, shot_result, timestamp_ms,
                  confidence, details_json, source_type
             FROM events
            WHERE game_id = ?
              AND COALESCE(source_type, 'ai') = 'ai'
            ORDER BY timestamp_ms ASC, id ASC""",
        (game_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
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
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Teach AI caps from MaxPreps/Hoopsalytics box scores")
    ap.add_argument("--hoops-dir", type=Path, default=HOOPS_DIR)
    ap.add_argument("--write-model", action="store_true", help=f"Write {DEFAULT_BOXSCORE_MODEL}")
    ap.add_argument("--compare-ai", action="store_true", help="Compare existing AI events to box scores")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    model = build_model_from_hoops_dir(args.hoops_dir)
    games = model.get("boxscore_by_game") or {}
    print(f"Loaded {len(games)} reference box scores from {args.hoops_dir}")
    print(model.get("principle"))
    print()

    report = {
        "principle": model.get("principle"),
        "game_count": len(games),
        "games": [],
    }

    conn = None
    if args.compare_ai and args.db.exists():
        conn = sqlite3.connect(str(args.db))

    for game_id, caps in sorted(games.items(), key=lambda kv: (kv[1].get("date") or "", kv[0])):
        opp = caps.get("opponent") or game_id
        date = caps.get("date") or ""
        team = caps.get("team") or {}
        pts = team.get("points")
        row = {
            "game_id": game_id,
            "opponent": opp,
            "date": date,
            "truth_points": pts,
            "truth_3pm": team.get("3pt_make"),
            "truth_ftm": team.get("ft_make"),
            "ai_event_count": 0,
            "compare": None,
        }
        if conn:
            events = _load_ai_events(conn, game_id)
            row["ai_event_count"] = len(events)
            if events:
                ai_caps = aggregate_ai_caps(events)
                diff = compare_caps(caps, ai_caps)
                row["compare"] = diff
                row["ai_points_est"] = (
                    2 * int((ai_caps.get("team") or {}).get("2pt_make") or 0)
                    + 3 * int((ai_caps.get("team") or {}).get("3pt_make") or 0)
                    + 1 * int((ai_caps.get("team") or {}).get("ft_make") or 0)
                )
                status = "MISMATCH — AI wrong" if diff.get("ai_wrong") else "MATCH"
                print(
                    f"  {date}  {opp:22} truthPTS={pts}  AI_events={len(events)}  "
                    f"AI_PTS≈{row['ai_points_est']}  {status}"
                )
                if diff.get("team_overcount"):
                    print(f"      overcount: {diff['team_overcount']}")
                if diff.get("team_undercount"):
                    print(f"      undercount (recall debt): {diff['team_undercount']}")
            else:
                print(f"  {date}  {opp:22} truthPTS={pts}  (no AI events yet — caps ready)")
        else:
            print(
                f"  {date}  {opp:22} PTS={pts}  "
                f"3PM={team.get('3pt_make')}  FTM={team.get('ft_make')}  "
                f"players={len(caps.get('by_jersey') or {})}"
            )
        report["games"].append(row)

    if conn:
        conn.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {REPORT_PATH}")

    if args.write_model:
        DEFAULT_BOXSCORE_MODEL.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_BOXSCORE_MODEL.write_text(json.dumps(model, indent=2), encoding="utf-8")
        print(f"Wrote model: {DEFAULT_BOXSCORE_MODEL}")
        print("Postprocess will cap AI events to these totals (highest confidence kept).")
    else:
        print("\nDry run only. Re-run with --write-model to activate caps in AI postprocess.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
