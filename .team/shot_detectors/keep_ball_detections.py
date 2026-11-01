"""D1 — keep every ball detection near the rim; choose among them by real arc.

Spec: .team/specs/19_d1_job_spec.md (v4, VETTED; BINDING NOTES f–g).
v4: detection is v6_ball()'s setup from collect_q4_bodd.py (crop around the hoop, imgsz 640,
conf 0.28, sequential reads), which is how the saved ball tracks were made.
Standalone only. Never edits ai_bridge.py, models/, or protected files.
Truth key \"result\" is read ONLY by scoring/report code.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# --- fixed numbers from spec §§8–9 (and mapping/confidence from §§2,5) — no tuning ---
BALL_CLASS_NAME = "basketball"
BALL_CONFIDENCE = 0.28  # v6_ball's conf (collect_q4_bodd.py:125); never lower
CROP_LEFT_RIGHT = 260  # v6_ball crop: hoop_x-260 .. hoop_x+260
CROP_ABOVE = 200  # hoop_y-200 ..
CROP_BELOW = 240  # .. hoop_y+240
PREDICT_IMGSZ = 640
ZONE_HOOP_WIDTHS_H = 3.0
ZONE_ABOVE_HOOP_WIDTHS = 4.0
ZONE_BELOW_PX = 300
CANDIDATE_CAP = 3
MIN_POINTS_BEFORE = 4
MIN_POINTS_AFTER = 3
RANSAC_ITERATIONS = 100
RANSAC_SEED = 42
RESIDUAL_HOOP_W_FRAC = 0.15
WINDOW_BEFORE_START = -15  # frames: anchor-15 .. anchor
WINDOW_BEFORE_END = 0
WINDOW_AFTER_START = 1  # frames: anchor+1 .. anchor+12
WINDOW_AFTER_END = 12
MAPPING_MATCH_PX = 3
MAPPING_MIN_MATCH_RATE = 0.90
DIAGNOSTIC_HALF_WINDOW = 8
FPS_FALLBACK = 25.0
BUILD_QUARTERS = {"Q1", "Q2", "Q3"}
EXPECTED_BUILD = 140
BASELINE_MAKES_RIGHT = 28

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_PIXEL_MISS = HERE / "pixel_miss"
if str(_PIXEL_MISS) not in sys.path:
    sys.path.insert(0, str(_PIXEL_MISS))

from measure_net_moved import (  # noqa: E402
    FILMS,
    load_shot_tags,
    load_tracks,
    peak_from_track,
)
from small_fixes_v6_copy import decide_shot, reason_of  # noqa: E402

TRACKS_FALLBACK_DIRS = [
    Path(r"C:\Users\scott\AppData\Local\Temp"),
    Path("/mnt/c/Users/scott/AppData/Local/Temp"),
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\tracks"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/tracks"),
]

DEFAULT_OUT_DIRS = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_arc"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc"),
]

DEFAULT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_arc\candidates.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json"),
]


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is None:
            continue
        p = Path(cand)
        if p.exists():
            return p
    return None


def resolve_path(path_str: str) -> Path:
    raw = Path(path_str)
    if raw.exists():
        return raw
    s = str(path_str)
    if len(s) >= 3 and s[1] == ":" and s[0].isalpha():
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/").lstrip("/")
        alt = Path(f"/mnt/{drive}/{rest}")
        if alt.exists():
            return alt
    if s.startswith("/mnt/") and len(s) > 7:
        drive = s[5].upper()
        rest = s[7:].replace("/", "\\")
        alt = Path(f"{drive}:\\{rest}")
        if alt.exists():
            return alt
    return raw


def resolve_track_file(name: str, tracks_dir: Optional[Path] = None) -> Path:
    """Pick the first existing copy of a v6 track JSON (Temp or Liberty_Shot_Outputs/tracks)."""
    candidates: List[Path] = []
    if tracks_dir is not None:
        candidates.append(Path(tracks_dir) / name)
    for folder in TRACKS_FALLBACK_DIRS:
        candidates.append(folder / name)
    found = pick_existing(*candidates)
    if found is None:
        raise FileNotFoundError(f"Track file not found: {name} (tried {candidates})")
    return found


def default_out_dir() -> Path:
    found = pick_existing(*DEFAULT_OUT_DIRS)
    if found is not None:
        return found
    parent = pick_existing(
        Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs"),
        Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs"),
    )
    if parent is not None:
        return parent / "ball_arc"
    return DEFAULT_OUT_DIRS[0]


def film_track_name(film: Dict[str, Any]) -> str:
    for cand in film["track_candidates"]:
        return Path(cand).name
    raise ValueError(f"No track name for film {film.get('name')}")


def resolve_film_tracks(film: Dict[str, Any], tracks_dir: Optional[Path] = None) -> Path:
    name = film_track_name(film)
    extras = list(film.get("track_candidates") or [])
    if tracks_dir is not None:
        extras = [Path(tracks_dir) / name] + extras
    for folder in TRACKS_FALLBACK_DIRS:
        extras.append(folder / name)
    found = pick_existing(*[Path(p) for p in extras])
    if found is None:
        raise FileNotFoundError(f"No track file for {film['name']}: {name}")
    return found


# ---------------------------------------------------------------------------
# Zone / candidate helpers (no truth)
# ---------------------------------------------------------------------------


def in_near_hoop_zone(
    x: float, y: float, hoop_x: float, hoop_y: float, hoop_w: float
) -> bool:
    if abs(x - hoop_x) > ZONE_HOOP_WIDTHS_H * hoop_w:
        return False
    y_lo = hoop_y - ZONE_ABOVE_HOOP_WIDTHS * hoop_w
    y_hi = hoop_y + ZONE_BELOW_PX
    return y_lo <= y <= y_hi


def zone_filter_candidates(
    dets: Sequence[Dict[str, Any]], hoop_x: float, hoop_y: float, hoop_w: float
) -> List[Dict[str, Any]]:
    out = []
    for d in dets:
        if d.get("class_name") != BALL_CLASS_NAME:
            continue
        if float(d.get("confidence", 0.0)) < BALL_CONFIDENCE:
            continue
        x, y = float(d["x_center"]), float(d["y_center"])
        if in_near_hoop_zone(x, y, hoop_x, hoop_y, hoop_w):
            out.append(d)
    return out


def crop_bounds(
    hoop_x: float, hoop_y: float, frame_w: int, frame_h: int
) -> Tuple[int, int, int, int]:
    """v6_ball's crop around the hoop, clamped to the frame exactly as it does."""
    x0 = int(max(0, hoop_x - CROP_LEFT_RIGHT))
    y0 = int(max(0, hoop_y - CROP_ABOVE))
    x1 = int(min(frame_w, hoop_x + CROP_LEFT_RIGHT))
    y1 = int(min(frame_h, hoop_y + CROP_BELOW))
    return x0, y0, x1, y1


def detect_on_crop(model: Any, frame: Any, hoop_x: float, hoop_y: float) -> List[Dict[str, Any]]:
    """Every box v6 finds on the hoop crop, in full-frame coordinates (no single-pick)."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = crop_bounds(hoop_x, hoop_y, w, h)
    pred = model.predict(
        frame[y0:y1, x0:x1], conf=BALL_CONFIDENCE, imgsz=PREDICT_IMGSZ, verbose=False
    )[0]
    dets: List[Dict[str, Any]] = []
    if pred.boxes is None:
        return dets
    for box in pred.boxes:
        bx1, by1, bx2, by2 = [float(v) for v in box.xyxy[0]]
        bx1, bx2, by1, by2 = bx1 + x0, bx2 + x0, by1 + y0, by2 + y0
        dets.append(
            {
                "class_name": model.names[int(box.cls[0])],
                "confidence": float(box.conf[0]),
                "x_center": (bx1 + bx2) / 2.0,
                "y_center": (by1 + by2) / 2.0,
                "x1": bx1,
                "y1": by1,
                "x2": bx2,
                "y2": by2,
                "width": bx2 - bx1,
                "height": by2 - by1,
            }
        )
    return dets


def cap_top_candidates(
    cands: Sequence[Dict[str, Any]], cap: int = CANDIDATE_CAP
) -> Tuple[List[Dict[str, Any]], bool]:
    ordered = sorted(cands, key=lambda d: float(d.get("confidence", 0.0)), reverse=True)
    over = len(ordered) > cap
    return list(ordered[:cap]), over


def frames_to_extract(
    track: Dict[str, Any], t_ms: int, fps: float, anchor_frame: int
) -> List[int]:
    """BINDING NOTE f: saved track span UNION anchor-15 .. anchor+12."""
    tag_frame = int(round(t_ms / 1000.0 * fps))
    frames = set()
    for key in ("ball", "bodd"):
        for pt in track.get(key) or []:
            frames.add(tag_frame + int(pt[0]))
    frames.add(tag_frame)
    for off in range(WINDOW_BEFORE_START, WINDOW_AFTER_END + 1):
        frames.add(anchor_frame + off)
    return sorted(frames)


# ---------------------------------------------------------------------------
# RANSAC arc (real candidates only; never reads truth)
# ---------------------------------------------------------------------------


def _fit_parabola(ts: np.ndarray, ys: np.ndarray) -> Optional[Tuple[float, float, float]]:
    if len(ts) < 3:
        return None
    try:
        a, b, c = np.polyfit(ts, ys, 2)
    except (np.linalg.LinAlgError, ValueError):
        return None
    return float(a), float(b), float(c)


def _fit_line(ts: np.ndarray, vs: np.ndarray) -> Optional[Tuple[float, float]]:
    if len(ts) < 2:
        return None
    try:
        m, k = np.polyfit(ts, vs, 1)
    except (np.linalg.LinAlgError, ValueError):
        return None
    return float(m), float(k)


def ransac_before_anchor(
    points: List[Dict[str, Any]],
    hoop_w: float,
    *,
    iterations: int = RANSAC_ITERATIONS,
    seed: int = RANSAC_SEED,
    residual_frac: float = RESIDUAL_HOOP_W_FRAC,
    min_points: int = MIN_POINTS_BEFORE,
) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    """Parabola in t for y (a>0) and line in t for x. Returns per-frame chosen inlier."""
    residual = residual_frac * float(hoop_w)
    empty_params: Dict[str, Any] = {"model": "before", "ok": False}
    if len(points) < min_points:
        return {}, empty_params

    rng = random.Random(seed)
    best_count = -1
    best_params: Optional[Dict[str, Any]] = None
    best_inlier_idx: List[int] = []

    n = len(points)
    for _ in range(iterations):
        sample_i = rng.sample(range(n), 3)
        ts = np.array([points[i]["t"] for i in sample_i], dtype=float)
        ys = np.array([points[i]["y"] for i in sample_i], dtype=float)
        xs = np.array([points[i]["x"] for i in sample_i], dtype=float)
        para = _fit_parabola(ts, ys)
        line = _fit_line(ts, xs)
        if para is None or line is None:
            continue
        a, b, c = para
        if not (a > 0):
            continue
        m, k = line
        inliers = []
        for i, p in enumerate(points):
            t = float(p["t"])
            y_hat = a * t * t + b * t + c
            x_hat = m * t + k
            err = math.hypot(p["x"] - x_hat, p["y"] - y_hat)
            if err <= residual:
                inliers.append(i)
        if len(inliers) > best_count:
            best_count = len(inliers)
            best_inlier_idx = inliers
            best_params = {
                "model": "before",
                "ok": True,
                "a": a,
                "b": b,
                "c": c,
                "m": m,
                "k": k,
                "inlier_count": len(inliers),
                "residual": residual,
            }

    if best_params is None or best_count < min_points:
        return {}, empty_params

    a, b, c = best_params["a"], best_params["b"], best_params["c"]
    m, k = best_params["m"], best_params["k"]
    by_frame: Dict[int, List[Tuple[float, Dict[str, Any]]]] = {}
    for i in best_inlier_idx:
        p = points[i]
        t = float(p["t"])
        y_hat = a * t * t + b * t + c
        x_hat = m * t + k
        dist = math.hypot(p["x"] - x_hat, p["y"] - y_hat)
        fr = int(p["frame"])
        by_frame.setdefault(fr, []).append((dist, p))

    chosen: Dict[int, Dict[str, Any]] = {}
    for fr, opts in by_frame.items():
        opts.sort(key=lambda z: z[0])
        chosen[fr] = opts[0][1]
    return chosen, best_params


def ransac_after_anchor(
    points: List[Dict[str, Any]],
    hoop_w: float,
    *,
    iterations: int = RANSAC_ITERATIONS,
    seed: int = RANSAC_SEED,
    residual_frac: float = RESIDUAL_HOOP_W_FRAC,
    min_points: int = MIN_POINTS_AFTER,
) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    """Straight line in t for x AND for y (no direction constraint)."""
    residual = residual_frac * float(hoop_w)
    empty_params: Dict[str, Any] = {"model": "after", "ok": False}
    if len(points) < min_points:
        return {}, empty_params

    rng = random.Random(seed)
    best_count = -1
    best_params: Optional[Dict[str, Any]] = None
    best_inlier_idx: List[int] = []

    n = len(points)
    for _ in range(iterations):
        sample_i = rng.sample(range(n), 2)
        ts = np.array([points[i]["t"] for i in sample_i], dtype=float)
        ys = np.array([points[i]["y"] for i in sample_i], dtype=float)
        xs = np.array([points[i]["x"] for i in sample_i], dtype=float)
        line_y = _fit_line(ts, ys)
        line_x = _fit_line(ts, xs)
        if line_y is None or line_x is None:
            continue
        my, ky = line_y
        mx, kx = line_x
        inliers = []
        for i, p in enumerate(points):
            t = float(p["t"])
            y_hat = my * t + ky
            x_hat = mx * t + kx
            err = math.hypot(p["x"] - x_hat, p["y"] - y_hat)
            if err <= residual:
                inliers.append(i)
        if len(inliers) > best_count:
            best_count = len(inliers)
            best_inlier_idx = inliers
            best_params = {
                "model": "after",
                "ok": True,
                "m_x": mx,
                "k_x": kx,
                "m_y": my,
                "k_y": ky,
                "inlier_count": len(inliers),
                "residual": residual,
            }

    if best_params is None or best_count < min_points:
        return {}, empty_params

    mx, kx = best_params["m_x"], best_params["k_x"]
    my, ky = best_params["m_y"], best_params["k_y"]
    by_frame: Dict[int, List[Tuple[float, Dict[str, Any]]]] = {}
    for i in best_inlier_idx:
        p = points[i]
        t = float(p["t"])
        dist = math.hypot(p["x"] - (mx * t + kx), p["y"] - (my * t + ky))
        fr = int(p["frame"])
        by_frame.setdefault(fr, []).append((dist, p))

    chosen: Dict[int, Dict[str, Any]] = {}
    for fr, opts in by_frame.items():
        opts.sort(key=lambda z: z[0])
        chosen[fr] = opts[0][1]
    return chosen, best_params


def _cand_points_for_window(
    cands_by_frame: Dict[int, List[Dict[str, Any]]],
    frames: Sequence[int],
    hoop_x: float,
    hoop_y: float,
    hoop_w: float,
) -> Tuple[List[Dict[str, Any]], int]:
    """Zone-filter + top-3 cap per frame; return flat point list and over-cap frame count."""
    points: List[Dict[str, Any]] = []
    over_cap = 0
    for fr in frames:
        raw = cands_by_frame.get(int(fr)) or []
        zoned = []
        for d in raw:
            # candidates.json may already be zone-filtered; still enforce constants
            x = float(d["x"] if "x" in d else d["x_center"])
            y = float(d["y"] if "y" in d else d["y_center"])
            conf = float(d.get("confidence", d.get("conf", 0.0)))
            if conf < BALL_CONFIDENCE:
                continue
            if not in_near_hoop_zone(x, y, hoop_x, hoop_y, hoop_w):
                continue
            zoned.append({"x": x, "y": y, "confidence": conf, "frame": int(fr), "t": float(fr)})
        capped, was_over = cap_top_candidates(zoned, CANDIDATE_CAP)
        if was_over:
            over_cap += 1
        points.extend(capped)
    return points, over_cap


def apply_arc_replacements(
    track: Dict[str, Any],
    *,
    tag_frame: int,
    anchor_frame: int,
    cands_by_frame: Dict[int, List[Dict[str, Any]]],
    seed: int = RANSAC_SEED,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Replace saved ball points in the two windows with arc inliers. Never reads result/bodd change."""
    # Strip truth so callers cannot accidentally leak it into arc logic.
    work = {k: copy.deepcopy(v) for k, v in track.items() if k != "result"}
    hoop = work["hoop"]
    hoop_x, hoop_y, hoop_w = float(hoop[0]), float(hoop[1]), float(hoop[2])
    bodd_before = copy.deepcopy(work.get("bodd") or [])

    before_frames = list(range(anchor_frame + WINDOW_BEFORE_START, anchor_frame + WINDOW_BEFORE_END + 1))
    after_frames = list(range(anchor_frame + WINDOW_AFTER_START, anchor_frame + WINDOW_AFTER_END + 1))

    before_pts, over_b = _cand_points_for_window(
        cands_by_frame, before_frames, hoop_x, hoop_y, hoop_w
    )
    after_pts, over_a = _cand_points_for_window(
        cands_by_frame, after_frames, hoop_x, hoop_y, hoop_w
    )

    before_chosen, before_params = ransac_before_anchor(
        before_pts, hoop_w, seed=seed
    )
    after_chosen, after_params = ransac_after_anchor(
        after_pts, hoop_w, seed=seed
    )

    window_frames = set(before_frames) | set(after_frames)
    chosen = dict(before_chosen)
    chosen.update(after_chosen)

    saved_ball = list(work.get("ball") or [])
    by_offset = {int(pt[0]): [int(pt[0]), float(pt[1]), float(pt[2])] for pt in saved_ball}

    replaced_frames = []
    added_frames = []
    for abs_fr, p in chosen.items():
        if abs_fr not in window_frames:
            continue
        offset = int(abs_fr - tag_frame)
        new_pt = [offset, float(p["x"]), float(p["y"])]
        if offset in by_offset:
            old = by_offset[offset]
            if old[1] != new_pt[1] or old[2] != new_pt[2]:
                replaced_frames.append(abs_fr)
            by_offset[offset] = new_pt
        else:
            by_offset[offset] = new_pt
            added_frames.append(abs_fr)

    new_ball = [by_offset[k] for k in sorted(by_offset.keys())]
    work["ball"] = new_ball
    work["bodd"] = bodd_before  # never changed

    meta = {
        "before_params": before_params,
        "after_params": after_params,
        "replaced_frames": replaced_frames,
        "added_frames": added_frames,
        "frames_over_cap": over_b + over_a,
        "chosen_by_frame": {
            str(fr): {"x": float(p["x"]), "y": float(p["y"]), "confidence": float(p.get("confidence", 0))}
            for fr, p in chosen.items()
        },
    }
    return work, meta


def frame_flags(
    *,
    abs_frame: int,
    saved_xy: Optional[Tuple[float, float]],
    zone_cands: List[Dict[str, Any]],
    inlier_xy: Optional[Tuple[float, float]],
) -> Optional[str]:
    """Mutually exclusive diagnostic flags (spec §11)."""
    if not zone_cands:
        return "ball_not_detected"
    if inlier_xy is not None and saved_xy is not None:
        if abs(saved_xy[0] - inlier_xy[0]) > 1e-6 or abs(saved_xy[1] - inlier_xy[1]) > 1e-6:
            return "tracker_jumped_to_false_candidate"
    if inlier_xy is not None and saved_xy is None:
        return "tracker_jumped_to_false_candidate"
    return None


# ---------------------------------------------------------------------------
# Scoring / report ONLY may read track["result"]
# ---------------------------------------------------------------------------


def truth_is_make(track_or_row: Dict[str, Any]) -> bool:
    """Scoring only. Accepts track result or build-results gt_make."""
    if "gt_make" in track_or_row:
        return bool(track_or_row["gt_make"])
    raw = track_or_row.get("result")
    if raw is None:
        raise KeyError("scoring needs track['result'] or row['gt_make']")
    s = str(raw).strip().lower()
    return s in {"make", "made", "1", "true"}


def prove_noop_identity(
    shots: List[Dict[str, Any]],
    tracks_by_film: Dict[str, Dict[int, Dict[str, Any]]],
) -> None:
    """Spec 9d: Stage A copy (all switches off) == run_saved_v6_rule on all build shots."""
    from ai_bridge import run_saved_v6_rule  # read-only

    by_path: Dict[str, List[Dict[str, Any]]] = {}
    for row in shots:
        by_path.setdefault(row["tracks_path_resolved"], []).append(row)

    orig_by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for path_str, group in by_path.items():
        timestamps = [int(r["t"]) for r in group]
        result = run_saved_v6_rule(timestamps, path_str)
        film = group[0]["film"]
        for r in result["results"]:
            orig_by_key[(film, int(r["tag_ts"]))] = r

    diffs = []
    for row in shots:
        film = row["film"]
        t = int(row["t"])
        track = tracks_by_film[film][t]
        track_no_truth = {k: v for k, v in track.items() if k != "result"}
        pred, details = decide_shot(
            track_no_truth,
            switch_a7=False,
            switch_a8=False,
            switch_a4=False,
            switch_c4=False,
        )
        copy_reason = reason_of(details)
        orig = orig_by_key.get((film, t))
        if orig is None:
            diffs.append(f"t={t} film={film}: missing from run_saved_v6_rule")
            continue
        orig_pred = bool(orig["pred"])
        orig_reason = reason_of(orig.get("details") or {})
        if bool(pred) != orig_pred or copy_reason != orig_reason:
            diffs.append(
                f"t={t} film={film}: rule={orig_pred}/{orig_reason} copy={pred}/{copy_reason}"
            )

    if diffs:
        msg = (
            f"NO-OP PROOF FAILED: Stage A copy (all switches off) differs from "
            f"run_saved_v6_rule on {len(diffs)} of {len(shots)} shots. Stopping."
        )
        print(msg)
        for line in diffs[:20]:
            print(f"  {line}")
        if len(diffs) > 20:
            print(f"  ... and {len(diffs) - 20} more")
        raise SystemExit(msg)
    print(f"NO-OP PROOF: {len(shots)}/{len(shots)} identical (decide_shot all-off == run_saved_v6_rule)")


def load_build_shot_list(
    tracks_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[int, Dict[str, Any]]], Dict[str, Path]]:
    """Same 140 as Stage A: FILMS + load_shot_tags + load_tracks, Q1–Q3 in tracks."""
    shots: List[Dict[str, Any]] = []
    tracks_by_film: Dict[str, Dict[int, Dict[str, Any]]] = {}
    path_by_film: Dict[str, Path] = {}

    for film in FILMS:
        tags_path = ROOT / film["tags_rel"]
        if not tags_path.exists():
            raise FileNotFoundError(f"Missing tags: {tags_path}")
        tracks_path = resolve_film_tracks(film, tracks_dir)
        tags = load_shot_tags(tags_path)
        tracks = load_tracks(tracks_path)
        tracks_by_film[film["name"]] = tracks
        path_by_film[film["name"]] = tracks_path
        for shot in tags:
            if shot["quarter"] not in BUILD_QUARTERS:
                continue
            t = int(shot["t"])
            if t not in tracks:
                continue
            shots.append(
                {
                    "film": film["name"],
                    "t": t,
                    "quarter": shot["quarter"],
                    "label": shot.get("label"),
                    "player": shot.get("player"),
                    "start": shot.get("start"),
                    "video_rel": film["video_rel"],
                    "tracks_path_resolved": str(tracks_path),
                    # truth for scoring only — kept on the shot row, not passed to arc
                    "gt_make": (shot["result"] == "Make"),
                }
            )

    # unique (film, t)
    seen = set()
    unique = []
    for s in shots:
        key = (s["film"], s["t"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)

    if len(unique) != EXPECTED_BUILD:
        raise SystemExit(
            f"SHOT COUNT STOP: expected exactly {EXPECTED_BUILD} build shots, got {len(unique)} "
            f"(tags∩tracks Q1–Q3). Stopping for Scott."
        )
    return unique, tracks_by_film, path_by_film


def run_arc_and_rule_on_shot(
    track: Dict[str, Any],
    *,
    t_ms: int,
    fps: float,
    cands_by_frame: Dict[int, List[Dict[str, Any]]],
    seed: int = RANSAC_SEED,
) -> Dict[str, Any]:
    """Arc + rule for one shot. Track may contain result; arc path never sees it."""
    track_no_truth = {k: copy.deepcopy(v) for k, v in track.items() if k != "result"}
    anchor_frame, _used_nc, _off, anchor_reason = peak_from_track(track_no_truth, t_ms, fps)
    tag_frame = int(round(t_ms / 1000.0 * fps))

    old_pred, old_details = decide_shot(
        track_no_truth,
        switch_a7=False,
        switch_a8=False,
        switch_a4=False,
        switch_c4=False,
    )
    old_reason = reason_of(old_details)

    modified, arc_meta = apply_arc_replacements(
        track_no_truth,
        tag_frame=tag_frame,
        anchor_frame=anchor_frame,
        cands_by_frame=cands_by_frame,
        seed=seed,
    )
    # bodd identity
    assert modified.get("bodd") == track_no_truth.get("bodd"), "bodd must never change"

    new_pred, new_details = decide_shot(
        modified,
        switch_a7=False,
        switch_a8=False,
        switch_a4=False,
        switch_c4=False,
    )
    new_reason = reason_of(new_details)

    return {
        "tag_frame": tag_frame,
        "anchor_frame": anchor_frame,
        "anchor_reason": anchor_reason,
        "old_pred": bool(old_pred),
        "old_reason": old_reason,
        "new_pred": bool(new_pred),
        "new_reason": new_reason,
        "arc_meta": arc_meta,
        "modified_ball": modified.get("ball"),
        "modified_bodd": modified.get("bodd"),
    }


def build_diagnostic_rows(
    track: Dict[str, Any],
    *,
    tag_frame: int,
    anchor_frame: int,
    anchor_reason: str,
    cands_by_frame: Dict[int, List[Dict[str, Any]]],
    chosen_by_frame: Dict[str, Dict[str, Any]],
    hoop_x: float,
    hoop_y: float,
    hoop_w: float,
    t_ms: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    saved = {int(pt[0]): (float(pt[1]), float(pt[2])) for pt in (track.get("ball") or [])}
    rows = []
    counts = {"tracker_jumped_to_false_candidate": 0, "ball_not_detected": 0}
    for abs_fr in range(
        anchor_frame - DIAGNOSTIC_HALF_WINDOW, anchor_frame + DIAGNOSTIC_HALF_WINDOW + 1
    ):
        off = abs_fr - tag_frame
        saved_xy = saved.get(off)
        raw = cands_by_frame.get(abs_fr) or []
        zone = []
        for d in raw:
            x = float(d["x"] if "x" in d else d["x_center"])
            y = float(d["y"] if "y" in d else d["y_center"])
            conf = float(d.get("confidence", d.get("conf", 0.0)))
            if conf < BALL_CONFIDENCE:
                continue
            if in_near_hoop_zone(x, y, hoop_x, hoop_y, hoop_w):
                zone.append({"x": x, "y": y, "confidence": conf})
        zone_sorted, _ = cap_top_candidates(zone, CANDIDATE_CAP)
        # diagnostic "no candidate" is after zone, before cap — use uncapped zone list
        zone_uncapped = []
        for d in raw:
            x = float(d["x"] if "x" in d else d["x_center"])
            y = float(d["y"] if "y" in d else d["y_center"])
            conf = float(d.get("confidence", d.get("conf", 0.0)))
            if conf < BALL_CONFIDENCE:
                continue
            if in_near_hoop_zone(x, y, hoop_x, hoop_y, hoop_w):
                zone_uncapped.append({"x": x, "y": y, "confidence": conf})

        ch = chosen_by_frame.get(str(abs_fr))
        inlier_xy = (float(ch["x"]), float(ch["y"])) if ch else None
        flag = frame_flags(
            abs_frame=abs_fr,
            saved_xy=saved_xy,
            zone_cands=zone_uncapped,
            inlier_xy=inlier_xy,
        )
        if flag:
            counts[flag] = counts.get(flag, 0) + 1
        rows.append(
            {
                "shot_t": t_ms,
                "frame": abs_fr,
                "anchor_type": anchor_reason,
                "saved_track_x": saved_xy[0] if saved_xy else None,
                "saved_track_y": saved_xy[1] if saved_xy else None,
                "candidates": zone_sorted,
                "arc_inlier_x": inlier_xy[0] if inlier_xy else None,
                "arc_inlier_y": inlier_xy[1] if inlier_xy else None,
                "flag": flag,
            }
        )
    return rows, counts


def summarize_results(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Scoring only — rows already carry gt_make from truth."""
    makes_right = 0
    missed_makes_recovered = []
    misses_called_makes = 0
    lost_makes = []
    verdict_changes = []

    for r in rows:
        gt = bool(r["gt_make"])
        old_p, new_p = bool(r["old_pred"]), bool(r["new_pred"])
        if gt and new_p:
            makes_right += 1
        if gt and (not old_p) and new_p:
            missed_makes_recovered.append(r["t"])
        if (not gt) and new_p:
            misses_called_makes += 1
        if gt and old_p and (not new_p):
            lost_makes.append(
                {
                    "t": r["t"],
                    "film": r["film"],
                    "old_reason": r["old_reason"],
                    "new_reason": r["new_reason"],
                }
            )
        if old_p != new_p or r["old_reason"] != r["new_reason"]:
            verdict_changes.append(
                {
                    "t": r["t"],
                    "film": r["film"],
                    "old_pred": old_p,
                    "old_reason": r["old_reason"],
                    "new_pred": new_p,
                    "new_reason": r["new_reason"],
                }
            )

    return {
        "makes_right": makes_right,
        "missed_makes_recovered": sorted(missed_makes_recovered),
        "misses_called_makes": misses_called_makes,
        "lost_makes": lost_makes,
        "verdict_changes": verdict_changes,
        "hard_gate_ok": misses_called_makes == 0,
        "baseline_makes_right_target": BASELINE_MAKES_RIGHT,
    }


def write_report_md(path: Path, summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    lines = [
        "# D1 — keep ball detections / arc choose",
        "",
        "Spec: `.team/specs/19_d1_job_spec.md` v3. Hard gate: 0 misses called makes.",
        "",
        "## Summary",
        "",
        f"- makes_right: {summary['makes_right']} (baseline target {BASELINE_MAKES_RIGHT})",
        f"- missed_makes_recovered: {summary['missed_makes_recovered']}",
        f"- misses_called_makes: {summary['misses_called_makes']}",
        f"- hard_gate_ok: {summary['hard_gate_ok']}",
        f"- lost_makes: {summary['lost_makes']}",
        "",
        "## Verdict changes",
        "",
    ]
    if not summary["verdict_changes"]:
        lines.append("(none)")
    else:
        lines.append("| t | film | old | new |")
        lines.append("| --- | --- | --- | --- |")
        for ch in summary["verdict_changes"]:
            old = f"{'make' if ch['old_pred'] else 'miss'}/{ch['old_reason']}"
            new = f"{'make' if ch['new_pred'] else 'miss'}/{ch['new_reason']}"
            lines.append(f"| {ch['t']} | {ch['film']} | {old} | {new} |")
    lines.append("")
    lines.append("## Diagnostic flag counts (19 missed makes)")
    lines.append("")
    lines.append("| t | film | jumped | not_detected |")
    lines.append("| --- | --- | --- | --- |")
    for r in rows:
        if not (r.get("gt_make") and not r.get("old_pred")):
            continue
        dc = r.get("diagnostic_counts") or {}
        lines.append(
            f"| {r['t']} | {r['film']} | "
            f"{dc.get('tracker_jumped_to_false_candidate', 0)} | "
            f"{dc.get('ball_not_detected', 0)} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def step_extract(
    *,
    v6_weights: Path,
    tracks_dir: Optional[Path],
    out_json: Path,
) -> int:
    """Windows / torch step: decode frames, run v6, write candidates + mapping check."""
    import cv2  # step-local
    from ultralytics import YOLO  # step-local

    weights = resolve_path(str(v6_weights))
    if not weights.exists():
        raise SystemExit(f"ERROR: v6 weights not found: {weights}")

    print(f"Loading v6 model from {weights}")
    model = YOLO(str(weights))
    print(f"Model classes: {model.names}")

    shots, tracks_by_film, path_by_film = load_build_shot_list(tracks_dir)
    mapping_hits = 0
    mapping_total = 0
    mapping_by_film: Dict[str, Dict[str, int]] = {}
    frames_over_cap = 0
    out_shots: List[Dict[str, Any]] = []

    for film in FILMS:
        film_name = film["name"]
        video_path = ROOT / film["video_rel"]
        if not video_path.exists():
            raise SystemExit(f"ERROR: missing video: {video_path}")
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise SystemExit(f"ERROR: cannot open video: {video_path}")
        fps_v = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = fps_v if fps_v > 1e-6 else FPS_FALLBACK
        mapping_by_film.setdefault(film_name, {"hits": 0, "total": 0})

        film_shots = [s for s in shots if s["film"] == film_name]
        for shot in film_shots:
            t = int(shot["t"])
            track = tracks_by_film[film_name][t]
            track_no_truth = {k: v for k, v in track.items() if k != "result"}
            hoop = track_no_truth["hoop"]
            hoop_x, hoop_y, hoop_w = float(hoop[0]), float(hoop[1]), float(hoop[2])
            anchor_frame, _u, _o, anchor_reason = peak_from_track(track_no_truth, t, fps)
            tag_frame = int(round(t / 1000.0 * fps))
            frame_list = frames_to_extract(track_no_truth, t, fps, anchor_frame)

            frames_out: Dict[str, Any] = {}
            # v6_ball reads in order: seek once to the earliest needed frame, then cap.read().
            needed = set(frame_list)
            first, last = min(frame_list), max(frame_list)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(max(0, first)))
            for abs_fr in range(max(0, first), last + 1):
                ok, frame = cap.read()
                if abs_fr not in needed:
                    if not ok:
                        break
                    continue
                if not ok or frame is None:
                    frames_out[str(abs_fr)] = {
                        "candidates": [],
                        "raw_basketball": [],
                        "decode_ok": False,
                    }
                    continue
                raw_dets = detect_on_crop(model, frame, hoop_x, hoop_y)

                raw_balls = [
                    d
                    for d in raw_dets
                    if d["class_name"] == BALL_CLASS_NAME and d["confidence"] >= BALL_CONFIDENCE
                ]
                zoned = zone_filter_candidates(raw_dets, hoop_x, hoop_y, hoop_w)
                if len(zoned) > CANDIDATE_CAP:
                    frames_over_cap += 1
                # store all after zone, before cap (spec step 1)
                frames_out[str(abs_fr)] = {
                    "candidates": [
                        {
                            "x": float(d["x_center"]),
                            "y": float(d["y_center"]),
                            "confidence": float(d["confidence"]),
                            "x1": float(d["x1"]),
                            "y1": float(d["y1"]),
                            "x2": float(d["x2"]),
                            "y2": float(d["y2"]),
                        }
                        for d in zoned
                    ],
                    "raw_basketball": [
                        {
                            "x": float(d["x_center"]),
                            "y": float(d["y_center"]),
                            "confidence": float(d["confidence"]),
                        }
                        for d in raw_balls
                    ],
                    "decode_ok": True,
                }

            # mapping check: every saved ball point vs raw (before zone)
            for pt in track_no_truth.get("ball") or []:
                off, sx, sy = int(pt[0]), float(pt[1]), float(pt[2])
                abs_fr = tag_frame + off
                mapping_total += 1
                mapping_by_film[film_name]["total"] += 1
                raw = (frames_out.get(str(abs_fr)) or {}).get("raw_basketball") or []
                hit = any(
                    math.hypot(float(r["x"]) - sx, float(r["y"]) - sy) <= MAPPING_MATCH_PX
                    for r in raw
                )
                if hit:
                    mapping_hits += 1
                    mapping_by_film[film_name]["hits"] += 1

            out_shots.append(
                {
                    "film": film_name,
                    "t": t,
                    "fps": fps,
                    "tag_frame": tag_frame,
                    "anchor_frame": anchor_frame,
                    "anchor_reason": anchor_reason,
                    "hoop": [hoop_x, hoop_y, hoop_w, float(hoop[3]) if len(hoop) > 3 else 0.0],
                    "tracks_path": str(path_by_film[film_name]),
                    "video_rel": film["video_rel"],
                    "frames": frames_out,
                }
            )

        cap.release()

    overall_rate = (mapping_hits / mapping_total) if mapping_total else 0.0
    per_film_rates = {
        name: {
            "hits": v["hits"],
            "total": v["total"],
            "rate": (v["hits"] / v["total"]) if v["total"] else 0.0,
        }
        for name, v in mapping_by_film.items()
    }
    print("MAPPING CHECK:")
    for name, v in per_film_rates.items():
        print(f"  {name}: {v['hits']}/{v['total']} = {v['rate']:.4f}")
    print(f"  overall: {mapping_hits}/{mapping_total} = {overall_rate:.4f}")
    print(f"frames with >{CANDIDATE_CAP} zone candidates before cap: {frames_over_cap}")

    payload = {
        "mapping_check": {
            "hits": mapping_hits,
            "total": mapping_total,
            "rate": overall_rate,
            "per_film": per_film_rates,
            "match_px": MAPPING_MATCH_PX,
            "min_rate": MAPPING_MIN_MATCH_RATE,
        },
        "frames_over_cap": frames_over_cap,
        "n_shots": len(out_shots),
        "shots": out_shots,
        "constants": {
            "BALL_CONFIDENCE": BALL_CONFIDENCE,
            "ZONE_HOOP_WIDTHS_H": ZONE_HOOP_WIDTHS_H,
            "ZONE_ABOVE_HOOP_WIDTHS": ZONE_ABOVE_HOOP_WIDTHS,
            "ZONE_BELOW_PX": ZONE_BELOW_PX,
            "CANDIDATE_CAP": CANDIDATE_CAP,
        },
    }
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_json}")

    if overall_rate < MAPPING_MIN_MATCH_RATE:
        msg = (
            f"MAPPING CHECK GATE FAILED: overall match rate {overall_rate:.4f} "
            f"< {MAPPING_MIN_MATCH_RATE}. Frame mapping or decoding is wrong. "
            f"Stopping for Scott — nothing else runs."
        )
        print(msg)
        raise SystemExit(msg)
    return 0


def _cands_map_from_shot(shot_payload: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    out: Dict[int, List[Dict[str, Any]]] = {}
    for fr_s, info in (shot_payload.get("frames") or {}).items():
        out[int(fr_s)] = list(info.get("candidates") or [])
    return out


def step_arc_rule_report(
    *,
    candidates_json: Path,
    tracks_dir: Optional[Path],
    out_json: Path,
    out_md: Path,
) -> int:
    cand_path = resolve_path(str(candidates_json))
    if not cand_path.exists():
        raise SystemExit(f"ERROR: candidates.json not found: {cand_path}")

    payload = json.loads(cand_path.read_text(encoding="utf-8"))
    mapping = payload.get("mapping_check") or {}
    rate = float(mapping.get("rate") or 0.0)
    if rate < MAPPING_MIN_MATCH_RATE:
        msg = (
            f"MAPPING CHECK GATE FAILED (from candidates.json): rate {rate:.4f} "
            f"< {MAPPING_MIN_MATCH_RATE}. Stopping for Scott."
        )
        print(msg)
        raise SystemExit(msg)

    shots, tracks_by_film, _paths = load_build_shot_list(tracks_dir)
    prove_noop_identity(shots, tracks_by_film)

    cand_by_key = {(s["film"], int(s["t"])): s for s in payload.get("shots") or []}
    result_rows: List[Dict[str, Any]] = []

    for shot in shots:
        film, t = shot["film"], int(shot["t"])
        track = tracks_by_film[film][t]
        # truth only here for scoring fields — arc function strips it
        gt_make = truth_is_make({"gt_make": shot["gt_make"]})
        # also allow track result as cross-check in scoring only
        if "result" in track:
            gt_make = truth_is_make(track)

        cand_shot = cand_by_key.get((film, t))
        if cand_shot is None:
            print(f"WARNING: no candidates for film={film} t={t}; treating as empty")
            cands_by_frame: Dict[int, List[Dict[str, Any]]] = {}
            fps = FPS_FALLBACK
        else:
            cands_by_frame = _cands_map_from_shot(cand_shot)
            fps = float(cand_shot.get("fps") or FPS_FALLBACK)

        outcome = run_arc_and_rule_on_shot(
            track, t_ms=t, fps=fps, cands_by_frame=cands_by_frame
        )
        hoop = track["hoop"]
        hoop_x, hoop_y, hoop_w = float(hoop[0]), float(hoop[1]), float(hoop[2])
        diag_rows, diag_counts = build_diagnostic_rows(
            {k: v for k, v in track.items() if k != "result"},
            tag_frame=outcome["tag_frame"],
            anchor_frame=outcome["anchor_frame"],
            anchor_reason=outcome["anchor_reason"],
            cands_by_frame=cands_by_frame,
            chosen_by_frame=outcome["arc_meta"].get("chosen_by_frame") or {},
            hoop_x=hoop_x,
            hoop_y=hoop_y,
            hoop_w=hoop_w,
            t_ms=t,
        )
        result_rows.append(
            {
                "film": film,
                "t": t,
                "gt_make": gt_make,
                "old_pred": outcome["old_pred"],
                "old_reason": outcome["old_reason"],
                "new_pred": outcome["new_pred"],
                "new_reason": outcome["new_reason"],
                "anchor_frame": outcome["anchor_frame"],
                "anchor_reason": outcome["anchor_reason"],
                "arc_meta": outcome["arc_meta"],
                "diagnostic_rows": diag_rows,
                "diagnostic_counts": diag_counts,
            }
        )

    summary = summarize_results(result_rows)
    print("\n=== D1 arc-rule-report ===")
    print(f"makes_right: {summary['makes_right']}")
    print(f"missed_makes_recovered: {summary['missed_makes_recovered']}")
    print(f"misses_called_makes: {summary['misses_called_makes']}")
    print(f"lost_makes: {summary['lost_makes']}")
    print(f"hard_gate (0 misses called makes): {'PASS' if summary['hard_gate_ok'] else 'FAIL'}")

    out_payload = {
        "summary": summary,
        "n_shots": len(result_rows),
        "shots": result_rows,
        "constants": {
            "ZONE_HOOP_WIDTHS_H": ZONE_HOOP_WIDTHS_H,
            "ZONE_ABOVE_HOOP_WIDTHS": ZONE_ABOVE_HOOP_WIDTHS,
            "ZONE_BELOW_PX": ZONE_BELOW_PX,
            "CANDIDATE_CAP": CANDIDATE_CAP,
            "MIN_POINTS_BEFORE": MIN_POINTS_BEFORE,
            "MIN_POINTS_AFTER": MIN_POINTS_AFTER,
            "RANSAC_ITERATIONS": RANSAC_ITERATIONS,
            "RANSAC_SEED": RANSAC_SEED,
            "RESIDUAL_HOOP_W_FRAC": RESIDUAL_HOOP_W_FRAC,
            "WINDOW_BEFORE_START": WINDOW_BEFORE_START,
            "WINDOW_BEFORE_END": WINDOW_BEFORE_END,
            "WINDOW_AFTER_START": WINDOW_AFTER_START,
            "WINDOW_AFTER_END": WINDOW_AFTER_END,
            "MAPPING_MIN_MATCH_RATE": MAPPING_MIN_MATCH_RATE,
            "BALL_CONFIDENCE": BALL_CONFIDENCE,
        },
        "applied_to_core": False,
    }
    out_json = Path(out_json)
    out_md = Path(out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    write_report_md(out_md, summary, result_rows)
    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")

    if not summary["hard_gate_ok"]:
        msg = (
            f"HARD GATE FAILED: misses_called_makes={summary['misses_called_makes']} "
            f"(must be 0). Stopping — no retry, no tuning."
        )
        print(msg)
        raise SystemExit(msg)
    if summary["lost_makes"]:
        msg = (
            f"LOST MAKES: {len(summary['lost_makes'])} baseline-right makes flipped to miss. "
            f"Stopping for Scott."
        )
        print(msg)
        raise SystemExit(msg)
    return 0


def step_overlays(
    *,
    results_json: Path,
    tracks_dir: Optional[Path],
    overlay_dir: Path,
) -> int:
    """Windows step: draw PNG overlays for the 19 missed makes."""
    import cv2  # step-local

    res_path = resolve_path(str(results_json))
    if not res_path.exists():
        raise SystemExit(f"ERROR: results json not found: {res_path}")
    data = json.loads(res_path.read_text(encoding="utf-8"))
    shots = data.get("shots") or []
    missed = [s for s in shots if s.get("gt_make") and not s.get("old_pred")]
    overlay_dir = Path(overlay_dir)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    # need candidates for boxes — look beside results
    cand_path = pick_existing(*DEFAULT_CANDIDATES)
    cand_by_key = {}
    if cand_path is not None:
        cand_payload = json.loads(cand_path.read_text(encoding="utf-8"))
        cand_by_key = {(s["film"], int(s["t"])): s for s in cand_payload.get("shots") or []}

    _shots, tracks_by_film, _ = load_build_shot_list(tracks_dir)
    written = 0
    for row in missed:
        film, t = row["film"], int(row["t"])
        film_meta = next((f for f in FILMS if f["name"] == film), None)
        if film_meta is None:
            continue
        video_path = ROOT / film_meta["video_rel"]
        if not video_path.exists():
            print(f"SKIP overlay t={t}: missing video {video_path}")
            continue
        anchor = int(row["anchor_frame"])
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, anchor)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            print(f"SKIP overlay t={t}: decode failed at {anchor}")
            continue

        track = tracks_by_film[film][t]
        hoop = track["hoop"]
        hx, hy, hw = float(hoop[0]), float(hoop[1]), float(hoop[2])
        # zone box
        x1 = int(hx - ZONE_HOOP_WIDTHS_H * hw)
        x2 = int(hx + ZONE_HOOP_WIDTHS_H * hw)
        y1 = int(hy - ZONE_ABOVE_HOOP_WIDTHS * hw)
        y2 = int(hy + ZONE_BELOW_PX)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 200, 0), 2)
        cv2.circle(frame, (int(hx), int(hy)), 4, (0, 255, 255), -1)

        cand_shot = cand_by_key.get((film, t))
        if cand_shot:
            info = (cand_shot.get("frames") or {}).get(str(anchor)) or {}
            for d in info.get("candidates") or []:
                conf = float(d.get("confidence", 0))
                color = (0, int(80 + 175 * conf), int(255 * conf))
                if "x1" in d:
                    cv2.rectangle(
                        frame,
                        (int(d["x1"]), int(d["y1"])),
                        (int(d["x2"]), int(d["y2"])),
                        color,
                        2,
                    )
                else:
                    cv2.circle(frame, (int(d["x"]), int(d["y"])), 6, color, 2)

        tag_frame = int(round(t / 1000.0 * float(cand_shot.get("fps", FPS_FALLBACK) if cand_shot else FPS_FALLBACK)))
        off = anchor - tag_frame
        for pt in track.get("ball") or []:
            if int(pt[0]) == off:
                cv2.circle(frame, (int(pt[1]), int(pt[2])), 7, (0, 0, 255), 2)
                break

        ch = (row.get("arc_meta") or {}).get("chosen_by_frame") or {}
        cin = ch.get(str(anchor))
        if cin:
            cv2.circle(frame, (int(cin["x"]), int(cin["y"])), 7, (0, 255, 0), 2)

        # fitted parabola curve (before model) if present
        bp = (row.get("arc_meta") or {}).get("before_params") or {}
        if bp.get("ok"):
            a, b, c = bp["a"], bp["b"], bp["c"]
            m, k = bp["m"], bp["k"]
            pts = []
            for fr in range(anchor + WINDOW_BEFORE_START, anchor + WINDOW_BEFORE_END + 1):
                yy = a * fr * fr + b * fr + c
                xx = m * fr + k
                pts.append((int(xx), int(yy)))
            for i in range(1, len(pts)):
                cv2.line(frame, pts[i - 1], pts[i], (255, 0, 255), 1)

        out_path = overlay_dir / f"{t}.png"
        cv2.imwrite(str(out_path), frame)
        written += 1
        print(f"Wrote {out_path}")

    print(f"overlays written: {written} of {len(missed)} missed makes")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D1 keep ball detections / RANSAC arc")
    parser.add_argument(
        "--step",
        required=True,
        choices=["extract", "arc-rule-report", "overlays"],
    )
    parser.add_argument("--v6-weights", type=Path, default=None)
    parser.add_argument("--tracks-dir", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-md", type=Path, default=None)
    parser.add_argument("--candidates-json", type=Path, default=None)
    parser.add_argument("--results-json", type=Path, default=None)
    parser.add_argument("--overlay-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    tracks_dir = Path(args.tracks_dir) if args.tracks_dir else None

    if args.step == "extract":
        if args.v6_weights is None:
            raise SystemExit("--v6-weights is required for --step extract")
        out_json = args.out_json or (default_out_dir() / "candidates.json")
        return step_extract(
            v6_weights=args.v6_weights, tracks_dir=tracks_dir, out_json=out_json
        )

    if args.step == "arc-rule-report":
        cand = args.candidates_json or pick_existing(*DEFAULT_CANDIDATES)
        if cand is None:
            raise SystemExit(
                "ERROR: candidates.json not found. Run --step extract on Windows first, "
                f"or pass --candidates-json. Looked in: {DEFAULT_CANDIDATES}"
            )
        out_dir = default_out_dir()
        out_json = args.out_json or (out_dir / "d1_results.json")
        out_md = args.out_md or (out_dir / "d1_report.md")
        return step_arc_rule_report(
            candidates_json=Path(cand),
            tracks_dir=tracks_dir,
            out_json=out_json,
            out_md=out_md,
        )

    if args.step == "overlays":
        if args.results_json is None:
            raise SystemExit("--results-json is required for --step overlays")
        overlay_dir = args.overlay_dir or (default_out_dir() / "overlays")
        return step_overlays(
            results_json=args.results_json,
            tracks_dir=tracks_dir,
            overlay_dir=overlay_dir,
        )

    raise SystemExit(f"unknown step {args.step}")


if __name__ == "__main__":
    raise SystemExit(main())
