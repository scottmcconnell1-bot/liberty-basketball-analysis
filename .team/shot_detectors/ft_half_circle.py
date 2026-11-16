"""Free-throw line. Video paint only. No tags, no scoreboard, no database.

Spec 41 L1-L8, then spec 42 band + lane. The half-circle ellipse of spec 40
is dropped. FT = players still AND exactly one player standing just behind
the straight painted FT line, near the hoop, with lane lines on both sides.
A make is still ball_through_rim or net_moved_after_shot.
"""
from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

STAGE1B_DIR = Path(__file__).resolve().parents[1] / "stage1b_frozen_0943"
if str(STAGE1B_DIR) not in sys.path:
    sys.path.insert(0, str(STAGE1B_DIR))

from stage1b_court_lines import build_paint_mask, load_config  # noqa: E402

# spec 40 Q1, fixed by Claude Code 2026-11-06
STILL_BEFORE_MS = 3000
# spec 40 Q1, fixed by Claude Code 2026-11-06
STILL_UNTIL_MS = 1000
# spec 40 Q1, fixed by Claude Code 2026-11-06
STILL_GAP_FRAMES = 25
# spec 40 Q1, fixed by Claude Code 2026-11-06
STILL_EVERY_FRAMES = 5
# spec 40 Q1, fixed by Claude Code 2026-11-06
STILL_MOVE_MAX = 0.15
# spec 40 Q2, fixed by Claude Code 2026-11-06
CANDIDATE_BEFORE_MS = 3000
# spec 40 Q2, fixed by Claude Code 2026-11-06
BALL_RELEASE_FACTOR = 0.6
# spec 40 Q2, fixed by Claude Code 2026-11-06
REGION_HALF = 2.0
# spec 41, fixed by Claude Code 2026-11-08
LINE_NEAR = 0.25
# spec 41, fixed by Claude Code 2026-11-08
END_PAD = 0.5
# spec 41, fixed by Claude Code 2026-11-08
ANGLE_MIN = 60.0
# spec 41, fixed by Claude Code 2026-11-08
DARK_MIN = 10.0
# spec 41, fixed by Claude Code 2026-11-08
DARK_OFFSET_AT_1280 = 8.0
# spec 41, fixed by Claude Code 2026-11-08
DARK_SAMPLES = 20
# spec 41, fixed by Claude Code 2026-11-08
GROUP_DEG = 5.0
# spec 42, fixed by Claude Code 2026-11-08
BAND_FRONT = 0.0
# spec 42, fixed by Claude Code 2026-11-08
BAND_BACK = 0.35
# spec 42, fixed by Claude Code 2026-11-08
HOOP_DIST_MAX = 3.8
# spec 42, fixed by Claude Code 2026-11-08
LANE_ANGLE_MIN = 30.0
# spec 42, fixed by Claude Code 2026-11-08
LANE_HOOP_SIDE = 0.15
# spec 42, fixed by Claude Code 2026-11-08
LANE_GAP = 1.0
# spec 42, fixed by Claude Code 2026-11-08
LANE_REACH = 2.5
# spec 42, fixed by Claude Code 2026-11-08
LANE_MIN_OFF = 0.2
# spec 43, fixed by Claude Code 2026-11-08
RELEASE_DX_MAX = 0.8
# spec 43, fixed by Claude Code 2026-11-08
MAYBE_STILL_MAX = 0.25
# spec 41, fixed by Claude Code 2026-11-08
ERASE_PAD = 3
# spec 41, fixed by Claude Code 2026-11-08
FRAME_WIDTH_REF = 1280.0

Region = Tuple[int, int, int, int]
Segment = Tuple[float, float, float, float]
KeptSegment = Tuple[float, float, float, float, float]
FtLine = Dict[str, Any]

_CFG: Optional[Dict[str, Any]] = None


def frame_to_ms(frame: int, fps: float) -> int:
    """Same rounding as rim_first_finder.frame_to_ms."""
    return int(round(1000.0 * float(frame) / float(fps)))


def ms_to_frame(t_ms: int, fps: float) -> int:
    """Same rounding as rim_first_finder.ms_to_frame."""
    return int(round(float(t_ms) / 1000.0 * float(fps)))


def stage1b_config() -> Dict[str, Any]:
    """Read the frozen yaml. The file is not modified."""
    global _CFG
    if _CFG is None:
        _CFG = load_config(STAGE1B_DIR / "stage1b_court_lines.yaml")
    return _CFG


def _box_key(box: Dict[str, Any]) -> Tuple[float, float, float, float]:
    return (
        round(float(box["x"]), 1),
        round(float(box["y"]), 1),
        round(float(box["w"]), 1),
        round(float(box["h"]), 1),
    )


def _feet(box: Dict[str, Any]) -> Tuple[float, float]:
    return float(box["x"]), float(box["y"]) + float(box["h"]) / 2.0


def _is_named_referee(box: Dict[str, Any]) -> bool:
    for key in ("class", "name"):
        if box.get(key) == "referee":
            return True
    return False


def _finder():
    """Spec 39 merge and referee drop. Imported at call time to avoid a cycle."""
    import rim_first_finder as rff

    return rff


def _cleaned_players(
    boxes: Sequence[Dict[str, Any]],
    frame: int,
    refs_by_frame: Dict[int, Sequence[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Spec 39: drop a box already classed referee, merge IoU, drop referee players."""
    rff = _finder()
    raw = [box for box in boxes if not _is_named_referee(box)]
    merged = rff.merge_same_body(raw, rff.MERGE_IOU)
    kept: List[Dict[str, Any]] = []
    for box in merged:
        if rff.is_referee_player(
            box,
            int(frame),
            refs_by_frame,
            rff.REF_WINDOW_FRAMES,
            rff.REF_MIN_FRAMES,
            rff.REF_INSIDE,
        ):
            continue
        kept.append(box)
    return kept


def _match_boxes(
    left: Sequence[Dict[str, Any]],
    right: Sequence[Dict[str, Any]],
) -> List[Tuple[int, int, float]]:
    """One-to-one nearest centres. Ties break toward the earlier index."""
    pairs: List[Tuple[float, int, int]] = []
    for i, a in enumerate(left):
        ax, ay = float(a["x"]), float(a["y"])
        for j, b in enumerate(right):
            dist = math.hypot(ax - float(b["x"]), ay - float(b["y"]))
            pairs.append((dist, i, j))
    pairs.sort()
    used_i: set = set()
    used_j: set = set()
    matches: List[Tuple[int, int, float]] = []
    for dist, i, j in pairs:
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        matches.append((i, j, dist))
    return matches


class _Union:
    def __init__(self) -> None:
        self.parent: Dict[Any, Any] = {}
        self.speeds: Dict[Any, List[float]] = {}

    def find(self, key: Any) -> Any:
        self.parent.setdefault(key, key)
        self.speeds.setdefault(key, [])
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def unite(self, a: Any, b: Any) -> Any:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        self.parent[rb] = ra
        self.speeds[ra].extend(self.speeds[rb])
        self.speeds[rb] = []
        return ra

    def add_speed(self, a: Any, b: Any, speed: float) -> None:
        root = self.unite(a, b)
        self.speeds[root].append(float(speed))


def stillness(
    players_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    trigger: int,
    fps: float,
) -> Optional[float]:
    """Median over players of move per second, in player heights.

    Window is [trigger-3000 ms, trigger-1000 ms]. Sample frames every 5.
    A player is a nearest-box chain across those samples. The move is the
    centre shift to the box 25 frames later, divided by that box height and
    by 25/fps seconds. One median per player, then the median of those.
    No pair of boxes means None (the moment is not called still).
    """
    fps = float(fps)
    if fps <= 0.0:
        return None
    trigger_ms = frame_to_ms(int(trigger), fps)
    lo_ms = trigger_ms - STILL_BEFORE_MS
    hi_ms = trigger_ms - STILL_UNTIL_MS

    def in_window(frame: int) -> bool:
        t_ms = frame_to_ms(frame, fps)
        return lo_ms <= t_ms <= hi_ms

    lo_f = ms_to_frame(lo_ms, fps)
    hi_f = ms_to_frame(hi_ms, fps)
    if hi_f < lo_f:
        return None
    first = lo_f
    while first <= hi_f and not in_window(first):
        first += 1
    if first > hi_f:
        return None
    sample_frames: List[int] = []
    frame = first
    while frame <= hi_f:
        if in_window(frame):
            sample_frames.append(frame)
        frame += STILL_EVERY_FRAMES
    sample_set = set(sample_frames)
    boxes_at: Dict[int, List[Dict[str, Any]]] = {}
    for sample in sample_frames:
        boxes_at[sample] = list(players_by_frame.get(sample) or ())

    groups = _Union()
    for index, sample in enumerate(sample_frames):
        if index == 0:
            continue
        prev = sample_frames[index - 1]
        if sample - prev != STILL_EVERY_FRAMES:
            continue
        for i, j, _dist in _match_boxes(boxes_at[prev], boxes_at[sample]):
            groups.unite((prev, i), (sample, j))

    dt = float(STILL_GAP_FRAMES) / fps
    if dt <= 0.0:
        return None
    for sample in sample_frames:
        later = sample + STILL_GAP_FRAMES
        if later not in sample_set:
            continue
        for i, j, dist in _match_boxes(boxes_at[sample], boxes_at[later]):
            height = float(boxes_at[sample][i]["h"])
            if height <= 0.0:
                continue
            groups.add_speed((sample, i), (later, j), (dist / height) / dt)

    per_player: List[float] = []
    seen: set = set()
    for key in list(groups.parent):
        root = groups.find(key)
        if root in seen:
            continue
        seen.add(root)
        speeds = groups.speeds.get(root) or []
        if speeds:
            per_player.append(float(statistics.median(speeds)))
    if not per_player:
        return None
    return float(statistics.median(per_player))


def is_still(
    players_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    trigger: int,
    fps: float,
) -> bool:
    """True when stillness is at or below STILL_MOVE_MAX. None is not still."""
    move = stillness(players_by_frame, trigger, fps)
    if move is None:
        return False
    return move <= STILL_MOVE_MAX


def still_frame_index(
    players_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    trigger: int,
    fps: float,
) -> int:
    """Frame nearest trigger-1000 ms. Prefer a frame that has player boxes."""
    trigger_ms = frame_to_ms(int(trigger), fps)
    target = ms_to_frame(trigger_ms - STILL_UNTIL_MS, fps)
    if not players_by_frame:
        return int(target)
    frames = [int(frame) for frame in players_by_frame]
    return min(frames, key=lambda frame: (abs(frame - target), frame))


def candidates(
    ball_points: Sequence[Sequence[float]],
    players_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    refs_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    trigger: int,
    fps: float,
    still_frame: int,
) -> List[Dict[str, Any]]:
    """Still-frame boxes that held the ball in [trigger-3000 ms, trigger].

    Each hold frame is merged and referee-dropped before the release-0.6
    test. A hold box is the nearest still-frame box (centre distance, no
    extra cutoff). The same still-frame box is returned once.
    """
    from shot_rules_measure import ball_inside_player

    trigger_ms = frame_to_ms(int(trigger), fps)
    lo_ms = trigger_ms - CANDIDATE_BEFORE_MS
    refs = refs_by_frame or {}
    holders: List[Dict[str, Any]] = []
    for pt in ball_points:
        frame = int(pt[0])
        t_ms = frame_to_ms(frame, fps)
        if t_ms < lo_ms or t_ms > trigger_ms:
            continue
        bx, by = float(pt[1]), float(pt[2])
        players = _cleaned_players(players_by_frame.get(frame) or (), frame, refs)
        for player in players:
            if ball_inside_player(
                bx, by, player, BALL_RELEASE_FACTOR, mode="release"
            ):
                holders.append(player)
    still_players = _cleaned_players(
        players_by_frame.get(int(still_frame)) or (), int(still_frame), refs
    )
    if not holders or not still_players:
        return []
    chosen: List[Dict[str, Any]] = []
    seen: set = set()
    for holder in holders:
        nearest = min(
            still_players,
            key=lambda player: (
                math.hypot(
                    float(player["x"]) - float(holder["x"]),
                    float(player["y"]) - float(holder["y"]),
                ),
                _box_key(player),
            ),
        )
        key = _box_key(nearest)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(nearest)
    chosen.sort(key=_box_key)
    return chosen


def region_for(
    player_box: Dict[str, Any],
    frame_w: int,
    frame_h: int,
) -> Region:
    """Square on the box bottom-centre. Half-size is REGION_HALF times box height.

    The square is clipped to the frame. x1, y1 are exclusive.
    """
    height = float(player_box["h"])
    half = REGION_HALF * height
    fx = float(player_box["x"])
    fy = float(player_box["y"]) + height / 2.0
    x0 = int(math.floor(fx - half))
    y0 = int(math.floor(fy - half))
    x1 = int(math.ceil(fx + half))
    y1 = int(math.ceil(fy + half))
    width = int(frame_w)
    limit_h = int(frame_h)
    x0 = max(0, min(width, x0))
    y0 = max(0, min(limit_h, y0))
    x1 = max(0, min(width, x1))
    y1 = max(0, min(limit_h, y1))
    return x0, y0, x1, y1


def paint_in_region(
    frame: np.ndarray,
    region: Region,
    gym: str,
    cfg: Dict[str, Any],
) -> np.ndarray:
    """build_paint_mask on the whole frame, then the region crop.

    The floor mask uses the bottom of the frame, so the crop happens after.
    """
    mask = build_paint_mask(frame, gym, cfg)
    x0, y0, x1, y1 = region
    return mask[y0:y1, x0:x1].copy()


def erase_players(
    mask: np.ndarray,
    players: Sequence[Dict[str, Any]],
    pad: int = ERASE_PAD,
) -> np.ndarray:
    """Copy of mask with each cleaned player box cleared to 0, padded."""
    out = np.array(mask, copy=True)
    pad_i = int(pad)
    for player in players:
        x = float(player["x"])
        y = float(player["y"])
        w = float(player["w"])
        h = float(player["h"])
        x0 = int(x - w / 2.0 - pad_i)
        y0 = int(y - h / 2.0 - pad_i)
        x1 = int(x + w / 2.0 + pad_i)
        y1 = int(y + h / 2.0 + pad_i)
        cv2.rectangle(out, (x0, y0), (x1, y1), 0, -1)
    return out


def line_segments(
    mask_with_players_erased: np.ndarray,
    cfg: Dict[str, Any],
    width: float,
) -> List[Segment]:
    """HoughLinesP on the full-frame paint mask. Spec 41 section 2."""
    det = cfg["detection"]
    scale = float(width) / FRAME_WIDTH_REF
    raw = cv2.HoughLinesP(
        mask_with_players_erased,
        1,
        np.pi / 180.0,
        threshold=int(det["hough_threshold"]),
        minLineLength=max(12, int(round(det["hough_min_line_length_px_at_1280"] * scale))),
        maxLineGap=max(4, int(round(det["hough_max_line_gap_px_at_1280"] * scale))),
    )
    if raw is None:
        return []
    return [tuple(float(v) for v in row) for row in raw.reshape(-1, 4)]


def _undirected_angle_off(seg_deg: float, ref_deg: float) -> float:
    """Angle between two undirected lines, 0-90 deg (L4)."""
    off = abs((seg_deg % 180.0) - (ref_deg % 180.0))
    return min(off, 180.0 - off)


def _adrian_darker_than_both_sides(
    gray: np.ndarray,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: float,
) -> bool:
    """True when the segment is DARK_MIN darker than both sides (prototype)."""
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1.0:
        return False
    nx = -(y2 - y1) / length
    ny = (x2 - x1) / length
    offset = DARK_OFFSET_AT_1280 * (float(width) / FRAME_WIDTH_REF)
    on_sum = 0.0
    side_sum = 0.0
    n = 0
    for t in np.linspace(0.0, 1.0, DARK_SAMPLES):
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        pts = ((x, y), (x + nx * offset, y + ny * offset), (x - nx * offset, y - ny * offset))
        if not all(
            0 <= int(a) < gray.shape[1] and 0 <= int(b) < gray.shape[0]
            for a, b in pts
        ):
            continue
        on_val = float(gray[int(y), int(x)])
        side_a = float(gray[int(pts[1][1]), int(pts[1][0])])
        side_b = float(gray[int(pts[2][1]), int(pts[2][0])])
        on_sum += on_val
        side_sum += min(side_a, side_b)
        n += 1
    if n == 0:
        return False
    return (on_sum - side_sum) / n <= -DARK_MIN


def keep_segments(
    segments: Sequence[Segment],
    feet: Tuple[float, float],
    h: float,
    hoop_xy: Tuple[float, float],
    gray: Optional[np.ndarray],
    gym: str,
    width: float,
) -> List[KeptSegment]:
    """Keep segments near feet, near-perpendicular to feet->hoop, Adrian-dark."""
    fx, fy = float(feet[0]), float(feet[1])
    hx, hy = float(hoop_xy[0]), float(hoop_xy[1])
    height = float(h)
    hd = math.degrees(math.atan2(hy - fy, hx - fx)) % 180.0
    kept: List[KeptSegment] = []
    for x1, y1, x2, y2 in segments:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 1.0:
            continue
        dist = abs(dy * (fx - x1) - dx * (fy - y1)) / length
        t = ((fx - x1) * dx + (fy - y1) * dy) / length
        angle = math.degrees(math.atan2(dy, dx)) % 180.0
        off = _undirected_angle_off(angle, hd)
        if dist > LINE_NEAR * height:
            continue
        if not (-END_PAD * height <= t <= length + END_PAD * height):
            continue
        if off < ANGLE_MIN:
            continue
        if gym == "adrian":
            if gray is None:
                continue
            if not _adrian_darker_than_both_sides(gray, x1, y1, x2, y2, width):
                continue
        kept.append((float(x1), float(y1), float(x2), float(y2), float(angle)))
    return kept


def ft_line(kept: Sequence[KeptSegment]) -> Optional[FtLine]:
    """Median angle, group within GROUP_DEG, mean endpoints, extent on direction."""
    if not kept:
        return None
    a0 = float(np.median([seg[4] for seg in kept]))
    ux = math.cos(math.radians(a0))
    uy = math.sin(math.radians(a0))
    group = [
        seg
        for seg in kept
        if _undirected_angle_off(seg[4], a0) <= GROUP_DEG
    ]
    if not group:
        return None
    xs = [v for seg in group for v in (seg[0], seg[2])]
    ys = [v for seg in group for v in (seg[1], seg[3])]
    mx = float(np.mean(xs))
    my = float(np.mean(ys))
    ts = [
        (px - mx) * ux + (py - my) * uy
        for seg in group
        for px, py in ((seg[0], seg[1]), (seg[2], seg[3]))
    ]
    return {
        "point": (mx, my),
        "direction": (ux, uy),
        "extent": (float(min(ts)), float(max(ts))),
        "kept": [(seg[0], seg[1], seg[2], seg[3]) for seg in group],
    }


def _line_normal(
    line: FtLine,
    hoop_xy: Tuple[float, float],
) -> Tuple[float, float]:
    """Unit normal with the hoop centre on the negative side (L5)."""
    ux, uy = line["direction"]
    mx, my = line["point"]
    nx, ny = -uy, ux
    hx, hy = float(hoop_xy[0]), float(hoop_xy[1])
    if (hx - mx) * nx + (hy - my) * ny > 0.0:
        nx, ny = -nx, -ny
    return nx, ny


def in_band(
    line: FtLine,
    players: Sequence[Dict[str, Any]],
    cand_h: float,
    hoop_xy: Tuple[float, float],
) -> List[Dict[str, Any]]:
    """Players whose feet sit in the FT band behind the line."""
    mx, my = line["point"]
    ux, uy = line["direction"]
    nx, ny = _line_normal(line, hoop_xy)
    tmin, tmax = line["extent"]
    pad = END_PAD * float(cand_h)
    inside: List[Dict[str, Any]] = []
    for player in players:
        px, py = _feet(player)
        s = (px - mx) * nx + (py - my) * ny
        t = (px - mx) * ux + (py - my) * uy
        ph = float(player["h"])
        if -BAND_FRONT * ph <= s <= BAND_BACK * ph and tmin - pad <= t <= tmax + pad:
            inside.append(player)
    return inside


def band_polygon(line: FtLine, cand_h: float, hoop_xy: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Rectangle covering the candidate-height band for debug draw."""
    mx, my = line["point"]
    ux, uy = line["direction"]
    nx, ny = _line_normal(line, hoop_xy)
    tmin, tmax = line["extent"]
    h = float(cand_h)
    t0 = tmin - END_PAD * h
    t1 = tmax + END_PAD * h
    s0 = -BAND_FRONT * h
    s1 = BAND_BACK * h
    return [
        (mx + t0 * ux + s0 * nx, my + t0 * uy + s0 * ny),
        (mx + t1 * ux + s0 * nx, my + t1 * uy + s0 * ny),
        (mx + t1 * ux + s1 * nx, my + t1 * uy + s1 * ny),
        (mx + t0 * ux + s1 * nx, my + t0 * uy + s1 * ny),
    ]


def lane_crossings(
    line: FtLine,
    feet: Tuple[float, float],
    bh: float,
    hoop_xy: Tuple[float, float],
    segments: Sequence[Segment],
    gray: Optional[np.ndarray],
    gym: str,
    width: float,
    out_segments: Optional[List[Tuple[float, float, float, float, float]]] = None,
) -> Tuple[List[float], List[float]]:
    """Lane r values left and right of the shooter feet (spec 42 prototype).

    No length minimum. Adrian uses darker-than-both-sides. Crossing is of the
    segment's infinite line with the FT line; r is relative to the feet
    projection along the FT line, divided by bh.
    """
    mx, my = line["point"]
    ux, uy = line["direction"]
    nx, ny = _line_normal(line, hoop_xy)
    fx, fy = float(feet[0]), float(feet[1])
    h = float(bh)
    tf = (fx - mx) * ux + (fy - my) * uy
    left: List[float] = []
    right: List[float] = []
    line_ang = math.degrees(math.atan2(uy, ux))
    for x1, y1, x2, y2 in segments:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1.0:
            continue
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        off = _undirected_angle_off(ang, line_ang)
        if off < LANE_ANGLE_MIN:
            continue
        s1 = (x1 - mx) * nx + (y1 - my) * ny
        s2 = (x2 - mx) * nx + (y2 - my) * ny
        if max(s1, s2) > LANE_HOOP_SIDE * h:
            continue
        if min(abs(s1), abs(s2)) > LANE_GAP * h:
            continue
        if gym == "adrian":
            if gray is None:
                continue
            if not _adrian_darker_than_both_sides(gray, x1, y1, x2, y2, width):
                continue
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        den = dx * nx + dy * ny
        if abs(den) < 1e-6:
            continue
        k = -s1 / den
        cx, cy = x1 + k * dx, y1 + k * dy
        ti = (cx - mx) * ux + (cy - my) * uy - tf
        r = ti / h
        counted = False
        if -LANE_REACH <= r <= -LANE_MIN_OFF:
            left.append(round(r, 2))
            counted = True
        if LANE_MIN_OFF <= r <= LANE_REACH:
            right.append(round(r, 2))
            counted = True
        if counted and out_segments is not None:
            out_segments.append(
                (float(x1), float(y1), float(x2), float(y2), float(r))
            )
    return left, right


def _shooter_record(box: Dict[str, Any], frame: int) -> Dict[str, float]:
    record: Dict[str, float] = {
        "frame": int(frame),
        "x": float(box["x"]),
        "y": float(box["y"]),
        "w": float(box["w"]),
        "h": float(box["h"]),
    }
    return record


def _decision(
    free_throw: bool,
    box: Optional[Dict[str, Any]],
    reason: str,
    views: Optional[List[Dict[str, Any]]] = None,
    *,
    ft_maybe_shooter_box: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "free_throw": bool(free_throw),
        "ft_shooter_box": box,
        "ft_reason": reason,
    }
    if ft_maybe_shooter_box is not None:
        out["ft_maybe_shooter_box"] = ft_maybe_shooter_box
    if views is not None:
        out["views"] = views
    return out


def _hoop_xy(hoop: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float]]:
    if not isinstance(hoop, dict):
        return None
    if hoop.get("x") is None or hoop.get("y") is None:
        return None
    return float(hoop["x"]), float(hoop["y"])


def _nearest_ball_at_release(
    ball_points: Sequence[Sequence[float]],
    release_frame: int,
) -> Optional[Sequence[float]]:
    """Ball point nearest in frame to release_frame; tie -> earlier frame."""
    if not ball_points:
        return None
    return min(
        ball_points,
        key=lambda pt: (abs(int(pt[0]) - int(release_frame)), int(pt[0])),
    )


def decide_ft(
    *,
    still: bool,
    frame: Optional[np.ndarray],
    players_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    refs_by_frame: Dict[int, Sequence[Dict[str, Any]]],
    ball_points: Sequence[Sequence[float]],
    trigger: int,
    fps: float,
    gym: str,
    cfg: Dict[str, Any],
    still_frame: int,
    hoop: Optional[Dict[str, Any]] = None,
    paint_mask: Optional[np.ndarray] = None,
    collect_debug: bool = False,
    release_frame: Optional[int] = None,
    stillness: Optional[float] = None,
) -> Dict[str, Any]:
    """Spec 43 next-candidate + release + maybe stillness. Spec 42 geometry.

    When stillness is not None (V5), the still arg is ignored: None or
    > MAYBE_STILL_MAX -> not_still; (STILL_MOVE_MAX, MAYBE_STILL_MAX] runs
    the decision and turns free_throw_line into maybe_free_throw; <=
    STILL_MOVE_MAX is the normal decision. When stillness is None the old
    still bool path is unchanged.

    N1: too_far_from_hoop / no_lane_lines / release_not_shooter records the
    first failure and tries the next candidate; if none pass, that first
    failure reason (else line_not_one / ft_line_not_found).

    N2 after lanes: ball nearest to release_frame (tie -> earlier); |dx|/h
    > RELEASE_DX_MAX -> release_not_shooter. No release_frame or no ball
    point -> check skipped.

    Candidates are tried in box-key order. paint_mask, when passed, replaces
    build_paint_mask so tests can hand a mask. It is not used on a film.
    """
    views: Optional[List[Dict[str, Any]]] = [] if collect_debug else None
    maybe_band = False
    if stillness is not None:
        if stillness > MAYBE_STILL_MAX:
            return _decision(False, None, "not_still", views)
        maybe_band = stillness > STILL_MOVE_MAX
    elif not still:
        return _decision(False, None, "not_still", views)

    def _finish(result: Dict[str, Any]) -> Dict[str, Any]:
        if not maybe_band:
            return result
        if result.get("ft_reason") == "free_throw_line":
            return _decision(
                False,
                None,
                "maybe_free_throw",
                result.get("views"),
                ft_maybe_shooter_box=result.get("ft_shooter_box"),
            )
        return _decision(False, None, "not_still", result.get("views"))

    if frame is None and paint_mask is None:
        return _finish(_decision(False, None, "frame_unreadable", views))
    hoop_xy = _hoop_xy(hoop)
    if hoop_xy is None:
        return _finish(_decision(False, None, "no_hoop", views))
    if frame is not None:
        frame_h, frame_w = frame.shape[:2]
    else:
        frame_h, frame_w = paint_mask.shape[:2]
    refs = refs_by_frame or {}
    players = _cleaned_players(
        players_by_frame.get(int(still_frame)) or (), int(still_frame), refs
    )
    found = candidates(
        ball_points,
        players_by_frame,
        refs,
        trigger,
        fps,
        int(still_frame),
    )
    if paint_mask is not None:
        base_mask = np.array(paint_mask, copy=True)
    else:
        base_mask = build_paint_mask(frame, gym, cfg)
    erased = erase_players(base_mask, players, ERASE_PAD)
    segments = line_segments(erased, cfg, float(frame_w))
    gray: Optional[np.ndarray] = None
    if frame is not None:
        if frame.ndim == 2:
            gray = frame.astype(float)
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(float)
    any_line = False
    first_fail: Optional[str] = None
    for player in found:
        fx, fy = _feet(player)
        height = float(player["h"])
        kept = keep_segments(
            segments,
            (fx, fy),
            height,
            hoop_xy,
            gray,
            gym,
            float(frame_w),
        )
        line = ft_line(kept) if kept else None
        polygon = band_polygon(line, height, hoop_xy) if line is not None else None
        view: Optional[Dict[str, Any]] = None
        if views is not None:
            view = {
                "kept_segments": [(s[0], s[1], s[2], s[3]) for s in kept],
                "ft_line": None
                if line is None
                else {
                    "point": line["point"],
                    "direction": line["direction"],
                    "extent": line["extent"],
                },
                "band_polygon": polygon,
                "boxes": players,
                "lane_segments": [],
                "hoop_dist_h": None,
                "release_checked": False,
                "release_dx_h": None,
            }
            views.append(view)
        if line is None:
            continue
        any_line = True
        band = in_band(line, players, height, hoop_xy)
        candidate_keys = {_box_key(box) for box in found}
        if len(band) == 1 and _box_key(band[0]) in candidate_keys:
            b = band[0]
            b_feet = _feet(b)
            bh = float(b["h"])
            hoop_dist_h = math.hypot(
                hoop_xy[0] - b_feet[0], hoop_xy[1] - b_feet[1]
            ) / bh
            lane_segs: List[Tuple[float, float, float, float, float]] = []
            left_r, right_r = lane_crossings(
                line,
                b_feet,
                bh,
                hoop_xy,
                segments,
                gray,
                gym,
                float(frame_w),
                out_segments=lane_segs if views is not None else None,
            )
            if view is not None:
                view["hoop_dist_h"] = float(hoop_dist_h)
                view["lane_segments"] = lane_segs
            if hoop_dist_h > HOOP_DIST_MAX:
                if first_fail is None:
                    first_fail = "too_far_from_hoop"
                continue
            if not left_r or not right_r:
                if first_fail is None:
                    first_fail = "no_lane_lines"
                continue
            release_checked = False
            release_dx_h: Optional[float] = None
            if release_frame is not None and ball_points:
                nearest = _nearest_ball_at_release(ball_points, int(release_frame))
                if nearest is not None:
                    release_checked = True
                    release_dx_h = abs(float(nearest[1]) - float(b["x"])) / bh
                    if view is not None:
                        view["release_checked"] = True
                        view["release_dx_h"] = float(release_dx_h)
                    if release_dx_h > RELEASE_DX_MAX:
                        if first_fail is None:
                            first_fail = "release_not_shooter"
                        continue
            if view is not None and not release_checked:
                view["release_checked"] = False
                view["release_dx_h"] = None
            return _finish(
                _decision(
                    True,
                    _shooter_record(b, int(still_frame)),
                    "free_throw_line",
                    views,
                )
            )
    if first_fail is not None:
        return _finish(_decision(False, None, first_fail, views))
    if not any_line:
        return _finish(_decision(False, None, "ft_line_not_found", views))
    return _finish(_decision(False, None, "line_not_one", views))


def debug_image(
    frame: np.ndarray,
    kept_segments: Sequence[Segment],
    line: Optional[Dict[str, Any]],
    polygon: Optional[Sequence[Tuple[float, float]]],
    boxes: Sequence[Dict[str, Any]],
    path: Path,
    lane_segments: Optional[Sequence[Tuple[float, float, float, float, float]]] = None,
) -> None:
    """Draw kept segments, FT line, band polygon, lane segments, and feet."""
    canvas = np.array(frame, copy=True)
    if canvas.ndim == 2:
        canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    for x1, y1, x2, y2 in kept_segments:
        cv2.line(
            canvas,
            (int(round(x1)), int(round(y1))),
            (int(round(x2)), int(round(y2))),
            (255, 0, 255),
            2,
        )
    if lane_segments:
        for x1, y1, x2, y2, _r in lane_segments:
            cv2.line(
                canvas,
                (int(round(x1)), int(round(y1))),
                (int(round(x2)), int(round(y2))),
                (0, 128, 255),
                2,
            )
    if line is not None:
        mx, my = line["point"]
        ux, uy = line["direction"]
        tmin, tmax = line["extent"]
        p0 = (int(round(mx + tmin * ux)), int(round(my + tmin * uy)))
        p1 = (int(round(mx + tmax * ux)), int(round(my + tmax * uy)))
        cv2.line(canvas, p0, p1, (0, 255, 255), 3)
    if polygon:
        pts = np.array(
            [[int(round(x)), int(round(y))] for x, y in polygon],
            dtype=np.int32,
        )
        cv2.polylines(canvas, [pts], True, (0, 165, 255), 2)
    for box in boxes:
        bw = float(box["w"])
        bh = float(box["h"])
        bx = float(box["x"])
        by = float(box["y"])
        p0 = (int(round(bx - bw / 2.0)), int(round(by - bh / 2.0)))
        p1 = (int(round(bx + bw / 2.0)), int(round(by + bh / 2.0)))
        cv2.rectangle(canvas, p0, p1, (0, 255, 255), 2)
        feet = (int(round(bx)), int(round(by + bh / 2.0)))
        cv2.circle(canvas, feet, 4, (0, 255, 255), -1)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), canvas)
