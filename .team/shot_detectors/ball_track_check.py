"""Ball track check on existing spec 33 tracks (spec 34, VETTED D1–D6).

Distributions only (D3) — no court/speed cutoffs. Reads collect_flight_tracks
moment JSON + shot_rules_measure results.json. Pure functions + CLI.

Imports hoop_at from shot_rules_measure (same-frame / earlier / later rule).
Does not edit shot_rules_measure, make/miss files, or any existing file.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from shot_rules_measure import combine_ball_track, hoop_at  # noqa: E402

FAILED_RULES = frozenset({"NOT_A_SHOT", "PASS", "ORANGE"})

DEFAULT_TRACK_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\shot_rules"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/shot_rules"),
]
DEFAULT_MEASURED_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\shot_rules_measured\results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/shot_rules_measured/results.json"),
]
DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_check"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/ball_check"),
]

VIDEO_BY_FILM = {
    "adrian": ROOT / "uploads" / "nfhs_gam0a66d85e12.mp4",
    "notus": ROOT / "uploads" / "LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
}

# Marker half-size when drawing center-only ball points (tracks store cx,cy,conf).
BALL_MARKER_HALF_PX = 22


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is not None and Path(cand).exists():
            return Path(cand)
    return None


def filter_out_q4(moments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adrian Q4 is never read (C5 / user D4)."""
    return [m for m in moments if str(m.get("quarter") or "") != "Q4"]


def ms_to_frame(t_ms: int, fps: float) -> int:
    return int(round(float(t_ms) / 1000.0 * float(fps)))


def frame_to_ms(frame: int, fps: float) -> int:
    return int(round(1000.0 * float(frame) / float(fps)))


def pct90(values: Sequence[float]) -> Optional[float]:
    """Nearest-rank 90th percentile (ceil(0.9 * n), 1-indexed)."""
    if not values:
        return None
    s = sorted(float(v) for v in values)
    k = max(1, int(math.ceil(0.9 * len(s))))
    return s[k - 1]


def summarize_values(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "median": None, "p90": None, "max": None}
    nums = [float(v) for v in values]
    return {
        "n": len(nums),
        "median": statistics.median(nums),
        "p90": pct90(nums),
        "max": max(nums),
    }


def hoop_for_frame(
    hoop_samples: Sequence[Dict[str, Any]],
    frame: int,
    fps: float,
) -> Optional[Dict[str, Any]]:
    """Wrapper: hoop_at on frame→ms (same rule as shot_rules_measure)."""
    return hoop_at(hoop_samples, frame_to_ms(int(frame), float(fps)))


# ---------------------------------------------------------------------------
# Per-point / per-track metrics (hoop widths)
# ---------------------------------------------------------------------------


def height_above_hoop_w(y: float, hoop: Dict[str, Any]) -> float:
    """(hoop_y - y) / hoop_w — positive when ball is above the hoop."""
    return (float(hoop["y"]) - float(y)) / float(hoop["w"])


def dist_from_hoop_w(x: float, y: float, hoop: Dict[str, Any]) -> float:
    return math.hypot(float(x) - float(hoop["x"]), float(y) - float(hoop["y"])) / float(
        hoop["w"]
    )


def point_metrics(
    frame: int,
    x: float,
    y: float,
    hoop_samples: Sequence[Dict[str, Any]],
    fps: float,
) -> Optional[Dict[str, float]]:
    hoop = hoop_for_frame(hoop_samples, int(frame), float(fps))
    if hoop is None or float(hoop.get("w") or 0) <= 0:
        return None
    return {
        "height_above_hoop_w": height_above_hoop_w(y, hoop),
        "dist_from_hoop_w": dist_from_hoop_w(x, y, hoop),
        "hoop_w": float(hoop["w"]),
        "hoop_x": float(hoop["x"]),
        "hoop_y": float(hoop["y"]),
    }


def track_height_and_distance(
    track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    fps: float,
) -> Dict[str, List[float]]:
    heights: List[float] = []
    dists: List[float] = []
    for pt in track:
        m = point_metrics(int(pt[0]), float(pt[1]), float(pt[2]), hoop_samples, fps)
        if m is None:
            continue
        heights.append(m["height_above_hoop_w"])
        dists.append(m["dist_from_hoop_w"])
    return {"height_above_hoop_w": heights, "dist_from_hoop_w": dists}


def track_jumps(
    track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    fps: float,
) -> List[Dict[str, Any]]:
    """Consecutive detected frames only. Raw jump / hoop_w; frame_gap separate.

    Does NOT divide jump by frame gap (D3).
    """
    out: List[Dict[str, Any]] = []
    if len(track) < 2:
        return out
    for i in range(len(track) - 1):
        f0 = int(track[i][0])
        f1 = int(track[i + 1][0])
        x0, y0 = float(track[i][1]), float(track[i][2])
        x1, y1 = float(track[i + 1][1]), float(track[i + 1][2])
        frame_gap = f1 - f0
        # Hoop at the later detection (same-frame rule on that frame).
        hoop = hoop_for_frame(hoop_samples, f1, fps)
        if hoop is None or float(hoop.get("w") or 0) <= 0:
            continue
        jump_px = math.hypot(x1 - x0, y1 - y0)
        out.append(
            {
                "from_frame": f0,
                "to_frame": f1,
                "frame_gap": frame_gap,
                "jump_px": jump_px,
                "jump_hoop_w": jump_px / float(hoop["w"]),
                "hoop_w": float(hoop["w"]),
            }
        )
    return out


def missing_in_window(
    track: Sequence[Sequence[float]],
    window_ms: Dict[str, Any],
    fps: float,
) -> Dict[str, Any]:
    """missing_frames / window_frames and longest consecutive missing run."""
    lo_f = ms_to_frame(int(window_ms["lo"]), fps)
    hi_f = ms_to_frame(int(window_ms["hi"]), fps)
    if hi_f < lo_f:
        return {
            "window_frames": 0,
            "detected_frames": 0,
            "missing_frames": 0,
            "missing_ratio": None,
            "longest_missing_run": 0,
        }
    window_frames = hi_f - lo_f + 1
    detected = {int(pt[0]) for pt in track if lo_f <= int(pt[0]) <= hi_f}
    missing_frames = window_frames - len(detected)
    longest = 0
    run = 0
    for f in range(lo_f, hi_f + 1):
        if f not in detected:
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return {
        "window_frames": window_frames,
        "detected_frames": len(detected),
        "missing_frames": missing_frames,
        "missing_ratio": (missing_frames / window_frames) if window_frames else None,
        "longest_missing_run": longest,
    }


def source_check(
    track: Sequence[Sequence[float]],
    hoop_samples: Sequence[Dict[str, Any]],
    window_ms: Dict[str, Any],
    fps: float,
) -> Dict[str, Any]:
    """Distributions + missing for one source track (v6 or BODD)."""
    hd = track_height_and_distance(track, hoop_samples, fps)
    jumps = track_jumps(track, hoop_samples, fps)
    jump_hw = [j["jump_hoop_w"] for j in jumps]
    frame_gaps = [j["frame_gap"] for j in jumps]
    missing = missing_in_window(track, window_ms, fps)
    return {
        "height_above_hoop_w": summarize_values(hd["height_above_hoop_w"]),
        "dist_from_hoop_w": summarize_values(hd["dist_from_hoop_w"]),
        "jump_hoop_w": summarize_values(jump_hw),
        "jump_frame_gap": summarize_values(frame_gaps),
        "jumps": jumps,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Failure frame / source
# ---------------------------------------------------------------------------


def ball_source_at_frame(
    ball_v6: Sequence[Sequence[float]],
    ball_bodd: Sequence[Sequence[float]],
    frame: int,
) -> Tuple[Optional[str], Optional[List[float]]]:
    """v6-first (same rule as combine_ball_track), else BODD, else None."""
    f = int(frame)
    for pt in ball_v6:
        if int(pt[0]) == f:
            return "v6", [float(v) for v in pt]
    for pt in ball_bodd:
        if int(pt[0]) == f:
            return "bodd", [float(v) for v in pt]
    return None, None


def resolve_failure_frame(
    measured: Dict[str, Any],
    combined_track: Sequence[Sequence[float]],
) -> Tuple[Optional[int], Optional[str]]:
    """Frame that set the failure, and which results.json field was used.

    Priority from recorded landing / coverage fields:
    - descent_not_seen → landing.peak_idx (frame via combined track), else
      landing.frame (find_landing stores the peak there when descent not seen)
    - never rose → landing.frame
    - else → landing.frame (distance / gap / PASS decisions)
    """
    landing = measured.get("landing") or {}
    reason = measured.get("reason") or ""
    cov = measured.get("coverage") or {}

    if landing.get("descent_not_seen") or "descent not seen" in reason:
        peak_idx = landing.get("peak_idx")
        if peak_idx is not None and combined_track:
            i = int(peak_idx)
            if 0 <= i < len(combined_track):
                return int(combined_track[i][0]), "landing.peak_idx"
        if landing.get("frame") is not None:
            return int(landing["frame"]), "landing.frame"
        return None, None

    if landing.get("rose_above_rim") is False or "never rose" in reason:
        if landing.get("frame") is not None:
            return int(landing["frame"]), "landing.frame"
        return None, None

    if landing.get("frame") is not None:
        return int(landing["frame"]), "landing.frame"
    if cov.get("landing_frame") is not None:
        return int(cov["landing_frame"]), "coverage.landing_frame"
    if cov.get("release_frame_estimate") is not None:
        return int(cov["release_frame_estimate"]), "coverage.release_frame_estimate"
    return None, None


def failure_moment_row(
    moment: Dict[str, Any],
    measured: Dict[str, Any],
    fps: float,
) -> Dict[str, Any]:
    """One failed tagged moment: metrics at failure frame + source + reason."""
    v6 = moment.get("ball_track") or []
    bodd = moment.get("bodd_track") or []
    hoops = moment.get("hoop_samples") or []
    combined = combine_ball_track(v6, bodd)
    frame, field = resolve_failure_frame(measured, combined)
    source, pt = (None, None)
    metrics = None
    if frame is not None:
        source, pt = ball_source_at_frame(v6, bodd, frame)
        if pt is not None:
            metrics = point_metrics(frame, float(pt[1]), float(pt[2]), hoops, fps)
    return {
        "moment_id": moment.get("moment_id"),
        "film": moment.get("film") or measured.get("film"),
        "quarter": moment.get("quarter") or measured.get("quarter"),
        "kind": moment.get("kind") or measured.get("kind"),
        "rule": measured.get("rule"),
        "reason": measured.get("reason") or "",
        "failure_frame": frame,
        "failure_frame_field": field,
        "ball_source": source,
        "ball_xy": [float(pt[1]), float(pt[2])] if pt is not None else None,
        "height_above_hoop_w": None if metrics is None else metrics["height_above_hoop_w"],
        "dist_from_hoop_w": None if metrics is None else metrics["dist_from_hoop_w"],
        "hoop_w": None if metrics is None else metrics["hoop_w"],
    }


# ---------------------------------------------------------------------------
# Coverage bug (D5) — report only
# ---------------------------------------------------------------------------


def coverage_bug_fields(coverage: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """If coverage_ratio > 1, return the fields that cause it; else None."""
    if not coverage:
        return None
    ratio = coverage.get("coverage_ratio")
    if ratio is None or float(ratio) <= 1.0:
        return None
    return {
        "coverage_ratio": float(ratio),
        "frames_seen": coverage.get("frames_seen"),
        "frames_in_flight_estimate": coverage.get("frames_in_flight_estimate"),
        "frames_span": coverage.get("frames_span"),
        "release_frame": coverage.get("release_frame"),
        "release_frame_estimate": coverage.get("release_frame_estimate"),
        "landing_frame": coverage.get("landing_frame"),
        "longest_gap_frames": coverage.get("longest_gap_frames"),
        "note": (
            "ELSE branch in shot_rules_measure.flight_coverage (lines 830-839): "
            "gap_report without lo/hi uses all ball_track frames as frames_seen "
            "while frames_in_flight_estimate uses release_f..end_f."
        ),
    }


def coverage_bug_check(measured: Dict[str, Any]) -> bool:
    """True when coverage_ratio > 1."""
    return coverage_bug_fields(measured.get("coverage") or {}) is not None


# ---------------------------------------------------------------------------
# Hand-check selection (D4)
# ---------------------------------------------------------------------------


def even_select(items: Sequence[Any], n: int = 20) -> List[Any]:
    """Every k-th item in order, k = floor(len/n). Takes n items when len >= n."""
    if n <= 0:
        return []
    if len(items) <= n:
        return list(items)
    k = len(items) // n
    return [items[i * k] for i in range(n)]


def hand_check_select(
    failed_tagged: Sequence[Dict[str, Any]],
    n: int = 20,
) -> List[Dict[str, Any]]:
    """20 failed tagged moments, evenly in moment order (already Q4-filtered)."""
    ordered = list(failed_tagged)
    return even_select(ordered, n)


# ---------------------------------------------------------------------------
# Aggregate run
# ---------------------------------------------------------------------------


def _kind_bucket(kind: Optional[str]) -> str:
    if kind == "tag":
        return "tagged"
    if kind == "fake":
        return "fake"
    return str(kind or "unknown")


def check_moment(
    moment: Dict[str, Any],
    measured: Optional[Dict[str, Any]],
    fps: float,
) -> Dict[str, Any]:
    window = moment.get("window_ms") or {}
    hoops = moment.get("hoop_samples") or []
    v6 = moment.get("ball_track") or []
    bodd = moment.get("bodd_track") or []
    row: Dict[str, Any] = {
        "moment_id": moment.get("moment_id"),
        "film": moment.get("film"),
        "kind": moment.get("kind"),
        "quarter": moment.get("quarter"),
        "tag_t_ms": moment.get("tag_t_ms"),
        "v6": source_check(v6, hoops, window, fps),
        "bodd": source_check(bodd, hoops, window, fps),
    }
    # Drop per-jump lists from the saved v6/bodd blobs to keep results.json lean;
    # summaries stay. Full jump lists available via source_check for tests.
    row["v6"] = {k: v for k, v in row["v6"].items() if k != "jumps"}
    row["bodd"] = {k: v for k, v in row["bodd"].items() if k != "jumps"}

    if measured is not None:
        cov_bug = coverage_bug_fields(measured.get("coverage") or {})
        row["coverage_bug"] = cov_bug
        row["rule"] = measured.get("rule")
        row["reason"] = measured.get("reason") or ""
        if (
            moment.get("kind") == "tag"
            and measured.get("rule") in FAILED_RULES
        ):
            row["failure"] = failure_moment_row(moment, measured, fps)
    return row


def pool_raw_distributions(
    moments: Sequence[Dict[str, Any]],
    fps_by_film: Dict[str, float],
    source_field: str,
) -> Dict[str, Any]:
    """True pooled n/median/p90/max over all detection points, per film×kind."""
    pools: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
    missing_pool: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for moment in moments:
        film = str(moment.get("film") or "?")
        bucket = _kind_bucket(moment.get("kind"))
        fps = float(fps_by_film.get(film) or moment.get("fps") or 25.0)
        track = moment.get(source_field) or []
        hoops = moment.get("hoop_samples") or []
        window = moment.get("window_ms") or {}
        hd = track_height_and_distance(track, hoops, fps)
        jumps = track_jumps(track, hoops, fps)
        miss = missing_in_window(track, window, fps)

        slot = pools.setdefault(film, {}).setdefault(
            bucket,
            {
                "height_above_hoop_w": [],
                "dist_from_hoop_w": [],
                "jump_hoop_w": [],
                "jump_frame_gap": [],
            },
        )
        slot["height_above_hoop_w"].extend(hd["height_above_hoop_w"])
        slot["dist_from_hoop_w"].extend(hd["dist_from_hoop_w"])
        slot["jump_hoop_w"].extend(j["jump_hoop_w"] for j in jumps)
        slot["jump_frame_gap"].extend(j["frame_gap"] for j in jumps)
        missing_pool.setdefault(film, {}).setdefault(bucket, []).append(miss)

    out: Dict[str, Any] = {}
    for film, buckets in sorted(pools.items()):
        out[film] = {}
        for bucket, slot in sorted(buckets.items()):
            miss_rows = missing_pool.get(film, {}).get(bucket, [])
            out[film][bucket] = {
                "n_moments": len(miss_rows),
                "height_above_hoop_w": summarize_values(slot["height_above_hoop_w"]),
                "dist_from_hoop_w": summarize_values(slot["dist_from_hoop_w"]),
                "jump_hoop_w": summarize_values(slot["jump_hoop_w"]),
                "jump_frame_gap": summarize_values(slot["jump_frame_gap"]),
                "missing_ratio": summarize_values(
                    [m["missing_ratio"] for m in miss_rows if m.get("missing_ratio") is not None]
                ),
                "longest_missing_run": summarize_values(
                    [m["longest_missing_run"] for m in miss_rows]
                ),
            }
    return out


def run_check(
    film_jsons: Sequence[Dict[str, Any]],
    measured_results: Dict[str, Any],
) -> Dict[str, Any]:
    measured_by_id = {
        m["moment_id"]: m for m in (measured_results.get("moments") or [])
    }
    fps_by_film: Dict[str, float] = {}
    all_moments: List[Dict[str, Any]] = []
    for film in film_jsons:
        film_name = film.get("film") or film.get("name")
        fps = float(film["fps"])
        if film_name:
            fps_by_film[str(film_name)] = fps
        for raw in filter_out_q4(film.get("moments") or []):
            m = dict(raw)
            m.setdefault("film", film_name)
            m.setdefault("fps", fps)
            all_moments.append(m)

    moment_rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    coverage_bugs: List[Dict[str, Any]] = []

    for moment in all_moments:
        mid = moment.get("moment_id")
        measured = measured_by_id.get(mid)
        fps = float(fps_by_film.get(str(moment.get("film")), moment.get("fps") or 25.0))
        row = check_moment(moment, measured, fps)
        moment_rows.append(row)
        if row.get("failure"):
            failures.append(row["failure"])
        if row.get("coverage_bug"):
            coverage_bugs.append(
                {
                    "moment_id": mid,
                    "film": moment.get("film"),
                    "kind": moment.get("kind"),
                    **row["coverage_bug"],
                }
            )

    # Preserve moment order as loaded (adrian then notus, within-file order).
    hand_selected = hand_check_select(failures, 20)

    return {
        "applied_to_core": False,
        "spec": "34_ball_track_check",
        "d3": "distributions only — no court/speed cutoffs",
        "n_moments": len(moment_rows),
        "n_failed_tagged": len(failures),
        "distributions": {
            "v6": pool_raw_distributions(all_moments, fps_by_film, "ball_track"),
            "bodd": pool_raw_distributions(all_moments, fps_by_film, "bodd_track"),
        },
        "failed_tagged": failures,
        "coverage_bugs": coverage_bugs,
        "hand_check_selection": hand_selected,
        "moments": moment_rows,
    }


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------


def _fmt(v: Any, digits: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, int):
        return str(v)
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def write_summary_md(results: Dict[str, Any], path: Path) -> None:
    lines: List[str] = []
    lines.append("# Ball track check (spec 34 / D3 distributions)")
    lines.append("")
    lines.append(
        "No cutoffs. Height = (hoop_y − y)/hoop_w; distance = |ball−hoop|/hoop_w; "
        "jump = consecutive-detection distance/hoop_w (frame_gap reported separately, "
        "not used as a divisor). Hoop via shot_rules_measure.hoop_at."
    )
    lines.append("")
    lines.append(
        f"Moments (Q4 filtered): {results['n_moments']}. "
        f"Failed tagged (NOT_A_SHOT/PASS/ORANGE): {results['n_failed_tagged']}."
    )
    lines.append("")

    for source_label, source_key in (("v6 crop (ball_track)", "v6"), ("BODD full (bodd_track)", "bodd")):
        lines.append(f"## {source_label} — pooled distributions")
        lines.append("")
        dist = results["distributions"][source_key]
        lines.append(
            "| Film | Kind | n_mom | height n/med/p90/max | "
            "dist n/med/p90/max | jump_hw n/med/p90/max | "
            "frame_gap med/p90/max | missing_ratio med/max | longest_miss med/max |"
        )
        lines.append("|---|---|---:|---|---|---|---|---|---|")
        for film, buckets in dist.items():
            for bucket, s in buckets.items():
                h, d, j, g = (
                    s["height_above_hoop_w"],
                    s["dist_from_hoop_w"],
                    s["jump_hoop_w"],
                    s["jump_frame_gap"],
                )
                mr, lr = s["missing_ratio"], s["longest_missing_run"]
                lines.append(
                    f"| {film} | {bucket} | {s['n_moments']} | "
                    f"{h['n']}/{_fmt(h['median'])}/{_fmt(h['p90'])}/{_fmt(h['max'])} | "
                    f"{d['n']}/{_fmt(d['median'])}/{_fmt(d['p90'])}/{_fmt(d['max'])} | "
                    f"{j['n']}/{_fmt(j['median'])}/{_fmt(j['p90'])}/{_fmt(j['max'])} | "
                    f"{_fmt(g['median'], 1)}/{_fmt(g['p90'], 1)}/{_fmt(g['max'], 1)} | "
                    f"{_fmt(mr['median'])}/{_fmt(mr['max'])} | "
                    f"{_fmt(lr['median'], 1)}/{_fmt(lr['max'], 1)} |"
                )
        lines.append("")

    lines.append("## Failed tagged moments")
    lines.append("")
    lines.append(
        "| moment_id | film | rule | reason | fail_frame | field_used | "
        "source | height_hw | dist_hw |"
    )
    lines.append("|---|---|---|---|---:|---|---|---:|---:|")
    for f in results["failed_tagged"]:
        lines.append(
            f"| {f.get('moment_id')} | {f.get('film')} | {f.get('rule')} | "
            f"{(f.get('reason') or '').replace('|', '/')} | {f.get('failure_frame')} | "
            f"{f.get('failure_frame_field')} | {f.get('ball_source')} | "
            f"{_fmt(f.get('height_above_hoop_w'))} | {_fmt(f.get('dist_from_hoop_w'))} |"
        )
    lines.append("")

    lines.append("## Coverage bug (D5, report only)")
    lines.append("")
    bugs = results.get("coverage_bugs") or []
    if not bugs:
        lines.append("None with coverage_ratio > 1.")
    else:
        lines.append(
            "| moment_id | film | coverage_ratio | frames_seen | "
            "frames_in_flight_estimate | release_frame_estimate |"
        )
        lines.append("|---|---|---:|---:|---:|---:|")
        for b in bugs:
            lines.append(
                f"| {b.get('moment_id')} | {b.get('film')} | "
                f"{_fmt(b.get('coverage_ratio'))} | {b.get('frames_seen')} | "
                f"{b.get('frames_in_flight_estimate')} | "
                f"{b.get('release_frame_estimate')} |"
            )
        lines.append("")
        lines.append(
            "Cause: shot_rules_measure.flight_coverage ELSE branch (lines 830–839) "
            "calls gap_report without lo/hi so frames_seen spans the whole track "
            "while frames_in_flight_estimate uses release_f..end_f."
        )
    lines.append("")

    lines.append("## Hand check selection (D4)")
    lines.append("")
    lines.append(
        "20 failed tagged moments, every k-th in moment order "
        f"(k = floor({results['n_failed_tagged']}/20)). "
        "Labels left blank for Claude Code. Images under hand_check/ when "
        "`--hand-check` is run."
    )
    lines.append("")
    lines.append("| # | moment_id | film | frame | source | label |")
    lines.append("|---:|---|---|---:|---|---|")
    for i, h in enumerate(results.get("hand_check_selection") or [], start=1):
        lines.append(
            f"| {i} | {h.get('moment_id')} | {h.get('film')} | "
            f"{h.get('failure_frame')} | {h.get('ball_source')} | |"
        )
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Hand-check image writer (CLI --hand-check only; uses cv2 + local video)
# ---------------------------------------------------------------------------


def _draw_center_box(img: Any, x: float, y: float, color: Tuple[int, int, int], half: int) -> None:
    import cv2

    x1, y1 = int(round(x - half)), int(round(y - half))
    x2, y2 = int(round(x + half)), int(round(y + half))
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)


def _draw_hoop(img: Any, hoop: Dict[str, Any], color: Tuple[int, int, int]) -> None:
    import cv2

    cx, cy = float(hoop["x"]), float(hoop["y"])
    hw, hh = float(hoop["w"]), float(hoop.get("h") or hoop["w"])
    x1, y1 = int(round(cx - hw / 2)), int(round(cy - hh / 2))
    x2, y2 = int(round(cx + hw / 2)), int(round(cy + hh / 2))
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)


def write_hand_check(
    selection: Sequence[Dict[str, Any]],
    moments_by_id: Dict[str, Dict[str, Any]],
    fps_by_film: Dict[str, float],
    out_dir: Path,
) -> Dict[str, Any]:
    """Write one full-frame JPEG per selected moment at the failure frame."""
    import cv2

    hand_dir = Path(out_dir) / "hand_check"
    hand_dir.mkdir(parents=True, exist_ok=True)
    entries: List[Dict[str, Any]] = []

    for item in selection:
        mid = item["moment_id"]
        film = str(item.get("film") or "")
        frame = item.get("failure_frame")
        moment = moments_by_id.get(mid)
        video_path = VIDEO_BY_FILM.get(film)
        entry: Dict[str, Any] = {
            "moment_id": mid,
            "film": film,
            "frame": frame,
            "video": str(video_path) if video_path else None,
            "source": item.get("ball_source"),
            "failure_frame_field": item.get("failure_frame_field"),
            "rule": item.get("rule"),
            "reason": item.get("reason") or "",
            "image": None,
            "label": None,  # Claude Code fills in
        }
        if moment is None or frame is None or video_path is None or not video_path.exists():
            entries.append(entry)
            continue

        fps = float(fps_by_film.get(film) or 25.0)
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame))
        ok, img = cap.read()
        cap.release()
        if not ok or img is None:
            entries.append(entry)
            continue

        v6 = moment.get("ball_track") or []
        bodd = moment.get("bodd_track") or []
        hoops = moment.get("hoop_samples") or []
        # BODD red, v6 green, hoop yellow (BGR).
        _, bodd_pt = ball_source_at_frame([], bodd, int(frame))
        _, v6_pt = ball_source_at_frame(v6, [], int(frame))
        if bodd_pt is not None:
            _draw_center_box(img, float(bodd_pt[1]), float(bodd_pt[2]), (0, 0, 255), BALL_MARKER_HALF_PX)
        if v6_pt is not None:
            _draw_center_box(img, float(v6_pt[1]), float(v6_pt[2]), (0, 255, 0), BALL_MARKER_HALF_PX)
        hoop = hoop_for_frame(hoops, int(frame), fps)
        if hoop is not None:
            _draw_hoop(img, hoop, (0, 255, 255))

        img_name = f"{mid}_f{int(frame)}.jpg"
        img_path = hand_dir / img_name
        cv2.imwrite(str(img_path), img)
        entry["image"] = str(img_path)
        entries.append(entry)

    meta = {
        "n": len(entries),
        "dir": str(hand_dir),
        "note": "label left null — Claude Code labels each frame",
        "frames": entries,
    }
    (Path(out_dir) / "hand_check.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return meta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_film_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ball track check (spec 34 / D3)")
    parser.add_argument(
        "--tracks-dir",
        type=Path,
        default=None,
        help="Directory with adrian.json and notus.json",
    )
    parser.add_argument(
        "--measured",
        type=Path,
        default=None,
        help="spec 33 results.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (refused if it already exists)",
    )
    parser.add_argument(
        "--hand-check",
        action="store_true",
        help="Also write hand_check/ JPEGs + hand_check.json into out-dir",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    tracks_dir = args.tracks_dir or pick_existing(*DEFAULT_TRACK_CANDIDATES)
    measured_path = args.measured or pick_existing(*DEFAULT_MEASURED_CANDIDATES)
    out_dir = args.out_dir or pick_existing(*DEFAULT_OUT_CANDIDATES)
    if out_dir is None:
        out_dir = DEFAULT_OUT_CANDIDATES[0]
    out_dir = Path(out_dir)

    if tracks_dir is None:
        print("ERROR: shot_rules tracks dir not found", file=sys.stderr)
        return 2
    if measured_path is None:
        print("ERROR: shot_rules_measured/results.json not found", file=sys.stderr)
        return 2
    if out_dir.exists():
        print(f"ERROR: out-dir already exists: {out_dir}", file=sys.stderr)
        return 2

    adrian = load_film_json(Path(tracks_dir) / "adrian.json")
    notus = load_film_json(Path(tracks_dir) / "notus.json")
    measured = json.loads(Path(measured_path).read_text(encoding="utf-8"))

    results = run_check([adrian, notus], measured)
    out_dir.mkdir(parents=True)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    write_summary_md(results, out_dir / "summary.md")
    print(f"Wrote {out_dir / 'results.json'}")
    print(f"Wrote {out_dir / 'summary.md'}")
    print(
        f"moments={results['n_moments']} failed_tagged={results['n_failed_tagged']} "
        f"coverage_bugs={len(results['coverage_bugs'])}"
    )

    if args.hand_check:
        moments_by_id: Dict[str, Dict[str, Any]] = {}
        fps_by_film: Dict[str, float] = {}
        for film in (adrian, notus):
            name = str(film.get("film") or "")
            fps_by_film[name] = float(film["fps"])
            for m in filter_out_q4(film.get("moments") or []):
                mm = dict(m)
                mm.setdefault("film", name)
                moments_by_id[mm["moment_id"]] = mm
        meta = write_hand_check(
            results["hand_check_selection"],
            moments_by_id,
            fps_by_film,
            out_dir,
        )
        print(f"Wrote hand_check n={meta['n']} -> {meta['dir']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
