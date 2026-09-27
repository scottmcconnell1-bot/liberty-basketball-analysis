#!/usr/bin/env python3
"""Delete film-analysis outputs so the next run starts clean.

Keeps videos, schedule, scores, playbook, rosters, and users.
Deletes AI detections, events, analysis runs, and related review/clip rows.

Coach-authored work is kept: human_corrections, player_development_clips,
practice_playlist_clips, manual clips (and their tags), manual-tag scouting
clips, and events a coach added or verified (plus any event a kept clip
points at). A verified backup is written first; the wipe aborts if it fails.

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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from liberty_data_paths import backup_dir, live_db_path  # noqa: E402

DEFAULT_DB = live_db_path()

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

# Authored by coaches; never deleted by a wipe.
COACH_TABLES = {"human_corrections", "player_development_clips", "practice_playlist_clips"}


def _tables(db) -> set[str]:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _cols(db, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def _build_keep_sets(db, existing: set[str]) -> None:
    """Fill temp tables _keep_clips / _keep_events with coach-owned ids."""
    db.execute("CREATE TEMP TABLE _keep_clips (id INTEGER PRIMARY KEY)")
    db.execute("CREATE TEMP TABLE _keep_events (id INTEGER PRIMARY KEY)")
    dev = "player_development_clips" in existing
    dev_cols = _cols(db, "player_development_clips") if dev else set()

    if "clips" in existing:
        ccols = _cols(db, "clips")
        conds = []
        if "source" in ccols:
            conds.append("COALESCE(source, 'manual') <> 'ai'")
        if "canonical_clip_id" in dev_cols:
            conds.append("id IN (SELECT canonical_clip_id FROM player_development_clips)")
        if conds:
            db.execute(f"INSERT OR IGNORE INTO _keep_clips SELECT id FROM clips WHERE {' OR '.join(conds)}")

    if "events" in existing:
        ecols = _cols(db, "events")
        conds = []
        if "human_verified" in ecols:
            conds.append("COALESCE(human_verified, 0) = 1")
        if "source_type" in ecols:
            conds.append("COALESCE(source_type, 'ai') NOT IN ('ai', '')")
        if "event_id" in dev_cols:
            conds.append("id IN (SELECT event_id FROM player_development_clips)")
        if "clips" in existing and "event_id" in _cols(db, "clips"):
            conds.append("id IN (SELECT c.event_id FROM clips c JOIN _keep_clips k ON k.id = c.id)")
        if conds:
            db.execute(f"INSERT OR IGNORE INTO _keep_events SELECT id FROM events WHERE {' OR '.join(conds)}")


def _delete_where(table: str, cols: set[str]) -> str:
    """WHERE clause selecting the rows of *table* the wipe removes."""
    if table == "clips":
        return "id NOT IN (SELECT id FROM _keep_clips)"
    if table == "clip_tags" and "clip_id" in cols:
        return "clip_id NOT IN (SELECT id FROM _keep_clips)"
    if table == "events":
        return "id NOT IN (SELECT id FROM _keep_events)"
    if table in ("event_participants", "shot_classifications") and "event_id" in cols:
        return "event_id IS NULL OR event_id NOT IN (SELECT id FROM _keep_events)"
    if table in ("review_items", "provenance_records") and {"entity_type", "entity_id"} <= cols:
        return "NOT (entity_type = 'event' AND entity_id IN (SELECT id FROM _keep_events))"
    if table == "scouting_clips" and "source" in cols:
        return "COALESCE(source, '') = 'ai_detected'"
    return "1"


def wipe(db_path: Path, *, apply: bool, backup_to: Path | None = None) -> dict:
    """Count (dry run) or delete AI analysis rows; returns rows affected per table.

    With apply=True a verified backup is taken first (default: the LibertyData
    backups folder); if that fails nothing is deleted.
    """
    backup_path = None
    if apply:
        from backup_db import backup_database  # sibling script

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = Path(backup_to) if backup_to else backup_dir()
        # Not named film_analysis_*.db so the nightly --keep rotation never prunes it.
        backup_path = backup_database(Path(db_path), dest_dir / f"prewipe_film_analysis_{stamp}.db")

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    existing = _tables(db)
    counts: dict = {}
    try:
        db.execute("PRAGMA foreign_keys = OFF")
        _build_keep_sets(db, existing)
        for name in ANALYSIS_TABLES:
            if name not in existing or name in COACH_TABLES:
                continue
            where = _delete_where(name, _cols(db, name))
            counts[name] = db.execute(f"SELECT COUNT(*) AS c FROM {name} WHERE {where}").fetchone()["c"]
            if apply:
                db.execute(f"DELETE FROM {name} WHERE {where}")
        if apply:
            # Kept rows must not point at rows that no longer exist.
            if "human_corrections" in existing and "event_id" in _cols(db, "human_corrections"):
                db.execute(
                    "UPDATE human_corrections SET event_id = NULL "
                    "WHERE event_id IS NOT NULL AND event_id NOT IN (SELECT id FROM _keep_events)"
                )
            for table in ("events", "clips"):
                if table in existing and "possession_id" in _cols(db, table):
                    db.execute(
                        f"UPDATE {table} SET possession_id = NULL WHERE possession_id IS NOT NULL "
                        "AND possession_id NOT IN (SELECT id FROM possessions)"
                        if "possessions" in existing
                        else f"UPDATE {table} SET possession_id = NULL"
                    )
            db.commit()
        else:
            db.rollback()
    finally:
        db.execute("PRAGMA foreign_keys = ON")
        db.close()
    if backup_path is not None:
        counts["_backup"] = str(backup_path)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wipe film analysis rows, keep videos")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--yes", action="store_true", help="Actually delete (otherwise dry-run)")
    parser.add_argument("--backup-dir", default=None, help="Where to write the pre-wipe backup")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1
    try:
        counts = wipe(db_path, apply=args.yes, backup_to=Path(args.backup_dir) if args.backup_dir else None)
    except Exception as exc:  # noqa: BLE001 - backup failed: refuse to wipe
        print(f"ABORTED (nothing deleted): {exc}", file=sys.stderr)
        return 1
    backup = counts.pop("_backup", None)
    mode = "DELETED" if args.yes else "DRY-RUN"
    print(f"{mode} {db_path} at {datetime.now().isoformat(timespec='seconds')}")
    if backup:
        print(f"Backup: {backup}")
    for name, n in counts.items():
        print(f"  {name}: {n}")
    print("Kept: videos, video_assets, scheduled_games, games scores, playbook, users,")
    print("      human_corrections, player development clips, practice playlists, manual/verified events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
