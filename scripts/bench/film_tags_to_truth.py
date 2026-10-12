#!/usr/bin/env python3
"""Turn a Film Tool tag export into a benchmark ``truth.json``.

The benchmark fixtures hold the coach's tags as ground truth, with player names
and free-text notes stripped: matching uses event type, result and time only, and
a fixture that travels with the repo should not carry a roster.

    python scripts/bench/film_tags_to_truth.py \
        tag-exports/jrhigh_adrian_q1_manual_tags.json \
        --out benchmarks/accuracy/adrian_q1/truth.json \
        --film "uploads/nfhs_gam0a66d85e12.mp4 (Adrian Jr High, video 73)"

``window_sec`` comes from the export's own ``lastTaggedTime`` when it has one, so
the window is the stretch the coach actually tagged rather than a guess. Stdlib
only, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shot_tag_gate import time_to_ms  # noqa: E402

# Kept: what the matcher reads. Dropped: player, team, label, notes, duration.
KEEP = ("quarter", "start", "category", "eventtype", "result", "side")


def convert(export: dict, film: str, source: str) -> dict:
    rows = export.get("rows") or []
    if not rows:
        raise SystemExit("no rows in the export")
    last_tagged = export.get("lastTaggedTime")
    window_ms = time_to_ms(last_tagged) if last_tagged else max(
        time_to_ms(r.get("start")) for r in rows)
    return {
        "source": source,
        "film": film,
        "window_sec": int(round(window_ms / 1000)),
        "note": "Player names and notes removed; matching uses event type, result and time only.",
        "rows": [{k: r.get(k, "") for k in KEEP} for r in rows],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path, help="Film Tool tag export JSON")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--film", default="", help="human-readable film description")
    ap.add_argument("--source", default="", help="overrides the generated provenance line")
    args = ap.parse_args(argv)

    export = json.loads(args.export.read_text(encoding="utf-8"))
    source = args.source or (
        f"Film Tool manual tags by the coach, {export.get('ourTeam', '?')} vs "
        f"{export.get('opponent', '?')}, client game {export.get('id', '?')}, "
        f"from {args.export.as_posix()}")
    truth = convert(export, args.film, source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(truth, indent=1) + "\n", encoding="utf-8")
    shots = sum(1 for r in truth["rows"]
                if str(r.get("eventtype", "")).upper() in ("2PT", "3PT", "FT"))
    print(f"{args.out}: {len(truth['rows'])} tags, {shots} shot tags, "
          f"window {truth['window_sec']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
