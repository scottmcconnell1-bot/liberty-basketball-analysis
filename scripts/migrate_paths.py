#!/usr/bin/env python3
"""Rewrite filesystem paths stored in film_analysis.db when the DB moves between machines.

The app stores ABSOLUTE upload paths in several columns (e.g. videos.file_path is the
joined UPLOAD_FOLDER path, see blueprints/ai.py). A DB copied from Scott's Windows box
therefore holds `C:\\Users\\scott\\...\\uploads\\game.mp4`, which os.path.exists() and
cv2.VideoCapture() consume raw - every video reads as missing until rewritten.

Default is a DRY RUN that only reports. Always snapshot first:

    python scripts/backup_db.py
    python scripts/migrate_paths.py --db film_analysis.db --audit
    python scripts/migrate_paths.py --db film_analysis.db \\
        --from-prefix 'C:\\Users\\scott\\Documents\\liberty-basketball-analysis\\uploads' \\
        --to-prefix   '/home/myaccount/LibertyData/uploads' --apply

Stat-book drafts (uploads/stat_books/<game>/draft.json) also embed absolute paths in
`meta.aligned_image`; pass --stat-books-dir to rewrite those files too.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# (table, column) pairs that hold filesystem paths - from schema.sql + helpers migrations.
PATH_COLUMNS = [
    ("videos", "file_path"),
    ("analysis_runs", "video_path"),
    ("video_assets", "file_path"),
    ("sources", "source_path"),
    ("issue_reports", "source_path"),
    ("provenance_records", "source_path"),
    ("play_steps", "source_image"),
]

_WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def audit(conn: sqlite3.Connection) -> dict:
    """Count rows per column that hold Windows-style absolute paths or backslashes."""
    report = {}
    for table, column in PATH_COLUMNS:
        if not (_table_exists(conn, table) and _column_exists(conn, table, column)):
            continue
        rows = conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != ''").fetchall()
        values = [r[0] for r in rows]
        windows = [v for v in values if _WINDOWS_ABS.match(v) or "\\" in v]
        missing = [v for v in values if not _WINDOWS_ABS.match(v) and "\\" not in v and not Path(v).exists()]
        report[f"{table}.{column}"] = {
            "rows": len(values),
            "windows_style": len(windows),
            "posix_but_missing_on_disk": len(missing),
            "sample": (windows or missing)[:2],
        }
    return report


def rewrite_value(value: str, from_prefix: str, to_prefix: str) -> str | None:
    """Return the rewritten path, or None if the value does not start with from_prefix.

    Matching is case-insensitive on the prefix and treats \\ and / as equivalent, since
    Windows paths arrive with either. Everything after the prefix is normalised to '/'."""
    if not value:
        return None
    norm_value = value.replace("\\", "/")
    norm_from = from_prefix.replace("\\", "/").rstrip("/")
    if not norm_value.lower().startswith(norm_from.lower()):
        return None
    rest = norm_value[len(norm_from):].lstrip("/")
    # Keep forward slashes even on Windows so DB paths stay portable POSIX-style.
    norm_to = to_prefix.replace("\\", "/").rstrip("/")
    return f"{norm_to}/{rest}" if rest else norm_to


def rewrite_db(conn: sqlite3.Connection, from_prefix: str, to_prefix: str, apply: bool) -> dict:
    changes = {}
    for table, column in PATH_COLUMNS:
        if not (_table_exists(conn, table) and _column_exists(conn, table, column)):
            continue
        rows = conn.execute(f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
        updates = []
        for rowid, value in rows:
            new = rewrite_value(value, from_prefix, to_prefix)
            if new is not None and new != value:
                updates.append((new, rowid))
        changes[f"{table}.{column}"] = len(updates)
        if apply and updates:
            conn.executemany(f"UPDATE {table} SET {column}=? WHERE rowid=?", updates)
    if apply:
        conn.commit()
    return changes


def rewrite_stat_book_drafts(stat_books_dir: Path, from_prefix: str, to_prefix: str, apply: bool) -> int:
    """Rewrite absolute paths inside uploads/stat_books/<game>/draft.json meta blocks."""
    n = 0
    for draft in sorted(stat_books_dir.glob("*/draft.json")):
        try:
            data = json.loads(draft.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = data.get("meta") or {}
        changed = False
        for key, value in list(meta.items()):
            if isinstance(value, str):
                new = rewrite_value(value, from_prefix, to_prefix)
                if new is not None and new != value:
                    meta[key] = new
                    changed = True
        if changed:
            n += 1
            if apply:
                draft.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--audit", action="store_true", help="Report path columns and exit")
    ap.add_argument("--from-prefix", help="Prefix to replace (Windows or POSIX)")
    ap.add_argument("--to-prefix", help="Replacement prefix on this machine")
    ap.add_argument("--stat-books-dir", type=Path, help="uploads/stat_books directory to rewrite draft.json meta paths")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    try:
        if args.audit or not (args.from_prefix and args.to_prefix):
            print(json.dumps(audit(conn), indent=2))
            if not (args.from_prefix and args.to_prefix):
                return 0
        changes = rewrite_db(conn, args.from_prefix, args.to_prefix, apply=args.apply)
        print(json.dumps({"mode": "APPLIED" if args.apply else "DRY RUN", "db_rows_rewritten": changes}, indent=2))
        if args.stat_books_dir:
            n = rewrite_stat_book_drafts(args.stat_books_dir, args.from_prefix, args.to_prefix, apply=args.apply)
            print(json.dumps({"stat_book_drafts_rewritten": n}))
        if args.apply:
            print(json.dumps({"post_apply_audit": audit(conn)}, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
