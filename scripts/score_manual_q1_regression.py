#!/usr/bin/env python3
"""Score AI events vs manual Q1 ground truth; fail on precision/recall regression.

Offline (no Flask / no GPU): reads manual tags from film_tool_games or backup JSON,
and AI events from film_analysis.db for the Q1 GPU rerun analysis key.

Usage:
  python tag-exports/score_manual_q1_regression.py
  python tag-exports/score_manual_q1_regression.py --write-report
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manual_vs_ai_q1_compare import (  # noqa: E402
    MATCH_TOLERANCE_MS,
    Q1_COMPARE_END_MS,
    Q1_COMPARE_END_SEC,
    STAT_EVENTTYPES,
    convert_ai_events_to_stat_rows,
    event_level_match,
    filter_ai_events_to_window,
    filter_manual_q1_rows,
    pr_summary,
)

DB_PATH = ROOT / "film_analysis.db"
BACKUP_PATH = Path(__file__).resolve().parent / "liberty-manual-tags-backup.json"
CLIENT_GAME_ID = "game-1784304093435"
DEFAULT_ANALYSIS_KEY = (
    "nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_"
    "trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754"
)

# Baseline before precision filters (manual_vs_ai_q1_side_by_side.json).
BASELINE = {
    "exact_matches": 22,
    "manual_only": 31,
    "ai_only": 2726,
    "precision_exact": 0.008,
    "recall_exact": 0.4151,
    "f1_exact": 0.0157,
}

# Regression gates: precision must jump; recall / exact matches must not collapse.
MIN_PRECISION = 0.08
MIN_RECALL = 0.25
MIN_EXACT = 12
MAX_AI_ONLY = 400


def load_manual_rows(db_path: Path) -> tuple[list[dict], str]:
    liberty = "Liberty"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT state_json FROM film_tool_games WHERE client_game_id=?",
            (CLIENT_GAME_ID,),
        ).fetchone()
        conn.close()
        if row:
            state = json.loads(row["state_json"])
            liberty = (state.get("ourTeam") or "Liberty").strip() or "Liberty"
            return state.get("rows") or [], liberty

    if not BACKUP_PATH.exists():
        raise SystemExit(f"No manual tags in DB or backup at {BACKUP_PATH}")
    backup = json.loads(BACKUP_PATH.read_text(encoding="utf-8"))
    games = backup.get("savedGames") or []
    game = next((g for g in games if g.get("id") == CLIENT_GAME_ID), None)
    if not game:
        raise SystemExit(f"Game {CLIENT_GAME_ID} not found in backup")
    liberty = (game.get("ourTeam") or "Liberty").strip() or "Liberty"
    return game.get("rows") or [], liberty


def normalize_manual_team(row: dict, liberty: str) -> dict:
    team = (row.get("team") or "").strip()
    if team in {liberty, "Our Team"}:
        team = liberty
    elif team == "Opponent":
        team = "Opponent"
    elif not team:
        team = liberty
    return {**row, "team": team}


def load_ai_events(db_path: Path, analysis_key: str) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE game_id = ? ORDER BY timestamp_ms ASC, id ASC",
        (analysis_key,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def score(analysis_key: str, db_path: Path) -> dict:
    all_manual, liberty = load_manual_rows(db_path)
    manual_q1 = filter_manual_q1_rows(all_manual)
    manual_for_box = [r for r in manual_q1 if r.get("eventtype") in STAT_EVENTTYPES]
    manual_norm = [normalize_manual_team(r, liberty) for r in manual_for_box]

    events = load_ai_events(db_path, analysis_key)
    ai_q1 = filter_ai_events_to_window(events)
    ai_rows = convert_ai_events_to_stat_rows(ai_q1, team_name=liberty)

    matches, extras, misses, disagreements = event_level_match(manual_norm, ai_rows)
    metrics = pr_summary(matches, extras, misses, disagreements)

    return {
        "analysis_key": analysis_key,
        "manual_action_tags": len(manual_norm),
        "ai_comparable_events": len(ai_rows),
        "ai_raw_events_in_window": len(ai_q1),
        "exact_matches": len(matches),
        "manual_only": len(misses),
        "ai_only": len(extras),
        "disagreements": len(disagreements),
        "precision_exact": metrics["precision_exact"],
        "recall_exact": metrics["recall_exact"],
        "f1_exact": metrics["f1_exact"],
        "match_tolerance_ms": MATCH_TOLERANCE_MS,
        "q1_end_sec": Q1_COMPARE_END_SEC,
        "baseline": BASELINE,
    }


def evaluate_gates(result: dict) -> list[str]:
    failures = []
    if result["precision_exact"] < MIN_PRECISION:
        failures.append(
            f"precision {result['precision_exact']:.4f} < min {MIN_PRECISION}"
        )
    if result["recall_exact"] < MIN_RECALL:
        failures.append(f"recall {result['recall_exact']:.4f} < min {MIN_RECALL}")
    if result["exact_matches"] < MIN_EXACT:
        failures.append(f"exact_matches {result['exact_matches']} < min {MIN_EXACT}")
    if result["ai_only"] > MAX_AI_ONLY:
        failures.append(f"ai_only {result['ai_only']} > max {MAX_AI_ONLY}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-key", default=DEFAULT_ANALYSIS_KEY)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write tag-exports/manual_q1_regression_score.json",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Print score but always exit 0 (for diagnostics)",
    )
    args = parser.parse_args(argv)

    result = score(args.analysis_key, Path(args.db))
    failures = evaluate_gates(result)
    result["gates"] = {
        "min_precision": MIN_PRECISION,
        "min_recall": MIN_RECALL,
        "min_exact": MIN_EXACT,
        "max_ai_only": MAX_AI_ONLY,
        "passed": not failures,
        "failures": failures,
    }
    result["delta_vs_baseline"] = {
        "exact_matches": result["exact_matches"] - BASELINE["exact_matches"],
        "manual_only": result["manual_only"] - BASELINE["manual_only"],
        "ai_only": result["ai_only"] - BASELINE["ai_only"],
        "precision_exact": round(result["precision_exact"] - BASELINE["precision_exact"], 4),
        "recall_exact": round(result["recall_exact"] - BASELINE["recall_exact"], 4),
        "f1_exact": round(result["f1_exact"] - BASELINE["f1_exact"], 4),
    }

    print(json.dumps(result, indent=2))

    if args.write_report:
        out = Path(__file__).resolve().parent / "manual_q1_regression_score.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)

    if failures and not args.no_fail:
        print("REGRESSION FAIL:", "; ".join(failures), file=sys.stderr)
        return 1
    print("REGRESSION PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
