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


def _dotenv_value(key: str) -> str:
    """Read one key from the repo .env (same parsing rules as app._load_dotenv)."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return ""
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        return value
    return ""


def live_db_path() -> Path:
    """The SQLite file the running app uses.

    Same precedence as app.py: real env LIBERTY_DATABASE, then LIBERTY_DATABASE
    from the repo .env, then the legacy LIBERTY_DB_PATH, then film_analysis.db.
    A relative value is resolved against the repo root (the app's working dir).
    """
    raw = ""
    for key in ("LIBERTY_DATABASE", "LIBERTY_DB_PATH"):
        raw = (os.environ.get(key) or "").strip() or _dotenv_value(key).strip()
        if raw:
            break
    if not raw:
        return ROOT / "film_analysis.db"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


LIVE_DB = live_db_path()


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


def readonly_uri(path: Path) -> str:
    """SQLite read-only URI for *path*, percent-encoded.

    A bare ``f"file:{path}?mode=ro"`` breaks on '#', '?' or '%' in the path
    (SQLite treats '#' as the start of a fragment and silently opens a
    different, empty file). ``Path.as_uri()`` escapes them and also produces the
    ``file:///C:/...`` form SQLite expects on Windows.
    """
    return Path(path).resolve().as_uri() + "?mode=ro"
