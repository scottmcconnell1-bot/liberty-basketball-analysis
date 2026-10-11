#!/usr/bin/env python3
"""Score a run against the coach's shot tags: right / makes missed / misses called makes.

This is the count gate, run on a machine that has the database and the tag file --
the home laptop, or a clone with the Shared drive folder copied over it. CI cannot
run it, because neither the film nor the tags are in git.

    python scripts/shot_tag_score.py --game-id "<analysis key>"
    python scripts/shot_tag_score.py --game-id "<key>" --json out.json
    python scripts/shot_tag_score.py --game-id "<key>" --update-baseline   # after Scott accepts

Exit status is 1 when the score is below the floor in benchmarks/shot_tags/baseline.json,
so it works in a shell loop or a pre-push hook. The floor on the Adrian film is 85 right,
20 makes missed, 6 misses called makes, which is the best score anyone has recorded. A
change that scores 84 fails. A change that trades a missed make for a miss called a make
fails, because that one puts points on the card that were never scored.

Stdlib only -- sqlite3 and json. No Flask, no OpenCV.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import shot_tag_gate  # noqa: E402

BASELINE_PATH = ROOT / "benchmarks" / "shot_tags" / "baseline.json"
DEFAULT_DB = ROOT / "film_analysis.db"
TAG_DIR = ROOT / "data" / "film_tags"


def _base_game_id(game_id: str) -> str:
    """``x__rerun_20261006_033941`` -> ``x``, which is how tag files are named."""
    return game_id.split("__rerun_")[0]


def find_tag_file(game_id: str, explicit: Path | None) -> Path:
    if explicit:
        if not explicit.is_file():
            raise SystemExit(f"no tag file at {explicit}")
        return explicit
    candidates = [TAG_DIR / f"{game_id}.json", TAG_DIR / f"{_base_game_id(game_id)}.json"]
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        "no tag file found. Looked for:\n  " + "\n  ".join(str(c) for c in candidates) +
        "\n\ndata/film_tags/ is not in git. Copy the Shared drive folder "
        "'Program data from home laptop ...' over the clone, or pass --tags.")


def load_events(db: Path, game_id: str) -> list[dict]:
    if not db.is_file():
        raise SystemExit(
            f"no database at {db}\n\nfilm_analysis.db is not in git. Run this on the home "
            "laptop, or copy the Shared drive snapshot over the clone, or pass --db.")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, event_type, shot_result, timestamp_ms, review_status, source_type "
            "FROM events WHERE game_id = ? ORDER BY timestamp_ms, id", (game_id,))]
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"no events for game_id {game_id!r} in {db}")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-id", required=True, help="analysis key of the run to score")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--tags", type=Path, help="Film Tool tag JSON (default: data/film_tags/<id>.json)")
    ap.add_argument("--fixture", help="baseline key (default: the tag file's stem)")
    ap.add_argument("--events", type=Path, help="score this events JSON instead of the database")
    ap.add_argument("--count-taught", action="store_true",
                    help="include rows the teach pass corrected from a tag. Reports what the "
                         "card says; cannot be used to claim a gate score.")
    ap.add_argument("--tolerance-ms", type=int, default=shot_tag_gate.MATCH_TOLERANCE_MS)
    ap.add_argument("--json", type=Path, help="write the full result, buckets included")
    ap.add_argument("--update-baseline", action="store_true",
                    help="write this score as the new floor. Only after Scott accepts it.")
    args = ap.parse_args(argv)

    tag_path = find_tag_file(args.game_id, args.tags)
    export = json.loads(tag_path.read_text(encoding="utf-8"))
    tag_rows = export if isinstance(export, list) else (export.get("rows") or [])
    tags = shot_tag_gate.shot_tags(tag_rows)
    if not tags:
        raise SystemExit(f"no shot tags (2PT/3PT/FT with Make or Miss) in {tag_path}")

    events = (json.loads(args.events.read_text(encoding="utf-8")) if args.events
              else load_events(args.db, args.game_id))
    makes = shot_tag_gate.stored_makes(events, count_taught=args.count_taught)
    result = shot_tag_gate.score(tags, makes, tolerance_ms=args.tolerance_ms)

    fixture = args.fixture or tag_path.stem
    print(f"fixture: {fixture}")
    print(f"tags:    {tag_path}  ({result['tags']} shot tags, "
          f"{result['tagged_makes']} makes, {result['tagged_misses']} misses)")
    print(f"run:     {args.game_id}")
    print(f"stored:  {result['stored_makes']} makes"
          + ("  (corrected rows included)" if args.count_taught else "")
          + f", {result['unmatched_stored_makes']} of them matched no tag")
    print()
    print(shot_tag_gate.summary_line(result))
    trivial = result["tagged_misses"]
    print(f"(calling every shot a miss would score {trivial} right on this answer key)")

    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.is_file() else {}
    if args.update_baseline:
        if args.count_taught:
            raise SystemExit("refusing to write a floor from corrected rows; drop --count-taught")
        baseline[fixture] = {k: result[k] for k in ("tags", *shot_tag_gate.METRICS)}
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        print(f"\nfloor for {fixture} written to {BASELINE_PATH.relative_to(ROOT)}")
        return 0

    floor = baseline.get(fixture)
    if not floor:
        print(f"\nno floor for {fixture!r} in {BASELINE_PATH.relative_to(ROOT)}. "
              "Nothing to compare against.")
        return 0
    problems = shot_tag_gate.regressions(result, floor)
    print(f"\nfloor:   right={floor['right']} makes_missed={floor['makes_missed']} "
          f"misses_called_makes={floor['misses_called_makes']} of {floor['tags']} tags")
    if args.count_taught:
        print("NOT A GATE SCORE: corrected rows were counted.")
        return 0
    for problem in problems:
        print("BELOW FLOOR:", problem)
    print("PASS" if not problems else "FAIL")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
