"""Shot flight rules — measure only (spec 33 v3).

Pure rule functions + A–D summaries + CLI. Reads per-moment JSON written by
collect_flight_tracks.py. No video, no model, no core edits.

Ball series policy (set by the collector; applied here when building the
combined track): use v6 when that frame has a detection, otherwise BODD
basketball. No averaging, no gap filling, no interpolation of any kind.

"At rim height" band (court_memory.py:190 hoop_y + 40 px) is scaled by
hoop_w / 98.0 (Adrian median hoop_w from the v6 track median). Comment at
rim_height_pad_px.

"Above rim" offset (court_memory.py:165 rim_r=72) is scaled the same way:
72 * hoop_w / 98.0. Comment at rim_r_at_hoop.

Hoop at a frame: same-frame sample, else most recent earlier in the moment,
else next later. No time-limit number.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# ---------------------------------------------------------------------------
# Scott-approved constants (spec 33 table, SCOTT APPROVED 2026-11-04).
# CLI only — rule functions take every number as an argument with no default
# (VETTED C7).
# ---------------------------------------------------------------------------
SCOTT_APPROVED_2026_11_04 = {
    "rim_contact_dist": 0.735,  # hoop widths (rim_r 72 / Adrian median hoop_w 98)
    "near_hoop_dist": 1.833,  # hoop widths (Scott: 2 ft past rim outer edge)
    "detection_window_before_ms": 3000,
    "detection_window_after_ms": 2000,
    "catch_distance_factor": 0.5,  # player box diagonal
    "release_trace_factor": 0.6,  # max(player_w, player_h)
    "gap_threshold_frames": 3,
}
# Existing-code rim radius (court_memory.py:165); not one of the seven Scott
# numbers, but every rule that uses it takes it as a required argument (C7).
RIM_R_PX = 72.0
# Adrian median hoop_w used to scale the court_memory.py:190 "+ 40 px" band
# and court_memory.py:165 rim_r=72.
ADRIAN_MEDIAN_HOOP_W = 98.0

RULE_SHOT = "SHOT"
RULE_PASS = "PASS"
RULE_AIRBALL = "AIRBALL"
RULE_NOT_A_SHOT = "NOT_A_SHOT"
RULE_ORANGE = "ORANGE"

DEFAULT_TRACK_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\shot_rules"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/shot_rules"),
]


# ---------------------------------------------------------------------------
# Geometry / track helpers
# ---------------------------------------------------------------------------


def rim_height_pad_px(hoop_w: float) -> float:
    """court_memory.py:190 hoop_y + 40 px, scaled by hoop_w / 98.0 (Adrian median)."""
    return 40.0 * (float(hoop_w) / ADRIAN_MEDIAN_HOOP_W)


def rim_r_at_hoop(rim_r_px: float, hoop_w: float) -> float:
    """court_memory.py:165 rim_r=72 scaled by hoop_w / 98.0 (Adrian median hoop_w)."""
    return float(rim_r_px) * (float(hoop_w) / ADRIAN_MEDIAN_HOOP_W)


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(float(ax) - float(bx), float(ay) - float(by))


def hoop_at(
    hoop_samples: Sequence[Dict[str, Any]],
    timestamp_ms: int,
) -> Optional[Dict[str, Any]]:
    """Hoop at t: same sample, else most recent earlier, else next later.

    No time-limit number (collector last_hoop carry-over within a moment).
    """
    if not hoop_samples:
        return None
    t_ms = int(timestamp_ms)
    exact = None
    best_earlier = None
    best_earlier_t: Optional[int] = None
    best_later = None
    best_later_t: Optional[int] = None
    for row in hoop_samples:
        t = int(row.get("t", row.get("timestamp_ms", 0)))
        if t == t_ms:
            exact = row
        elif t < t_ms:
            if best_earlier_t is None or t > best_earlier_t:
                best_earlier_t = t
                best_earlier = row
        else:
            if best_later_t is None or t < best_later_t:
                best_later_t = t
                best_later = row
    if exact is not None:
        return exact
    if best_earlier is not None:
        return best_earlier
    return best_later


def hoop_for_frame(
    hoop_samples: Sequence[Dict[str, Any]],
    frame: int,
    fps: float,
) -> Optional[Dict[str, Any]]:
    t_ms = int(round(1000.0 * float(frame) / float(fps)))
    return hoop_at(hoop_samples, t_ms)


def box_diagonal(w: float, h: float) -> float:
    return math.hypot(float(w), float(h))


def ball_inside_player(
    bx: float,
    by: float,
    player: Dict[str, Any],
    factor: float,
    *,
    mode: str,
) -> bool:
    """Ball center near a player box center.

    mode='catch': distance < diagonal * factor
    mode='release': distance < max(w,h) * factor
    """
    px = float(player["x"])
    py = float(player["y"])
    pw = float(player["w"])
    ph = float(player["h"])
    d = dist(bx, by, px, py)
    if mode == "catch":
        return d < box_diagonal(pw, ph) * float(factor)
    if mode == "release":
        return d < max(pw, ph) * float(factor)
    raise ValueError(f"unknown mode {mode!r}")


def players_on_frame(
    player_boxes: Sequence[Dict[str, Any]], frame: int
) -> List[Dict[str, Any]]:
    return [p for p in player_boxes if int(p["frame"]) == int(frame)]


def combine_ball_track(
    ball_v6: Sequence[Sequence[float]],
    ball_bodd: Sequence[Sequence[float]],
) -> List[List[float]]:
    """Per frame: v6 if present, else BODD. No average, no fill across gaps."""
    by_frame: Dict[int, List[float]] = {}
    for pt in ball_bodd:
        f = int(pt[0])
        by_frame[f] = [float(v) for v in pt]
    for pt in ball_v6:
        f = int(pt[0])
        by_frame[f] = [float(v) for v in pt]
    return [by_frame[f] for f in sorted(by_frame)]


def track_frames(ball_track: Sequence[Sequence[float]]) -> List[int]:
    return [int(pt[0]) for pt in ball_track]


def longest_gap_frames(ball_track: Sequence[Sequence[float]]) -> int:
    """Largest missing-frame run between consecutive detections (0 if <2 pts)."""
    frames = track_frames(ball_track)
    if len(frames) < 2:
        return 0
    return max(frames[i + 1] - frames[i] - 1 for i in range(len(frames) - 1))


def _longest_gap_in_frames(frames: Sequence[int]) -> int:
    if len(frames) < 2:
        return 0
    return max(frames[i + 1] - frames[i] - 1 for i in range(len(frames) - 1))


def gap_report(
    ball_track: Sequence[Sequence[float]],
    gap_threshold_frames: int,
    *,
    lo_frame: Optional[int] = None,
    hi_frame: Optional[int] = None,
) -> Dict[str, Any]:
    """Report gaps; never fill.

    When lo_frame/hi_frame are set (release..landing), gap_exceeds_threshold
    uses ONLY that flight span. Pre-release and post-landing gaps are context
    and never feed the orange-card check.
    """
    frames = track_frames(ball_track)
    if lo_frame is not None and hi_frame is not None:
        lo, hi = int(lo_frame), int(hi_frame)
        flight = [f for f in frames if lo <= f <= hi]
        pre = [f for f in frames if f < lo]
        post = [f for f in frames if f > hi]
        longest = _longest_gap_in_frames(flight)
        pre_longest = _longest_gap_in_frames(pre)
        if pre and flight:
            pre_longest = max(pre_longest, flight[0] - pre[-1] - 1)
        post_longest = _longest_gap_in_frames(post)
        if flight and post:
            post_longest = max(post_longest, post[0] - flight[-1] - 1)
        span = (hi - lo + 1) if hi >= lo else 0
        return {
            "frames_seen": len(flight),
            "frames_span": span,
            "longest_gap_frames": longest,
            "gap_exceeds_threshold": longest > int(gap_threshold_frames),
            "pre_flight_longest_gap_frames": pre_longest,
            "post_landing_longest_gap_frames": post_longest,
            "release_frame": lo,
            "landing_frame": hi,
        }

    longest = longest_gap_frames(ball_track)
    if len(frames) < 2:
        span = 0
    else:
        span = frames[-1] - frames[0] + 1
    return {
        "frames_seen": len(frames),
        "frames_span": span,
        "longest_gap_frames": longest,
        "gap_exceeds_threshold": longest > int(gap_threshold_frames),
        "pre_flight_longest_gap_frames": 0,
        "post_landing_longest_gap_frames": 0,
        "release_frame": None,
        "landing_frame": None,
    }


def rises_above_rim(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_r_px: float,
    fps: float,
) -> Optional[int]:
    """First frame index in ball_track where ball.y < hoop_y - rim_r_at_hoop."""
    for i, pt in enumerate(ball_track):
        hoop = hoop_for_frame(hoop_samples, int(pt[0]), fps)
        if hoop is None:
            continue
        hw = float(hoop["w"])
        if hw <= 0:
            continue
        if float(pt[2]) < float(hoop["y"]) - rim_r_at_hoop(rim_r_px, hw):
            return i
    return None


def release_estimate_frame(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_r_px: float,
    fps: float,
) -> Optional[int]:
    """Last ball frame before the rise; rise frame itself if that is the first."""
    rise_i = rises_above_rim(ball_track, hoop_samples, rim_r_px, fps)
    if rise_i is None:
        return None
    if rise_i == 0:
        return int(ball_track[0][0])
    return int(ball_track[rise_i - 1][0])


def _landing_dict(
    i: int,
    pt: Sequence[float],
    hoop: Dict[str, Any],
    *,
    rose_above_rim: bool,
    descent_not_seen: bool,
    peak_idx: Optional[int] = None,
) -> Dict[str, Any]:
    hx, hy = float(hoop["x"]), float(hoop["y"])
    hw = float(hoop["w"])
    d = dist(float(pt[1]), float(pt[2]), hx, hy) if hw > 0 else None
    return {
        "idx": i,
        "frame": int(pt[0]),
        "x": float(pt[1]),
        "y": float(pt[2]),
        "land_dist_px": d,
        "hoop_w": hw,
        "hoop_x": hx,
        "hoop_y": hy,
        "rose_above_rim": rose_above_rim,
        "descent_not_seen": descent_not_seen,
        "peak_idx": peak_idx,
    }


def find_landing(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_r_px: float,
    fps: float,
) -> Optional[Dict[str, Any]]:
    """Flight comes down where the ball, after its peak, first reaches hoop_y.

    rise = first frame with ball above rim (scaled rim_r).
    peak = highest ball point (min y) from the rise until the ball first goes
    back below hoop_y (y >= hoop_y).
    landing = FIRST frame after the peak with ball.y >= hoop_y (hoop at that
    frame). Land distance is measured there, in hoop widths.

    If no frame after the peak reaches hoop_y → descent_not_seen=True
    (caller → ORANGE \"descent not seen\"). No new number.
    """
    if not ball_track:
        return None

    rise_i = rises_above_rim(ball_track, hoop_samples, rim_r_px, fps)
    if rise_i is None:
        # Never rose: last usable point for Rule 4 distance; not a flight landing.
        best = None
        for i in range(len(ball_track) - 1, -1, -1):
            pt = ball_track[i]
            hoop = hoop_for_frame(hoop_samples, int(pt[0]), fps)
            if hoop is None or float(hoop["w"]) <= 0:
                continue
            best = _landing_dict(
                i, pt, hoop, rose_above_rim=False, descent_not_seen=False
            )
            break
        return best

    # Peak: min y from rise while still above hoop_y (y < hoop_y).
    peak_i: Optional[int] = None
    peak_y: Optional[float] = None
    for i in range(rise_i, len(ball_track)):
        pt = ball_track[i]
        hoop = hoop_for_frame(hoop_samples, int(pt[0]), fps)
        if hoop is None:
            continue
        y = float(pt[2])
        hy = float(hoop["y"])
        if y >= hy:
            break
        if peak_i is None or y < peak_y:  # type: ignore[operator]
            peak_i = i
            peak_y = y

    if peak_i is None:
        # Rose but no peak frame with a hoop while still above hoop_y.
        return {
            "idx": rise_i,
            "frame": int(ball_track[rise_i][0]),
            "x": float(ball_track[rise_i][1]),
            "y": float(ball_track[rise_i][2]),
            "land_dist_px": None,
            "hoop_w": None,
            "hoop_x": None,
            "hoop_y": None,
            "rose_above_rim": True,
            "descent_not_seen": True,
            "peak_idx": None,
        }

    # Landing: first frame after the peak with ball.y >= hoop_y.
    for i in range(peak_i + 1, len(ball_track)):
        pt = ball_track[i]
        hoop = hoop_for_frame(hoop_samples, int(pt[0]), fps)
        if hoop is None or float(hoop["w"]) <= 0:
            continue
        if float(pt[2]) >= float(hoop["y"]):
            return _landing_dict(
                i,
                pt,
                hoop,
                rose_above_rim=True,
                descent_not_seen=False,
                peak_idx=peak_i,
            )

    # Ball lost on the way down — never seen back at hoop_y.
    peak_pt = ball_track[peak_i]
    peak_hoop = hoop_for_frame(hoop_samples, int(peak_pt[0]), fps)
    if peak_hoop is None or float(peak_hoop.get("w") or 0) <= 0:
        return {
            "idx": peak_i,
            "frame": int(peak_pt[0]),
            "x": float(peak_pt[1]),
            "y": float(peak_pt[2]),
            "land_dist_px": None,
            "hoop_w": None,
            "hoop_x": None,
            "hoop_y": None,
            "rose_above_rim": True,
            "descent_not_seen": True,
            "peak_idx": peak_i,
        }
    out = _landing_dict(
        peak_i,
        peak_pt,
        peak_hoop,
        rose_above_rim=True,
        descent_not_seen=True,
        peak_idx=peak_i,
    )
    return out


def flight_span_frames(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_r_px: float,
    fps: float,
) -> Tuple[Optional[int], Optional[int], Optional[Dict[str, Any]]]:
    """(release_frame, landing_frame, landing_dict) for gap/coverage span."""
    landing = find_landing(ball_track, hoop_samples, rim_r_px, fps)
    release_f = release_estimate_frame(ball_track, hoop_samples, rim_r_px, fps)
    if landing is None or not landing.get("rose_above_rim"):
        return release_f, None, landing
    if landing.get("descent_not_seen"):
        return release_f, None, landing
    return release_f, int(landing["frame"]), landing


# ---------------------------------------------------------------------------
# Rule functions — every numeric threshold is a required argument (C7)
# ---------------------------------------------------------------------------


def hits_rim(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_contact_dist_hoop_w: float,
    rim_r_px: float,
    fps: float,
) -> Tuple[bool, Optional[int]]:
    """Rule 2: distance <= rim_contact_dist (hoop widths) and at rim-height band.

    Band: y <= hoop_y + 40*(hoop_w/98)  # court_memory.py:190 scaled
    rim_r_px is kept for API symmetry with other rules (not used in the
    distance test; distance uses rim_contact_dist_hoop_w * hoop_w).
    """
    del rim_r_px  # distance uses hoop-width units (C3); rim_r informed the 0.735 value
    for pt in ball_track:
        hoop = hoop_for_frame(hoop_samples, int(pt[0]), fps)
        if hoop is None:
            continue
        hw = float(hoop["w"])
        if hw <= 0:
            continue
        hx, hy = float(hoop["x"]), float(hoop["y"])
        d = dist(float(pt[1]), float(pt[2]), hx, hy)
        if d <= float(rim_contact_dist_hoop_w) * hw and float(pt[2]) <= hy + rim_height_pad_px(
            hw
        ):
            return True, int(pt[0])
    return False, None


def is_caught_near_hoop(
    ball_track: Sequence[Sequence[float]],
    player_boxes: Sequence[Dict[str, Any]],
    hoop_samples: Sequence[Dict[str, Any]],
    near_hoop_dist_hoop_w: float,
    rim_contact_dist_hoop_w: float,
    rim_r_px: float,
    catch_distance_factor: float,
    fps: float,
) -> bool:
    """Rule 1 (C1/C2): leave a player box, in flight, then enter a player box.

    Only meaningful when landing is near the hoop (not rim zone, not far).
    Shooter's own hands at release are NOT a catch — the ball must leave first
    (was_in → left), then enter a player box before the rim-height band /
    rim zone. Rim-zone balls are never a catch (C2); classify_flight also
    short-circuits rim → SHOT before calling this.
    """
    landing = find_landing(ball_track, hoop_samples, rim_r_px, fps)
    if landing is None or not landing.get("rose_above_rim"):
        return False
    if landing.get("descent_not_seen"):
        return False
    if landing.get("land_dist_px") is None or not landing.get("hoop_w"):
        return False
    land_hw = landing["land_dist_px"] / landing["hoop_w"]
    if land_hw <= float(rim_contact_dist_hoop_w):
        return False  # rim zone → never a catch (C2)
    if land_hw > float(near_hoop_dist_hoop_w):
        return False  # far → catch never checked (v3)

    # C1: catch = leave a box, in flight, enter a box, before first reaching
    # the rim zone in TIME. Do not abort on release frames that sit below the
    # rim-height band before the ball has risen.
    was_in_box = False
    left_box = False
    seen_above_rim = False
    for pt in ball_track:
        frame = int(pt[0])
        bx, by = float(pt[1]), float(pt[2])
        hoop = hoop_for_frame(hoop_samples, frame, fps)
        if hoop is None:
            continue
        hw = float(hoop["w"])
        if hw <= 0:
            continue
        hy = float(hoop["y"])
        d_hoop = dist(bx, by, float(hoop["x"]), hy)
        # Reached rim zone → too late for a catch (C1/C2).
        if d_hoop <= float(rim_contact_dist_hoop_w) * hw:
            break
        if by < hy - rim_r_at_hoop(rim_r_px, hw):
            seen_above_rim = True
        # After rising, dropping through the rim-height band ends the catch window.
        if seen_above_rim and by > hy + rim_height_pad_px(hw):
            break

        on = players_on_frame(player_boxes, frame)
        inside = any(
            ball_inside_player(bx, by, p, catch_distance_factor, mode="catch") for p in on
        )
        if inside:
            if left_box:
                return True  # re-entry after flight = catch
            was_in_box = True
        else:
            if was_in_box:
                left_box = True
    return False


def is_airball_near_hoop(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    near_hoop_dist_hoop_w: float,
    rim_contact_dist_hoop_w: float,
    rim_r_px: float,
    fps: float,
) -> bool:
    """Rule 3: rose above rim, lands near hoop, not in rim zone (C4: no net check)."""
    landing = find_landing(ball_track, hoop_samples, rim_r_px, fps)
    if landing is None or not landing.get("rose_above_rim"):
        return False
    if landing.get("descent_not_seen"):
        return False
    if landing.get("land_dist_px") is None or not landing.get("hoop_w"):
        return False
    land_hw = landing["land_dist_px"] / landing["hoop_w"]
    if land_hw <= float(rim_contact_dist_hoop_w):
        return False
    return land_hw <= float(near_hoop_dist_hoop_w)


def is_bad_pass(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    near_hoop_dist_hoop_w: float,
    rim_r_px: float,
    fps: float,
) -> bool:
    """Rule 4: never rises above rim, or lands farther than near_hoop_dist."""
    landing = find_landing(ball_track, hoop_samples, rim_r_px, fps)
    if landing is None:
        return False
    if landing.get("descent_not_seen"):
        return False
    if not landing.get("rose_above_rim"):
        return True
    if landing.get("land_dist_px") is None or not landing.get("hoop_w"):
        return False
    land_hw = landing["land_dist_px"] / landing["hoop_w"]
    return land_hw > float(near_hoop_dist_hoop_w)


def is_orange_card(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    player_boxes: Sequence[Dict[str, Any]],
    near_hoop_dist_hoop_w: float,
    rim_r_px: float,
    gap_threshold_frames: int,
    fps: float,
) -> Tuple[bool, str]:
    """Unclear / incomplete track → orange with a reason."""
    del player_boxes  # reserved for future ambiguity checks; reason is track-based
    del near_hoop_dist_hoop_w
    if not ball_track:
        return True, "empty ball track"

    release_f, land_f, landing = flight_span_frames(
        ball_track, hoop_samples, rim_r_px, fps
    )
    if landing is not None and landing.get("descent_not_seen"):
        return True, "descent not seen"

    if release_f is not None and land_f is not None:
        gaps = gap_report(
            ball_track,
            gap_threshold_frames,
            lo_frame=release_f,
            hi_frame=land_f,
        )
        if gaps["gap_exceeds_threshold"]:
            return True, (
                f"gap > {int(gap_threshold_frames)} frames during flight "
                f"(longest_gap_frames={gaps['longest_gap_frames']})"
            )
    elif release_f is not None and land_f is None and landing is None:
        # Rose never established cleanly / no hoop — fall through.
        pass

    if landing is None:
        return True, "no hoop sample for landing"
    if not landing.get("rose_above_rim") and len(ball_track) < 3:
        return True, "incomplete track (short, never rose above rim)"
    return False, ""


def trace_release(
    ball_track: Sequence[Sequence[float]],
    player_boxes: Sequence[Dict[str, Any]],
    start_frame: int,
    release_trace_factor: float,
) -> Tuple[bool, Optional[int], Optional[Dict[str, Any]]]:
    """Walk backward from start_frame to first frame ball is in a player box."""
    pts = [pt for pt in ball_track if int(pt[0]) <= int(start_frame)]
    pts.sort(key=lambda p: int(p[0]), reverse=True)
    for pt in pts:
        frame = int(pt[0])
        bx, by = float(pt[1]), float(pt[2])
        for player in players_on_frame(player_boxes, frame):
            if ball_inside_player(bx, by, player, release_trace_factor, mode="release"):
                return True, frame, dict(player)
    return False, None, None


def classify_flight(
    ball_track: Sequence[Sequence[float]],
    player_boxes: Sequence[Dict[str, Any]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_contact_dist_hoop_w: float,
    near_hoop_dist_hoop_w: float,
    rim_r_px: float,
    catch_distance_factor: float,
    gap_threshold_frames: int,
    fps: float,
) -> Dict[str, Any]:
    """v3 decision order: rim → SHOT; near → catch? PASS : AIRBALL; far → NOT A SHOT.

    Incomplete / unclear → ORANGE with reason. Gaps reported only in
    release..landing; pre/post gaps are context and never force ORANGE.
    """
    release_f, land_f, landing = flight_span_frames(
        ball_track, hoop_samples, rim_r_px, fps
    )
    if release_f is not None and land_f is not None:
        gaps = gap_report(
            ball_track,
            gap_threshold_frames,
            lo_frame=release_f,
            hi_frame=land_f,
        )
    else:
        gaps = gap_report(ball_track, gap_threshold_frames)

    orange, reason = is_orange_card(
        ball_track,
        hoop_samples,
        player_boxes,
        near_hoop_dist_hoop_w,
        rim_r_px,
        gap_threshold_frames,
        fps,
    )
    if not ball_track or gaps["frames_seen"] == 0 and release_f is None:
        return {
            "rule": RULE_ORANGE,
            "reason": reason or "empty ball track",
            "gaps": gaps,
            "landing": None,
        }
    if not ball_track:
        return {
            "rule": RULE_ORANGE,
            "reason": reason or "empty ball track",
            "gaps": gaps,
            "landing": None,
        }

    if landing is None:
        return {
            "rule": RULE_ORANGE,
            "reason": "no hoop sample for landing",
            "gaps": gaps,
            "landing": None,
        }

    if landing.get("descent_not_seen"):
        return {
            "rule": RULE_ORANGE,
            "reason": "descent not seen",
            "gaps": gaps,
            "landing": landing,
        }

    # Flight-span gap that blocks a clean 1–3 call → orange (still report gap).
    if gaps["gap_exceeds_threshold"] and landing.get("rose_above_rim"):
        return {
            "rule": RULE_ORANGE,
            "reason": reason,
            "gaps": gaps,
            "landing": landing,
        }

    if landing.get("land_dist_px") is None or not landing.get("hoop_w"):
        return {
            "rule": RULE_ORANGE,
            "reason": reason or "no hoop sample for landing",
            "gaps": gaps,
            "landing": landing,
        }

    land_hw = landing["land_dist_px"] / landing["hoop_w"]

    hit, hit_frame = hits_rim(
        ball_track,
        hoop_samples,
        rim_contact_dist_hoop_w,
        rim_r_px,
        fps,
    )

    # 1. Rim zone at landing → SHOT (never a catch, even if a player overlaps).
    if land_hw <= float(rim_contact_dist_hoop_w):
        return {
            "rule": RULE_SHOT,
            "reason": "",
            "gaps": gaps,
            "landing": landing,
            "rim_frame": hit_frame if hit else landing["frame"],
        }

    # 2. Near hoop → catch check → PASS else AIRBALL
    if land_hw <= float(near_hoop_dist_hoop_w):
        caught = is_caught_near_hoop(
            ball_track,
            player_boxes,
            hoop_samples,
            near_hoop_dist_hoop_w,
            rim_contact_dist_hoop_w,
            rim_r_px,
            catch_distance_factor,
            fps,
        )
        if caught:
            return {
                "rule": RULE_PASS,
                "reason": "",
                "gaps": gaps,
                "landing": landing,
            }
        if landing.get("rose_above_rim"):
            return {
                "rule": RULE_AIRBALL,
                "reason": "",
                "gaps": gaps,
                "landing": landing,
            }
        return {
            "rule": RULE_ORANGE,
            "reason": "near hoop but never rose above rim",
            "gaps": gaps,
            "landing": landing,
        }

    # 3. Far → NOT A SHOT (catch never checked)
    if orange and reason.startswith("ambiguous"):
        return {
            "rule": RULE_ORANGE,
            "reason": reason,
            "gaps": gaps,
            "landing": landing,
        }
    return {
        "rule": RULE_NOT_A_SHOT,
        "reason": "",
        "gaps": gaps,
        "landing": landing,
    }


# ---------------------------------------------------------------------------
# A–D summaries
# ---------------------------------------------------------------------------


def flight_coverage(
    ball_track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    rim_r_px: float,
    fps: float,
    gap_threshold_frames: int,
) -> Dict[str, Any]:
    """Question A fields for one moment — span is release..landing."""
    release_f, land_f, landing = flight_span_frames(
        ball_track, hoop_samples, rim_r_px, fps
    )
    if release_f is not None and land_f is not None:
        gaps = gap_report(
            ball_track,
            gap_threshold_frames,
            lo_frame=release_f,
            hi_frame=land_f,
        )
        frames_in_flight_estimate = max(0, int(land_f) - int(release_f) + 1)
    else:
        gaps = gap_report(ball_track, gap_threshold_frames)
        if ball_track and release_f is not None:
            end_f = int(ball_track[-1][0])
            frames_in_flight_estimate = max(0, end_f - int(release_f) + 1)
        elif ball_track:
            frames_in_flight_estimate = (
                int(ball_track[-1][0]) - int(ball_track[0][0]) + 1
            )
        else:
            frames_in_flight_estimate = 0
    return {
        **gaps,
        "release_frame_estimate": release_f,
        "frames_in_flight_estimate": frames_in_flight_estimate,
        "coverage_ratio": (
            (gaps["frames_seen"] / frames_in_flight_estimate)
            if frames_in_flight_estimate
            else None
        ),
        "landing": landing,
    }


def summarize_coverage(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"n": 0, "median": None, "min": None, "max": None}
    ratios = [r["coverage_ratio"] for r in rows if r.get("coverage_ratio") is not None]
    gaps = [int(r["longest_gap_frames"]) for r in rows]
    seen = [int(r["frames_seen"]) for r in rows]
    flight = [int(r["frames_in_flight_estimate"]) for r in rows]
    return {
        "n": len(rows),
        "coverage_ratio": {
            "median": statistics.median(ratios) if ratios else None,
            "min": min(ratios) if ratios else None,
            "max": max(ratios) if ratios else None,
        },
        "frames_seen": {
            "median": int(statistics.median(seen)),
            "min": min(seen),
            "max": max(seen),
        },
        "frames_in_flight_estimate": {
            "median": int(statistics.median(flight)),
            "min": min(flight),
            "max": max(flight),
        },
        "longest_gap_frames": {
            "median": int(statistics.median(gaps)),
            "min": min(gaps),
            "max": max(gaps),
        },
    }


def count_rules(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    out = {
        RULE_SHOT: 0,
        RULE_PASS: 0,
        RULE_AIRBALL: 0,
        RULE_NOT_A_SHOT: 0,
        RULE_ORANGE: 0,
    }
    for r in rows:
        key = r.get("rule")
        if key in out:
            out[key] += 1
    return out


def measure_moment(
    moment: Dict[str, Any],
    *,
    rim_contact_dist: float,
    near_hoop_dist: float,
    rim_r_px: float,
    catch_distance_factor: float,
    release_trace_factor: float,
    gap_threshold_frames: int,
    fps: float,
) -> Dict[str, Any]:
    ball = combine_ball_track(moment.get("ball_track") or [], moment.get("bodd_track") or [])
    players = moment.get("player_boxes") or []
    hoops = moment.get("hoop_samples") or []
    decision = classify_flight(
        ball,
        players,
        hoops,
        rim_contact_dist,
        near_hoop_dist,
        rim_r_px,
        catch_distance_factor,
        gap_threshold_frames,
        fps,
    )
    cov = flight_coverage(ball, hoops, rim_r_px, fps, gap_threshold_frames)
    release = {"success": False, "release_frame": None, "player_box": None}
    if decision["rule"] in (RULE_SHOT, RULE_AIRBALL):
        start_f = decision.get("rim_frame") or (
            decision["landing"]["frame"] if decision.get("landing") else None
        )
        if start_f is not None:
            ok, rf, box = trace_release(ball, players, int(start_f), release_trace_factor)
            release = {"success": ok, "release_frame": rf, "player_box": box}
    return {
        "moment_id": moment.get("moment_id"),
        "kind": moment.get("kind"),
        "film": moment.get("film"),
        "tag_t_ms": moment.get("tag_t_ms"),
        "eventtype": moment.get("eventtype"),
        "quarter": moment.get("quarter"),
        "result": moment.get("result"),
        "rule": decision["rule"],
        "reason": decision.get("reason") or "",
        "gaps": decision["gaps"],
        "landing": decision.get("landing"),
        "coverage": cov,
        "release_trace": release,
    }


def load_film_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def measure_all(
    film_jsons: Sequence[Dict[str, Any]],
    *,
    rim_contact_dist: float,
    near_hoop_dist: float,
    rim_r_px: float,
    catch_distance_factor: float,
    release_trace_factor: float,
    gap_threshold_frames: int,
) -> Dict[str, Any]:
    measured: List[Dict[str, Any]] = []
    for film in film_jsons:
        fps = float(film["fps"])
        for moment in film.get("moments") or []:
            m = dict(moment)
            m.setdefault("film", film.get("film") or film.get("name"))
            measured.append(
                measure_moment(
                    m,
                    rim_contact_dist=rim_contact_dist,
                    near_hoop_dist=near_hoop_dist,
                    rim_r_px=rim_r_px,
                    catch_distance_factor=catch_distance_factor,
                    release_trace_factor=release_trace_factor,
                    gap_threshold_frames=gap_threshold_frames,
                    fps=fps,
                )
            )

    def is_tag(r: Dict[str, Any]) -> bool:
        return r.get("kind") == "tag"

    def is_fake(r: Dict[str, Any]) -> bool:
        return r.get("kind") == "fake"

    tagged = [r for r in measured if is_tag(r)]
    fakes = [r for r in measured if is_fake(r)]

    # A — coverage by film × kind
    table_a: Dict[str, Any] = {}
    for film_name in sorted({r.get("film") for r in tagged}):
        table_a[film_name] = {}
        for kind in ("2PT", "3PT", "FT", "all"):
            subset = [
                r["coverage"]
                for r in tagged
                if r.get("film") == film_name
                and (kind == "all" or r.get("eventtype") == kind)
            ]
            table_a[film_name][kind] = summarize_coverage(subset)

    # B — rule counts tagged
    table_b: Dict[str, Any] = {}
    for film_name in sorted({r.get("film") for r in tagged}):
        table_b[film_name] = {}
        for kind in ("2PT", "3PT", "FT", "all"):
            subset = [
                r
                for r in tagged
                if r.get("film") == film_name
                and (kind == "all" or r.get("eventtype") == kind)
            ]
            table_b[film_name][kind] = count_rules(subset)

    # C — rule counts fakes
    table_c: Dict[str, Any] = {}
    for film_name in sorted({r.get("film") for r in fakes} | {r.get("film") for r in tagged}):
        subset = [r for r in fakes if r.get("film") == film_name]
        table_c[film_name] = count_rules(subset)

    # D — release trace on Rule 2/3 tagged
    table_d: Dict[str, Any] = {}
    for film_name in sorted({r.get("film") for r in tagged}):
        table_d[film_name] = {}
        for kind in ("2PT", "3PT", "FT", "all"):
            subset = [
                r
                for r in tagged
                if r.get("film") == film_name
                and r.get("rule") in (RULE_SHOT, RULE_AIRBALL)
                and (kind == "all" or r.get("eventtype") == kind)
            ]
            successes = [r for r in subset if r["release_trace"]["success"]]
            frames_back = []
            for r in successes:
                land_f = (
                    r.get("landing", {}) or {}
                ).get("frame")
                rf = r["release_trace"]["release_frame"]
                if land_f is not None and rf is not None:
                    frames_back.append(int(land_f) - int(rf))
            table_d[film_name][kind] = {
                "n": len(subset),
                "success": len(successes),
                "success_rate": (len(successes) / len(subset)) if subset else None,
                "median_frames_back": (
                    int(statistics.median(frames_back)) if frames_back else None
                ),
            }

    return {
        "applied_to_core": False,
        "constants": {
            **SCOTT_APPROVED_2026_11_04,
            "rim_r_px": rim_r_px,
            "adrian_median_hoop_w": ADRIAN_MEDIAN_HOOP_W,
        },
        "moments": measured,
        "A_flight_coverage": table_a,
        "B_rules_tagged": table_b,
        "C_rules_fakes": table_c,
        "D_release_trace": table_d,
    }


def write_summary_md(results: Dict[str, Any], path: Path) -> None:
    lines: List[str] = []
    lines.append("# Shot flight rules — measure")
    lines.append("")
    c = results["constants"]
    lines.append(
        f"Scott approved 2026-11-04: rim_contact_dist={c['rim_contact_dist']}, "
        f"near_hoop_dist={c['near_hoop_dist']}, window "
        f"{c['detection_window_before_ms']}/{c['detection_window_after_ms']} ms, "
        f"catch={c['catch_distance_factor']}, release={c['release_trace_factor']}, "
        f"gap_threshold_frames={c['gap_threshold_frames']}."
    )
    lines.append("")
    lines.append("## A. Flight coverage (tagged)")
    lines.append("")
    for film, kinds in results["A_flight_coverage"].items():
        lines.append(f"### {film}")
        lines.append("")
        lines.append(
            "| Kind | n | cov median | cov min | cov max | "
            "gap median | gap max |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for kind in ("2PT", "3PT", "FT", "all"):
            s = kinds[kind]
            cr = s.get("coverage_ratio") or {}
            lg = s.get("longest_gap_frames") or {}
            lines.append(
                f"| {kind} | {s.get('n', 0)} | {cr.get('median')} | "
                f"{cr.get('min')} | {cr.get('max')} | {lg.get('median')} | "
                f"{lg.get('max')} |"
            )
        lines.append("")

    lines.append("## B. Rules — tagged shots")
    lines.append("")
    for film, kinds in results["B_rules_tagged"].items():
        lines.append(f"### {film}")
        lines.append("")
        lines.append(
            "| Kind | SHOT | PASS | AIRBALL | NOT_A_SHOT | ORANGE |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|")
        for kind in ("2PT", "3PT", "FT", "all"):
            c_ = kinds[kind]
            lines.append(
                f"| {kind} | {c_[RULE_SHOT]} | {c_[RULE_PASS]} | "
                f"{c_[RULE_AIRBALL]} | {c_[RULE_NOT_A_SHOT]} | {c_[RULE_ORANGE]} |"
            )
        lines.append("")

    lines.append("## C. Rules — fake shots (spec 32 extras)")
    lines.append("")
    for film, c_ in results["C_rules_fakes"].items():
        lines.append(
            f"- **{film}**: SHOT={c_[RULE_SHOT]} PASS={c_[RULE_PASS]} "
            f"AIRBALL={c_[RULE_AIRBALL]} NOT_A_SHOT={c_[RULE_NOT_A_SHOT]} "
            f"ORANGE={c_[RULE_ORANGE]}"
        )
    lines.append("")

    lines.append("## D. Release trace-back (tagged Rule 2/3)")
    lines.append("")
    for film, kinds in results["D_release_trace"].items():
        lines.append(f"### {film}")
        lines.append("")
        lines.append("| Kind | n | success | rate | median frames back |")
        lines.append("|---|---:|---:|---:|---:|")
        for kind in ("2PT", "3PT", "FT", "all"):
            d = kinds[kind]
            rate = d["success_rate"]
            rate_s = f"{100.0 * rate:.1f}%" if rate is not None else "—"
            lines.append(
                f"| {kind} | {d['n']} | {d['success']} | {rate_s} | "
                f"{d['median_frames_back']} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def pick_tracks_dir(*candidates: Path) -> Optional[Path]:
    for c in candidates:
        if c is not None and Path(c).exists():
            return Path(c)
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Apply shot-flight rules to collected tracks (measure only)."
    )
    p.add_argument(
        "--tracks-dir",
        type=Path,
        default=None,
        help="Directory with per-film JSON from collect_flight_tracks.py",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for results.json + summary.md (created; refuse if exists)",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    tracks_dir = args.tracks_dir or pick_tracks_dir(*DEFAULT_TRACK_CANDIDATES)
    if tracks_dir is None:
        raise SystemExit("No tracks dir found. Pass --tracks-dir.")
    out_dir = args.out_dir or tracks_dir
    # Allow writing results into the same tracks dir; only refuse if results
    # already exist when out_dir is a fresh dedicated folder that exists with
    # results.json already present — collector owns the dir-exists refuse.
    results_path = Path(out_dir) / "results.json"
    if results_path.exists():
        raise SystemExit(f"Refuse: {results_path} already exists")

    film_paths = sorted(Path(tracks_dir).glob("*.json"))
    film_paths = [p for p in film_paths if p.name != "results.json"]
    if not film_paths:
        raise SystemExit(f"No film JSON files in {tracks_dir}")

    films = [load_film_json(p) for p in film_paths]
    consts = SCOTT_APPROVED_2026_11_04
    results = measure_all(
        films,
        rim_contact_dist=float(consts["rim_contact_dist"]),
        near_hoop_dist=float(consts["near_hoop_dist"]),
        rim_r_px=float(RIM_R_PX),
        catch_distance_factor=float(consts["catch_distance_factor"]),
        release_trace_factor=float(consts["release_trace_factor"]),
        gap_threshold_frames=int(consts["gap_threshold_frames"]),
    )
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    write_summary_md(results, Path(out_dir) / "summary.md")
    print(f"Wrote {results_path} and {Path(out_dir) / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
