#!/usr/bin/env python3
"""Delete film-analysis outputs so the next run starts clean.

Keeps videos, schedule, scores, playbook, rosters, and users.
Deletes detections, events, analysis runs, and related review/clip rows.

Usage:
  py -3.12 scripts/wipe_film_analysis.py --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "film_analysis.db"

# FK-safe order (children first). Videos / schedule / playbook are not listed.
ANALYSIS_TABLES = [
    "clip_tags",
    "player_development_clips",
    "practice_playlist_clips",
    "clips",
    "event_participants",
    "review_items",
    "human_corrections",
    "shot_classifications",
    "play_recognitions",
    "player_effect",
    "scouting_clips",
    "provenance_records",
    "possessions",
    "events",
    "detections",
    "track_identity_labels",
    "analysis_runs",
]


def _tables(db) -> set[str]:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def wipe(db_path: Path, *, apply: bool) -> dict:
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    existing = _tables(db)
    counts = {}
    for name in ANALYSIS_TABLES:
        if name not in existing:
            continue
        counts[name] = db.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]
    if apply:
        schema = (ROOT / "schema.sql").read_text(encoding="utf-8")
        db.execute("PRAGMA foreign_keys = OFF")
        for name in ANALYSIS_TABLES:
            if name not in existing:
                continue
            db.execute(f"DROP TABLE IF EXISTS {name}")
        db.executescript(schema)
        db.execute("PRAGMA foreign_keys = ON")
        db.commit()
    db.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wipe film analysis rows, keep videos")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--yes", action="store_true", help="Actually delete (otherwise dry-run)")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1
    counts = wipe(db_path, apply=args.yes)
    mode = "DELETED" if args.yes else "DRY-RUN"
    print(f"{mode} {db_path} at {datetime.now().isoformat(timespec='seconds')}")
    for name, n in counts.items():
        print(f"  {name}: {n}")
    print("Kept: videos, video_assets, scheduled_games, games scores, playbook, users")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
