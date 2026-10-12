#!/usr/bin/env python3
"""Write a game's scoreboard track: one `read_scoreboard` sample per second of film.

    python scripts/build_scoreboard_track.py GAME_ID VIDEO [--video-label uploads\\x.mp4] [--out PATH] [--keep-clock]

The file is {game_id, video, samples}. `clock_running` compares a sample's clock with the
last sample that had one; None when either is missing.

--keep-clock copies `clock` and `clock_running` from the file being replaced, matched by
timestamp. The Adrian track's clocks came from an older, looser clock read; today's read
returns far fewer legal clocks, and a quarter needs a legal clock.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from scoreboard_clock import read_scoreboard, track_path  # noqa: E402

_KEYS = ("clock", "period", "mustangs", "guest", "mustangs_fouls", "guest_fouls", "foul_jersey", "foul_count")


def build_samples(video: str, every_ms: int = 1000) -> list[dict]:
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps * every_ms / 1000.0)))
    samples: list[dict] = []
    last_clock = None
    frame_index = 0
    while cap.grab():
        if frame_index % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            read = read_scoreboard(frame) or {}
            clock = read.get("clock")
            row = {"timestamp_ms": int(round(frame_index * 1000.0 / fps)), "frame": frame_index}
            row["clock"] = clock
            row["clock_running"] = None if clock is None or last_clock is None else clock != last_clock
            row.update({key: read.get(key) for key in _KEYS if key != "clock"})
            samples.append(row)
            if clock is not None:
                last_clock = clock
        frame_index += 1
    cap.release()
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("game_id")
    parser.add_argument("video")
    parser.add_argument("--video-label", help="path stored in the file (default: VIDEO as given)")
    parser.add_argument("--out", help="default: data/scoreboard_tracks/<game_id>.json")
    parser.add_argument("--keep-clock", action="store_true", help="keep clock and clock_running from the existing file")
    args = parser.parse_args()
    out = Path(args.out) if args.out else track_path(args.game_id)
    samples = build_samples(args.video)
    if args.keep_clock:
        previous = json.loads(out.read_text(encoding="utf-8"))
        previous = previous.get("samples") if isinstance(previous, dict) else previous
        by_time = {int(row["timestamp_ms"]): row for row in previous or []}
        missing = [row["timestamp_ms"] for row in samples if row["timestamp_ms"] not in by_time]
        if missing:
            raise SystemExit(f"{len(missing)} samples have no match in {out}, first at {missing[0]} ms")
        for row in samples:
            old = by_time[row["timestamp_ms"]]
            row["clock"] = old.get("clock")
            row["clock_running"] = old.get("clock_running")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"game_id": args.game_id, "video": args.video_label or args.video, "samples": samples}
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(f"{len(samples)} samples -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
