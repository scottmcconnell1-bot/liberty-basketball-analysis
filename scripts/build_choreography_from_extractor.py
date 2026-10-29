"""Build choreography JSON for plays straight from the FastDraw vector extractor.

Plan: .team/specs/12_numbered_lines_plan.md, Stage 1 deliverable 3.

The computer's order guess is the extractor's draw order: 1..N per square
(one square = one PDF page = one choreography step). The output matches the
shape of data/playbook/choreography/<id>.json so Play All can read it.

Two ways to pick plays:
  --index <numbered>/index.json   every play group written by generate_numbered_lines
  --db <copy.db> --play-ids ...   the pages of plays already in the DB (read-only, mode=ro)

Outputs go outside the repo (Liberty_Play_Catalog). Nothing is written to the DB.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playbook_vector_extract import extract_play_pages  # noqa: E402

_PAGE_RE = re.compile(r"page_(\d+)\.(?:png|jpe?g)$", re.I)


def sheet_url(import_id: str, page_1: int) -> str:
    return f"/uploads/bulk_imports/{import_id}/page_{page_1:04d}.png"


def movement_from_action(act: dict) -> dict:
    pts = [dict(p) for p in act.get("points") or []]
    frm = act.get("fromPid") or act.get("pid")
    return {
        "type": act.get("kind") or "cut",
        "timing": "sync",
        "from": frm,
        "to": act.get("toPid") or frm,
        "points": pts,
        "anchors": [dict(p) for p in pts],
        "shape": "straight" if len(pts) <= 2 else "curve",
    }


def step_from_extract(ext: dict, step_index: int, import_id: str) -> dict:
    ink = ext.get("ink") or {}
    actions = list(ink.get("actions") or [])
    return {
        "step_index": step_index,
        "source_image": sheet_url(import_id, int(ext["page"])),
        "court_frac": ext.get("court_frac"),
        "positions": ext.get("positions") or {},
        "coachOrder": True,
        "movements": [movement_from_action(a) for a in actions],
        "ink": {
            "paths": ink.get("paths") or {},
            "marks": ink.get("marks") or {},
            "passes": ink.get("passes") or [],
            "actions": actions,
        },
    }


def build_play(pdf: Path, pages: list[int], play_id, import_id: str) -> dict:
    steps = extract_play_pages(pdf, pages)
    return {
        "version": 1,
        "play_id": play_id,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "auto_extract_numbered",
        "sticky": False,
        "pages": pages,
        "steps": [step_from_extract(s, i, import_id) for i, s in enumerate(steps)],
    }


def pages_from_db(db_path: Path, play_ids: list[int]) -> dict[int, list[int]]:
    """play_id -> PDF pages, from play_steps.source_image (DB opened read-only)."""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        out: dict[int, list[int]] = {}
        for pid in play_ids:
            rows = con.execute(
                "SELECT source_image FROM play_steps WHERE play_id = ? ORDER BY step_number",
                (pid,),
            ).fetchall()
            pages = []
            for (img,) in rows:
                m = _PAGE_RE.search(str(img or ""))
                if m:
                    pages.append(int(m.group(1)))
            if pages:
                out[pid] = pages
        return out
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--import-id", default=None, help="bulk import id for source_image URLs (default: PDF stem)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--index", type=Path, help="index.json written by generate_numbered_lines")
    src.add_argument("--db", type=Path, help="DB COPY; with --play-ids")
    ap.add_argument("--play-ids", default="", help="comma-separated play ids (with --db)")
    args = ap.parse_args(argv)

    import_id = args.import_id or args.pdf.stem
    if args.index:
        groups = {g["key"]: g["pages"] for g in json.loads(args.index.read_text(encoding="utf-8"))["plays"]}
    else:
        ids = [int(x) for x in args.play_ids.split(",") if x.strip()]
        groups = pages_from_db(args.db, ids)

    args.out.mkdir(parents=True, exist_ok=True)
    for key, pages in groups.items():
        doc = build_play(args.pdf, pages, key, import_id)
        (args.out / f"{key}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        n = sum(len(s["ink"]["actions"]) for s in doc["steps"])
        print(f"{key}: pages {pages[0]}-{pages[-1]} ({len(pages)} squares), {n} lines")
    print(f"Wrote {len(groups)} plays to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
