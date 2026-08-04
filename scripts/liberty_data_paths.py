"""Resolve separate Backup / Archive roots away from the live app DB.

Live operating data stays in the project (film_analysis.db + uploads/).
Backups and archives go to LIBERTY_DATA_ROOT (default: ~/LibertyData) so
large copies never sit next to the hot SQLite file or the git working tree.

Override examples (PowerShell):
  $env:LIBERTY_DATA_ROOT = "E:\\LibertyData"
  $env:LIBERTY_BACKUP_DIR = "E:\\LibertyData\\backups"
  $env:LIBERTY_ARCHIVE_DIR = "E:\\LibertyData\\archives"
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = Path(os.environ.get("LIBERTY_DB_PATH", str(ROOT / "film_analysis.db")))


def data_root() -> Path:
    raw = (os.environ.get("LIBERTY_DATA_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    # Outside Documents/liberty-basketball-analysis on purpose
    return (Path.home() / "LibertyData").resolve()


def backup_dir() -> Path:
    raw = (os.environ.get("LIBERTY_BACKUP_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return data_root() / "backups"


def archive_dir() -> Path:
    raw = (os.environ.get("LIBERTY_ARCHIVE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return data_root() / "archives"


def ensure_data_dirs() -> dict[str, Path]:
    paths = {
        "data_root": data_root(),
        "backups": backup_dir(),
        "archives": archive_dir(),
        "archives_seasons": archive_dir() / "seasons",
        "archives_playbook": archive_dir() / "playbook",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    readme = paths["data_root"] / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Liberty Basketball — offline storage (NOT the live app database)\n"
            "\n"
            "backups/   Full SQLite snapshots of film_analysis.db (disaster recovery)\n"
            "archives/  Season / playbook exports kept for history & school records\n"
            "\n"
            "The live DB stays in the Liberty project folder so backups here cannot\n"
            "corrupt or slow the running app. Point LIBERTY_DATA_ROOT at an external\n"
            "drive when you have one.\n",
            encoding="utf-8",
        )
    return paths
