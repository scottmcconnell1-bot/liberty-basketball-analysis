"""Rim-first shot finder. Video in, shot moments out.

Reads no tags, no scoreboard, and no database. A make is still
collect_q4_bodd.is_make (imported, not copied). E1–E9 override spec v2.

Rule functions take every number as an argument and have no defaults.
v6_pick keeps the signature from the vetted spec and reads its two pick
numbers from the constants block below.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from collect_q4_bodd import is_make  # noqa: E402
from shot_rules_measure import (  # noqa: E402
    ball_inside_player,
    combine_ball_track,
    hoop_at,
    release_estimate_frame,
)
import ft_half_circle as ft  # noqa: E402

# ---------------------------------------------------------------------------
# Numbers. Each one is quoted. Do not retune after a run (E9).
# ---------------------------------------------------------------------------
# collect_q4_bodd.py:83 collect_samples predict
BODD_CONF = 0.12
BODD_IMGSZ = 960
# collect_flight_tracks.py:349 classes kept (basketball/hoop also collect_samples)
BODD_CLASSES = ("basketball", "hoop", "player")
# collect_q4_bodd.py:121-125 v6_ball crop and predict
V6_CROP_HX_PX = 260
V6_CROP_HY_ABOVE_PX = 200
V6_CROP_HY_BELOW_PX = 240
V6_CONF = 0.28
V6_IMGSZ = 640
# collect_q4_bodd.py:133 pick radius; :137 continuity weight
V6_PICK_RADIUS_PX = 220
V6_CONTINUITY = 0.35
# collect_q4_bodd.py:49 is_make; called as is_make(series, hoop, 0.55, 180, 8)
# at collect_q4_bodd.py:220. 0.9 and 1.3 widths stay inside is_make.
MAKE_HALF = 0.55
MAKE_DROP_PX = 180
MAKE_GAP_FRAMES = 8
# spec 38 S8, Scott approved 2026-11-06
TRACK_BREAK_GAP_FRAMES = MAKE_GAP_FRAMES
# collect_q4_bodd.py:54 and :56 — is_make's own above-the-hoop test (E4)
ABOVE_X_WIDTHS = 2.2
ABOVE_HOOP_PX = 6
# spec 33 Scott-approved; court_memory.py:165 rim_r=72 / median hoop_w 98
MISS_RIM_ZONE_WIDTHS = 0.735
# court_memory.py:190 "y <= hoop_y + 40", scaled by hoop_w / 98
RIM_BAND_PX = 40
# shot_rules_measure.py:51 Adrian median hoop_w
ADRIAN_MEDIAN_HOOP_W = 98.0
# court_memory.py:165 rim_r default; release_estimate_frame scales it
RIM_R_PX = 72.0
# collect_flight_tracks.py:59; spec 33 Scott-approved window before the trigger
TRACE_BEFORE_MS = 3000
# spec 33 Scott-approved; shot_rules_measure.py:43 release_trace_factor
RELEASE_TRACE_FACTOR = 0.6
# spec 39, fixed by Claude Code 2026-11-06
REF_INSIDE = 0.5
REF_WINDOW_FRAMES = 12
REF_MIN_FRAMES = 5
MERGE_IOU = 0.5
# collect_q4_bodd.py:177 used only when the file reports no fps
FPS_FALLBACK = 25.0
# collect_q4_bodd.py:40 groups — int(x // 80), one hoop per bucket
HOOP_X_BUCKET_PX = 80
# spec 36 K8, Scott approved 2026-11-05
HOOP_W_MIN_WIDTHS = 0.5
# spec 36 K8, Scott approved 2026-11-05
HOOP_W_MAX_WIDTHS = 1.5
# spec 36 K8, Scott approved 2026-11-05
MIN_SERIES_V6_POINTS = 3
# spec 36 K8, Scott approved 2026-11-05
SHOOT_AROUND_MIN_BALLS = 3
# Scott decided 2026-11-06, spec 37
SHOOT_AROUND_MIN_FRAMES = 12
# Shoot-around look-back reuses TRACE_BEFORE_MS (3000). No new constant.
# Referee boxes stay out of BODD_CLASSES so they are never merged into players.
REFEREE_CLASS = "referee"

Point = Tuple[float, ...]
HoopTuple = Tuple[float, float, float, float]


def frame_to_ms(frame: int, fps: float) -> int:
    return int(round(1000.0 * float(frame) / float(fps)))


def ms_to_frame(t_ms: int, fps: float) -> int:
    return int(round(float(t_ms) / 1000.0 * float(fps)))


def both_passes_estimate_s(elapsed_s: float, frames_done: int, total_frames: int) -> float:
    """Scale elapsed BODD time to a full BODD pass plus a full v6 pass."""
    done = int(frames_done)
    if done <= 0:
        raise ValueError("frames_done is 0")
    return float(elapsed_s) * (2.0 * float(total_frames)) / float(done)


def refuse_existing_out_dir(out_dir: Path) -> None:
    path = Path(out_dir)
    if path.exists():
        raise SystemExit(f"Refuse: output directory already exists: {path}")


def distance_hoop_widths(dx_px: float, dy_px: float, hoop_w: float) -> float:
    width = float(hoop_w)
    if width == 0.0:
        raise ValueError("hoop_w is 0")
    return math.hypot(float(dx_px), float(dy_px)) / width


def v6_crop_bounds(
    hx: float,
    hy: float,
    frame_w: int,
    frame_h: int,
    hx_pad: float,
    hy_above: float,
    hy_below: float,
) -> Tuple[int, int, int, int]:
    """collect_q4_bodd.v6_ball crop: hx±pad, hy-above..hy+below, clamped."""
    x0 = int(max(0, float(hx) - float(hx_pad)))
    y0 = int(max(0, float(hy) - float(hy_above)))
    x1 = int(min(int(frame_w), float(hx) + float(hx_pad)))
    y1 = int(min(int(frame_h), float(hy) + float(hy_below)))
    return x0, y0, x1, y1


def v6_pick(
    boxes_in_crop_coords: Iterable[Sequence[float]],
    x0: float,
    y0: float,
    hoop: Sequence[float],
    prev: Optional[Sequence[float]],
) -> Optional[Tuple[float, float]]:
    """One frame of collect_q4_bodd.v6_ball lines 129–145.

    boxes are xyxy in the crop. Returns picture (cx, cy), or None.
    Radius and continuity come from V6_PICK_RADIUS_PX and V6_CONTINUITY.
    """
    hx = float(hoop[0])
    hy = float(hoop[1])
    radius = V6_PICK_RADIUS_PX
    continuity = V6_CONTINUITY
    picks: List[Tuple[float, float, float]] = []
    for box in boxes_in_crop_coords:
        a, b, c, d = (float(v) for v in box[:4])
        cx = float(x0) + (a + c) / 2.0
        cy = float(y0) + (b + d) / 2.0
        if abs(cx - hx) > radius or abs(cy - hy) > radius:
            continue
        dist = (cx - hx) ** 2 + (cy - hy) ** 2
        if prev is not None:
            dist += ((cx - float(prev[0])) ** 2 + (cy - float(prev[1])) ** 2) * continuity
        picks.append((dist, cx, cy))
    if not picks:
        return None
    picks.sort()
    _dist, cx, cy = picks[0]
    return (cx, cy)


def split_runs(points: Sequence[Sequence[float]], gap_frames: int) -> List[List[Any]]:
    """Split where the ball is missing for more than gap_frames (E5).

    missing = next_frame - prev_frame - 1. A hole of gap_frames stays one run.
    """
    if not points:
        return []
    ordered = sorted(points, key=lambda pt: int(pt[0]))
    runs: List[List[Any]] = [[ordered[0]]]
    limit = int(gap_frames)
    for pt in ordered[1:]:
        missing = int(pt[0]) - int(runs[-1][-1][0]) - 1
        if missing > limit:
            runs.append([pt])
        else:
            runs[-1].append(pt)
    return runs


def miss_trigger_frame(
    ball: Sequence[Sequence[float]],
    hoop: Sequence[float],
    rim_zone_widths: float,
    above_px: float,
    x_widths: float,
    y_pad_px: float,
    median_hoop_w: float,
    lookback: int,
) -> Optional[int]:
    """First v6 frame in the rim zone that came down from above (E4).

    Zone: within rim_zone_widths of the hoop centre and
    y <= hoop_y + y_pad_px * hoop_w / median_hoop_w.
    Above: an earlier point at most `lookback` v6 samples back
    (is_make's index gap) with y < hoop_y - above_px and
    |x - hx| <= x_widths * hoop_w.
    """
    hx, hy, hw, _hh = (float(v) for v in hoop[:4])
    if hw == 0.0:
        return None
    band = float(hy) + float(y_pad_px) * hw / float(median_hoop_w)
    back = int(lookback)
    for i, pt in enumerate(ball):
        x = float(pt[1])
        y = float(pt[2])
        if distance_hoop_widths(x - hx, y - hy, hw) > float(rim_zone_widths):
            continue
        if y > band:
            continue
        came_down = False
        for j in range(max(0, i - back), i):
            xj = float(ball[j][1])
            yj = float(ball[j][2])
            if yj < hy - float(above_px) and abs(xj - hx) <= float(x_widths) * hw:
                came_down = True
                break
        if came_down:
            return int(pt[0])
    return None


def make_trigger_frame(
    ball: Sequence[Sequence[float]],
    hoop: Sequence[float],
    half: float,
    drop_px: float,
    gap: int,
) -> Optional[int]:
    """Frame where is_make first becomes true on a prefix. None if it never does."""
    if not ball or not is_make(list(ball), hoop, half, drop_px, gap):
        return None
    for k in range(1, len(ball) + 1):
        if is_make(list(ball[:k]), hoop, half, drop_px, gap):
            return int(ball[k - 1][0])
    return None


def moment_for_run(
    ball: Sequence[Sequence[float]],
    hoop: Sequence[float],
    fps: float,
    half: float,
    drop_px: float,
    gap: int,
    rim_zone_widths: float,
    above_px: float,
    x_widths: float,
    y_pad_px: float,
    median_hoop_w: float,
    lookback: int,
) -> Optional[Dict[str, Any]]:
    """One moment per run (E5). kind_hint make when is_make is true, else rim.

    Moment time is the make trigger frame when is_make is true, otherwise
    the miss trigger frame. No moment when neither fires.
    """
    if not ball:
        return None
    made = bool(is_make(list(ball), hoop, half, drop_px, gap))
    miss_frame = miss_trigger_frame(
        ball,
        hoop,
        rim_zone_widths,
        above_px,
        x_widths,
        y_pad_px,
        median_hoop_w,
        lookback,
    )
    if made:
        frame = make_trigger_frame(ball, hoop, half, drop_px, gap)
        if frame is None:
            return None
        kind = "make"
    elif miss_frame is not None:
        frame = miss_frame
        kind = "rim"
    else:
        return None
    hx, hy, hw, hh = (float(v) for v in hoop[:4])
    return {
        "frame": int(frame),
        "t_ms": frame_to_ms(int(frame), fps),
        "kind_hint": kind,
        "hoop": {"x": hx, "y": hy, "w": hw, "h": hh},
    }


def median_hoop(points: Sequence[Sequence[float]]) -> HoopTuple:
    """One hoop for is_make. Each column is the median of that series' hoops."""
    cols: List[float] = []
    for idx in (3, 4, 5, 6):
        vals = sorted(float(pt[idx]) for pt in points)
        mid = len(vals) // 2
        if len(vals) % 2 == 1:
            cols.append(vals[mid])
        else:
            cols.append((vals[mid - 1] + vals[mid]) / 2.0)
    return (cols[0], cols[1], cols[2], cols[3])


def series_hoop_width(series: Dict[str, Any]) -> Optional[float]:
    """Median w of this series' hoop_samples. None when the series has none.

    Carried hoops that were written into hoop_samples count. Point columns
    are not a substitute: a series with no hoop_samples has no width.
    """
    widths = [
        float(row["w"])
        for row in (series.get("hoop_samples") or [])
        if row.get("w") is not None
    ]
    if not widths:
        return None
    return float(statistics.median(widths))


def hoop_series_ok(
    series_hoop_w: Optional[float],
    film_hoop_w: Optional[float],
    n_v6_points: int,
    w_min: float,
    w_max: float,
    min_points: int,
) -> Tuple[bool, Optional[str]]:
    """Size against the film median, then v6 traffic.

    series_hoop_w is the median w of that series' hoop_samples.
    film_hoop_w is the median w of raw BODD hoops after dedupe_hoops
    per frame (not carried hoops). Ratio is series / film.
    Not ok when the ratio is below w_min or above w_max
    ("not_a_hoop_size"), or when n_v6_points is below min_points
    ("not_a_hoop_traffic"). A missing width, or a film width of 0,
    cannot pass the size check, so the reason is "not_a_hoop_size".
    When both size and traffic fail, the size reason wins.
    Equal to w_min, w_max, or min_points is ok.
    """
    if (
        series_hoop_w is None
        or film_hoop_w is None
        or float(film_hoop_w) == 0.0
    ):
        return False, "not_a_hoop_size"
    ratio = float(series_hoop_w) / float(film_hoop_w)
    if ratio < float(w_min) or ratio > float(w_max):
        return False, "not_a_hoop_size"
    if int(n_v6_points) < int(min_points):
        return False, "not_a_hoop_traffic"
    return True, None


def index_by_frame(
    rows: Sequence[Any], frame_of: Callable[[Any], int]
) -> Tuple[List[int], Dict[int, List[Any]]]:
    """Frame -> rows, plus the sorted frame keys for bisect."""
    buckets: Dict[int, List[Any]] = {}
    for row in rows:
        buckets.setdefault(int(frame_of(row)), []).append(row)
    return sorted(buckets), buckets


def index_hoop_samples(
    hoop_samples: Sequence[Dict[str, Any]],
) -> Tuple[List[int], Dict[int, List[Dict[str, Any]]]]:
    """t_ms -> rows in original order, plus sorted times for bisect."""
    buckets: Dict[int, List[Dict[str, Any]]] = {}
    for row in hoop_samples:
        t_ms = int(row.get("t", row.get("timestamp_ms", 0)))
        buckets.setdefault(t_ms, []).append(row)
    return sorted(buckets), buckets


def _bisect_frame_window(
    frames: Sequence[int], lo_ms: int, hi_ms: int, fps: float
) -> Tuple[int, int]:
    """[start, stop) of sorted frames with lo_ms <= frame_to_ms <= hi_ms."""
    n = len(frames)
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if frame_to_ms(frames[mid], fps) < lo_ms:
            lo = mid + 1
        else:
            hi = mid
    start = lo
    lo, hi = start, n
    while lo < hi:
        mid = (lo + hi) // 2
        if frame_to_ms(frames[mid], fps) <= hi_ms:
            lo = mid + 1
        else:
            hi = mid
    return start, lo


def _rows_in_frame_window(
    frames: Sequence[int],
    buckets: Dict[int, List[Any]],
    lo_ms: int,
    hi_ms: int,
    fps: float,
) -> List[Any]:
    if not frames:
        return []
    start, stop = _bisect_frame_window(frames, lo_ms, hi_ms, fps)
    out: List[Any] = []
    for frame in frames[start:stop]:
        out.extend(buckets[frame])
    return out


def slice_hoop_window(
    times: Sequence[int],
    buckets: Dict[int, List[Dict[str, Any]]],
    lo_ms: int,
    hi_ms: int,
) -> List[Dict[str, Any]]:
    """Hoop rows with t in [lo_ms, hi_ms], plus the first row of the latest earlier t.

    That earlier row is the one hoop_at keeps when the window itself has no
    earlier sample. Rows after hi_ms stay out.
    """
    if not times:
        return []
    start = bisect.bisect_left(times, lo_ms)
    stop = bisect.bisect_right(times, hi_ms)
    out: List[Dict[str, Any]] = []
    if start > 0:
        out.append(buckets[times[start - 1]][0])
    for t_ms in times[start:stop]:
        out.extend(buckets[t_ms])
    return out


def slice_trace_window(
    ball_frames: Sequence[int],
    balls_by_frame: Dict[int, List[Any]],
    player_frames: Sequence[int],
    players_by_frame: Dict[int, List[Any]],
    hoop_times: Sequence[int],
    hoops_by_t: Dict[int, List[Dict[str, Any]]],
    v6_frames: Sequence[int],
    v6_by_frame: Dict[int, List[Any]],
    trigger_frame: int,
    fps: float,
    before_ms: int,
) -> Tuple[List[Any], List[Dict[str, Any]], List[Any], List[Any]]:
    """Balls, hoop samples, players, and v6 points for one trace window."""
    hi_ms = frame_to_ms(int(trigger_frame), fps)
    lo_ms = hi_ms - int(before_ms)
    balls = _rows_in_frame_window(ball_frames, balls_by_frame, lo_ms, hi_ms, fps)
    players = _rows_in_frame_window(
        player_frames, players_by_frame, lo_ms, hi_ms, fps
    )
    hoops = slice_hoop_window(hoop_times, hoops_by_t, lo_ms, hi_ms)
    v6_points = _rows_in_frame_window(v6_frames, v6_by_frame, lo_ms, hi_ms, fps)
    return balls, hoops, players, v6_points


def _is_referee_box(box: Dict[str, Any]) -> bool:
    """Referee boxes are never players. Live player rows have no class key."""
    for key in ("class", "name"):
        if box.get(key) == REFEREE_CLASS:
            return True
    return False


def _box_xyxy(box: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Picture box from center x,y and size w,h. That is how boxes are stored."""
    x = float(box["x"])
    y = float(box["y"])
    w = float(box["w"])
    h = float(box["h"])
    return (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)


def _xyxy_area(x1: float, y1: float, x2: float, y2: float) -> float:
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def box_iou(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """Intersection over union of two center-based boxes. No area means 0."""
    ax1, ay1, ax2, ay2 = _box_xyxy(a)
    bx1, by1, bx2, by2 = _box_xyxy(b)
    inter = _xyxy_area(max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2))
    if inter <= 0.0:
        return 0.0
    union = _xyxy_area(ax1, ay1, ax2, ay2) + _xyxy_area(bx1, by1, bx2, by2) - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def inside_fraction(player: Dict[str, Any], ref: Dict[str, Any]) -> float:
    """area(player INTERSECT ref) / area(ref). A ref with no area is 0."""
    px1, py1, px2, py2 = _box_xyxy(player)
    rx1, ry1, rx2, ry2 = _box_xyxy(ref)
    ref_area = _xyxy_area(rx1, ry1, rx2, ry2)
    if ref_area <= 0.0:
        return 0.0
    inter = _xyxy_area(max(px1, rx1), max(py1, ry1), min(px2, rx2), min(py2, ry2))
    return inter / ref_area


def _box_area(box: Dict[str, Any]) -> float:
    return max(0.0, float(box["w"])) * max(0.0, float(box["h"]))


def merge_same_body(
    players: Sequence[Dict[str, Any]], merge_iou: float
) -> List[Dict[str, Any]]:
    """On one frame, merge boxes with IoU >= merge_iou. Keep the larger box.

    Sort by x, y, w, h, then the original index, and repeatedly merge the
    first pair in that order. An area tie keeps the earlier box. The kept
    box is the original dict, not a new union.
    """
    ordered = sorted(
        enumerate(players),
        key=lambda item: (
            float(item[1]["x"]),
            float(item[1]["y"]),
            float(item[1]["w"]),
            float(item[1]["h"]),
            item[0],
        ),
    )
    boxes: List[Dict[str, Any]] = [item[1] for item in ordered]
    threshold = float(merge_iou)
    while True:
        pair: Optional[Tuple[int, int]] = None
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if box_iou(boxes[i], boxes[j]) >= threshold:
                    pair = (i, j)
                    break
            if pair is not None:
                break
        if pair is None:
            return boxes
        i, j = pair
        drop = j if _box_area(boxes[i]) >= _box_area(boxes[j]) else i
        del boxes[drop]


def _player_boxes_only(
    boxes: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """A box already classed referee is not a player, so it cannot be merged."""
    return [box for box in boxes if not _is_referee_box(box)]


def is_referee_player(
    box: Dict[str, Any],
    frame: int,
    refs_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    window: int,
    min_frames: int,
    inside: float,
) -> bool:
    """True when the tested box covers a referee on at least min_frames nearby frames.

    Frames are frame-window through frame+window. The tested box geometry stays
    fixed on every frame. A frame counts when some referee box q on that frame
    has inside_fraction(box, q) >= inside. No player box is matched.
    """
    frame = int(frame)
    span = int(window)
    need = int(min_frames)
    inside_min = float(inside)
    count = 0
    for g in range(frame - span, frame + span + 1):
        for ref in refs_by_frame.get(g) or ():
            if inside_fraction(box, ref) >= inside_min:
                count += 1
                break
    return count >= need


def _rounded_box_key(box: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """One-decimal box, the precision frames.json already stores."""
    return (
        round(float(box["x"]), 1),
        round(float(box["y"]), 1),
        round(float(box["w"]), 1),
        round(float(box["h"]), 1),
    )


def _shooter_fix_names(fix_ref: bool, fix_merge: bool) -> List[str]:
    names: List[str] = []
    if fix_ref:
        names.append("ref")
    if fix_merge:
        names.append("merge")
    return names


def _box_record(box: Dict[str, Any], frame: int) -> Dict[str, float]:
    return {
        "frame": int(frame),
        "x": float(box["x"]),
        "y": float(box["y"]),
        "w": float(box["w"]),
        "h": float(box["h"]),
    }


def _trace_fields(
    *,
    status: str,
    reason: Optional[str],
    shooter_box: Optional[Dict[str, Any]],
    floor_spot: Optional[Dict[str, float]],
    release_frame: Optional[int],
    trace_mode: str,
    hold_boxes: Optional[List[Dict[str, Any]]],
    last_checked_frame: Optional[int],
) -> Dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "shooter_box": shooter_box,
        "floor_spot": floor_spot,
        "release_frame": release_frame,
        "trace_mode": trace_mode,
        "hold_boxes": hold_boxes,
        "last_checked_frame": last_checked_frame,
    }


def _single_frame_fields(core: Dict[str, Any]) -> Dict[str, Any]:
    """Today's one-frame result plus the mode tag. No walk fields are filled."""
    out = dict(core)
    out["trace_mode"] = "single_frame"
    out["hold_boxes"] = None
    out["last_checked_frame"] = None
    return out


def _window_ball_track(
    bodd_balls: Sequence[Sequence[float]],
    v6_points: Sequence[Sequence[float]],
    trigger_frame: int,
    fps: float,
    before_ms: int,
) -> List[List[float]]:
    """v6-first ball per frame in [trigger - before_ms, trigger]. No fill."""
    hi_ms = frame_to_ms(int(trigger_frame), fps)
    lo_ms = hi_ms - int(before_ms)
    best: Dict[int, Tuple[int, float, float, float]] = {}
    for pt in bodd_balls:
        frame = int(pt[0])
        t_ms = frame_to_ms(frame, fps)
        if t_ms < lo_ms or t_ms > hi_ms:
            continue
        conf = float(pt[3]) if len(pt) > 3 else 0.0
        row = (frame, float(pt[1]), float(pt[2]), conf)
        prev = best.get(frame)
        if prev is None or conf > prev[3]:
            best[frame] = row
    bodd_track = [
        [best[f][0], best[f][1], best[f][2], best[f][3]] for f in sorted(best)
    ]
    v6_track: List[List[float]] = []
    for pt in v6_points:
        frame = int(pt[0])
        t_ms = frame_to_ms(frame, fps)
        if t_ms < lo_ms or t_ms > hi_ms:
            continue
        v6_track.append([float(frame), float(pt[1]), float(pt[2])])
    return combine_ball_track(v6_track, bodd_track)


def _holders_on_frame(
    bx: float,
    by: float,
    player_boxes: Sequence[Dict[str, Any]],
    frame: int,
    release_factor: float,
) -> List[Dict[str, Any]]:
    """BODD players on this frame whose release circle holds the ball."""
    holders: List[Dict[str, Any]] = []
    for player in player_boxes:
        if int(player.get("frame", -1)) != int(frame):
            continue
        if _is_referee_box(player):
            continue
        if ball_inside_player(bx, by, player, release_factor, mode="release"):
            holders.append(player)
    return holders


def _trace_single_frame(
    track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    player_boxes: Sequence[Dict[str, Any]],
    fps: float,
    rim_r_px: float,
    release_factor: float,
) -> Dict[str, Any]:
    """One frame: release_estimate_frame, then the nearest player on that frame."""
    release_f = release_estimate_frame(track, hoop_samples, rim_r_px, fps)
    if release_f is None:
        return _single_frame_fields(_orange("no release frame", None))
    ball_pt = None
    for pt in track:
        if int(pt[0]) == int(release_f):
            ball_pt = pt
            break
    if ball_pt is None:
        return _single_frame_fields(_orange("no ball at release frame", int(release_f)))
    bx, by = float(ball_pt[1]), float(ball_pt[2])
    on_frame = [p for p in player_boxes if int(p.get("frame", -1)) == int(release_f)]
    if not on_frame:
        return _single_frame_fields(_orange("no player at release frame", int(release_f)))
    chosen = None
    chosen_d: Optional[float] = None
    for player in on_frame:
        if not ball_inside_player(bx, by, player, release_factor, mode="release"):
            continue
        dist = math.hypot(bx - float(player["x"]), by - float(player["y"]))
        if chosen_d is None or dist < chosen_d:
            chosen = player
            chosen_d = dist
    if chosen is None:
        return _single_frame_fields(
            _orange("ball not inside a player box", int(release_f))
        )
    box = _box_record(chosen, int(release_f))
    return _single_frame_fields(
        {
            "status": "found",
            "reason": None,
            "shooter_box": box,
            "floor_spot": {"x": box["x"], "y": box["y"] + box["h"] / 2.0},
            "release_frame": int(release_f),
        }
    )


def _trace_walk_back(
    track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    player_boxes: Sequence[Dict[str, Any]],
    trigger_frame: int,
    fps: float,
    rim_r_px: float,
    release_factor: float,
    fix_ref: bool = True,
    fix_merge: bool = True,
    players_by_frame: Optional[Dict[int, Sequence[Dict[str, Any]]]] = None,
    refs_by_frame: Optional[Dict[int, Sequence[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Walk detected ball points backward from the in-flight start to a hold.

    The start is release_estimate_frame. When the ball never rises, the start
    is the latest track frame at or before the trigger. An empty track is
    orange "no release frame". A hole of more than TRACK_BREAK_GAP_FRAMES
    missing frames stops the walk (same count as split_runs).

    fix_merge merges same-body player boxes on the walked frame before the
    hold test. fix_ref then drops a box is_referee_player accepts. Both off
    is the spec 38 walk. The hold test, two-player stop, and track break
    are unchanged. release_factor stays the release circle (0.6).
    """
    if not track:
        return _trace_fields(
            status="orange",
            reason="no release frame",
            shooter_box=None,
            floor_spot=None,
            release_frame=None,
            trace_mode="walk_back",
            hold_boxes=None,
            last_checked_frame=None,
        )
    start = release_estimate_frame(track, hoop_samples, rim_r_px, fps)
    if start is None:
        start = None
        for pt in track:
            frame = int(pt[0])
            if frame <= int(trigger_frame):
                start = frame
        if start is None:
            return _trace_fields(
                status="orange",
                reason="no release frame",
                shooter_box=None,
                floor_spot=None,
                release_frame=None,
                trace_mode="walk_back",
                hold_boxes=None,
                last_checked_frame=None,
            )
    points = [pt for pt in track if int(pt[0]) <= int(start)]
    if not points:
        return _trace_fields(
            status="orange",
            reason="no release frame",
            shooter_box=None,
            floor_spot=None,
            release_frame=None,
            trace_mode="walk_back",
            hold_boxes=None,
            last_checked_frame=None,
        )
    if players_by_frame is None:
        _frames, players_by_frame = index_by_frame(
            player_boxes, lambda box: int(box.get("frame", -1))
        )
    if refs_by_frame is None:
        refs_by_frame = {}
    # Same box on the same frame is not classified twice in one walk.
    ref_cache: Dict[Tuple[Any, ...], bool] = {}
    last_checked: Optional[int] = None
    for i in range(len(points) - 1, -1, -1):
        pt = points[i]
        frame = int(pt[0])
        bx, by = float(pt[1]), float(pt[2])
        raw = _player_boxes_only(players_by_frame.get(frame) or ())
        if fix_merge:
            players = merge_same_body(raw, MERGE_IOU)
        else:
            players = list(raw)
        if fix_ref:
            kept: List[Dict[str, Any]] = []
            for player in players:
                key = (frame, _rounded_box_key(player))
                if key not in ref_cache:
                    ref_cache[key] = is_referee_player(
                        player,
                        frame,
                        refs_by_frame,
                        REF_WINDOW_FRAMES,
                        REF_MIN_FRAMES,
                        REF_INSIDE,
                    )
                if not ref_cache[key]:
                    kept.append(player)
            players = kept
        holders = _holders_on_frame(bx, by, players, frame, release_factor)
        last_checked = frame
        if len(holders) == 1:
            box = _box_record(holders[0], frame)
            return _trace_fields(
                status="found",
                reason=None,
                shooter_box=box,
                floor_spot={"x": box["x"], "y": box["y"] + box["h"] / 2.0},
                release_frame=frame,
                trace_mode="walk_back",
                hold_boxes=None,
                last_checked_frame=frame,
            )
        if len(holders) >= 2:
            return _trace_fields(
                status="orange",
                reason="two players hold",
                shooter_box=None,
                floor_spot=None,
                release_frame=None,
                trace_mode="walk_back",
                hold_boxes=[_box_record(player, frame) for player in holders],
                last_checked_frame=frame,
            )
        if i == 0:
            break
        earlier = int(points[i - 1][0])
        # Missing frames, same count as split_runs. A hole of
        # TRACK_BREAK_GAP_FRAMES continues; one more is "track broken".
        missing = frame - earlier - 1
        if missing > TRACK_BREAK_GAP_FRAMES:
            return _trace_fields(
                status="orange",
                reason="track broken",
                shooter_box=None,
                floor_spot=None,
                release_frame=None,
                trace_mode="walk_back",
                hold_boxes=None,
                last_checked_frame=last_checked,
            )
    return _trace_fields(
        status="orange",
        reason="ball not inside a player box",
        shooter_box=None,
        floor_spot=None,
        release_frame=None,
        trace_mode="walk_back",
        hold_boxes=None,
        last_checked_frame=last_checked,
    )


def trace_shooter(
    bodd_balls: Sequence[Sequence[float]],
    v6_points: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    player_boxes: Sequence[Dict[str, Any]],
    trigger_frame: int,
    fps: float,
    before_ms: int,
    rim_r_px: float,
    release_factor: float,
    walk_back: bool,
    fix_ref: bool = True,
    fix_merge: bool = True,
    players_by_frame: Optional[Dict[int, Sequence[Dict[str, Any]]]] = None,
    refs_by_frame: Optional[Dict[int, Sequence[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Shooter from the v6-first ball in the before_ms window ending at the trigger.

    combine_ball_track uses this series' v6 points in the window, else the
    best-conf BODD ball on that frame. walk_back False checks one frame
    (release_estimate_frame, then the nearest player). walk_back True walks
    detected points backward from that frame to a single hold. Floor spot is
    the bottom-centre of the shooter box in picture pixels. No shooter ->
    status orange with a reason. Otherwise status found.

    Pass the trace window (balls, players, v6) and hoop samples in that
    window plus the latest sample before it. The same time filter runs here
    so a full list still matches that window. Referee boxes are never chosen.
    The one-frame path does not apply the spec 39 fixes. The walk does when
    the flags are on. shooter_fixes lists the flags that are on.
    """
    track = _window_ball_track(
        bodd_balls, v6_points, trigger_frame, fps, before_ms
    )
    if walk_back:
        traced = _trace_walk_back(
            track,
            hoop_samples,
            player_boxes,
            trigger_frame,
            fps,
            rim_r_px,
            release_factor,
            fix_ref,
            fix_merge,
            players_by_frame,
            refs_by_frame,
        )
    else:
        traced = _trace_single_frame(
            track, hoop_samples, player_boxes, fps, rim_r_px, release_factor
        )
    traced["shooter_fixes"] = _shooter_fix_names(fix_ref, fix_merge)
    return traced


def _orange(reason: str, release_frame: Optional[int]) -> Dict[str, Any]:
    return {
        "status": "orange",
        "reason": reason,
        "shooter_box": None,
        "floor_spot": None,
        "release_frame": release_frame,
    }


def build_hoop_carry(hoop_samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Index hoop rows once. `i` is a forward cursor over sorted times."""
    first: Dict[int, Dict[str, Any]] = {}
    last: Dict[int, Dict[str, Any]] = {}
    seen: List[int] = []
    for row in hoop_samples:
        t = int(row.get("t", row.get("timestamp_ms", 0)))
        if t not in first:
            first[t] = row
            seen.append(t)
        last[t] = row
    seen.sort()
    return {"times": seen, "first": first, "last": last, "i": 0}


def hoop_from_carry(carry: Dict[str, Any], t_ms: int) -> Optional[Dict[str, Any]]:
    """Same row hoop_at would return, without scanning every sample.

    Exact time: the last row at that time. Later than a sample: the first
    row of the latest earlier time. Before the first sample: the first row
    of the first later time. The cursor only moves forward; a backward query
    restarts it.
    """
    times: List[int] = carry["times"]
    n = len(times)
    if n == 0:
        return None
    t_ms = int(t_ms)
    i = int(carry["i"])
    if i > n:
        i = n
    if i > 0 and times[i - 1] > t_ms:
        i = 0
    while i < n and times[i] < t_ms:
        i += 1
    carry["i"] = i
    if i < n and times[i] == t_ms:
        return carry["last"][times[i]]
    if i > 0:
        return carry["first"][times[i - 1]]
    return carry["first"][times[0]]


def resolve_frame_hoops(
    detected_hoops: Sequence[Dict[str, Any]],
    hoop_samples: Sequence[Dict[str, Any]],
    t_ms: int,
    carry: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """BODD hoops this frame, else the one hoop a forward carry keeps.

    The carry matches hoop_at: first row of the latest earlier time, or,
    before the first hoop of the span, the first row of the first later time.
    Pass the same carry down the span so each empty frame does not rescan.
    """
    if detected_hoops:
        return list(detected_hoops)
    if carry is None:
        carry = build_hoop_carry(hoop_samples)
    found = hoop_from_carry(carry, int(t_ms))
    if found is None:
        return []
    return [found]


def pair_hoops_to_series(
    hoop_xs: Sequence[float],
    series_xs: Sequence[float],
) -> Tuple[List[Optional[int]], set]:
    """Nearest hoop x, one series each. None means the hoop starts a new series."""
    assigned: List[Optional[int]] = [None] * len(hoop_xs)
    used_h: set = set()
    used_s: set = set()
    pairs: List[Tuple[float, int, int]] = []
    for hi, hx in enumerate(hoop_xs):
        for si, sx in enumerate(series_xs):
            pairs.append((abs(float(hx) - float(sx)), hi, si))
    pairs.sort()
    for _dist, hi, si in pairs:
        if hi in used_h or si in used_s:
            continue
        used_h.add(hi)
        used_s.add(si)
        assigned[hi] = si
    return assigned, used_s


def dedupe_hoops(hoops: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One hoop per int(x // HOOP_X_BUCKET_PX) bucket. Highest `c` wins."""
    best: Dict[int, Tuple[float, Dict[str, Any]]] = {}
    order: List[int] = []
    for hoop in hoops:
        bucket = int(hoop["x"] // HOOP_X_BUCKET_PX)
        conf = float(hoop["c"]) if "c" in hoop else 0.0
        prev = best.get(bucket)
        if prev is None:
            order.append(bucket)
            best[bucket] = (conf, hoop)
        elif conf > prev[0]:
            best[bucket] = (conf, hoop)
    return [best[bucket][1] for bucket in order]


def kept_hoop_indices(
    original: Sequence[Dict[str, Any]], kept: Sequence[Dict[str, Any]]
) -> List[int]:
    """Indices into `original` of the same hoop dicts `kept` still holds."""
    kept_ids = {id(hoop) for hoop in kept}
    return [i for i, hoop in enumerate(original) if id(hoop) in kept_ids]


def filter_frame_hoops(
    hoops: Sequence[Dict[str, Any]],
    film_hoop_w: Optional[float],
    w_min: float,
    w_max: float,
    same_hoop_widths: float,
) -> List[Dict[str, Any]]:
    """Width band, then same-hoop collapse, then dedupe_hoops.

    Band: drop a box whose w / film_hoop_w is outside [w_min, w_max].
    Equal to either end stays. Collapse: boxes whose centre distance
    hypot(dx, dy) is within same_hoop_widths * film_hoop_w (inclusive)
    become one box, the highest conf (an earlier box wins a tie).
    dedupe_hoops runs last, on what survived.

    When film_hoop_w is None the band and the collapse are skipped
    (current behaviour: dedupe_hoops only). A non-positive film width
    is skipped the same way, because the ratio and the distance are undefined.
    """
    rows = list(hoops)
    if film_hoop_w is None or float(film_hoop_w) <= 0.0:
        return dedupe_hoops(rows)
    fw = float(film_hoop_w)
    banded: List[Dict[str, Any]] = []
    for hoop in rows:
        ratio = float(hoop.get("w", 0.0)) / fw
        if ratio < float(w_min) or ratio > float(w_max):
            continue
        banded.append(hoop)
    limit = float(same_hoop_widths) * fw
    ranked = sorted(
        range(len(banded)),
        key=lambda i: (
            -(float(banded[i]["c"]) if "c" in banded[i] else 0.0),
            i,
        ),
    )
    absorbed = [False] * len(banded)
    chosen: List[int] = []
    for i in ranked:
        hoop = banded[i]
        cx = float(hoop["x"])
        cy = float(hoop["y"])
        too_close = False
        for j in chosen:
            other = banded[j]
            dx = cx - float(other["x"])
            dy = cy - float(other["y"])
            if math.hypot(dx, dy) <= limit:
                too_close = True
                break
        if too_close:
            absorbed[i] = True
        else:
            chosen.append(i)
    collapsed = [banded[i] for i in range(len(banded)) if not absorbed[i]]
    return dedupe_hoops(collapsed)


def film_median_hoop_w(raw_frames: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Median w of raw BODD hoops after dedupe_hoops on each frame.

    Carried hoops are not in raw_frames and do not count.
    """
    widths: List[float] = []
    for fr in raw_frames:
        for hoop in dedupe_hoops(fr.get("hoops") or []):
            widths.append(float(hoop["w"]))
    if not widths:
        return None
    return float(statistics.median(widths))


def series_payload(
    series_list: Sequence[Dict[str, Any]],
    film_hoop_w: Optional[float],
    w_min: float,
    w_max: float,
    min_points: int,
) -> List[Dict[str, Any]]:
    """One frames.json series row per hoop series, in series order."""
    rows: List[Dict[str, Any]] = []
    for si, series in enumerate(series_list):
        width = series_hoop_width(series)
        n_points = len(series.get("points") or [])
        ok, reason = hoop_series_ok(
            width, film_hoop_w, n_points, w_min, w_max, min_points
        )
        rows.append(
            {
                "series": si,
                "ref_x": (
                    float(series["ref_x"]) if series.get("ref_x") is not None else None
                ),
                "median_hoop_w": width,
                "n_v6_points": n_points,
                "kept": bool(ok),
                "drop_reason": reason,
                "points": [
                    [int(pt[0]), float(pt[1]), float(pt[2])]
                    for pt in series.get("points") or []
                ],
            }
        )
    return rows


def assign_frame_hoops(
    series_list: List[Dict[str, Any]],
    hoops: Sequence[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Pair this frame's hoops to series by nearest x. Unused series lose prev.

    Duplicate BODD boxes on one hoop collapse to one box per x bucket first.
    """
    hoops = dedupe_hoops(hoops)
    assigned, used_s = pair_hoops_to_series(
        [float(h["x"]) for h in hoops],
        [float(s["ref_x"]) for s in series_list],
    )
    for si, series in enumerate(series_list):
        if si not in used_s:
            series["prev"] = None
    paired: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for hi, hoop in enumerate(hoops):
        si = assigned[hi]
        if si is None:
            series = {
                "ref_x": float(hoop["x"]),
                "prev": None,
                "points": [],
                "hoop_samples": [],
            }
            series_list.append(series)
        else:
            series = series_list[si]
            series["ref_x"] = float(hoop["x"])
        paired.append((series, hoop))
    return paired


def accumulate_series(frames: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hand-track helper: each hoop dict may carry ball=(cx, cy) or None."""
    series_list: List[Dict[str, Any]] = []
    for fr in frames:
        for series, hoop in assign_frame_hoops(series_list, fr["hoops"]):
            hx = float(hoop["x"])
            hy = float(hoop["y"])
            hw = float(hoop["w"])
            hh = float(hoop["h"])
            t_ms = int(fr["t_ms"]) if "t_ms" in fr else int(fr["frame"])
            series["hoop_samples"].append(
                {"t": t_ms, "x": hx, "y": hy, "w": hw, "h": hh}
            )
            ball = hoop.get("ball")
            if ball is None:
                series["prev"] = None
                continue
            cx, cy = float(ball[0]), float(ball[1])
            series["points"].append((int(fr["frame"]), cx, cy, hx, hy, hw, hh))
            series["prev"] = (cx, cy)
    return series_list


def _ball_in_any_box(
    bx: float,
    by: float,
    boxes: Sequence[Dict[str, Any]],
    factor: float,
) -> bool:
    for box in boxes:
        if ball_inside_player(bx, by, box, factor, mode="release"):
            return True
    return False


def _frames_touch_window(
    frames: Sequence[int], lo_ms: int, hi_ms: int, fps: float
) -> bool:
    """True when a sorted frame list has any frame with lo_ms <= t_ms <= hi_ms."""
    if not frames or int(lo_ms) > int(hi_ms):
        return False
    start, stop = _bisect_frame_window(frames, int(lo_ms), int(hi_ms), fps)
    return start < stop


def _best_conf_bodd(
    bodd_balls: Sequence[Sequence[float]],
) -> Tuple[List[List[float]], Dict[int, List[Tuple[float, float]]], Dict[int, int]]:
    """Best-conf ball per frame (first wins a tie), every ball, and counts.

    The tie rule matches trace_shooter: a later box replaces the kept one
    only when its confidence is strictly higher.
    """
    best: Dict[int, Tuple[float, float, float]] = {}
    all_balls: Dict[int, List[Tuple[float, float]]] = {}
    counts: Dict[int, int] = {}
    for pt in bodd_balls:
        frame = int(pt[0])
        x = float(pt[1])
        y = float(pt[2])
        conf = float(pt[3]) if len(pt) > 3 else 0.0
        counts[frame] = counts.get(frame, 0) + 1
        all_balls.setdefault(frame, []).append((x, y))
        prev = best.get(frame)
        if prev is None or conf > prev[0]:
            best[frame] = (conf, x, y)
    rows = [
        [frame, best[frame][1], best[frame][2], best[frame][0]]
        for frame in sorted(best)
    ]
    return rows, all_balls, counts


def _moment_hoop_xy(moment: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    hoop = moment.get("hoop")
    if not isinstance(hoop, dict) or "x" not in hoop or "y" not in hoop:
        return None
    return float(hoop["x"]), float(hoop["y"])


def assign_shot_calls(
    moments: List[Dict[str, Any]],
    series_ok: Sequence[bool],
    bodd_balls: Sequence[Sequence[float]],
    referee_boxes: Sequence[Dict[str, Any]],
    player_boxes: Sequence[Dict[str, Any]],
    v6_by_series: Sequence[Sequence[Sequence[float]]],
    fps: float,
    release_factor: float,
    before_ms: int,
    shoot_around_min_balls: int,
    film_hoop_w: Optional[float],
    same_hoop_widths: float,
    gap: int,
    shoot_around_min_frames: int,
) -> List[Dict[str, Any]]:
    """Set shot_call on moments that already exist. Does not read tags.

    First rule that fires sets shot_call. flags lists every rule that
    fired, in this order, including rules that lost to an earlier one:
      1 not_a_hoop -> not_a_shot
      2 same_shot_merged -> not_a_shot (plus merged_into_frame)
      3 possible_shoot_around -> orange
      4 otherwise shot, shot_reason None
    referee_boxes is accepted and not read. Referee boxes stay in
    frames.json and do not change shot_call.
    D blocks: no rule. A block looks like a miss, and this finder does not
    read tags, so a blocked attempt stays shot_call shot. The measure scores
    that shot wrong when the truth label is a block.

    Ball per frame for the same-series merge is combine_ball_track of
    this series' v6 points and the best-conf BODD ball per frame.
    Same-series same_shot_merged looks for a player box on a frame strictly
    between the two trigger frames (release factor, mode release). The first
    moment of a series is never merged that way, and merged_into_frame stays
    the immediate earlier trigger frame.
    Cross-series same_shot_merged: moments in trigger-frame order. A later
    moment on a different series merges when hypot of the moment-hoop
    centres is within same_hoop_widths * film_hoop_w (inclusive) and
    earlier.run_last_frame + gap >= later.run_first_frame. merged_into_frame
    is the earliest trigger frame after following merges (a moment already
    merged points at what it was merged into). When film_hoop_w is None
    the cross-series test is skipped. When both same-series and cross-series
    merge the same moment, merged_into_frame is the earlier of the two frames.
    possible_shoot_around fires when the number of frames in
    [trigger_ms - before_ms, trigger_ms] that hold at least
    shoot_around_min_balls BODD basketballs is >= shoot_around_min_frames.
    The count is a total, not a run of consecutive frames. before_ms is
    TRACE_BEFORE_MS at the call. The hot-frame list is sorted and the
    window is taken with bisect.

    Frame lists are indexed once and queried with bisect so a span of
    ~83,000 frames is not scanned once per moment.
    """
    factor = float(release_factor)
    best_rows, _, counts = _best_conf_bodd(bodd_balls)
    _player_frames, players_by = index_by_frame(
        player_boxes, lambda box: int(box.get("frame", -1))
    )

    n_series = len(v6_by_series)
    for moment in moments:
        n_series = max(n_series, int(moment["series"]) + 1)
    series_xy: List[Dict[int, Tuple[float, float]]] = []
    series_ball_frames: List[List[int]] = []
    for si in range(n_series):
        points = list(v6_by_series[si]) if si < len(v6_by_series) else []
        v6_rows = [
            [float(pt[0]), float(pt[1]), float(pt[2])] for pt in points
        ]
        combined = combine_ball_track(v6_rows, best_rows)
        xy: Dict[int, Tuple[float, float]] = {}
        ball_frames: List[int] = []
        for pt in combined:
            frame = int(pt[0])
            xy[frame] = (float(pt[1]), float(pt[2]))
            ball_frames.append(frame)
        series_xy.append(xy)
        series_ball_frames.append(ball_frames)

    hot_frames = sorted(
        frame
        for frame, n in counts.items()
        if n >= int(shoot_around_min_balls)
    )
    hot_ms = [frame_to_ms(frame, fps) for frame in hot_frames]

    def series_is_ok(si: int) -> bool:
        if si < 0 or si >= len(series_ok):
            return False
        return bool(series_ok[si])

    def possession_between(si: int, frame_a: int, frame_b: int) -> bool:
        """Ball inside a player on some frame strictly between the triggers."""
        if frame_b <= frame_a + 1 or si < 0 or si >= len(series_ball_frames):
            return False
        frames = series_ball_frames[si]
        xy = series_xy[si]
        lo = bisect.bisect_right(frames, int(frame_a))
        hi = bisect.bisect_left(frames, int(frame_b))
        for frame in frames[lo:hi]:
            ball = xy.get(frame)
            if ball is None:
                continue
            boxes = players_by.get(frame) or ()
            if boxes and _ball_in_any_box(ball[0], ball[1], boxes, factor):
                return True
        return False

    by_id: Dict[int, Dict[str, Any]] = {id(moment): moment for moment in moments}
    same_into: Dict[int, int] = {}
    same_link: Dict[int, int] = {}
    groups: Dict[int, List[Dict[str, Any]]] = {}
    for moment in moments:
        groups.setdefault(int(moment["series"]), []).append(moment)
    for group in groups.values():
        ordered_group = sorted(
            group, key=lambda m: (int(m["frame"]), int(m.get("t_ms", 0)))
        )
        for earlier, later in zip(ordered_group, ordered_group[1:]):
            if possession_between(
                int(later["series"]), int(earlier["frame"]), int(later["frame"])
            ):
                continue
            same_into[id(later)] = int(earlier["frame"])
            same_link[id(later)] = id(earlier)

    cross_into: Dict[int, int] = {}
    cross_link: Dict[int, int] = {}

    def root_moment(moment: Dict[str, Any]) -> Dict[str, Any]:
        """Earliest trigger frame reachable through same-series or cross links."""
        seen: set = set()
        best = moment
        stack = [moment]
        while stack:
            current = stack.pop()
            cid = id(current)
            if cid in seen:
                continue
            seen.add(cid)
            if int(current["frame"]) < int(best["frame"]):
                best = current
            for nxt_id in (cross_link.get(cid), same_link.get(cid)):
                if nxt_id is not None and nxt_id not in seen:
                    stack.append(by_id[nxt_id])
        return best

    cross_limit: Optional[float] = None
    if film_hoop_w is not None and float(film_hoop_w) > 0.0:
        cross_limit = float(same_hoop_widths) * float(film_hoop_w)
    if cross_limit is not None:
        ordered = sorted(
            moments, key=lambda m: (int(m["frame"]), int(m.get("t_ms", 0)))
        )
        for index, moment in enumerate(ordered):
            here = _moment_hoop_xy(moment)
            if here is None or "run_first_frame" not in moment:
                continue
            run_first = int(moment["run_first_frame"])
            best_root: Optional[Dict[str, Any]] = None
            for earlier in ordered[:index]:
                if int(earlier["frame"]) >= int(moment["frame"]):
                    continue
                if int(earlier["series"]) == int(moment["series"]):
                    continue
                there = _moment_hoop_xy(earlier)
                if there is None or "run_last_frame" not in earlier:
                    continue
                dx = here[0] - there[0]
                dy = here[1] - there[1]
                if math.hypot(dx, dy) > cross_limit:
                    continue
                if int(earlier["run_last_frame"]) + int(gap) < run_first:
                    continue
                root = root_moment(earlier)
                if best_root is None or int(root["frame"]) < int(best_root["frame"]):
                    best_root = root
            if best_root is None:
                continue
            cross_into[id(moment)] = int(best_root["frame"])
            cross_link[id(moment)] = id(best_root)

    for moment in moments:
        si = int(moment["series"])
        trigger = int(moment["frame"])
        trigger_ms = frame_to_ms(trigger, fps)
        flags: List[str] = []
        if not series_is_ok(si):
            flags.append("not_a_hoop")
        merged_frame: Optional[int] = None
        if id(moment) in same_into:
            merged_frame = int(same_into[id(moment)])
        if id(moment) in cross_into:
            cross_frame = int(cross_into[id(moment)])
            merged_frame = (
                cross_frame
                if merged_frame is None
                else min(merged_frame, cross_frame)
            )
        if merged_frame is not None:
            flags.append("same_shot_merged")
            moment["merged_into_frame"] = int(merged_frame)
        lo_ms = trigger_ms - int(before_ms)
        start = bisect.bisect_left(hot_ms, lo_ms)
        stop = bisect.bisect_right(hot_ms, trigger_ms)
        if stop - start >= int(shoot_around_min_frames):
            flags.append("possible_shoot_around")
        moment["flags"] = flags
        if not flags:
            moment["shot_call"] = "shot"
            moment["shot_reason"] = None
        else:
            first = flags[0]
            if first == "possible_shoot_around":
                moment["shot_call"] = "orange"
            else:
                moment["shot_call"] = "not_a_shot"
            moment["shot_reason"] = first
        status = moment.get("status")
        if status in ("found", "orange"):
            moment["shooter"] = status
            moment["shooter_reason"] = moment.get("reason")
    return moments


def emit_moments(
    series_list: Sequence[Dict[str, Any]],
    bodd_balls: Sequence[Sequence[float]],
    player_boxes: Sequence[Dict[str, Any]],
    fps: float,
    half: float,
    drop_px: float,
    gap: int,
    rim_zone_widths: float,
    above_px: float,
    x_widths: float,
    y_pad_px: float,
    median_hoop_w: float,
    lookback: int,
    before_ms: int,
    rim_r_px: float,
    release_factor: float,
    film_hoop_w: Optional[float],
    hoop_w_min: float,
    hoop_w_max: float,
    min_v6_points: int,
    shoot_around_min_balls: int,
    same_hoop_widths: float,
    shoot_around_min_frames: int,
    referee_boxes: Sequence[Dict[str, Any]],
    walk_back: bool,
    fix_ref: bool = True,
    fix_merge: bool = True,
) -> List[Dict[str, Any]]:
    ball_frames, balls_by = index_by_frame(bodd_balls, lambda pt: int(pt[0]))
    player_frames, players_by = index_by_frame(
        player_boxes, lambda box: int(box.get("frame", -1))
    )
    _ref_frames, refs_by = index_by_frame(
        referee_boxes, lambda box: int(box.get("frame", -1))
    )
    series_ok: List[bool] = []
    v6_by_series: List[List[List[float]]] = []
    for series in series_list:
        ok, _reason = hoop_series_ok(
            series_hoop_width(series),
            film_hoop_w,
            len(series.get("points") or []),
            hoop_w_min,
            hoop_w_max,
            min_v6_points,
        )
        series_ok.append(ok)
        v6_by_series.append(
            [
                [int(pt[0]), float(pt[1]), float(pt[2])]
                for pt in series.get("points") or []
            ]
        )
    moments: List[Dict[str, Any]] = []
    for si, series in enumerate(series_list):
        hoop_times, hoops_by = index_hoop_samples(series.get("hoop_samples") or [])
        v6_rows = [
            (int(pt[0]), float(pt[1]), float(pt[2])) for pt in series["points"]
        ]
        v6_frames, v6_by = index_by_frame(v6_rows, lambda pt: int(pt[0]))
        for run in split_runs(series["points"], gap):
            hoop = median_hoop(run)
            ball = [(int(pt[0]), float(pt[1]), float(pt[2])) for pt in run]
            moment = moment_for_run(
                ball,
                hoop,
                fps,
                half,
                drop_px,
                gap,
                rim_zone_widths,
                above_px,
                x_widths,
                y_pad_px,
                median_hoop_w,
                lookback,
            )
            if moment is None:
                continue
            moment["series"] = si
            moment["run_first_frame"] = int(run[0][0])
            moment["run_last_frame"] = int(run[-1][0])
            if not series_ok[si]:
                # Not a hoop: keep the moment for audit, and do not trace.
                moment.update(_orange("not_a_hoop", None))
            else:
                win_balls, win_hoops, win_players, win_v6 = slice_trace_window(
                    ball_frames,
                    balls_by,
                    player_frames,
                    players_by,
                    hoop_times,
                    hoops_by,
                    v6_frames,
                    v6_by,
                    int(moment["frame"]),
                    fps,
                    before_ms,
                )
                moment.update(
                    trace_shooter(
                        win_balls,
                        win_v6,
                        win_hoops,
                        win_players,
                        int(moment["frame"]),
                        fps,
                        before_ms,
                        rim_r_px,
                        release_factor,
                        walk_back,
                        fix_ref,
                        fix_merge,
                        players_by,
                        refs_by,
                    )
                )
            moment["shooter_fixes"] = _shooter_fix_names(fix_ref, fix_merge)
            moments.append(moment)
    assign_shot_calls(
        moments,
        series_ok,
        bodd_balls,
        referee_boxes,
        player_boxes,
        v6_by_series,
        fps,
        release_factor,
        before_ms,
        shoot_around_min_balls,
        film_hoop_w,
        same_hoop_widths,
        gap,
        shoot_around_min_frames,
    )
    moments.sort(key=lambda m: (int(m["t_ms"]), int(m["series"]), int(m["frame"])))
    return moments


def _box_item(box: Any, names: Any) -> Optional[Tuple[str, Dict[str, float]]]:
    name = names[int(box.cls[0])]
    if name not in BODD_CLASSES and name != REFEREE_CLASS:
        return None
    x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
    item = {
        "x": round((x1 + x2) / 2.0, 1),
        "y": round((y1 + y2) / 2.0, 1),
        "w": round(x2 - x1, 1),
        "h": round(y2 - y1, 1),
        "c": round(float(box.conf[0]), 3),
    }
    return name, item


def _compact_frame(
    frame_i: int,
    balls: Sequence[Dict[str, float]],
    hoops: Sequence[Dict[str, float]],
    players: Sequence[Dict[str, float]],
    referees: Sequence[Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    """One saved frame. Referees are key "r" and are not mixed into "p".

    A frame that has only referees is still saved. "r" is always present.
    """
    if not balls and not hoops and not players and not referees:
        return None
    return {
        "f": int(frame_i),
        "b": [[b["x"], b["y"], b["w"], b["h"], b["c"]] for b in balls],
        "h": [[h["x"], h["y"], h["w"], h["h"], h["c"]] for h in hoops],
        "p": [[p["x"], p["y"], p["w"], p["h"]] for p in players],
        "r": [[r["x"], r["y"], r["w"], r["h"], r["c"]] for r in referees],
    }


def _hoop_samples_from_raw(
    raw: Sequence[Dict[str, Any]], fps: float
) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for fr in raw:
        t_ms = frame_to_ms(int(fr["frame"]), fps)
        for hoop in fr["hoops"]:
            samples.append(
                {
                    "t": t_ms,
                    "x": float(hoop["x"]),
                    "y": float(hoop["y"]),
                    "w": float(hoop["w"]),
                    "h": float(hoop["h"]),
                }
            )
    return samples


def detect_span(
    video_path: Path,
    start_ms: int,
    end_ms: int,
    bodd_path: Path,
    v6_path: Path,
    *,
    bodd_conf: float,
    bodd_imgsz: int,
    v6_conf: float,
    v6_imgsz: int,
    hx_pad: float,
    hy_above: float,
    hy_below: float,
    half: float,
    drop_px: float,
    gap: int,
    rim_zone_widths: float,
    above_px: float,
    x_widths: float,
    y_pad_px: float,
    median_hoop_w: float,
    lookback: int,
    before_ms: int,
    rim_r_px: float,
    release_factor: float,
    fps_fallback: float,
    hoop_w_min: float,
    hoop_w_max: float,
    min_series_v6_points: int,
    shoot_around_min_balls: int,
    shoot_around_min_frames: int,
    fix_ref: bool = True,
    fix_merge: bool = True,
    gym: Optional[str] = None,
    ft_off: bool = False,
) -> Dict[str, Any]:
    """BODD on every frame, then one v6 crop per hoop. Writes nothing.

    When gym is set and ft_off is false, still moments use the same free-throw
    step as retrace. The capture is opened again only for those frames.
    """
    import cv2
    from ultralytics import YOLO

    video_path = Path(video_path)
    bodd_path = Path(bodd_path)
    v6_path = Path(v6_path)
    if not bodd_path.exists():
        raise SystemExit(f"BODD weights not found: {bodd_path}")
    if not v6_path.exists():
        raise SystemExit(f"v6 weights not found: {v6_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or float(fps_fallback)
        size = {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        }
        start_f = max(0, ms_to_frame(int(start_ms), fps))
        end_f = ms_to_frame(int(end_ms), fps)
        if end_f < start_f:
            raise SystemExit(f"end-ms {end_ms} is before start-ms {start_ms}")
        total = end_f - start_f + 1
        print(
            f"span {start_ms}-{end_ms} ms frames {start_f}-{end_f} ({total}) fps {fps} size {size['width']}x{size['height']}",
            flush=True,
        )

        bodd_model = YOLO(str(bodd_path))
        v6_model = YOLO(str(v6_path))
        print("bodd classes", bodd_model.names, flush=True)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        raw: List[Dict[str, Any]] = []
        compact: List[Dict[str, Any]] = []
        bodd_t0 = time.time()
        for offset in range(total):
            ok, frame = cap.read()
            if not ok:
                print(f"bodd stopped early at {offset}/{total}", flush=True)
                break
            frame_i = start_f + offset
            if offset == 0:
                frame_h, frame_w = frame.shape[:2]
                size = {"width": int(frame_w), "height": int(frame_h)}
            pred = bodd_model.predict(
                frame, conf=float(bodd_conf), imgsz=int(bodd_imgsz), verbose=False
            )[0]
            balls: List[Dict[str, float]] = []
            hoops: List[Dict[str, float]] = []
            players: List[Dict[str, float]] = []
            referees: List[Dict[str, float]] = []
            if pred.boxes is not None:
                for box in pred.boxes:
                    parsed = _box_item(box, bodd_model.names)
                    if parsed is None:
                        continue
                    name, item = parsed
                    if name == "basketball":
                        balls.append(item)
                    elif name == "hoop":
                        hoops.append(item)
                    elif name == "player":
                        players.append(item)
                    elif name == REFEREE_CLASS:
                        # Own list. Never merged into players.
                        referees.append(item)
            raw.append(
                {
                    "frame": frame_i,
                    "balls": balls,
                    "hoops": hoops,
                    "players": players,
                    "referees": referees,
                }
            )
            packed = _compact_frame(frame_i, balls, hoops, players, referees)
            if packed is not None:
                compact.append(packed)
            done = offset + 1
            if done == 500:
                elapsed = time.time() - bodd_t0
                est = both_passes_estimate_s(elapsed, done, total)
                print(
                    f"ESTIMATE {est:.1f}s total for both passes at this bodd rate",
                    flush=True,
                )
            if offset % 50 == 0:
                print(f"bodd frame {frame_i} ({offset + 1}/{total})", flush=True)

        # film median from the raw BODD hoops, then drop boxes before any
        # series, carry, or v6 crop sees them. frames.json "h" was already
        # copied from these raw boxes inside the BODD pass.
        film_hoop_w = film_median_hoop_w(raw)
        hk_by_frame: Dict[int, List[int]] = {}
        for fr in raw:
            original = list(fr.get("hoops") or [])
            kept = filter_frame_hoops(
                original,
                film_hoop_w,
                hoop_w_min,
                hoop_w_max,
                rim_zone_widths,
            )
            hk_by_frame[int(fr["frame"])] = kept_hoop_indices(original, kept)
            fr["hoops"] = kept
        for packed in compact:
            packed["hk"] = hk_by_frame.get(int(packed["f"]), [])

        hoop_samples = _hoop_samples_from_raw(raw, fps)
        hoop_carry = build_hoop_carry(hoop_samples)
        series_list: List[Dict[str, Any]] = []
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        n_raw = len(raw)
        for offset in range(n_raw):
            ok, frame = cap.read()
            if not ok:
                print(f"v6 stopped early at {offset}/{n_raw}", flush=True)
                break
            frame_h, frame_w = frame.shape[:2]
            fr = raw[offset]
            frame_i = int(fr["frame"])
            t_ms = frame_to_ms(frame_i, fps)
            hoops = resolve_frame_hoops(fr["hoops"], hoop_samples, t_ms, hoop_carry)
            for series, hoop in assign_frame_hoops(series_list, hoops):
                hx = float(hoop["x"])
                hy = float(hoop["y"])
                hw = float(hoop["w"])
                hh = float(hoop["h"])
                series["hoop_samples"].append(
                    {"t": t_ms, "x": hx, "y": hy, "w": hw, "h": hh}
                )
                x0, y0, x1, y1 = v6_crop_bounds(
                    hx, hy, frame_w, frame_h, hx_pad, hy_above, hy_below
                )
                if x1 <= x0 or y1 <= y0:
                    series["prev"] = None
                    continue
                vpred = v6_model.predict(
                    frame[y0:y1, x0:x1],
                    conf=float(v6_conf),
                    imgsz=int(v6_imgsz),
                    verbose=False,
                )[0]
                boxes: List[Tuple[float, float, float, float]] = []
                if vpred.boxes is not None:
                    for box in vpred.boxes:
                        a, b, c, d = (float(v) for v in box.xyxy[0])
                        boxes.append((a, b, c, d))
                chosen = v6_pick(boxes, x0, y0, (hx, hy, hw, hh), series["prev"])
                if chosen is None:
                    series["prev"] = None
                    continue
                series["prev"] = chosen
                series["points"].append((frame_i, chosen[0], chosen[1], hx, hy, hw, hh))
            if offset % 50 == 0:
                print(f"v6 frame {frame_i} ({offset + 1}/{n_raw})", flush=True)

        bodd_balls: List[List[float]] = []
        player_boxes: List[Dict[str, Any]] = []
        referee_boxes: List[Dict[str, Any]] = []
        for packed in compact:
            frame_i = int(packed["f"])
            for ball in packed["b"]:
                bodd_balls.append([frame_i, ball[0], ball[1], ball[4]])
            for player in packed["p"]:
                player_boxes.append(
                    {
                        "frame": frame_i,
                        "x": player[0],
                        "y": player[1],
                        "w": player[2],
                        "h": player[3],
                    }
                )
            for ref in packed.get("r") or []:
                referee_boxes.append(
                    {
                        "frame": frame_i,
                        "x": ref[0],
                        "y": ref[1],
                        "w": ref[2],
                        "h": ref[3],
                    }
                )
        series_doc = series_payload(
            series_list,
            film_hoop_w,
            hoop_w_min,
            hoop_w_max,
            min_series_v6_points,
        )
        moments = emit_moments(
            series_list,
            bodd_balls,
            player_boxes,
            fps,
            half,
            drop_px,
            gap,
            rim_zone_widths,
            above_px,
            x_widths,
            y_pad_px,
            median_hoop_w,
            lookback,
            before_ms,
            rim_r_px,
            release_factor,
            film_hoop_w,
            hoop_w_min,
            hoop_w_max,
            min_series_v6_points,
            shoot_around_min_balls,
            rim_zone_widths,
            shoot_around_min_frames,
            referee_boxes,
            True,
            fix_ref,
            fix_merge,
        )
        if gym and not ft_off:
            _frames, players_by = index_by_frame(
                player_boxes, lambda box: int(box.get("frame", -1))
            )
            _frames, refs_by = index_by_frame(
                referee_boxes, lambda box: int(box.get("frame", -1))
            )
            annotate_free_throws(
                moments,
                players_by,
                refs_by,
                lambda moment: _ball_points_for_moment(
                    moment, series_list, bodd_balls, fps
                ),
                fps,
                video_path,
                gym,
            )
    finally:
        cap.release()

    return {
        "video": str(video_path),
        "start_ms": int(start_ms),
        "end_ms": int(end_ms),
        "frames_read": len(raw),
        "fps": fps,
        "size": size,
        "film_hoop_w": film_hoop_w,
        "moments": moments,
        "frames": {"frames": compact, "series": series_doc},
        "applied_to_core": False,
    }


def _hoop_dict_from_h(row: Sequence[float]) -> Dict[str, float]:
    item = {
        "x": float(row[0]),
        "y": float(row[1]),
        "w": float(row[2]),
        "h": float(row[3]),
    }
    if len(row) > 4:
        item["c"] = float(row[4])
    return item


def rebuild_series_from_frames(
    compact: Sequence[Dict[str, Any]],
    fps: float,
) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    """Hoop series from saved frames, in frame order. No video and no model.

    The steps are the live ones: film_median_hoop_w on raw "h", then
    filter_frame_hoops, _hoop_samples_from_raw, build_hoop_carry,
    resolve_frame_hoops, and assign_frame_hoops. ref_x is the last paired
    hoop x. Frames with no saved boxes are not in this list.
    """
    ordered = sorted(compact, key=lambda fr: int(fr["f"]))
    raw: List[Dict[str, Any]] = []
    for packed in ordered:
        raw.append(
            {
                "frame": int(packed["f"]),
                "hoops": [_hoop_dict_from_h(row) for row in (packed.get("h") or [])],
            }
        )
    film_hoop_w = film_median_hoop_w(raw)
    for fr in raw:
        fr["hoops"] = filter_frame_hoops(
            fr["hoops"],
            film_hoop_w,
            HOOP_W_MIN_WIDTHS,
            HOOP_W_MAX_WIDTHS,
            MISS_RIM_ZONE_WIDTHS,
        )
    hoop_samples = _hoop_samples_from_raw(raw, fps)
    carry = build_hoop_carry(hoop_samples)
    series_list: List[Dict[str, Any]] = []
    for fr in raw:
        frame_i = int(fr["frame"])
        t_ms = frame_to_ms(frame_i, fps)
        hoops = resolve_frame_hoops(fr["hoops"], hoop_samples, t_ms, carry)
        for series, hoop in assign_frame_hoops(series_list, hoops):
            series["hoop_samples"].append(
                {
                    "t": t_ms,
                    "x": float(hoop["x"]),
                    "y": float(hoop["y"]),
                    "w": float(hoop["w"]),
                    "h": float(hoop["h"]),
                }
            )
    return series_list, film_hoop_w


def _attach_saved_v6(
    series_list: List[Dict[str, Any]],
    saved_series: Sequence[Dict[str, Any]],
) -> None:
    """v6 points come from the saved series rows, not from a new crop."""
    for i, row in enumerate(saved_series):
        si = int(row["series"]) if "series" in row else i
        if si < 0 or si >= len(series_list):
            continue
        series_list[si]["points"] = [
            (int(pt[0]), float(pt[1]), float(pt[2]))
            for pt in (row.get("points") or [])
        ]


def _balls_and_players_from_frames(
    compact: Sequence[Dict[str, Any]],
) -> Tuple[List[List[float]], List[Dict[str, Any]]]:
    """BODD balls and players. Referees stay in key "r" and are read apart."""
    balls: List[List[float]] = []
    players: List[Dict[str, Any]] = []
    for packed in compact:
        frame_i = int(packed["f"])
        for ball in packed.get("b") or []:
            conf = float(ball[4]) if len(ball) > 4 else 0.0
            balls.append([frame_i, float(ball[0]), float(ball[1]), conf])
        for player in packed.get("p") or []:
            players.append(
                {
                    "frame": frame_i,
                    "x": float(player[0]),
                    "y": float(player[1]),
                    "w": float(player[2]),
                    "h": float(player[3]),
                }
            )
    return balls, players


def _referees_from_frames(
    compact: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """frames.json key "r" is [x, y, w, h, c] per referee box."""
    refs: List[Dict[str, Any]] = []
    for packed in compact:
        frame_i = int(packed["f"])
        for ref in packed.get("r") or []:
            if len(ref) < 4:
                continue
            item: Dict[str, Any] = {
                "frame": frame_i,
                "x": float(ref[0]),
                "y": float(ref[1]),
                "w": float(ref[2]),
                "h": float(ref[3]),
            }
            if len(ref) > 4:
                item["c"] = float(ref[4])
            refs.append(item)
    return refs


def _ref_x_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _saved_ref_by_series(
    saved_series: Sequence[Dict[str, Any]],
) -> Dict[int, Any]:
    by_series: Dict[int, Any] = {}
    for i, row in enumerate(saved_series):
        si = int(row["series"]) if "series" in row else i
        by_series[si] = row.get("ref_x")
    return by_series


def _series_rows_differ(
    series_list: Sequence[Dict[str, Any]],
    saved_series: Sequence[Dict[str, Any]],
) -> bool:
    saved_by_series = _saved_ref_by_series(saved_series)
    if len(saved_series) != len(series_list):
        return True
    if len(saved_by_series) != len(saved_series):
        return True
    if set(saved_by_series) != set(range(len(series_list))):
        return True
    for i, series in enumerate(series_list):
        if _ref_x_value(series.get("ref_x")) != _ref_x_value(saved_by_series[i]):
            return True
    return False


def _print_series_gate(
    series_list: Sequence[Dict[str, Any]],
    saved_series: Sequence[Dict[str, Any]],
) -> None:
    saved_by_series = _saved_ref_by_series(saved_series)
    print(
        f"retrace series count rebuilt={len(series_list)} saved={len(saved_series)}",
        flush=True,
    )
    shown = set(range(len(series_list))) | set(saved_by_series)
    for si in sorted(shown):
        rebuilt = series_list[si].get("ref_x") if si < len(series_list) else None
        saved = saved_by_series.get(si)
        print(
            f"retrace series {si} ref_x rebuilt={rebuilt} saved={saved}",
            flush=True,
        )


def _trace_triple(moment: Dict[str, Any]) -> Tuple[Any, Any, Any]:
    return (moment.get("status"), moment.get("reason"), moment.get("release_frame"))


def parse_ft_debug_moments(text: str) -> set:
    """Comma-separated moment t_ms values. Empty is refused."""
    found = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        found.add(int(part))
    if not found:
        raise SystemExit("--ft-debug-moments is empty")
    return found


def _read_video_frame(cap: Any, frame_i: int) -> Optional[Any]:
    import cv2

    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_i))
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    return frame


def _apply_ft_decision(moment: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Stamp free_throw on every moment. Override the trace only for FT hits.

    free_throw true: status found, shooter_box and floor_spot from that
    player's bottom-centre, shooter found, shooter_reason
    free_throw_line. The previous shooter box is kept on
    trace_shooter_box. reason is cleared because a found trace has no
    orange reason.

    Still and no FT line: status orange, reason ft_line_not_found.
    shooter and shooter_reason follow status and reason, the same way
    assign_shot_calls left them. The trace shooter box stays.

    line_not_one, not_still, too_far_from_hoop, no_lane_lines, and
    release_not_shooter leave the trace fields as they are (free_throw
    false). maybe_free_throw stores ft_maybe_shooter_box, appends the
    flag, and leaves the trace unchanged.
    """
    moment["free_throw"] = bool(result["free_throw"])
    moment["ft_reason"] = result["ft_reason"]
    if result["free_throw"]:
        old = moment.get("shooter_box")
        moment["trace_shooter_box"] = copy.deepcopy(old) if isinstance(old, dict) else old
        box = result["ft_shooter_box"]
        moment["shooter_box"] = {
            "frame": int(box["frame"]),
            "x": float(box["x"]),
            "y": float(box["y"]),
            "w": float(box["w"]),
            "h": float(box["h"]),
        }
        moment["floor_spot"] = {
            "x": float(box["x"]),
            "y": float(box["y"]) + float(box["h"]) / 2.0,
        }
        moment["status"] = "found"
        moment["reason"] = None
        moment["shooter"] = "found"
        moment["shooter_reason"] = "free_throw_line"
        return
    if result["ft_reason"] == "maybe_free_throw":
        maybe_box = result.get("ft_maybe_shooter_box")
        moment["ft_maybe_shooter_box"] = (
            copy.deepcopy(maybe_box) if isinstance(maybe_box, dict) else maybe_box
        )
        flags = moment.get("flags")
        if not isinstance(flags, list):
            flags = []
            moment["flags"] = flags
        if "maybe_free_throw" not in flags:
            flags.append("maybe_free_throw")
        return
    if result["ft_reason"] == "ft_line_not_found":
        moment["status"] = "orange"
        moment["reason"] = "ft_line_not_found"
        moment["shooter"] = "orange"
        moment["shooter_reason"] = "ft_line_not_found"
    # too_far / no_lane / release_not_shooter: free_throw false, trace unchanged.


def annotate_free_throws(
    moments: Sequence[Dict[str, Any]],
    players_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    refs_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    ball_points_for: Callable[[Dict[str, Any]], Sequence[Sequence[float]]],
    fps: float,
    video_path: Path,
    gym: str,
    *,
    debug_dir: Optional[Path] = None,
    debug_moments: Optional[set] = None,
    debug_only: bool = False,
) -> None:
    """Still moments read one frame each. The video stays closed otherwise.

    Computes ft.stillness once (V1/V5). None or > MAYBE_STILL_MAX ->
    not_still with no frame read. Otherwise one frame and decide_ft with
    stillness and release_frame. debug_only writes mask images for
    debug_moments and does not stamp moments.
    """
    import cv2

    cfg = ft.stage1b_config()
    cap = None
    try:
        for moment in moments:
            t_ms = int(moment["t_ms"]) if moment.get("t_ms") is not None else None
            if debug_only and (debug_moments is None or t_ms not in debug_moments):
                continue
            if moment.get("frame") is None:
                if not debug_only:
                    moment["free_throw"] = False
                    moment["ft_reason"] = "no_frame"
                continue
            trigger = int(moment["frame"])
            still_value = ft.stillness(players_by_frame, trigger, fps)
            if still_value is None or still_value > ft.MAYBE_STILL_MAX:
                if not debug_only:
                    moment["free_throw"] = False
                    moment["ft_reason"] = "not_still"
                continue
            want_debug = (
                debug_dir is not None
                and t_ms is not None
                and (debug_moments is None or t_ms in debug_moments)
            )
            frame_i = ft.still_frame_index(players_by_frame, trigger, fps)
            if cap is None:
                cap = cv2.VideoCapture(str(video_path))
                if not cap.isOpened():
                    raise SystemExit(f"Could not open video: {video_path}")
            frame = _read_video_frame(cap, frame_i)
            if frame is None:
                if not debug_only:
                    moment["free_throw"] = False
                    moment["ft_reason"] = "frame_unreadable"
                continue
            result = ft.decide_ft(
                still=True,
                frame=frame,
                players_by_frame=players_by_frame,
                refs_by_frame=refs_by_frame,
                ball_points=ball_points_for(moment),
                trigger=trigger,
                fps=fps,
                gym=gym,
                cfg=cfg,
                still_frame=frame_i,
                hoop=moment.get("hoop"),
                collect_debug=want_debug,
                release_frame=moment.get("release_frame"),
                stillness=still_value,
            )
            if want_debug:
                for index, view in enumerate(result.get("views") or []):
                    ft.debug_image(
                        frame,
                        view["kept_segments"],
                        view["ft_line"],
                        view["band_polygon"],
                        view["boxes"],
                        Path(debug_dir) / f"{t_ms}_c{index}.png",
                    )
            if not debug_only:
                _apply_ft_decision(moment, result)
    finally:
        if cap is not None:
            cap.release()


def _ball_points_for_moment(
    moment: Dict[str, Any],
    series_list: Sequence[Dict[str, Any]],
    bodd_balls: Sequence[Sequence[float]],
    fps: float,
) -> List[List[float]]:
    """v6-first ball in [trigger-3000 ms, trigger]. Same window the trace uses."""
    if moment.get("frame") is None:
        return []
    trigger = int(moment["frame"])
    v6_rows: List[List[float]] = []
    si = moment.get("series")
    if isinstance(si, int) and 0 <= si < len(series_list):
        v6_rows = [
            [int(pt[0]), float(pt[1]), float(pt[2])]
            for pt in (series_list[si].get("points") or [])
        ]
    return _window_ball_track(bodd_balls, v6_rows, trigger, fps, TRACE_BEFORE_MS)


def _apply_shooter_trace(moment: Dict[str, Any], traced: Dict[str, Any]) -> None:
    """Overwrite the shooter fields. Every other moment field stays."""
    moment["status"] = traced.get("status")
    moment["reason"] = traced.get("reason")
    moment["shooter_box"] = traced.get("shooter_box")
    moment["floor_spot"] = traced.get("floor_spot")
    moment["release_frame"] = traced.get("release_frame")
    moment["trace_mode"] = traced.get("trace_mode")
    moment["hold_boxes"] = traced.get("hold_boxes")
    moment["last_checked_frame"] = traced.get("last_checked_frame")
    moment["shooter"] = traced.get("status")
    moment["shooter_reason"] = traced.get("reason")
    moment["shooter_fixes"] = list(traced.get("shooter_fixes") or [])


def retrace_moments(
    moments: Sequence[Dict[str, Any]],
    compact: Sequence[Dict[str, Any]],
    saved_series: Sequence[Dict[str, Any]],
    fps: float,
    walk_back: bool,
    fix_ref: bool = True,
    fix_merge: bool = True,
    video_path: Optional[Path] = None,
    gym: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Re-run only the shooter trace. Returns moments, rebuilt series, series differ.

    A series that is not a hoop keeps the saved shooter fields, matching the
    live run which does not trace it. When video_path and gym are both set,
    a still moment may be flagged free_throw. Without them the moments match
    the spec 39 retrace.
    """
    series_list, film_hoop_w = rebuild_series_from_frames(compact, fps)
    _attach_saved_v6(series_list, saved_series)
    _print_series_gate(series_list, saved_series)
    series_differ = _series_rows_differ(series_list, saved_series)
    series_ok: List[bool] = []
    for series in series_list:
        ok, _reason = hoop_series_ok(
            series_hoop_width(series),
            film_hoop_w,
            len(series.get("points") or []),
            HOOP_W_MIN_WIDTHS,
            HOOP_W_MAX_WIDTHS,
            MIN_SERIES_V6_POINTS,
        )
        series_ok.append(ok)
    bodd_balls, player_boxes = _balls_and_players_from_frames(compact)
    ball_frames, balls_by = index_by_frame(bodd_balls, lambda pt: int(pt[0]))
    player_frames, players_by = index_by_frame(
        player_boxes, lambda box: int(box.get("frame", -1))
    )
    referee_boxes = _referees_from_frames(compact)
    _ref_frames, refs_by = index_by_frame(
        referee_boxes, lambda box: int(box.get("frame", -1))
    )
    hoop_index = [
        index_hoop_samples(series.get("hoop_samples") or []) for series in series_list
    ]
    v6_index = []
    for series in series_list:
        rows = [
            (int(pt[0]), float(pt[1]), float(pt[2]))
            for pt in (series.get("points") or [])
        ]
        v6_index.append(index_by_frame(rows, lambda pt: int(pt[0])))
    new_moments: List[Dict[str, Any]] = []
    for moment in moments:
        copied = copy.deepcopy(moment)
        copied["shooter_fixes"] = _shooter_fix_names(fix_ref, fix_merge)
        si = copied.get("series")
        if (
            isinstance(si, int)
            and 0 <= si < len(series_list)
            and series_ok[si]
            and copied.get("frame") is not None
        ):
            trigger = int(copied["frame"])
            hoop_times, hoops_by = hoop_index[si]
            v6_frames, v6_by = v6_index[si]
            win_balls, win_hoops, win_players, win_v6 = slice_trace_window(
                ball_frames,
                balls_by,
                player_frames,
                players_by,
                hoop_times,
                hoops_by,
                v6_frames,
                v6_by,
                trigger,
                fps,
                TRACE_BEFORE_MS,
            )
            traced = trace_shooter(
                win_balls,
                win_v6,
                win_hoops,
                win_players,
                trigger,
                fps,
                TRACE_BEFORE_MS,
                RIM_R_PX,
                RELEASE_TRACE_FACTOR,
                walk_back,
                fix_ref,
                fix_merge,
                players_by,
                refs_by,
            )
            _apply_shooter_trace(copied, traced)
        new_moments.append(copied)
    if video_path is not None and gym:
        annotate_free_throws(
            new_moments,
            players_by,
            refs_by,
            lambda moment: _ball_points_for_moment(
                moment, series_list, bodd_balls, fps
            ),
            fps,
            Path(video_path),
            gym,
        )
    return new_moments, series_list, series_differ


def run_retrace(
    src: Path,
    out_dir: Path,
    walk_back: bool,
    fix_ref: bool = True,
    fix_merge: bool = True,
    video_path: Optional[Path] = None,
    gym: Optional[str] = None,
) -> int:
    """Read one saved run and write a new dir. Refuse when the new dir exists.

    Reads moments.json and frames.json only. frames.json is copied. The
    shooter fields are replaced by the trace. When video_path and gym are
    set, a still moment may also gain the free-throw stamp. retrace_from is
    recorded on the new moments document.
    """
    src = Path(src)
    out_dir = Path(out_dir)
    refuse_existing_out_dir(out_dir)
    moments_path = src / "moments.json"
    frames_path = src / "frames.json"
    if not moments_path.is_file() or not frames_path.is_file():
        raise SystemExit(f"Retrace needs moments.json and frames.json in {src}")
    frames_bytes = frames_path.read_bytes()
    frames_doc = json.loads(frames_bytes.decode("utf-8"))
    if (
        not isinstance(frames_doc, dict)
        or "frames" not in frames_doc
        or "series" not in frames_doc
    ):
        raise SystemExit("frames.json has no frames and series")
    moments_doc = json.loads(moments_path.read_text(encoding="utf-8"))
    if not isinstance(moments_doc, dict) or not isinstance(moments_doc.get("moments"), list):
        raise SystemExit("moments.json has no moments list")
    if "fps" not in moments_doc:
        raise SystemExit("moments.json has no fps")
    fps = float(moments_doc["fps"])
    new_moments, _series_list, series_differ = retrace_moments(
        moments_doc["moments"],
        frames_doc["frames"],
        frames_doc["series"],
        fps,
        walk_back,
        fix_ref,
        fix_merge,
        video_path,
        gym,
    )
    diffs = sum(
        1
        for old, new in zip(moments_doc["moments"], new_moments)
        if _trace_triple(old) != _trace_triple(new)
    )
    if len(moments_doc["moments"]) != len(new_moments):
        diffs += abs(len(moments_doc["moments"]) - len(new_moments))
    if not walk_back:
        print(f"retrace walk-off moments_differ={diffs}", flush=True)
    out_doc = dict(moments_doc)
    out_doc["moments"] = new_moments
    out_doc["retrace_from"] = str(src.resolve())
    out_dir.mkdir(parents=True)
    (out_dir / "moments.json").write_text(
        json.dumps(out_doc, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "frames.json").write_bytes(frames_bytes)
    if series_differ or (not walk_back and diffs):
        return 2
    return 0


def run_ft_debug(
    src: Path,
    video_path: Path,
    gym: str,
    debug_dir: Path,
    debug_moments: set,
) -> int:
    """Write paint-mask images for the named moments. Writes no moments file."""
    src = Path(src)
    moments_path = src / "moments.json"
    frames_path = src / "frames.json"
    if not moments_path.is_file() or not frames_path.is_file():
        raise SystemExit(f"Retrace needs moments.json and frames.json in {src}")
    frames_doc = json.loads(frames_path.read_text(encoding="utf-8"))
    moments_doc = json.loads(moments_path.read_text(encoding="utf-8"))
    if not isinstance(moments_doc, dict) or not isinstance(moments_doc.get("moments"), list):
        raise SystemExit("moments.json has no moments list")
    if "fps" not in moments_doc:
        raise SystemExit("moments.json has no fps")
    fps = float(moments_doc["fps"])
    compact = frames_doc["frames"]
    series_list, _film_hoop_w = rebuild_series_from_frames(compact, fps)
    _attach_saved_v6(series_list, frames_doc.get("series") or [])
    bodd_balls, player_boxes = _balls_and_players_from_frames(compact)
    _frames, players_by = index_by_frame(
        player_boxes, lambda box: int(box.get("frame", -1))
    )
    referee_boxes = _referees_from_frames(compact)
    _frames, refs_by = index_by_frame(
        referee_boxes, lambda box: int(box.get("frame", -1))
    )
    debug_dir = Path(debug_dir)
    debug_dir.mkdir(parents=True)
    annotate_free_throws(
        moments_doc["moments"],
        players_by,
        refs_by,
        lambda moment: _ball_points_for_moment(moment, series_list, bodd_balls, fps),
        fps,
        Path(video_path),
        gym,
        debug_dir=debug_dir,
        debug_moments=debug_moments,
        debug_only=True,
    )
    written = sorted(path.name for path in debug_dir.glob("*.png"))
    print(
        f"ft debug images {len(written)} in {debug_dir}",
        flush=True,
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rim-first shot finder. Video and model paths, or a saved-run retrace."
    )
    parser.add_argument("--video", type=Path)
    parser.add_argument("--start-ms", type=int)
    parser.add_argument("--end-ms", type=int)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--bodd", type=Path)
    parser.add_argument("--v6", type=Path)
    parser.add_argument("--retrace-from", type=Path)
    parser.add_argument("--walk-off", action="store_true")
    parser.add_argument(
        "--fixes-off",
        action="store_true",
        help="Turn off the spec 39 referee and same-body fixes. The walk matches spec 38.",
    )
    parser.add_argument(
        "--gym",
        choices=("adrian", "liberty"),
        help="Gym for the free-throw paint mask. With --video, retrace runs the FT step.",
    )
    parser.add_argument(
        "--ft-off",
        action="store_true",
        help="Skip the free-throw step. Retrace matches the spec 39 trace.",
    )
    parser.add_argument("--ft-debug-dir", type=Path)
    parser.add_argument(
        "--ft-debug-moments",
        default=None,
        help="Comma-separated t_ms. Write debug images only, and only for these moments.",
    )
    return parser


def write_span_outputs(out_dir: Path, doc: Dict[str, Any]) -> Tuple[Path, Path]:
    """moments.json is metadata + moments. frames.json is the compact detections."""
    out = Path(out_dir)
    moments_doc = {key: value for key, value in doc.items() if key != "frames"}
    moments_path = out / "moments.json"
    frames_path = out / "frames.json"
    moments_path.write_text(
        json.dumps(moments_doc, indent=2) + "\n", encoding="utf-8"
    )
    frames_path.write_text(
        json.dumps(doc.get("frames", []), separators=(",", ":")),
        encoding="utf-8",
    )
    return moments_path, frames_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    fixes_on = not args.fixes_off
    if args.ft_debug_moments is not None:
        if args.retrace_from is None:
            parser.error("--ft-debug-moments is a retrace check and needs --retrace-from")
        if args.video is None or args.gym is None:
            parser.error("--ft-debug-moments requires --video and --gym")
        if args.ft_debug_dir is None:
            parser.error("--ft-debug-moments requires --ft-debug-dir")
        if args.ft_off:
            parser.error("--ft-debug-moments cannot be combined with --ft-off")
        refuse_existing_out_dir(args.ft_debug_dir)
        return run_ft_debug(
            args.retrace_from,
            args.video,
            args.gym,
            args.ft_debug_dir,
            parse_ft_debug_moments(args.ft_debug_moments),
        )
    if args.out_dir is None:
        parser.error("--out-dir is required")
    if args.retrace_from is not None:
        ft_on = (not args.ft_off) and args.video is not None and args.gym is not None
        return run_retrace(
            args.retrace_from,
            args.out_dir,
            walk_back=not args.walk_off,
            fix_ref=fixes_on,
            fix_merge=fixes_on,
            video_path=args.video if ft_on else None,
            gym=args.gym if ft_on else None,
        )
    missing = [
        flag
        for flag, value in (
            ("--video", args.video),
            ("--start-ms", args.start_ms),
            ("--end-ms", args.end_ms),
            ("--bodd", args.bodd),
            ("--v6", args.v6),
        )
        if value is None
    ]
    if missing:
        parser.error("live run requires " + " ".join(missing))
    refuse_existing_out_dir(args.out_dir)
    t0 = time.time()
    doc = detect_span(
        args.video,
        args.start_ms,
        args.end_ms,
        args.bodd,
        args.v6,
        bodd_conf=BODD_CONF,
        bodd_imgsz=BODD_IMGSZ,
        v6_conf=V6_CONF,
        v6_imgsz=V6_IMGSZ,
        hx_pad=V6_CROP_HX_PX,
        hy_above=V6_CROP_HY_ABOVE_PX,
        hy_below=V6_CROP_HY_BELOW_PX,
        half=MAKE_HALF,
        drop_px=MAKE_DROP_PX,
        gap=MAKE_GAP_FRAMES,
        rim_zone_widths=MISS_RIM_ZONE_WIDTHS,
        above_px=ABOVE_HOOP_PX,
        x_widths=ABOVE_X_WIDTHS,
        y_pad_px=RIM_BAND_PX,
        median_hoop_w=ADRIAN_MEDIAN_HOOP_W,
        lookback=MAKE_GAP_FRAMES,
        before_ms=TRACE_BEFORE_MS,
        rim_r_px=RIM_R_PX,
        release_factor=RELEASE_TRACE_FACTOR,
        fps_fallback=FPS_FALLBACK,
        hoop_w_min=HOOP_W_MIN_WIDTHS,
        hoop_w_max=HOOP_W_MAX_WIDTHS,
        min_series_v6_points=MIN_SERIES_V6_POINTS,
        shoot_around_min_balls=SHOOT_AROUND_MIN_BALLS,
        shoot_around_min_frames=SHOOT_AROUND_MIN_FRAMES,
        fix_ref=fixes_on,
        fix_merge=fixes_on,
        gym=None if args.ft_off else args.gym,
        ft_off=bool(args.ft_off),
    )
    doc["run_time_s"] = round(time.time() - t0, 3)
    out = Path(args.out_dir)
    out.mkdir(parents=True)
    dest, frames_path = write_span_outputs(out, doc)
    print(
        f"Wrote {dest} and {frames_path} moments={len(doc['moments'])} "
        f"frames_read={doc['frames_read']} "
        f"fps={doc['fps']} size={doc['size']['width']}x{doc['size']['height']} "
        f"run_time_s={doc['run_time_s']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
