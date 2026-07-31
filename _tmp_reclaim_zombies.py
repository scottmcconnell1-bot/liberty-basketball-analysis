#!/usr/bin/env python3
"""One-shot: mark status=running analysis_runs as failed when no live workers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "film_analysis.db"


def main() -> int:
    conn = sqlite3.connect(str(DB), timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    rows = conn.execute(
        "SELECT id, analysis_key FROM analysis_runs WHERE status='running'"
    ).fetchall()
    print(f"reclaiming {len(rows)}")
    for run_id, key in rows:
        conn.execute(
            """UPDATE analysis_runs
               SET status='failed',
                   progress_step='Failed (zombie reclaim - no live worker)',
                   error_message='zombie reclaim 2026-07-31: status=running with no analysis worker',
                   completed_at=CURRENT_TIMESTAMP
             WHERE id=?""",
            (run_id,),
        )
        print(f"  fixed {run_id} {key}")
    conn.commit()
    left = conn.execute(
        "SELECT COUNT(*) FROM analysis_runs WHERE status='running'"
    ).fetchone()[0]
    print(f"running now {left}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
