"""One-shot: import JrHigh videos + scorebook images. Upload only — no analysis."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent
SRC = Path(r"C:\Users\scott\Documents\JrHigh")
UPLOADS = ROOT / "uploads"
STAT_BOOKS = UPLOADS / "stat_books" / "jrhigh"
DB = ROOT / "film_analysis.db"

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".pdf"}

# Align with scripts/import_hudl.py ALIAS where possible
OPPONENT_ALIAS = {
    "adrian": "Adrian, OR",
    "hsb": "Horseshoe Bend",
    "horseshoe bend": "Horseshoe Bend",
    "rimrock": "Rimrock",
    "garden valley": "Garden Valley",
    "idaho city": "Idaho City",
    "notus": "Notus",
    "riverstone": "Riverstone",
}


def parse_opponent(stem: str) -> str:
    """LIBERTY (A) v ADRIAN (H)1 -> Adrian, OR"""
    m = re.search(r"\bv\s+(.+?)(?:\s*\([AH]\))?\s*\d*$", stem, re.I)
    if not m:
        return "unknown"
    name = m.group(1).strip()
    name = re.sub(r"\s*\([AH]\)\s*$", "", name, flags=re.I).strip()
    name = re.sub(r"\d+$", "", name).strip()
    key = re.sub(r"\s+", " ", name.lower()).strip()
    if key in OPPONENT_ALIAS:
        return OPPONENT_ALIAS[key]
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in name.split())


def ensure_archived_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    if "archived" not in cols:
        conn.execute(
            "ALTER TABLE videos ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def already_imported(conn: sqlite3.Connection, original: str, size: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, stored_filename, opponent, game_id, archived
          FROM videos
         WHERE original_filename = ?
           AND file_size_bytes = ?
         ORDER BY id DESC LIMIT 1
        """,
        (original, size),
    ).fetchone()


def copy_or_link(src: Path, dest: Path) -> str:
    """Prefer hardlink (same volume, instant); fall back to copy."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.stat().st_size == src.stat().st_size:
            return "exists"
        dest.unlink()
    try:
        os.link(src, dest)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dest)
        return "copy"


def import_videos(conn: sqlite3.Connection) -> list[dict]:
    results = []
    videos = sorted(p for p in SRC.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for src in videos:
        size = src.stat().st_size
        safe_name = secure_filename(src.name) or src.name.replace(" ", "_")
        prior = already_imported(conn, safe_name, size)
        if prior:
            # Keep Active for JrHigh
            if int(prior["archived"] or 0) != 0:
                conn.execute("UPDATE videos SET archived=0 WHERE id=?", (prior["id"],))
                conn.commit()
            results.append(
                {
                    "file": src.name,
                    "status": "skipped_existing",
                    "id": prior["id"],
                    "stored": prior["stored_filename"],
                    "opponent": prior["opponent"],
                    "game_id": prior["game_id"],
                    "display": f"Liberty vs {prior['opponent']}",
                }
            )
            print(f"SKIP existing id={prior['id']}: {src.name}", flush=True)
            continue

        stem, ext = os.path.splitext(safe_name)
        stored = f"{stem}_{ts}{ext}"
        dest = UPLOADS / stored
        opponent = parse_opponent(src.stem)
        game_id = f"jrhigh_{opponent.lower().replace(' ', '_')}_{stem}_{ts}"

        print(f"IMPORT {src.name} ({size/1e9:.2f} GB) -> {stored} opponent={opponent}", flush=True)
        mode = copy_or_link(src, dest)
        file_size = dest.stat().st_size
        cur = conn.execute(
            """
            INSERT INTO videos (
                original_filename, stored_filename, file_path, file_size_bytes,
                opponent, game_id, relational_game_id, is_duplicate, duplicate_of_id, archived
            ) VALUES (?,?,?,?,?,?,?,?,?,0)
            """,
            (
                safe_name,
                stored,
                str(dest),
                file_size,
                opponent,
                game_id,
                None,
                0,
                None,
            ),
        )
        conn.commit()
        results.append(
            {
                "file": src.name,
                "status": f"imported_{mode}",
                "id": cur.lastrowid,
                "stored": stored,
                "opponent": opponent,
                "game_id": game_id,
                "display": f"Liberty vs {opponent}",
                "bytes": file_size,
            }
        )
        print(f"  OK id={cur.lastrowid} via {mode}", flush=True)
    return results


def import_images() -> list[dict]:
    STAT_BOOKS.mkdir(parents=True, exist_ok=True)
    results = []
    images = sorted(
        p
        for p in SRC.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    for src in images:
        dest = STAT_BOOKS / src.name
        mode = copy_or_link(src, dest)
        results.append({"file": src.name, "status": mode, "dest": str(dest)})
        print(f"STATBOOK {src.name} -> {dest} ({mode})", flush=True)
    # Note zip contents: duplicates of images/videos already present — skip extract
    zip_path = SRC / "LIBERTY (A) v HSB (H).zip"
    if zip_path.exists():
        results.append(
            {
                "file": zip_path.name,
                "status": "skipped_zip_duplicate_bundle",
                "note": "Zip holds same jpeg/mp4 already imported from folder root",
            }
        )
        print(f"SKIP zip (duplicate bundle): {zip_path.name}", flush=True)
    return results


def main() -> int:
    if not SRC.is_dir():
        print(f"Missing source: {SRC}", file=sys.stderr)
        return 1
    if not DB.is_file():
        print(f"Missing DB: {DB}", file=sys.stderr)
        return 1
    UPLOADS.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    ensure_archived_column(conn)
    print("=== VIDEOS ===", flush=True)
    videos = import_videos(conn)
    print("=== STAT BOOKS / IMAGES ===", flush=True)
    images = import_images()
    conn.close()
    print("=== SUMMARY ===", flush=True)
    for v in videos:
        print(v, flush=True)
    for i in images:
        print(i, flush=True)
    imported = [v for v in videos if str(v["status"]).startswith("imported")]
    print(
        f"videos_imported={len(imported)} skipped={len(videos)-len(imported)} images={len(images)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
