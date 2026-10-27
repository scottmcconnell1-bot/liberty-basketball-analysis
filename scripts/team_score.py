#!/usr/bin/env python3
"""Print the make/miss score for both films as one JSON line.

Usage:
    .\\.venv\\Scripts\\python.exe scripts/team_score.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ai_bridge  # noqa: E402

NOTUS_TRACKS = ROOT / "gemini-upload" / "notus_q1_v6_tracks.json"
ADRIAN_FALLBACK = (
    Path(r"C:\Users\scott\Documents\liberty_offline_backup\temp_scoring\v6_tracks.json")
)


def adrian_tracks_path() -> Path | None:
    """Return the first existing Adrian tracks file, or None."""
    candidates: list[Path] = []
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        candidates.append(Path(temp) / "v6_tracks.json")
    candidates.append(ADRIAN_FALLBACK)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def score_tracks(tracks_path: str | Path) -> dict[str, Any]:
    """Run the saved v6 rule on one tracks file and return the four score counts."""
    path = Path(tracks_path)
    with path.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    times = [r["t"] for r in rows if r.get("hoop") and len(r["hoop"]) == 4]
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        score = ai_bridge.run_saved_v6_rule(times, str(path))
    return {
        "right": score["right"],
        "total": score["total_tags"],
        "makes_missed": score["makes_missed"],
        "misses_called_makes": score["misses_called_makes"],
    }


def build_score() -> dict[str, Any]:
    """Score both films and evaluate the goal."""
    notus = score_tracks(NOTUS_TRACKS)
    adrian_path = adrian_tracks_path()
    if adrian_path is None:
        print(
            "team_score: Adrian tracks not found; expected %TEMP%\\v6_tracks.json "
            f"or {ADRIAN_FALLBACK}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    adrian = score_tracks(adrian_path)
    goal_reached = (
        notus["right"] == notus["total"]
        and adrian["misses_called_makes"] == 0
        and adrian["makes_missed"] <= 12
    )
    return {"notus": notus, "adrian": adrian, "goal_reached": goal_reached}


def main() -> int:
    print(json.dumps(build_score()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
