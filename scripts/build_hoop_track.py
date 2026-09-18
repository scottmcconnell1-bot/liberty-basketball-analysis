#!/usr/bin/env python3
"""Build a hoop/net track from film. Sidecar JSON, no schema change."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from net_detector import detect_hoop, save_hoop_track  # noqa: E402

GAME = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
VIDEO = ROOT / "uploads" / "nfhs_gam0a66d85e12.mp4"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-id", default=GAME)
    parser.add_argument("--video", default=str(VIDEO))
    parser.add_argument("--step-ms", type=int, default=2000)
    parser.add_argument("--max-ms", type=int, default=0, help="0 = full video")
    parser.add_argument("--pose", action="store_true", help="also try court pose (slow)")
    args = parser.parse_args()

    import cv2

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"FAIL: cannot open {args.video}")
        return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step_frames = max(1, int(round((args.step_ms / 1000.0) * fps)))
    samples = []
    fn = 0
    while fn < frame_count:
        ts = int(round(fn * 1000.0 / fps))
        if args.max_ms and ts > args.max_ms:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ok, frame = cap.read()
        if not ok:
            break
        if args.pose:
            hit = detect_hoop(frame)
        else:
            from net_detector import detect_hoop_cv

            hit = detect_hoop_cv(frame)
        if hit:
            hit["timestamp_ms"] = ts
            hit["frame"] = fn
            samples.append(hit)
        fn += step_frames
        if len(samples) % 40 == 0 and samples:
            print(f"scanned frame {fn}/{frame_count}, {len(samples)} hoop hits", flush=True)
    cap.release()
    path = save_hoop_track(args.game_id, samples, video=Path(args.video).name)
    print({"samples": len(samples), "path": str(path), "frames": fn})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
