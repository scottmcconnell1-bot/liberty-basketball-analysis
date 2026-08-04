#!/usr/bin/env python3
"""Export a closed season's historical rows into a SEPARATE archive SQLite file.

The live film_analysis.db is left unchanged (no prune). Archives are for
school records / career history without growing risk on the hot DB file.

Examples:
  py -3.12 scripts/archive_season.py --list
  py -3.12 scripts/archive_season.py --season-id 3
  py -3.12 scripts/archive_season.py --season-id 3 --label 2024-25

Later (separate Scott-approved step): prune archived seasons from the live DB.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from liberty_data_paths import LIVE_DB, archive_dir, ensure_data_dirs  # noqa: E402

# Tables copied when present (FK-safe order for a snapshot; archive is self-contained).
SEASON_SCOPED = [
    "games_videos",
    "events",
    "stats",
    "scheduled_games",
    "games_notes",
    "games",
]


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def list_seasons(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "seasons"):
        print("No seasons table.")
        return
    colnames = cols(conn, "seasons")
    rows = conn.execute(f"SELECT {', '.join(colnames)} FROM seasons ORDER BY id").fetchall()
    for r in rows:
        parts = [f"id={r[0]}"]
        for i, name in enumerate(colnames[1:], start=1):
            parts.append(f"{name}={r[i]!r}")
        print("  " + "  ".join(parts))


def copy_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    table: str,
    where_sql: str,
    params: tuple,
) -> int:
    if not table_exists(src, table):
        return 0
    create = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not create or not create[0]:
        return 0
    dst.execute(create[0])
    colnames = cols(src, table)
    col_list = ", ".join(colnames)
    rows = src.execute(f"SELECT {col_list} FROM {table} WHERE {where_sql}", params).fetchall()
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in colnames)
    dst.executemany(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive one season to external storage")
    parser.add_argument("--db", type=Path, default=LIVE_DB)
    parser.add_argument("--list", action="store_true", help="List seasons and exit")
    parser.add_argument("--season-id", type=int, help="Season id to archive")
    parser.add_argument("--label", type=str, default="", help="Filename label override")
    args = parser.parse_args()

    ensure_data_dirs()
    live = Path(args.db).expanduser().resolve()
    if not live.exists():
        print(f"ERROR: live DB not found: {live}", file=sys.stderr)
        return 1

    src = sqlite3.connect(f"file:{live.as_posix()}?mode=ro", uri=True, timeout=60)
    src.row_factory = sqlite3.Row
    try:
        if args.list or not args.season_id:
            print("Seasons in live DB:")
            list_seasons(src)
            if not args.season_id:
                print("\nPass --season-id N to write an archive file (live DB unchanged).")
                return 0

        season = src.execute("SELECT * FROM seasons WHERE id=?", (args.season_id,)).fetchone()
        if not season:
            print(f"ERROR: season id {args.season_id} not found", file=sys.stderr)
            return 1

        label = (args.label or season["name"] or f"season_{args.season_id}").strip()
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80]
        stamp = datetime.now().strftime("%Y%m%d")
        out_dir = archive_dir() / "seasons"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_db = out_dir / f"{safe}_{stamp}_id{args.season_id}.db"
        manifest_path = out_dir / f"{safe}_{stamp}_id{args.season_id}.json"

        if out_db.exists():
            print(f"ERROR: already exists: {out_db}", file=sys.stderr)
            return 1

        dst = sqlite3.connect(str(out_db))
        counts: dict[str, int] = {}
        try:
            # seasons row + schema
            create = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='seasons'"
            ).fetchone()
            if create and create[0]:
                dst.execute(create[0])
                scols = cols(src, "seasons")
                dst.execute(
                    f"INSERT INTO seasons ({', '.join(scols)}) VALUES ({', '.join('?' for _ in scols)})",
                    tuple(season[c] for c in scols),
                )
                counts["seasons"] = 1

            # games for season
            if table_exists(src, "games") and "season_id" in cols(src, "games"):
                counts["games"] = copy_table(
                    src, dst, "games", "season_id = ?", (args.season_id,)
                )
                game_ids = [
                    r[0]
                    for r in src.execute(
                        "SELECT id FROM games WHERE season_id = ?", (args.season_id,)
                    ).fetchall()
                ]
            else:
                game_ids = []

            if game_ids:
                placeholders = ",".join("?" for _ in game_ids)
                for table, fk in (
                    ("stats", "game_id"),
                    ("events", "game_id"),
                    ("game_videos", "game_id"),
                    ("game_notes", "game_id"),
                ):
                    if not table_exists(src, table):
                        continue
                    if fk not in cols(src, table):
                        continue
                    counts[table] = copy_table(
                        src, dst, table, f"{fk} IN ({placeholders})", tuple(game_ids)
                    )

            # scheduled_games if season-linked
            if table_exists(src, "scheduled_games") and "season_id" in cols(src, "scheduled_games"):
                counts["scheduled_games"] = copy_table(
                    src, dst, "scheduled_games", "season_id = ?", (args.season_id,)
                )

            dst.commit()
        finally:
            dst.close()

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "live_db": str(live),
            "archive_db": str(out_db),
            "season_id": args.season_id,
            "season_name": season["name"],
            "row_counts": counts,
            "note": "Export only — live DB not modified. Safe for school records / career history.",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Archived season {args.season_id} ({season['name']!r})")
        print(f"  DB:       {out_db}")
        print(f"  Manifest: {manifest_path}")
        print(f"  Counts:   {counts}")
        print("Live database unchanged.")
        return 0
    finally:
        src.close()


if __name__ == "__main__":
    raise SystemExit(main())
