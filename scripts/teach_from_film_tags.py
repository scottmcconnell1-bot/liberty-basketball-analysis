#!/usr/bin/env python3
"""Teach AI event labels from Film Tool sidecar tags (Liberty vs Adrian Q1).

Usage:
  python scripts/teach_from_film_tags.py --write-model
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from film_tool_calibrator import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_GAME_ID,
    build_film_tool_calibrator,
    write_film_tool_calibrator,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default=DEFAULT_GAME_ID)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--write-model", action="store_true")
    args = parser.parse_args(argv)

    model = build_film_tool_calibrator(args.game_id, db_path=Path(args.db))
    print(json.dumps(model.get("train_snapshot") or {}, indent=2))
    if args.write_model:
        out = write_film_tool_calibrator(model)
        print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
