#!/usr/bin/env python3
"""Mark analysis_runs stuck in 'pending'/'running' as failed when nothing is happening.

The detector runs as a detached subprocess (helpers.start_analysis_subprocess). If it dies
without reporting (OOM, reboot, kill), its analysis_runs row stays 'running' forever and the
UI keeps saying "Analysis already in progress" for that video - the open bug in
docs/agent_handoffs/ACTIVE.md. A run is considered stale when BOTH:

  * it has been started for more than --minutes, and
  * its log file (logs/ai-<analysis_key>.log) has not been modified for --minutes
    (or does not exist).

Default is a dry run. Cron/systemd-timer friendly.

    python scripts/mark_stale_analysis_runs.py --db film_analysis.db            # report
    python scripts/mark_stale_analysis_runs.py --db film_analysis.db --apply    # mark failed
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _log_path(logs_dir: Path, analysis_key: str) -> Path:
    safe = re.sub(r"[^\w.\-]+", "_", analysis_key or "")[:120]
    return logs_dir / f"ai-{safe}.log"


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def find_stale(conn: sqlite3.Connection, logs_dir: Path, minutes: float, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    cutoff = now - minutes * 60
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, analysis_key, status, progress_step, started_at FROM analysis_runs WHERE status IN ('pending','running')"
    ).fetchall()
    stale = []
    for r in rows:
        started = _parse_ts(r["started_at"])
        if started is None or started > cutoff:
            continue
        log = _log_path(logs_dir, r["analysis_key"])
        log_mtime = os.path.getmtime(log) if log.exists() else None
        if log_mtime is not None and log_mtime > cutoff:
            continue  # still writing
        stale.append({
            "id": r["id"], "analysis_key": r["analysis_key"], "status": r["status"],
            "progress_step": r["progress_step"], "started_at": r["started_at"],
            "log": str(log) if log.exists() else None,
            "log_idle_min": None if log_mtime is None else round((now - log_mtime) / 60, 1),
        })
    return stale


def mark_failed(conn: sqlite3.Connection, stale: list[dict], minutes: float) -> int:
    for s in stale:
        conn.execute(
            """UPDATE analysis_runs
               SET status='failed', progress_step='Failed',
                   error_message=?, completed_at=CURRENT_TIMESTAMP
               WHERE id=? AND status IN ('pending','running')""",
            (f"Marked stale: no progress for more than {minutes:g} minutes (mark_stale_analysis_runs.py)", s["id"]),
        )
    conn.commit()
    return len(stale)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(ROOT / "film_analysis.db"))
    ap.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    ap.add_argument("--minutes", type=float, default=45.0, help="idle threshold (default 45, like LIBERTY_HUNG_STALE_SEC)")
    ap.add_argument("--apply", action="store_true", help="mark stale runs failed (default: report only)")
    args = ap.parse_args(argv)
    conn = sqlite3.connect(args.db, timeout=30)
    try:
        stale = find_stale(conn, args.logs_dir, args.minutes)
        print(json.dumps({"mode": "APPLIED" if args.apply else "DRY RUN", "stale": stale}, indent=2))
        if args.apply and stale:
            print(json.dumps({"marked_failed": mark_failed(conn, stale, args.minutes)}))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
