#!/usr/bin/env python3
"""Online SQLite backup of the LIVE Liberty DB into a SEPARATE folder.

Does not copy into the project tree by default. Uses SQLite's backup API so
the app can keep running (safer than copying film_analysis.db while WAL is hot).

Examples:
  py -3.12 scripts/backup_db.py
  py -3.12 scripts/backup_db.py --keep 14
  set LIBERTY_DATA_ROOT=E:\\LibertyData
  py -3.12 scripts/backup_db.py

Schedule daily (Task Scheduler):
  Program: py
  Arguments: -3.12 C:\\Users\\scott\\Documents\\liberty-basketball-analysis\\scripts\\backup_db.py --keep 14
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from liberty_data_paths import LIVE_DB, backup_dir, ensure_data_dirs, readonly_uri  # noqa: E402


def prune_old(dest: Path, keep: int) -> list[Path]:
    files = sorted(dest.glob("film_analysis_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for old in files[keep:]:
        old.unlink(missing_ok=True)
        removed.append(old)
    return removed


class BackupError(RuntimeError):
    """The snapshot could not be verified; nothing usable was written."""


def backup_database(live: Path, dest: Path) -> Path:
    """Consistent online snapshot of *live* into *dest*, verified before returning.

    Raises BackupError (and removes *dest*) when the source cannot be opened,
    has no tables, or the copy fails ``PRAGMA integrity_check``. Callers must not
    prune older backups unless this returned.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src = sqlite3.connect(readonly_uri(live), uri=True, timeout=60)
    except sqlite3.Error as exc:
        raise BackupError(f"cannot open live DB read-only: {live}: {exc}") from exc
    try:
        try:
            n_tables = src.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        except sqlite3.Error as exc:
            raise BackupError(f"cannot read live DB {live}: {exc}") from exc
        if not n_tables:
            raise BackupError(f"live DB {live} has no tables - refusing to back up an empty file")
        dst = sqlite3.connect(str(dest), timeout=60)
        try:
            src.backup(dst)
            check = dst.execute("PRAGMA integrity_check").fetchone()
        finally:
            dst.close()
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    if not check or str(check[0]).lower() != "ok":
        dest.unlink(missing_ok=True)
        raise BackupError(f"integrity_check failed on {dest}: {check[0] if check else None}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup live Liberty SQLite DB to external storage")
    parser.add_argument("--db", type=Path, default=LIVE_DB, help="Live database path")
    parser.add_argument("--out-dir", type=Path, default=None, help="Override backup directory")
    parser.add_argument("--keep", type=int, default=14, help="Keep newest N backups (0 = keep all)")
    args = parser.parse_args()

    ensure_data_dirs()
    dest_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    live = Path(args.db).expanduser().resolve()
    if not live.exists():
        print(f"ERROR: live DB not found: {live}", file=sys.stderr)
        return 1

    # Refuse to write backups next to the live DB (defeats the separation goal)
    if dest_dir.resolve() == live.parent.resolve() or dest_dir.resolve() == live.parent.resolve() / "backups":
        # Allow .../project/backups only if explicitly forced via --out-dir under project —
        # but warn loudly. Prefer LibertyData.
        if "LibertyData" not in str(dest_dir) and dest_dir.is_relative_to(live.parent):
            print(
                f"WARNING: backup dir is inside the project ({dest_dir}). "
                "Prefer LIBERTY_DATA_ROOT on another folder/drive.",
                file=sys.stderr,
            )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"film_analysis_{stamp}.db"
    size_gb = live.stat().st_size / (1024**3)
    print(f"Live DB: {live} ({size_gb:.2f} GB)")
    print(f"Backup -> {dest}")

    try:
        backup_database(live, dest)
    except (BackupError, sqlite3.Error) as exc:
        # Keep every older backup: a failed snapshot must never trigger pruning.
        print(f"ERROR: backup failed: {exc}", file=sys.stderr)
        return 1

    out_gb = dest.stat().st_size / (1024**3)
    print(f"OK wrote {out_gb:.2f} GB")

    if args.keep > 0:
        removed = prune_old(dest_dir, args.keep)
        if removed:
            print(f"Pruned {len(removed)} older backup(s); keeping {args.keep}")

    print(f"Backup folder: {dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
