#!/usr/bin/env python3
"""Backfill scheduled-game scores from the MaxPreps team schedule page."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maxpreps_web import apply_results_to_season, fetch_url, parse_schedule_results, schedule_url  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill MaxPreps scores onto scheduled games")
    parser.add_argument("--season-id", type=int, default=3)
    parser.add_argument("--gender", choices=("boys", "girls"), default="boys")
    parser.add_argument("--season-start-year", type=int, default=2025)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    html = fetch_url(schedule_url(args.gender))
    parsed = parse_schedule_results(html, season_start_year=args.season_start_year)
    print(f"Parsed {len(parsed)} MaxPreps results", flush=True)
    if args.dry_run:
        for game in parsed:
            print(f"  {game['game_date']} {game['result']} {game['liberty_score']}-{game['opponent_score']} vs {game['opponent_name']}")
        return 0

    from app import app
    from helpers import get_db, save_scheduled_game_record

    with app.app_context():
        db = get_db()
        matched, unmatched = apply_results_to_season(db, args.season_id, parsed, save_scheduled_game_record)
        print(f"Wrote scores for {matched} scheduled games")
        if unmatched:
            print("Unmatched:", "; ".join(unmatched))
    return 0 if not unmatched else 1


if __name__ == "__main__":
    raise SystemExit(main())
