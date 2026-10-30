"""Stage A — copy of run_saved_v6_rule with four opt-in switches (default OFF).

Plan: .team/specs/18_makes_misses_work_plan.md (VETTED + BINDING NOTES a–e).
Creates ONLY this file. Never edits ai_bridge.py or protected files; imports
run_saved_v6_rule read-only for the identity check.

Windows checker / Scott:
  C:\\Users\\scott\\Documents\\liberty-basketball-analysis\\.venv\\Scripts\\python.exe \\
    .team/shot_detectors/small_fixes_v6_copy.py

Sandbox:
  python3 .team/shot_detectors/small_fixes_v6_copy.py \\
    --out .team/shot_outputs_test/small_fixes
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_bridge import run_saved_v6_rule  # noqa: E402  — read-only identity check

EXPECTED_BUILD = 140
EXPECTED_MAKES = 47
EXPECTED_RULE_RIGHT = 28
EXPECTED_MISSED_MAKES = 19
EXPECTED_REAL_MISSES = 93

DEFAULT_RESULTS_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_build_results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/net_moved_build_results.json"),
]

TRACKS_FALLBACK_DIRS = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\tracks"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/tracks"),
]

DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\small_fixes"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/small_fixes"),
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
    """Return a Path that exists, accepting Windows or /mnt/c forms."""
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


def resolve_tracks_path(tracks_path: str) -> Path:
    """Prefer the row's tracks_path; if missing, map by file name under Liberty_Shot_Outputs/tracks."""
    p = resolve_path(tracks_path)
    if p.exists():
        return p
    name = Path(str(tracks_path).replace("\\", "/")).name
    for folder in TRACKS_FALLBACK_DIRS:
        cand = folder / name
        if cand.exists():
            return cand
    return p


def default_results_path() -> Path:
    found = pick_existing(*DEFAULT_RESULTS_CANDIDATES)
    if found is not None:
        return found
    return DEFAULT_RESULTS_CANDIDATES[0]


def default_out_dir() -> Path:
    found = pick_existing(*DEFAULT_OUT_CANDIDATES)
    if found is not None:
        return found
    parent_u = Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs")
    parent_w = Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs")
    if parent_u.exists():
        return parent_u / "small_fixes"
    if parent_w.exists():
        return parent_w / "small_fixes"
    return DEFAULT_OUT_CANDIDATES[0]


# --- helpers copied from ai_bridge.py (decision logic only) ---


def short_track_stays_in_net(net_depth_frames, bodd, ball, hoop_x, hoop_y, hoop_w, scale_y=1.0):
    """A short ball track is a make when it disappears inside the rim.

    The ball's last point is inside 0.65 hoop-widths. A body-track point in the
    next 70 pixels must not sit more than one hoop-width off center. A body
    track that keeps falling and leaves the rim is a carom, unless the ball
    itself ended in the center of the hoop. A track that stops above 150 pixels
    with nothing under it must have ended inside 0.20 hoop-widths.
    """
    max_y = max(pt[2] for pt in net_depth_frames) - hoop_y
    end_w = abs(net_depth_frames[-1][1] - hoop_x) / hoop_w
    if end_w > 0.65:
        return False
    last_ball_frame = ball[-1][0] if ball else -1
    after = [pt for pt in (bodd or []) if pt[0] > last_ball_frame]

    def width(pt):
        return abs(pt[1] - hoop_x) / hoop_w

    band = [pt for pt in after if max_y < (pt[2] - hoop_y) <= max_y + (70.0 * scale_y)]
    if band and min(width(pt) for pt in band) > 1.0:
        return False
    if after:
        y0 = after[0][2]
        falling = [pt for pt in after if pt[2] > y0 + (40.0 * scale_y)]
        if falling and min(width(pt) for pt in falling) > 0.85 and end_w > 0.15:
            return False
    in_column_fall = bool(after) and any(
        pt[2] > after[0][2] + (40.0 * scale_y) and width(pt) <= 0.85 for pt in after
    )
    if max_y < (150.0 * scale_y) and end_w > 0.20 and not in_column_fall:
        return False
    return True


def detect_dynamic_entry_crossing(combined_track, hoop_x, hoop_y, hoop_w, scale_y=1.0):
    """Crossing at the first point when the window opens at the hoop and the ball is falling.

    Used when no above-hoop crossing was found. No tag time is consulted.
    """
    if not combined_track or len(combined_track) < 2:
        return None
    first_x = combined_track[0][1]
    first_y = combined_track[0][2]
    if first_y >= hoop_y - (10.0 * scale_y) and abs(first_x - hoop_x) <= 0.55 * hoop_w:
        if combined_track[1][2] > first_y:
            return 0
    return None


def _box_jump_px(pt1, pt2) -> float:
    """Same Euclidean jump measure the ball_box_jump check uses."""
    return ((pt2[1] - pt1[1]) ** 2 + (pt2[2] - pt1[2]) ** 2) ** 0.5


def decide_shot(
    track: Dict[str, Any],
    *,
    switch_a7: bool = False,
    switch_a8: bool = False,
    switch_a4: bool = False,
    switch_c4: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """Copy of run_saved_v6_rule's per-shot decision, with four default-OFF switches.

    No cutoff values change. Switches only change the four listed behaviours.
    """
    hoop = track["hoop"]
    hoop_x, hoop_y, hoop_w, hoop_area = hoop
    scale_x = track.get("_court_scale_x", 1.0)
    scale_y = track.get("_court_scale_y", 1.0)
    geo_mean_scale = math.sqrt(scale_x * scale_y)

    ball = track.get("ball", [])
    bodd = track.get("bodd", [])

    combined = list(ball)
    if bodd and ball:
        last_ball_frame = ball[-1][0]
        for pt in bodd:
            if pt[0] > last_ball_frame:
                combined.append(pt)
    elif not ball and bodd:
        combined = list(bodd)

    if len(combined) < 3:
        return False, {"reason": "short_combined_track"}

    cross_idx = None
    for i in range(len(combined) - 1):
        y1 = combined[i][2]
        if y1 < hoop_y:
            found_cross = False
            for j in range(i + 1, min(i + 9, len(combined))):
                y2 = combined[j][2]
                x2 = combined[j][1]
                if y2 >= hoop_y:
                    horiz_dist = abs(x2 - hoop_x)
                    if horiz_dist <= 0.55 * hoop_w:
                        cross_idx = j
                        found_cross = True
                        break
            if found_cross:
                break

    if cross_idx is None:
        cross_idx = detect_dynamic_entry_crossing(combined, hoop_x, hoop_y, hoop_w, scale_y)

    if cross_idx is None:
        return False, {"reason": "no_valid_crossing"}

    # C4 (1): LINE TEST index — ball frames at/after the accepted crossing frame
    if switch_c4:
        cross_frame = combined[cross_idx][0]
        post_cross_dense = [pt for pt in ball if pt[0] >= cross_frame]
    else:
        post_cross_dense = ball[cross_idx:] if cross_idx < len(ball) else []

    net_depth_frames = []
    for pt in post_cross_dense:
        y_rel = pt[2] - hoop_y
        if y_rel <= (180.0 * scale_y):
            net_depth_frames.append(pt)
        else:
            break

    # A7: bodd points count toward >=3 net-depth points (below rim, in 0.6 widths)
    if switch_a7 and len(net_depth_frames) < 3:
        cross_frame = combined[cross_idx][0]
        seen = {(pt[0], pt[1], pt[2]) for pt in net_depth_frames}
        extras = []
        for pt in bodd or []:
            if pt[0] < cross_frame:
                continue
            if not (pt[2] > hoop_y):
                continue
            y_rel = pt[2] - hoop_y
            if y_rel > (180.0 * scale_y):
                continue
            if abs(pt[1] - hoop_x) > 0.6 * hoop_w:
                continue
            key = (pt[0], pt[1], pt[2])
            if key in seen:
                continue
            seen.add(key)
            extras.append(pt)
        if extras:
            merged = list(net_depth_frames) + extras
            merged.sort(key=lambda p: p[0])
            net_depth_frames = merged

    if len(net_depth_frames) < 3:
        return False, {"reason": "short_net_depth"}

    first_y = net_depth_frames[0][2]
    last_y = net_depth_frames[-1][2]
    # A8: ignore an upward move only where the same frame pair is a box jump > 60 px
    if switch_a8:
        filtered = [net_depth_frames[0]]
        for i in range(1, len(net_depth_frames)):
            pt1 = net_depth_frames[i - 1]
            pt2 = net_depth_frames[i]
            jump = _box_jump_px(pt1, pt2)
            upward = pt2[2] < pt1[2]
            if upward and jump > (60.0 * geo_mean_scale):
                continue
            filtered.append(pt2)
        if not filtered:
            filtered = [net_depth_frames[0]]
        first_y = filtered[0][2]
        last_y = filtered[-1][2]

    if last_y <= first_y:
        return False, {"reason": "ball_went_up", "first_y": first_y, "last_y": last_y}

    in_column_count = 0
    total_in_zone = 0
    for pt in net_depth_frames:
        frame, x, y = pt
        y_rel = y - hoop_y
        if y_rel >= (80.0 * scale_y):
            total_in_zone += 1
            horiz_dist = abs(x - hoop_x)
            if horiz_dist <= 0.6 * hoop_w:
                in_column_count += 1

    column_ratio = in_column_count / total_in_zone if total_in_zone >= 3 else 1.0

    came_back = False
    deep_pts = [pt for pt in ball if pt[2] - hoop_y >= (80.0 * scale_y)]
    if hoop_w and len(deep_pts) >= 3:
        widths = [abs(pt[1] - hoop_x) / hoop_w for pt in deep_pts]
        widest = max(range(len(widths)), key=lambda k: widths[k])
        if widest < len(widths) - 1:
            later = min(widths[widest + 1 :])
            came_back = (widths[widest] - later) >= 0.40 and later <= 0.70
    if column_ratio < 0.5 and not came_back:
        return False, {"reason": "column_ratio_low", "column_ratio": round(column_ratio, 3)}

    # STEP 2: Ball box stays on ball
    # C4 (2): use the crossing the rule accepted (cross_idx), not a separate true crossing
    max_jump = 0
    if switch_c4:
        true_cross_frame = combined[cross_idx][0]
        ball_cross_idx = None
        for i, pt in enumerate(ball):
            if pt[0] == true_cross_frame:
                ball_cross_idx = i
                break
        if ball_cross_idx is not None:
            for i in range(ball_cross_idx + 1, len(ball)):
                pt1 = ball[i - 1]
                pt2 = ball[i]
                gap = max(1, pt2[0] - pt1[0])
                jump = _box_jump_px(pt1, pt2)
                upward = pt2[2] < pt1[2] - (20.0 * scale_y)
                through = (pt1[2] - hoop_y) >= (200.0 * scale_y) and abs(pt1[1] - hoop_x) <= 0.6 * hoop_w
                slow = jump / gap <= (12.0 * geo_mean_scale) and not upward
                if through or slow:
                    continue
                max_jump = max(max_jump, jump)
    else:
        true_cross_idx = None
        for i in range(len(combined) - 1):
            y1 = combined[i][2]
            y2 = combined[i + 1][2]
            if y1 < hoop_y and y2 >= hoop_y:
                true_cross_idx = i + 1
                break

        if true_cross_idx is not None:
            true_cross_frame = combined[true_cross_idx][0]
            ball_cross_idx = None
            for i, pt in enumerate(ball):
                if pt[0] == true_cross_frame:
                    ball_cross_idx = i
                    break

            if ball_cross_idx is not None:
                for i in range(ball_cross_idx + 1, len(ball)):
                    pt1 = ball[i - 1]
                    pt2 = ball[i]
                    gap = max(1, pt2[0] - pt1[0])
                    jump = _box_jump_px(pt1, pt2)
                    upward = pt2[2] < pt1[2] - (20.0 * scale_y)
                    through = (pt1[2] - hoop_y) >= (200.0 * scale_y) and abs(pt1[1] - hoop_x) <= 0.6 * hoop_w
                    slow = jump / gap <= (12.0 * geo_mean_scale) and not upward
                    if through or slow:
                        continue
                    max_jump = max(max_jump, jump)

    if max_jump > (60.0 * geo_mean_scale):
        return False, {"reason": "ball_box_jump", "max_jump": round(max_jump, 1)}

    ball_starts_below = False
    first_ball_y = None
    if ball:
        first_ball_y = ball[0][2]
        if first_ball_y > hoop_y + (50.0 * scale_y):
            ball_starts_below = True

    fell_on = bool(ball) and (max(pt[2] for pt in ball) - ball[0][2]) >= (80.0 * scale_y)
    near_rim_start = (
        bool(ball)
        and abs(ball[0][1] - hoop_x) <= 0.55 * hoop_w
        and ball[0][2] <= hoop_y + (100.0 * scale_y)
    )
    if ball_starts_below and fell_on and near_rim_start:
        ball_starts_below = False
    if ball_starts_below:
        return False, {"reason": "ball_starts_well_below", "first_y": first_ball_y, "hoop_y": hoop_y}

    # else-branch of the original (ball_starts_below is False here)
    if ball_starts_below and bodd:
        first_ball_frame = ball[0][0] if ball else -1
        bodd_before_ball = [pt for pt in bodd if pt[0] < first_ball_frame]
        floor_frames = [pt for pt in bodd_before_ball if pt[2] - hoop_y > (180.0 * scale_y)]
        if floor_frames:
            return False, {"reason": "floor_to_hoop_putback", "floor_frames": len(floor_frames)}

    if bodd and ball and not ball_starts_below:
        first_ball_frame = ball[0][0] if ball else -1
        bodd_before_ball = [pt for pt in bodd if pt[0] < first_ball_frame]
        if bodd_before_ball:
            last_floor = bodd_before_ball[-1]
            first_ball = ball[0]
            dx = abs(first_ball[1] - last_floor[1])
            dy = abs(first_ball[2] - last_floor[2])
            spatial_gap = (dx ** 2 + dy ** 2) ** 0.5

            frames = [pt[0] for pt in bodd_before_ball]
            frames.sort()
            max_frame_gap = 0
            for i in range(1, len(frames)):
                gap = frames[i] - frames[i - 1]
                if gap > max_frame_gap:
                    max_frame_gap = gap

            if max_frame_gap <= 3 and spatial_gap > (100.0 * geo_mean_scale):
                return False, {
                    "reason": "tracker_swap_bodd_ball",
                    "spatial_gap": round(spatial_gap, 1),
                    "frame_gap": max_frame_gap,
                }

    if not ball_starts_below:
        x_at_80 = None
        x_at_180 = None
        for pt in post_cross_dense:
            frame, x, y = pt
            y_rel = y - hoop_y
            if x_at_80 is None and y_rel >= (80.0 * scale_y):
                x_at_80 = x
            if y_rel >= (180.0 * scale_y):
                x_at_180 = x
                break

        is_short_make = x_at_180 is None
        pred = True
        details: Dict[str, Any] = {
            "cross_idx": cross_idx,
            "x_at_80": round(x_at_80, 1) if x_at_80 else None,
            "x_at_180": round(x_at_180, 1) if x_at_180 else None,
            "column_ratio": round(in_column_count / total_in_zone, 3) if total_in_zone >= 3 else None,
            "max_jump": round(max_jump, 1),
            "is_short_make": is_short_make,
        }

        if x_at_80 is not None and x_at_180 is not None:
            # A4: drift from the crossing point's x instead of x_at_80
            if switch_a4:
                x_anchor = combined[cross_idx][1]
                dist_anchor = abs(x_anchor - hoop_x)
                dist_at_180 = abs(x_at_180 - hoop_x)
                sideways = (dist_at_180 - dist_anchor) / hoop_w
                details["x_anchor_cross"] = round(x_anchor, 1)
            else:
                dist_at_80 = abs(x_at_80 - hoop_x)
                dist_at_180 = abs(x_at_180 - hoop_x)
                sideways = (dist_at_180 - dist_at_80) / hoop_w
            details["sideways"] = round(sideways, 3)

            if sideways > 0.43:
                pred = False
                details["vetoed"] = True
                details["veto_reason"] = "sideways_drift"

            if dist_at_180 > 0.85 * hoop_w and not came_back:
                pred = False
                details["vetoed"] = True
                details["veto_reason"] = "x_at_180_outside_rim"

        if pred:
            max_depth_idx = None
            max_depth = -1
            for i, pt in enumerate(net_depth_frames):
                y_rel = pt[2] - hoop_y
                if y_rel > max_depth:
                    max_depth = y_rel
                    max_depth_idx = i

            if max_depth_idx is not None:
                for i in range(max_depth_idx + 1, len(net_depth_frames)):
                    y_rel = net_depth_frames[i][2] - hoop_y
                    if y_rel < max_depth - (5.0 * scale_y):
                        pred = False
                        details["vetoed"] = True
                        details["veto_reason"] = "ball_bounces_up"
                        break

        if pred and is_short_make:
            if not short_track_stays_in_net(
                net_depth_frames, bodd, ball, hoop_x, hoop_y, hoop_w, scale_y
            ):
                pred = False
                details["vetoed"] = True
                details["veto_reason"] = "short_track_left_net"
            else:
                last_ball_frame = ball[-1][0] if ball else -1
                bodd_after = [pt for pt in bodd if pt[0] > last_ball_frame]
                deep = [pt for pt in bodd_after if pt[2] - hoop_y > (180.0 * scale_y)]
                if len(deep) >= 2:
                    bodd_ratio = sum(
                        1 for pt in deep if abs(pt[1] - hoop_x) <= 0.6 * hoop_w
                    ) / len(deep)
                    if bodd_ratio >= 0.95:
                        pred = False
                        details["vetoed"] = True
                        details["veto_reason"] = "short_make_bodd_fail"
                        details["bodd_ratio"] = round(bodd_ratio, 3)

        return pred, details

    return False, {"reason": "ball_starts_well_below", "first_y": first_ball_y, "hoop_y": hoop_y}


def reason_of(details: Dict[str, Any]) -> Optional[str]:
    if not details:
        return None
    if details.get("veto_reason"):
        return details["veto_reason"]
    return details.get("reason")


def load_build_shots(results_path: Path) -> List[Dict[str, Any]]:
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    seen = set()
    shots: List[Dict[str, Any]] = []
    for row in rows:
        key = (row["film"], row["t"])
        if key in seen:
            continue
        seen.add(key)
        shots.append(row)

    makes = [s for s in shots if s.get("gt_make")]
    misses = [s for s in shots if not s.get("gt_make")]
    rule_right = [s for s in makes if s.get("rule_pred_make")]
    missed = [s for s in makes if not s.get("rule_pred_make")]
    if (
        len(shots) != EXPECTED_BUILD
        or len(makes) != EXPECTED_MAKES
        or len(rule_right) != EXPECTED_RULE_RIGHT
        or len(missed) != EXPECTED_MISSED_MAKES
        or len(misses) != EXPECTED_REAL_MISSES
    ):
        raise SystemExit(
            "ERROR: expected 140 = 47 makes (28 rule-right + 19 missed) + 93 misses; "
            f"got {len(shots)} unique, makes={len(makes)} rule_right={len(rule_right)} "
            f"missed={len(missed)} misses={len(misses)}"
        )
    return shots


def load_tracks_by_path(shots: List[Dict[str, Any]]) -> Dict[str, Dict[Any, Dict[str, Any]]]:
    """Map resolved tracks path string -> {t: track}."""
    cache: Dict[str, Dict[Any, Dict[str, Any]]] = {}
    for row in shots:
        resolved = resolve_tracks_path(row["tracks_path"])
        key = str(resolved)
        if key not in cache:
            if not resolved.exists():
                raise SystemExit(f"ERROR: tracks file not found: {row['tracks_path']} -> {resolved}")
            data = json.loads(resolved.read_text(encoding="utf-8"))
            cache[key] = {tr["t"]: tr for tr in data}
        if row["t"] not in cache[key]:
            raise SystemExit(f"ERROR: t={row['t']} film={row['film']} missing from {resolved}")
    return cache


def run_copy_on_shots(
    shots: List[Dict[str, Any]],
    tracks_cache: Dict[str, Dict[Any, Dict[str, Any]]],
    **switches: bool,
) -> List[Dict[str, Any]]:
    out = []
    for row in shots:
        resolved = str(resolve_tracks_path(row["tracks_path"]))
        track = tracks_cache[resolved][row["t"]]
        pred, details = decide_shot(track, **switches)
        out.append(
            {
                "film": row["film"],
                "t": row["t"],
                "gt_make": bool(row["gt_make"]),
                "pred": bool(pred),
                "reason": reason_of(details),
                "details": details,
            }
        )
    return out


def summarize(
    baseline: List[Dict[str, Any]],
    current: List[Dict[str, Any]],
    label: str,
) -> Dict[str, Any]:
    by_key = {(r["film"], r["t"]): r for r in current}
    base_by_key = {(r["film"], r["t"]): r for r in baseline}

    makes_right = 0
    missed_makes = 0
    misses_called_makes = 0
    recovered_t: List[Any] = []
    changed: List[Dict[str, Any]] = []

    for key, cur in by_key.items():
        gt = cur["gt_make"]
        pred = cur["pred"]
        if gt and pred:
            makes_right += 1
        elif gt and not pred:
            missed_makes += 1
        elif (not gt) and pred:
            misses_called_makes += 1

        base = base_by_key[key]
        if base["pred"] != cur["pred"] or base["reason"] != cur["reason"]:
            changed.append(
                {
                    "t": cur["t"],
                    "film": cur["film"],
                    "gt_make": gt,
                    "old_pred": base["pred"],
                    "old_reason": base["reason"],
                    "new_pred": cur["pred"],
                    "new_reason": cur["reason"],
                }
            )
        # recovered: was missed make under baseline (all-off / identity), now make
        if gt and (not base["pred"]) and cur["pred"]:
            recovered_t.append(cur["t"])

    summary = {
        "label": label,
        "makes_right": makes_right,
        "missed_makes": missed_makes,
        "misses_called_makes": misses_called_makes,
        "recovered_missed_make_t": sorted(recovered_t),
        "verdict_changes": changed,
        "hard_gate_ok": misses_called_makes == 0,
    }
    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    print(f"\n=== {summary['label']} ===")
    print(f"makes right: {summary['makes_right']}")
    print(f"missed makes: {summary['missed_makes']}")
    print(f"misses called makes: {summary['misses_called_makes']}")
    print(f"missed makes recovered (t): {summary['recovered_missed_make_t']}")
    print(f"hard gate (0 misses called makes): {'PASS' if summary['hard_gate_ok'] else 'FAIL'}")
    print(f"verdict changes ({len(summary['verdict_changes'])}):")
    if not summary["verdict_changes"]:
        print("  (none)")
    else:
        for ch in summary["verdict_changes"]:
            old = "make" if ch["old_pred"] else "miss"
            new = "make" if ch["new_pred"] else "miss"
            print(
                f"  t={ch['t']} film={ch['film']} "
                f"{old}/{ch['old_reason']} -> {new}/{ch['new_reason']}"
            )


def identity_check(
    shots: List[Dict[str, Any]],
    tracks_cache: Dict[str, Dict[Any, Dict[str, Any]]],
    copy_baseline: List[Dict[str, Any]],
) -> None:
    """BINDING NOTE b: every switch off must match run_saved_v6_rule verdict+reason on all 140."""
    # Group shots by resolved tracks file
    by_path: Dict[str, List[Dict[str, Any]]] = {}
    for row in shots:
        key = str(resolve_tracks_path(row["tracks_path"]))
        by_path.setdefault(key, []).append(row)

    orig_by_key: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for path_str, group in by_path.items():
        timestamps = [r["t"] for r in group]
        # Suppress the original's SCORE prints from mixing mid-check? Keep them; report verbatim.
        result = run_saved_v6_rule(timestamps, path_str)
        film = group[0]["film"]
        for r in result["results"]:
            # Match film for this tracks file (one film per tracks file here)
            orig_by_key[(film, r["tag_ts"])] = r

    diffs = []
    for row, copy_row in zip(shots, copy_baseline):
        key = (row["film"], row["t"])
        if key not in orig_by_key:
            # try any film with that t from orig (Adrian/Notus are separate files)
            found = None
            for (f, t), r in orig_by_key.items():
                if t == row["t"] and f == row["film"]:
                    found = r
                    break
            if found is None:
                diffs.append(f"t={row['t']} film={row['film']}: missing from run_saved_v6_rule results")
                continue
            orig = found
        else:
            orig = orig_by_key[key]
        orig_pred = bool(orig["pred"])
        orig_reason = reason_of(orig.get("details") or {})
        copy_pred = bool(copy_row["pred"])
        copy_reason = copy_row["reason"]
        if orig_pred != copy_pred or orig_reason != copy_reason:
            diffs.append(
                f"t={row['t']} film={row['film']}: "
                f"orig={orig_pred}/{orig_reason} copy={copy_pred}/{copy_reason}"
            )

    if diffs:
        print(f"IDENTITY: FAILED ({len(diffs)} differ)")
        for line in diffs:
            print(f"  {line}")
        raise SystemExit(1)
    print("IDENTITY: 140/140 same")


def write_outputs(out_dir: Path, payload: Dict[str, Any], summaries: List[Dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "build_results.json"
    md_path = out_dir / "per_fix_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Stage A — small fixes per-fix report",
        "",
        "Plan: `.team/specs/18_makes_misses_work_plan.md` (VETTED). Switches default OFF; no cutoff changes.",
        "",
        f"Identity: {payload['identity']}",
        "",
        f"Build set: {EXPECTED_BUILD} = {EXPECTED_MAKES} makes "
        f"({EXPECTED_RULE_RIGHT} rule-right + {EXPECTED_MISSED_MAKES} missed) + {EXPECTED_REAL_MISSES} misses.",
        "",
        "Hard gate: 0 misses called makes. Numbers are measured once; nothing was tuned to them.",
        "",
    ]
    for s in summaries:
        lines.append(f"## {s['label']}")
        lines.append("")
        lines.append(f"- makes right: {s['makes_right']}")
        lines.append(f"- missed makes: {s['missed_makes']}")
        lines.append(f"- misses called makes: {s['misses_called_makes']}")
        lines.append(f"- hard gate: {'PASS' if s['hard_gate_ok'] else 'FAIL'}")
        lines.append(f"- missed makes recovered (t): {s['recovered_missed_make_t']}")
        lines.append(f"- verdict changes: {len(s['verdict_changes'])}")
        lines.append("")
        if s["verdict_changes"]:
            lines.append("| t | film | old | new |")
            lines.append("| --- | --- | --- | --- |")
            for ch in s["verdict_changes"]:
                old = f"{'make' if ch['old_pred'] else 'miss'}/{ch['old_reason']}"
                new = f"{'make' if ch['new_pred'] else 'miss'}/{ch['new_reason']}"
                lines.append(f"| {ch['t']} | {ch['film']} | {old} | {new} |")
            lines.append("")
        else:
            lines.append("(no verdict changes)")
            lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage A small-fixes copy of run_saved_v6_rule")
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="net_moved_build_results.json (default: Liberty_Shot_Outputs)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: Liberty_Shot_Outputs/small_fixes)",
    )
    args = parser.parse_args(argv)

    results_path = args.results if args.results is not None else default_results_path()
    results_path = resolve_path(str(results_path))
    if not results_path.exists():
        raise SystemExit(f"ERROR: results file not found: {results_path}")

    out_dir = args.out if args.out is not None else default_out_dir()

    shots = load_build_shots(results_path)
    tracks_cache = load_tracks_by_path(shots)

    # Baseline: every switch OFF
    baseline = run_copy_on_shots(
        shots,
        tracks_cache,
        switch_a7=False,
        switch_a8=False,
        switch_a4=False,
        switch_c4=False,
    )

    print("Running IDENTITY CHECK (all switches OFF vs run_saved_v6_rule)...")
    identity_check(shots, tracks_cache, baseline)
    identity_line = "IDENTITY: 140/140 same"

    configs = [
        ("A7_alone", dict(switch_a7=True, switch_a8=False, switch_a4=False, switch_c4=False)),
        ("A8_alone", dict(switch_a7=False, switch_a8=True, switch_a4=False, switch_c4=False)),
        ("A4_alone", dict(switch_a7=False, switch_a8=False, switch_a4=True, switch_c4=False)),
        ("C4_alone", dict(switch_a7=False, switch_a8=False, switch_a4=False, switch_c4=True)),
        ("all_four", dict(switch_a7=True, switch_a8=True, switch_a4=True, switch_c4=True)),
    ]

    # Also report baseline counts vs gt
    base_summary = summarize(baseline, baseline, "baseline_all_off")
    # recovered vs itself is empty; still print makes right etc.
    print_summary(base_summary)

    summaries = [base_summary]
    per_run_rows: Dict[str, List[Dict[str, Any]]] = {"baseline_all_off": baseline}

    for label, switches in configs:
        current = run_copy_on_shots(shots, tracks_cache, **switches)
        summary = summarize(baseline, current, label)
        print_summary(summary)
        summaries.append(summary)
        per_run_rows[label] = [
            {
                "film": r["film"],
                "t": r["t"],
                "gt_make": r["gt_make"],
                "pred": r["pred"],
                "reason": r["reason"],
            }
            for r in current
        ]

    payload = {
        "identity": identity_line,
        "results_path": str(results_path),
        "n_shots": len(shots),
        "expected": {
            "build": EXPECTED_BUILD,
            "makes": EXPECTED_MAKES,
            "rule_right": EXPECTED_RULE_RIGHT,
            "missed_makes": EXPECTED_MISSED_MAKES,
            "real_misses": EXPECTED_REAL_MISSES,
        },
        "summaries": summaries,
        "per_run": per_run_rows,
        "applied_to_core": False,
    }
    write_outputs(out_dir, payload, summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
