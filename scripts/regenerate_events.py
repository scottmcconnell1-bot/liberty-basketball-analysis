#!/usr/bin/env python3
"""Regenerate events and enhanced analysis from existing detections."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate events for an analysis key")
    parser.add_argument("analysis_key", help="Analysis key / game_id used in detections")
    parser.add_argument("--db", default=str(ROOT / "film_analysis.db"), help="SQLite database path")
    parser.add_argument("--video", help="Optional video path for enhanced analysis FPS lookup")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db, timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT game_id FROM analysis_runs WHERE analysis_key=? ORDER BY id DESC LIMIT 1",
        (args.analysis_key,),
    ).fetchone()
    relational_game_id = row["game_id"] if row else None
    # Do not flip a live detector run to "Regenerating…" — that stalls the teach loop.
    conn.execute(
        """UPDATE analysis_runs
           SET status='running', progress_pct=50, progress_step='Regenerating events…'
           WHERE analysis_key=?
             AND NOT (status='running' AND COALESCE(progress_step,'') LIKE 'Detecting%')""",
        (args.analysis_key,),
    )
    conn.commit()
    conn.close()

    from app import app
    from event_generator import main as generate_events

    print(f"Regenerating events for {args.analysis_key}...", flush=True)
    with app.app_context():
        if generate_events(
            args.analysis_key, args.db, relational_game_id=relational_game_id
        ) is False:
            print("Event generation failed.", file=sys.stderr)
            return 1

        if args.video:
            import cv2
            from film_analysis import run_enhanced_analysis

            cap = cv2.VideoCapture(args.video, cv2.CAP_FFMPEG)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.release()
            run_enhanced_analysis(args.db, args.analysis_key, fps)

    conn = sqlite3.connect(args.db, timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    event_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE game_id=?",
        (args.analysis_key,),
    ).fetchone()[0]
    conn.execute(
        """UPDATE analysis_runs
           SET status='completed', progress_pct=100, progress_step='Done',
               completed_at=CURRENT_TIMESTAMP
           WHERE analysis_key=?
             AND NOT (status='running' AND COALESCE(progress_step,'') LIKE 'Detecting%')""",
        (args.analysis_key,),
    )
    conn.commit()
    conn.close()
    print(f"Done. {event_count} events for {args.analysis_key}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
