#!/usr/bin/env python3
"""Recover teach progress after reboot — keep detections, avoid full re-analyze.

Marks stuck analysis_runs as completed when detections already exist, and
failed only when coverage is too thin to keep.

Usage:
  py -3.12 scripts/recover_teach_progress.py
  py -3.12 scripts/recover_teach_progress.py --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Import helpers from teach loop
from hoops_teach_loop import det_max_ms, recover_interrupted_runs  # noqa: E402

DB = ROOT / "film_analysis.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write status fixes")
    args = parser.parse_args()
    conn = sqlite3.connect(str(DB))
    rows = conn.execute(
        "SELECT id, analysis_key, status, progress_pct, progress_step FROM analysis_runs WHERE status IN ('running','failed')"
    ).fetchall()
    print(f"candidates: {len(rows)}")
    for run_id, key, status, pct, step in rows:
        mx = det_max_ms(conn, key or "")
        print(f"  id={run_id} {status} pct={pct} max_ms={mx} step={step!r} key={key}")
    if not args.apply:
        print("Dry run. Pass --apply to fix running/failed rows with kept detections.")
        conn.close()
        return 0
    # First recover running
    n = recover_interrupted_runs(conn)
    # Then promote failed-with-good-coverage to completed (reboot thrash)
    failed = conn.execute(
        "SELECT id, analysis_key FROM analysis_runs WHERE status='failed'"
    ).fetchall()
    promoted = 0
    for run_id, key in failed:
        mx = det_max_ms(conn, key or "")
        if mx >= 1_200_000:
            conn.execute(
                """UPDATE analysis_runs
                   SET status='completed', progress_pct=100,
                       progress_step='Promoted after reboot (detections kept)',
                       error_message=NULL,
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (run_id,),
            )
            promoted += 1
    conn.commit()
    conn.close()
    print(f"recovered_running_logic={n} promoted_failed={promoted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
