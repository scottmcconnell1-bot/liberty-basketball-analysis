#!/usr/bin/env python3
"""Apply Adrian jersey lookaround (OCR before/after event → scorebook name/team)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adrian_identity import apply_lookaround_to_accepted  # noqa: E402
from adrian_quality import ADRIAN_BASE  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "film_analysis.db")
    args = ap.parse_args()
    conn = sqlite3.connect(str(args.db), timeout=180)
    conn.row_factory = sqlite3.Row
    # Speed lookaround queries on large detections table
    conn.execute("CREATE INDEX IF NOT EXISTS idx_det_gid_tid_ts ON detections(game_id, tracker_id, timestamp_ms)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_det_gid_cluster_ts ON detections(game_id, player_cluster, timestamp_ms)")
    report = apply_lookaround_to_accepted(conn, ADRIAN_BASE, commit=True)
    print(json.dumps(report, indent=2, default=str))

    # Sample matched rows
    rows = conn.execute(
        """
        SELECT id, event_type, player, timestamp_ms, details_json
          FROM events
         WHERE game_id=? AND review_notes LIKE '%adrian_jersey_lookaround_v2:matched%'
         ORDER BY timestamp_ms LIMIT 8
        """,
        (ADRIAN_BASE,),
    ).fetchall()
    print("sample matched:")
    for r in rows:
        d = json.loads(r["details_json"] or "{}")
        print(
            f"  {r['timestamp_ms']/1000:.1f}s {r['event_type']} "
            f"#{d.get('jersey_number')} {d.get('player_name')} · {d.get('team_name')} "
            f"(tracker {d.get('identity_lookaround', {}).get('tracker_id')})"
        )
    conn.close()
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
