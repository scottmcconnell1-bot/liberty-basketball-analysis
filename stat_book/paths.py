"""Filesystem paths for templates, uploads, and confirmed boxes."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "stat_books"
TEMPLATES_ROOT = DATA_ROOT / "templates"
CONFIRMED_ROOT = DATA_ROOT / "confirmed"

# Commas appear in JrHigh keys like jrhigh_adrian,_or_... (city, ST → city,_st).
# Reject path separators and Windows-reserved filename chars only.
_GAME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._,\-]{0,119}$")
_TEMPLATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,64}$")


def ensure_dirs() -> None:
    TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)
    CONFIRMED_ROOT.mkdir(parents=True, exist_ok=True)


def sanitize_game_id(game_id: str) -> str:
    text = (game_id or "").strip()
    if not _GAME_ID_RE.match(text):
        raise ValueError("Invalid game_id")
    if ".." in text:
        raise ValueError("Invalid game_id")
    return text


def sanitize_template_id(template_id: str) -> str:
    text = (template_id or "").strip()
    if not _TEMPLATE_ID_RE.match(text):
        raise ValueError("Invalid template_id")
    return text


def template_dir(template_id: str) -> Path:
    return TEMPLATES_ROOT / sanitize_template_id(template_id)


def layout_path(template_id: str) -> Path:
    return template_dir(template_id) / "layout.json"


def blank_path(template_id: str) -> Path:
    d = template_dir(template_id)
    for name in ("blank.png", "blank.jpg", "blank.jpeg", "blank.webp"):
        p = d / name
        if p.is_file():
            return p
    return d / "blank.png"


def confirmed_path(game_id: str) -> Path:
    return CONFIRMED_ROOT / f"{sanitize_game_id(game_id)}.json"


def upload_dir(game_id: str, upload_folder: str | Path | None = None) -> Path:
    base = Path(upload_folder or os.environ.get("LIBERTY_UPLOAD_FOLDER", "uploads"))
    if not base.is_absolute():
        base = ROOT / base
    path = base / "stat_books" / sanitize_game_id(game_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_templates() -> list[str]:
    ensure_dirs()
    return sorted(p.name for p in TEMPLATES_ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))


def list_confirmed() -> list[str]:
    ensure_dirs()
    return sorted(p.stem for p in CONFIRMED_ROOT.glob("*.json"))
