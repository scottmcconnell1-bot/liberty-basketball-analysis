"""Measure net_moved_after_shot on tagged shots (read-only baseline).

Task 1 step 1 — NEXT_TASK.md. Imports net_detector / ai_bridge only; never edits them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_bridge import detect_dynamic_entry_crossing, run_saved_v6_rule  # noqa: E402
from net_detector import net_moved_after_shot  # noqa: E402

SHOT_KINDS = {"2PT", "3PT", "FT"}
RESULTS = {"Make", "Miss"}
BUILD_QUARTERS = {"Q1", "Q2", "Q3"}

DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs"),
]

FILMS = [
    {
        "name": "notus_a1",
        "video_rel": "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
        "tags_rel": "data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json",
        "track_candidates": [
            Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks_notus_q1.json"),
            Path("/mnt/c/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json"),
        ],
    },
    {
        "name": "adrian",
        "video_rel": "uploads/nfhs_gam0a66d85e12.mp4",
        "tags_rel": "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json",
        "track_candidates": [
            Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks.json"),
            Path("/mnt/c/Users/scott/AppData/Local/Temp/v6_tracks.json"),
        ],
    },
]

Q4_TRACK_CANDIDATES = [
    Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks_q4.json"),
    Path("/mnt/c/Users/scott/AppData/Local/Temp/v6_tracks_q4.json"),
]


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is None:
            continue
        p = Path(cand)
        if p.exists():
            return p
    return None


def clock_ms(text: str) -> int:
    minutes, seconds = str(text).split(":")
    return int(round((int(minutes) * 60 + float(seconds)) * 1000))


def load_shot_tags(tags_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(tags_path.read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    shots = []
    for row in rows:
        if row.get("eventtype") not in SHOT_KINDS:
            continue
        if (row.get("result") or "") not in RESULTS:
            continue
        quarter = row.get("quarter") or ""
        if quarter not in {"Q1", "Q2", "Q3", "Q4"}:
            continue
        t = clock_ms(row["start"])
        shots.append(
            {
                "t": t,
                "quarter": quarter,
                "eventtype": row.get("eventtype"),
                "result": row.get("result"),
                "label": row.get("label") or f"{row.get('eventtype')} {row.get('result')}",
                "player": row.get("player") or "",
                "start": row.get("start"),
            }
        )
    return shots


def load_tracks(path: Path) -> Dict[int, Dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {int(row["t"]): row for row in rows}


def build_combined(track: Dict[str, Any]) -> List[List[float]]:
    ball = list(track.get("ball") or [])
    bodd = list(track.get("bodd") or [])
    combined = list(ball)
    if bodd and ball:
        last_ball_frame = ball[-1][0]
        for pt in bodd:
            if pt[0] > last_ball_frame:
                combined.append(pt)
    elif not ball and bodd:
        combined = list(bodd)
    return combined


def find_cross_idx(combined: List[List[float]], hoop_x: float, hoop_y: float, hoop_w: float, scale_y: float):
    """Exact crossing logic from ai_bridge.run_saved_v6_rule (lines 1014–1043)."""
    if len(combined) < 3:
        return None

    cross_idx = None
    for i in range(len(combined) - 1):
        y1 = combined[i][2]

        # Ball ABOVE hoop_y
        if y1 < hoop_y:
            # Check next 8 samples for crossing
            found_cross = False
            for j in range(i + 1, min(i + 9, len(combined))):
                y2 = combined[j][2]
                x2 = combined[j][1]

                # Ball crosses hoop_y going DOWN
                if y2 >= hoop_y:
                    # "within 0.55 of the hoop's WIDTH"
                    horiz_dist = abs(x2 - hoop_x)
                    if horiz_dist <= 0.55 * hoop_w:
                        cross_idx = j
                        found_cross = True
                        break

            if found_cross:
                break
            # Continue checking other above frames if no crossing found

    if cross_idx is None:
        cross_idx = detect_dynamic_entry_crossing(combined, hoop_x, hoop_y, hoop_w, scale_y)

    return cross_idx


def peak_from_track(
    track: Dict[str, Any], t_ms: int, fps: float
) -> Tuple[int, bool, Optional[int], str]:
    """Return (absolute_peak_frame, used_no_crossing, ball_offset, reason)."""
    hoop = track["hoop"]
    hoop_x, hoop_y, hoop_w, _hoop_area = hoop
    scale_y = float(track.get("_court_scale_y", 1.0))
    ball = list(track.get("ball") or [])
    combined = build_combined(track)
    tag_frame = int(round(t_ms / 1000.0 * fps))

    cross_idx = find_cross_idx(combined, hoop_x, hoop_y, hoop_w, scale_y)
    if cross_idx is not None:
        offset = int(combined[cross_idx][0])
        return tag_frame + offset, False, offset, "crossing"

    # NO-CROSSING RULE: every shot without a crossing (makes and misses).
    if ball:
        hx, hy = float(hoop_x), float(hoop_y)
        best = min(ball, key=lambda pt: (pt[1] - hx) ** 2 + (pt[2] - hy) ** 2)
        offset = int(best[0])
        return tag_frame + offset, True, offset, "no_crossing_closest_ball"
    return tag_frame, True, 0, "no_crossing_tag_frame"


class FrameReader:
    def __init__(self, video_path: Path):
        self.path = video_path
        self.cap = cv2.VideoCapture(str(video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = float(fps) if fps and fps > 1e-6 else 25.0

    def __call__(self, frame_idx: int):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
        ok, frame = self.cap.read()
        if not ok:
            return None
        return frame

    def close(self) -> None:
        self.cap.release()


def rule_predictions(timestamps: List[int], tracks_path: Path) -> Dict[int, Dict[str, Any]]:
    scored = run_saved_v6_rule([float(t) for t in timestamps], str(tracks_path))
    return {int(row["tag_ts"]): row for row in scored["results"]}


def process_film(
    film: Dict[str, Any],
    out_rows: List[Dict[str, Any]],
    counters: Dict[str, int],
) -> None:
    video_path = ROOT / film["video_rel"]
    tags_path = ROOT / film["tags_rel"]
    tracks_path = pick_existing(*film["track_candidates"])
    if tracks_path is None:
        raise FileNotFoundError(f"No track file for {film['name']}: {film['track_candidates']}")
    if not video_path.exists():
        raise FileNotFoundError(f"Missing video: {video_path}")
    if not tags_path.exists():
        raise FileNotFoundError(f"Missing tags: {tags_path}")

    tags = load_shot_tags(tags_path)
    tracks = load_tracks(tracks_path)
    reader = FrameReader(video_path)
    try:
        build_tags = [
            s
            for s in tags
            if s["quarter"] in BUILD_QUARTERS and int(s["t"]) in tracks
        ]
        times = [int(s["t"]) for s in build_tags]
        preds = rule_predictions(times, tracks_path) if times else {}

        for shot in build_tags:
            t = int(shot["t"])
            track = tracks[t]
            hoop = track["hoop"]
            hoop_x, hoop_y, hoop_w = float(hoop[0]), float(hoop[1]), float(hoop[2])
            peak_frame, used_nc, offset, peak_reason = peak_from_track(track, t, reader.fps)
            if used_nc:
                counters["no_crossing"] += 1

            rim_r = hoop_w / 2.0
            moved = bool(
                net_moved_after_shot(reader, peak_frame, (hoop_x, hoop_y), rim_r=rim_r)
            )

            pred_row = preds.get(t) or {}
            rule_pred = bool(pred_row.get("pred", False))
            gt_make = (shot["result"] == "Make")
            # Prefer tag ground truth; fall back to rule's true if present.
            if "true" in pred_row:
                gt_make = bool(pred_row["true"])

            missed_make = gt_make and (not rule_pred)
            is_miss = not gt_make

            row = {
                "film": film["name"],
                "set": "build",
                "t": t,
                "start": shot["start"],
                "quarter": shot["quarter"],
                "label": shot["label"],
                "player": shot["player"],
                "gt_make": gt_make,
                "rule_pred_make": rule_pred,
                "missed_make": missed_make,
                "is_miss": is_miss,
                "net_moved": moved,
                "peak_frame": peak_frame,
                "ball_offset": offset,
                "peak_reason": peak_reason,
                "used_no_crossing_rule": used_nc,
                "hoop_x": hoop_x,
                "hoop_y": hoop_y,
                "hoop_w": hoop_w,
                "rim_r": rim_r,
                "fps": reader.fps,
                "tracks_path": str(tracks_path),
                "video_path": str(video_path),
            }
            out_rows.append(row)

            if missed_make:
                counters["missed_makes"] += 1
                if moved:
                    counters["missed_makes_net_true"] += 1
                else:
                    counters["missed_makes_net_false"] += 1
            if is_miss:
                counters["misses"] += 1
                if moved:
                    counters["misses_net_true"] += 1
                else:
                    counters["misses_net_false"] += 1
            counters["build_processed"] += 1
            print(
                f"[{film['name']}] t={t} q={shot['quarter']} "
                f"gt={'make' if gt_make else 'miss'} rule={'make' if rule_pred else 'miss'} "
                f"net_moved={moved} peak={peak_frame} nc={used_nc}",
                flush=True,
            )
    finally:
        reader.close()


def summarize(build_rows: List[Dict[str, Any]], counters: Dict[str, int], unseen_note: str) -> str:
    mm = counters["missed_makes"]
    mm_t = counters["missed_makes_net_true"]
    mm_f = counters["missed_makes_net_false"]
    miss = counters["misses"]
    miss_t = counters["misses_net_true"]
    miss_f = counters["misses_net_false"]
    recovery = (100.0 * mm_t / mm) if mm else 0.0

    lines = [
        "# net_moved_after_shot baseline (Task 1 step 1)",
        "",
        f"Build shots processed: {counters['build_processed']}",
        f"Shots using no-crossing rule: {counters['no_crossing']}",
        "",
        "| Metric | Build Set | Unseen Set |",
        "|--------|-----------|------------|",
        f"| Missed Makes (GT=Make, Rule=Miss) | {mm} | n/a |",
        f"| Of Missed Makes: Net Moved = True | {mm_t} (recovery {recovery:.1f}%) | n/a |",
        f"| Of Missed Makes: Net Moved = False | {mm_f} | n/a |",
        f"| Misses (GT=Miss) | {miss} | n/a |",
        f"| Of Misses: Net Moved = True (False Makes) | {miss_t} | n/a |",
        f"| Of Misses: Net Moved = False | {miss_f} | n/a |",
        "",
        f"Unseen set: {unseen_note}",
        "",
        "## Missed makes detail",
        "",
    ]
    for row in build_rows:
        if not row["missed_make"]:
            continue
        lines.append(
            f"- t={row['t']} q={row['quarter']} {row['label']} player={row['player']!r} "
            f"net_moved={row['net_moved']} peak={row['peak_frame']} "
            f"hoop=({row['hoop_x']}, {row['hoop_y']}, w={row['hoop_w']}) "
            f"peak_reason={row['peak_reason']}"
        )
    lines.append("")
    lines.append("## Misses with net_moved=True (false makes)")
    lines.append("")
    false_makes = [r for r in build_rows if r["is_miss"] and r["net_moved"]]
    if not false_makes:
        lines.append("- (none)")
    else:
        for row in false_makes:
            lines.append(
                f"- t={row['t']} q={row['quarter']} {row['label']} "
                f"peak={row['peak_frame']} peak_reason={row['peak_reason']}"
            )
    lines.append("")
    return "\n".join(lines)


def default_out_dir() -> Path:
    found = pick_existing(*DEFAULT_OUT_CANDIDATES)
    if found is not None:
        return found
    # Prefer the Windows-shaped path string as the documented default even if missing;
    # callers should pass --out in the sandbox.
    return DEFAULT_OUT_CANDIDATES[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Results folder (default: Liberty_Shot_Outputs outside the repo)",
    )
    args = parser.parse_args()
    out_dir = Path(args.out) if args.out is not None else default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    q4 = pick_existing(*Q4_TRACK_CANDIDATES)
    if q4 is None:
        unseen_note = "not available: Adrian Q4 tracks were never built"
        unseen_rows: List[Dict[str, Any]] = []
    else:
        unseen_note = f"tracks found at {q4} (unexpected for this task; not scored here)"
        unseen_rows = []

    build_rows: List[Dict[str, Any]] = []
    counters = {
        "build_processed": 0,
        "no_crossing": 0,
        "missed_makes": 0,
        "missed_makes_net_true": 0,
        "missed_makes_net_false": 0,
        "misses": 0,
        "misses_net_true": 0,
        "misses_net_false": 0,
    }

    for film in FILMS:
        process_film(film, build_rows, counters)

    summary_md = summarize(build_rows, counters, unseen_note)
    build_path = out_dir / "net_moved_build_results.json"
    unseen_path = out_dir / "net_moved_unseen_results.json"
    summary_path = out_dir / "net_moved_summary.md"

    build_path.write_text(json.dumps(build_rows, indent=2), encoding="utf-8")
    unseen_path.write_text(
        json.dumps(
            {
                "available": q4 is not None,
                "note": unseen_note,
                "rows": unseen_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_path.write_text(summary_md, encoding="utf-8")

    print("")
    print("=== SUMMARY ===")
    print(summary_md)
    print(f"Wrote {build_path}")
    print(f"Wrote {unseen_path}")
    print(f"Wrote {summary_path}")
    print(f"no_crossing_rule_count={counters['no_crossing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
