#!/usr/bin/env python3
"""Batch auto-digitize imported playbook diagram PNGs into positions_json.

Examples:
  py -3.12 scripts/digitize_playbook_plays.py --play-id 2 --write
  py -3.12 scripts/digitize_playbook_plays.py --all --write
  py -3.12 scripts/digitize_playbook_plays.py --play-id 15 --dry-run
  py -3.12 scripts/digitize_playbook_plays.py --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playbook_digitize import (  # noqa: E402
    digitize_play_steps,
    get_easyocr_reader,
    list_image_only_play_ids,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Digitize Fast Scout play diagram PNGs → positions_json")
    ap.add_argument("--db", default=str(ROOT / "film_analysis.db"), help="SQLite DB path")
    ap.add_argument("--uploads", default=str(ROOT / "uploads"), help="Upload folder root")
    ap.add_argument("--play-id", type=int, action="append", dest="play_ids", help="Play id (repeatable)")
    ap.add_argument("--all", action="store_true", help="All image-only plays")
    ap.add_argument("--list", action="store_true", help="List image-only play ids and exit")
    ap.add_argument("--write", action="store_true", help="Write positions_json to DB")
    ap.add_argument("--force", action="store_true", help="Overwrite existing positions")
    ap.add_argument("--min-markers", type=int, default=3, help="Min markers to accept a step")
    ap.add_argument("--limit", type=int, default=0, help="Max plays when using --all")
    ap.add_argument("--json-out", default="", help="Optional path to write full JSON report")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    if args.list:
        ids = list_image_only_play_ids(db)
        print(f"image-only plays: {len(ids)}")
        print(", ".join(str(i) for i in ids))
        return 0

    play_ids: list[int] = list(args.play_ids or [])
    if args.all:
        play_ids = list_image_only_play_ids(db)
        if args.limit and args.limit > 0:
            play_ids = play_ids[: args.limit]
    play_ids = sorted(set(play_ids))
    if not play_ids:
        print("No plays selected. Use --play-id N or --all (or --list).", file=sys.stderr)
        return 1

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"{mode}: {len(play_ids)} play(s)  db={db}")
    print("Loading EasyOCR (first run may download models)...")
    reader = get_easyocr_reader()
    print("Reader ready.\n")

    reports = []
    ok_plays = 0
    for pid in play_ids:
        report = digitize_play_steps(
            db,
            pid,
            upload_root=args.uploads,
            write=args.write,
            force=args.force,
            min_markers=args.min_markers,
            reader=reader,
        )
        reports.append(report)
        if not report.get("ok"):
            print(f"play {pid}: ERROR {report.get('error')}")
            continue
        accepted = report.get("accepted_steps", 0)
        total = report.get("step_count", 0)
        flag = "OK" if accepted > 0 else "SKIP"
        if accepted > 0:
            ok_plays += 1
        print(
            f"[{flag}] play {pid} {report.get('name')!r} "
            f"({report.get('category')}) prefer={report.get('prefer')} "
            f"accepted_steps={accepted}/{total}"
        )
        for step in report.get("steps", []):
            if step.get("skipped"):
                print(f"    step {step.get('step_number')}: skipped — {step.get('reason')}")
                continue
            keys = sorted((step.get("positions") or {}).keys())
            status = "accepted" if step.get("accepted") else f"low-conf ({step.get('skip_reason','')})"
            written = " written" if step.get("written") else ""
            print(
                f"    step {step.get('step_number')}: {status}{written} "
                f"keys={keys} conf={step.get('confidence')}"
            )

    print(f"\nDone. Plays with >=1 accepted step: {ok_plays}/{len(play_ids)}")
    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
