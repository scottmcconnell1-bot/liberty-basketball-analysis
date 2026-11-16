"""Collect full-flight ball / hoop / player tracks for shot-rules measure.

Detection only — no rules. Reuses EXISTING settings from collect_q4_bodd.py
(do not edit that file); adds no new detector number.

BODD = C:\\Users\\scott\\AppData\\Local\\Temp\\BODD_yolov8n_0001.pt
  full frame, conf=0.12, imgsz=960 (collect_samples). Classes kept:
  basketball, hoop, player. Player boxes per frame only — NO tracker,
  NO tracker_id.

V6 = C:\\Users\\scott\\AppData\\Local\\Temp\\ball_net_runs\\v6\\weights\\best.pt
  hoop crop exactly as v6_ball: hx-260..hx+260, hy-200..hy+240, conf=0.28,
  imgsz=640.

Both ball series are stored separately per frame. The rules layer uses v6
where it has a detection in that frame, otherwise BODD basketball (no
averaging, no filling).

Adrian Q4 is never read, detected, or reported (VETTED C5).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIXEL_MISS = HERE / "pixel_miss"

# Existing model paths (collect_q4_bodd.py) — Windows + WSL candidates.
BODD_CANDIDATES = [
    Path(r"C:\Users\scott\AppData\Local\Temp\BODD_yolov8n_0001.pt"),
    Path("/mnt/c/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt"),
]
V6_CANDIDATES = [
    Path(r"C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt"),
    Path("/mnt/c/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt"),
]

ADRIAN_VIDEO_REL = "uploads/nfhs_gam0a66d85e12.mp4"
NOTUS_VIDEO_REL = "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4"
ADRIAN_TAGS_REL = (
    "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
)
NOTUS_TAGS_REL = (
    "data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json"
)
ADRIAN_GAME_ID = (
    "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941"
)
NOTUS_GAME_ID = "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334"

# Scott-approved window (spec 33); collector CLI uses these for ranges.
DEFAULT_BEFORE_MS = 3000
DEFAULT_AFTER_MS = 2000
# Matching window used by find_shots_measure to define "fake" = unmatched finder.
FAKE_MATCH_WINDOW_MS = 8000

FAKE_GENERATORS = frozenset({"precision", "rim_arc"})  # exclude tagged_gap

EXPECTED_TAG_COUNTS = {"adrian": 109, "notus": 31}
EXPECTED_FAKE_COUNTS = {"adrian": 106, "notus": 31}

DEFAULT_FAKES_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\find_shots\results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/find_shots/results.json"),
]


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is not None and Path(cand).exists():
            return Path(cand)
    return None


def filter_out_q4(moments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adrian Q4 is never read, detected, or reported (C5)."""
    return [m for m in moments if str(m.get("quarter") or "") != "Q4"]


def moment_window_ms(
    t_ms: int, before_ms: int, after_ms: int
) -> Tuple[int, int]:
    return (int(t_ms) - int(before_ms), int(t_ms) + int(after_ms))


def merge_overlapping_windows(
    moments: Sequence[Dict[str, Any]],
    before_ms: int,
    after_ms: int,
) -> List[Dict[str, Any]]:
    """Merge overlapping [t-before, t+after] ranges. Each frame detected once.

    Returns list of {start_ms, end_ms, moment_indices}.
    Two moments 2000 ms apart with before=3000/after=2000 → one merged range.
    """
    if not moments:
        return []
    items = []
    for i, m in enumerate(moments):
        lo, hi = moment_window_ms(int(m["tag_t_ms"]), before_ms, after_ms)
        items.append((lo, hi, i))
    items.sort(key=lambda x: (x[0], x[1], x[2]))

    merged: List[Dict[str, Any]] = []
    cur_lo, cur_hi, cur_idx = items[0][0], items[0][1], [items[0][2]]
    for lo, hi, i in items[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
            cur_idx.append(i)
        else:
            merged.append(
                {"start_ms": cur_lo, "end_ms": cur_hi, "moment_indices": list(cur_idx)}
            )
            cur_lo, cur_hi, cur_idx = lo, hi, [i]
    merged.append(
        {"start_ms": cur_lo, "end_ms": cur_hi, "moment_indices": list(cur_idx)}
    )
    return merged


def load_shot_tags(tags_path: Path) -> List[Dict[str, Any]]:
    """Via measure_net_moved.load_shot_tags (lines 73–97)."""
    if str(PIXEL_MISS) not in sys.path:
        sys.path.insert(0, str(PIXEL_MISS))
    from measure_net_moved import load_shot_tags as _load  # noqa: WPS433

    return _load(Path(tags_path))


def open_db_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    uri = resolved.as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_finder_rows(conn: sqlite3.Connection, game_id: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT id, timestamp_ms, details_json
        FROM events
        WHERE source_type = 'ai'
          AND event_type = 'shot'
          AND game_id = ?
        """,
        (game_id,),
    )
    rows: List[Dict[str, Any]] = []
    for event_id, timestamp_ms, details_json in cur.fetchall():
        try:
            details = json.loads(details_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(details, dict) or "generator" not in details:
            continue
        rows.append(
            {
                "id": int(event_id),
                "t": int(timestamp_ms),
                "generator": details.get("generator"),
                "shot_kind": details.get("shot_kind"),
            }
        )
    return rows


def match_unmatched_finder(
    tag_times: Sequence[int],
    finder_times: Sequence[int],
    window_ms: int,
) -> List[int]:
    """Return indices into finder_times that have no matched tag (greedy NN)."""
    # Import pure matcher from find_shots_measure (same package; not core).
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import find_shots_measure as fsm  # noqa: WPS433

    idx = fsm.match_shot_indices(tag_times, finder_times, window_ms)
    return list(idx["unmatched_finder"])


def load_fakes_from_find_shots_results(
    fakes_path: Path,
    db_path: Path,
    root: Path = ROOT,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fakes = precision+rim_arc finder shots with no tag (exclude tagged_gap).

    Uses spans / window / game ids from find_shots/results.json and recomputes
    unmatched finders from the DB (results.json stores counts, not extra times).
    Adrian Q4 part is ignored (C5).
    """
    data = json.loads(Path(fakes_path).read_text(encoding="utf-8"))
    window_ms = int(data.get("window_ms") or FAKE_MATCH_WINDOW_MS)
    parts = data.get("parts") or {}

    conn = open_db_readonly(db_path)
    try:
        adrian_finders = load_finder_rows(conn, data.get("adrian_game_id") or ADRIAN_GAME_ID)
        notus_finders = load_finder_rows(conn, data.get("notus_game_id") or NOTUS_GAME_ID)
    finally:
        conn.close()

    out: Dict[str, List[Dict[str, Any]]] = {"adrian": [], "notus": []}

    def fakes_for_part(
        part_name: str,
        film_key: str,
        tags: List[Dict[str, Any]],
        finders_all: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        part = parts.get(part_name) or {}
        span = part.get("span") or {}
        t_min = span.get("t_min")
        t_max = span.get("t_max")
        if t_min is None or t_max is None:
            # Fall back to tag span ± window.
            if not tags:
                return []
            ts = [int(t["t"]) for t in tags]
            t_min = min(ts) - window_ms
            t_max = max(ts) + window_ms
        finders = [
            r
            for r in finders_all
            if str(r.get("generator")) in FAKE_GENERATORS
            and int(t_min) <= int(r["t"]) <= int(t_max)
        ]
        tag_times = [int(t["t"]) for t in tags]
        finder_times = [int(r["t"]) for r in finders]
        unmatched_i = match_unmatched_finder(tag_times, finder_times, window_ms)
        fakes = []
        for i in unmatched_i:
            row = finders[i]
            fakes.append(
                {
                    "moment_id": f"fake_{film_key}_{row['id']}",
                    "kind": "fake",
                    "film": film_key,
                    "tag_t_ms": int(row["t"]),
                    "quarter": None,
                    "eventtype": None,
                    "result": None,
                    "generator": row.get("generator"),
                    "finder_id": row["id"],
                }
            )
        return fakes

    adrian_tags = [
        t
        for t in load_shot_tags(root / ADRIAN_TAGS_REL)
        if t.get("quarter") in {"Q1", "Q2", "Q3"}
    ]
    notus_tags = [
        t
        for t in load_shot_tags(root / NOTUS_TAGS_REL)
        if t.get("quarter") == "Q1"
    ]

    # Never use Adrian Q4 part from results.json (C5).
    out["adrian"] = fakes_for_part(
        "Adrian Q1-Q3", "adrian", adrian_tags, adrian_finders
    )
    out["notus"] = fakes_for_part("Notus Q1", "notus", notus_tags, notus_finders)
    return out


def tags_to_moments(
    tags: Sequence[Dict[str, Any]], film_key: str
) -> List[Dict[str, Any]]:
    moments = []
    for i, t in enumerate(tags):
        moments.append(
            {
                "moment_id": f"tag_{film_key}_{int(t['t'])}_{i}",
                "kind": "tag",
                "film": film_key,
                "tag_t_ms": int(t["t"]),
                "quarter": t.get("quarter"),
                "eventtype": t.get("eventtype"),
                "result": t.get("result"),
                "player": t.get("player"),
                "start": t.get("start"),
            }
        )
    return moments


def ms_to_frame(t_ms: int, fps: float) -> int:
    return int(round(float(t_ms) / 1000.0 * float(fps)))


def frame_to_ms(frame: int, fps: float) -> int:
    return int(round(1000.0 * float(frame) / float(fps)))


def detect_range(
    bodd_model: Any,
    v6_model: Any,
    cap: Any,
    start_frame: int,
    end_frame: int,
    *,
    bodd_conf: float = 0.12,
    bodd_imgsz: int = 960,
    v6_conf: float = 0.28,
    v6_imgsz: int = 640,
) -> Dict[int, Dict[str, Any]]:
    """Run BODD full-frame + V6 hoop-crop once per frame in [start, end].

    Returns dict keyed by absolute frame number:
      {ball_bodd, ball_v6, hoop, players}
    Settings match collect_q4_bodd.collect_samples / v6_ball.
    """
    import cv2  # local: detection CLI only

    per_frame: Dict[int, Dict[str, Any]] = {}
    last_hoop: Optional[Tuple[float, float, float, float]] = None
    # v6_ball prev pick (collect_q4_bodd.py:129-145): carried within one
    # merged range; reset to None on a frame with no pick.
    prev: Optional[Tuple[float, float]] = None

    total = max(0, int(end_frame) - int(start_frame) + 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_frame))
    for offset in range(total):
        frame_i = int(start_frame) + offset
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]

        # --- BODD full frame (collect_samples settings) ---
        pred = bodd_model.predict(
            frame, conf=bodd_conf, imgsz=bodd_imgsz, verbose=False
        )[0]
        balls: List[Dict[str, float]] = []
        hoops: List[Dict[str, float]] = []
        players: List[Dict[str, float]] = []
        if pred.boxes is not None:
            for box in pred.boxes:
                name = bodd_model.names[int(box.cls[0])]
                if name not in ("basketball", "hoop", "player"):
                    continue
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                item = {
                    "x": round((x1 + x2) / 2, 1),
                    "y": round((y1 + y2) / 2, 1),
                    "w": round(x2 - x1, 1),
                    "h": round(y2 - y1, 1),
                    "c": round(float(box.conf[0]), 3),
                }
                if name == "basketball":
                    balls.append(item)
                elif name == "hoop":
                    hoops.append(item)
                else:
                    players.append(item)

        hoop_box = None
        if hoops:
            hoop_box = max(hoops, key=lambda it: it["c"])
            last_hoop = (hoop_box["x"], hoop_box["y"], hoop_box["w"], hoop_box["h"])

        ball_bodd = None
        if balls:
            best = max(balls, key=lambda it: it["c"])
            ball_bodd = [frame_i, best["x"], best["y"], best["c"]]

        # --- V6 on hoop crop (exactly as v6_ball / collect_q4_bodd.py:129-145) ---
        ball_v6 = None
        hx_hy = None
        if hoop_box is not None:
            hx_hy = (hoop_box["x"], hoop_box["y"])
        elif last_hoop is not None:
            hx_hy = (last_hoop[0], last_hoop[1])
        if hx_hy is not None:
            hx, hy = hx_hy
            x0 = int(max(0, hx - 260))
            y0 = int(max(0, hy - 200))
            x1 = int(min(w, hx + 260))
            y1 = int(min(h, hy + 240))
            crop = frame[y0:y1, x0:x1]
            vpred = v6_model.predict(
                crop, conf=v6_conf, imgsz=v6_imgsz, verbose=False
            )[0]
            if vpred.boxes is None or len(vpred.boxes) == 0:
                prev = None
            else:
                picks = []
                for box in vpred.boxes:
                    a, b, c, d = [float(v) for v in box.xyxy[0]]
                    cx, cy = x0 + (a + c) / 2, y0 + (b + d) / 2
                    if abs(cx - hx) > 220 or abs(cy - hy) > 220:
                        continue
                    conf = float(box.conf[0])
                    dist2 = (cx - hx) ** 2 + (cy - hy) ** 2
                    if prev is not None:
                        dist2 += ((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) * 0.35
                    picks.append((dist2, cx, cy, conf))
                if not picks:
                    prev = None
                else:
                    picks.sort()
                    _d, cx, cy, conf = picks[0]
                    prev = (cx, cy)
                    ball_v6 = [frame_i, round(cx, 1), round(cy, 1), round(conf, 3)]
        else:
            prev = None

        per_frame[frame_i] = {
            "ball_bodd": ball_bodd,
            "ball_v6": ball_v6,
            "hoop": hoop_box,
            "players": [
                {
                    "frame": frame_i,
                    "x": p["x"],
                    "y": p["y"],
                    "w": p["w"],
                    "h": p["h"],
                    # no tracker_id
                }
                for p in players
            ],
        }
        if offset % 50 == 0:
            print(
                f"  frame {frame_i} ({offset + 1}/{total})",
                flush=True,
            )
    return per_frame


def slice_moment(
    moment: Dict[str, Any],
    per_frame: Dict[int, Dict[str, Any]],
    fps: float,
    before_ms: int,
    after_ms: int,
) -> Dict[str, Any]:
    lo_ms, hi_ms = moment_window_ms(int(moment["tag_t_ms"]), before_ms, after_ms)
    lo_f = ms_to_frame(lo_ms, fps)
    hi_f = ms_to_frame(hi_ms, fps)
    ball_track: List[List[float]] = []
    bodd_track: List[List[float]] = []
    hoop_samples: List[Dict[str, Any]] = []
    player_boxes: List[Dict[str, Any]] = []
    for f in range(lo_f, hi_f + 1):
        row = per_frame.get(f)
        if row is None:
            continue
        if row.get("ball_v6") is not None:
            ball_track.append(list(row["ball_v6"]))
        if row.get("ball_bodd") is not None:
            bodd_track.append(list(row["ball_bodd"]))
        if row.get("hoop") is not None:
            h = row["hoop"]
            hoop_samples.append(
                {
                    "t": frame_to_ms(f, fps),
                    "x": h["x"],
                    "y": h["y"],
                    "w": h["w"],
                    "h": h["h"],
                }
            )
        player_boxes.extend(row.get("players") or [])
    out = dict(moment)
    out.update(
        {
            "ball_track": ball_track,
            "bodd_track": bodd_track,
            "hoop_samples": hoop_samples,
            "player_boxes": player_boxes,
            "window_ms": {"before": before_ms, "after": after_ms, "lo": lo_ms, "hi": hi_ms},
        }
    )
    return out


def collect_film(
    *,
    film_key: str,
    video_path: Path,
    moments: List[Dict[str, Any]],
    bodd_model: Any,
    v6_model: Any,
    before_ms: int,
    after_ms: int,
) -> Dict[str, Any]:
    import cv2

    moments = filter_out_q4(moments)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if fps <= 0:
        raise SystemExit(f"Bad fps from cv2 for {video_path}")

    merged = merge_overlapping_windows(moments, before_ms, after_ms)
    print(
        f"{film_key}: {len(moments)} moments → {len(merged)} merged ranges; "
        f"video {width}x{height} @ {fps} fps",
        flush=True,
    )

    t0 = time.time()
    # Detect each merged range once; accumulate per-frame dict.
    all_frames: Dict[int, Dict[str, Any]] = {}
    for mi, seg in enumerate(merged):
        sf = ms_to_frame(seg["start_ms"], fps)
        ef = ms_to_frame(seg["end_ms"], fps)
        print(
            f"{film_key}: range {mi + 1}/{len(merged)} "
            f"frames {sf}..{ef} ({len(seg['moment_indices'])} moments)",
            flush=True,
        )
        part = detect_range(bodd_model, v6_model, cap, sf, ef)
        all_frames.update(part)
    cap.release()
    elapsed = time.time() - t0

    sliced = [
        slice_moment(m, all_frames, fps, before_ms, after_ms) for m in moments
    ]
    return {
        "film": film_key,
        "video": str(video_path),
        "fps": fps,
        "width": width,
        "height": height,
        "run_time_s": round(elapsed, 3),
        "n_moments": len(sliced),
        "n_merged_ranges": len(merged),
        "moments": sliced,
        "applied_to_core": False,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Collect flight tracks (BODD+V6). Detection only; no rules."
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Output directory (REFUSE if it already exists).",
    )
    p.add_argument(
        "--fakes",
        type=Path,
        default=None,
        help="Path to find_shots/results.json (spec 32 extras source).",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=ROOT / "film_analysis.db",
        help="film_analysis.db (read-only) for fake finder rows.",
    )
    p.add_argument(
        "--before-ms",
        type=int,
        default=DEFAULT_BEFORE_MS,
        help="Detection window before tag/finder time (Scott-approved 3000).",
    )
    p.add_argument(
        "--after-ms",
        type=int,
        default=DEFAULT_AFTER_MS,
        help="Detection window after tag/finder time (Scott-approved 2000).",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    if out_dir.exists():
        raise SystemExit(f"Refuse: output directory already exists: {out_dir}")

    fakes_path = args.fakes or pick_existing(*DEFAULT_FAKES_CANDIDATES)
    if fakes_path is None:
        raise SystemExit(
            "No find_shots/results.json found. Pass --fakes PATH."
        )

    bodd_path = pick_existing(*BODD_CANDIDATES)
    v6_path = pick_existing(*V6_CANDIDATES)
    if bodd_path is None or v6_path is None:
        raise SystemExit(f"Missing models: BODD={bodd_path} V6={v6_path}")

    # Tags (Q4 filtered out before any video read).
    adrian_tags_all = load_shot_tags(ROOT / ADRIAN_TAGS_REL)
    notus_tags_all = load_shot_tags(ROOT / NOTUS_TAGS_REL)
    adrian_tags = [t for t in adrian_tags_all if t.get("quarter") in {"Q1", "Q2", "Q3"}]
    notus_tags = [t for t in notus_tags_all if t.get("quarter") == "Q1"]
    # Belt-and-suspenders C5: drop any Q4 that slipped through.
    adrian_tags = filter_out_q4(adrian_tags)

    adrian_tag_moments = tags_to_moments(adrian_tags, "adrian")
    notus_tag_moments = tags_to_moments(notus_tags, "notus")

    fakes_by_film = load_fakes_from_find_shots_results(
        fakes_path, Path(args.db), root=ROOT
    )
    adrian_fakes = fakes_by_film["adrian"]
    notus_fakes = fakes_by_film["notus"]

    print(
        f"tags adrian={len(adrian_tag_moments)} (expected {EXPECTED_TAG_COUNTS['adrian']}) "
        f"notus={len(notus_tag_moments)} (expected {EXPECTED_TAG_COUNTS['notus']})",
        flush=True,
    )
    print(
        f"fakes adrian={len(adrian_fakes)} (expected {EXPECTED_FAKE_COUNTS['adrian']}) "
        f"notus={len(notus_fakes)} (expected {EXPECTED_FAKE_COUNTS['notus']})",
        flush=True,
    )
    for film_key, n, exp in (
        ("adrian tags", len(adrian_tag_moments), EXPECTED_TAG_COUNTS["adrian"]),
        ("notus tags", len(notus_tag_moments), EXPECTED_TAG_COUNTS["notus"]),
        ("adrian fakes", len(adrian_fakes), EXPECTED_FAKE_COUNTS["adrian"]),
        ("notus fakes", len(notus_fakes), EXPECTED_FAKE_COUNTS["notus"]),
    ):
        if n != exp:
            print(f"COUNT DIFFERS: {film_key} got {n}, expected {exp} — continuing", flush=True)

    from ultralytics import YOLO

    print(f"Loading BODD {bodd_path}", flush=True)
    bodd_model = YOLO(str(bodd_path))
    print("bodd classes", bodd_model.names, flush=True)
    print(f"Loading V6 {v6_path}", flush=True)
    v6_model = YOLO(str(v6_path))

    adrian_moments = adrian_tag_moments + adrian_fakes
    notus_moments = notus_tag_moments + notus_fakes

    out_dir.mkdir(parents=True, exist_ok=False)

    adrian_json = collect_film(
        film_key="adrian",
        video_path=ROOT / ADRIAN_VIDEO_REL,
        moments=adrian_moments,
        bodd_model=bodd_model,
        v6_model=v6_model,
        before_ms=int(args.before_ms),
        after_ms=int(args.after_ms),
    )
    (out_dir / "adrian.json").write_text(
        json.dumps(adrian_json, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote adrian.json run_time_s={adrian_json['run_time_s']}",
        flush=True,
    )

    notus_json = collect_film(
        film_key="notus",
        video_path=ROOT / NOTUS_VIDEO_REL,
        moments=notus_moments,
        bodd_model=bodd_model,
        v6_model=v6_model,
        before_ms=int(args.before_ms),
        after_ms=int(args.after_ms),
    )
    (out_dir / "notus.json").write_text(
        json.dumps(notus_json, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote notus.json run_time_s={notus_json['run_time_s']}",
        flush=True,
    )
    print(f"Done. Output: {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
