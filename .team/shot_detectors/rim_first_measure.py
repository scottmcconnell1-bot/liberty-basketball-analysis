"""Measure rim-first moments against tags. This is the only script that reads tags.

Finder output + tags. No video, no model, no database, no fakes (E8).
Adrian Q4 tags are removed before matching.
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
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from collect_flight_tracks import filter_out_q4, load_shot_tags  # noqa: E402
from find_shots_measure import match_shot_indices, match_shots  # noqa: E402

# manual_tag_teach.py:18 MATCH_TOLERANCE_MS; find_shots_measure.py:27
MATCH_WINDOW_MS = 8000
# spec 36 K8, Scott approved 2026-11-05
EXTRA_MATCH_WINDOW_MS = 1500
# spec 38 S8, Scott approved 2026-11-06
FT_SPOT_PASS_WIDTHS = 1.5

KINDS = ("2PT", "3PT", "FT")
_TRUTH_COUNT_KEYS = ("correct", "wrong", "missed", "orange", "gone", "shot_on_unclear")


def refuse_existing_out_dir(out_dir: Path) -> None:
    path = Path(out_dir)
    if path.exists():
        raise SystemExit(f"Refuse: output directory already exists: {path}")


def _median(values: Sequence[int]) -> Optional[float]:
    if not values:
        return None
    med = statistics.median(values)
    if isinstance(med, float) and med.is_integer():
        return int(med)
    return med


def _kind_row(
    found: int,
    missed: int,
    extra: Optional[int],
    deltas: Sequence[int],
) -> Dict[str, Any]:
    return {
        "found": found,
        "missed": missed,
        "extra": extra,
        "median_abs_delta_ms": _median(deltas),
        "max_abs_delta_ms": max(deltas) if deltas else None,
    }


def shot_call_of(moment: Dict[str, Any]) -> str:
    """Missing shot_call, or null, counts as shot so old moments files still score."""
    if "shot_call" not in moment or moment.get("shot_call") is None:
        return "shot"
    return str(moment["shot_call"])


def shot_call_counts(moments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """How many moments carry each shot_call and each shot_reason."""
    by_call: Dict[str, int] = {"shot": 0, "orange": 0, "not_a_shot": 0}
    by_reason: Dict[str, int] = {}
    for moment in moments:
        call = shot_call_of(moment)
        by_call[call] = by_call.get(call, 0) + 1
        reason = moment.get("shot_reason")
        key = "none" if reason is None else str(reason)
        by_reason[key] = by_reason.get(key, 0) + 1
    return {"by_call": by_call, "by_reason": by_reason}


def truth_entries_for_run(truth: Any, run: str) -> List[Dict[str, Any]]:
    """Rows for this run, except label Q4_not_examined.

    A dict uses the extras list. A bare list is the rows themselves.
    """
    if isinstance(truth, dict):
        rows = truth.get("extras")
        if rows is None:
            raise ValueError("truth file has no extras list")
    elif isinstance(truth, list):
        rows = truth
    else:
        raise ValueError("truth file is not an object or list")
    kept: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("run") != run:
            continue
        if row.get("label") == "Q4_not_examined":
            continue
        kept.append(row)
    return kept


def _truth_group(label: str) -> str:
    return str(label).split("_", 1)[0]


def _blank_truth_counts() -> Dict[str, int]:
    return {key: 0 for key in _TRUTH_COUNT_KEYS}


def score_truth(
    candidates: Sequence[Dict[str, Any]],
    entries: Sequence[Dict[str, Any]],
    window_ms: int,
) -> Dict[str, Any]:
    """Verdicts for truth rows against moments that were not matched to a tag.

    A candidate can sit in more than one truth window. A shot candidate
    within window_ms of no truth row is a new_extra.

    E_putback: exactly one shot is correct, even if an orange candidate
    shares the window. Zero shots is orange when an orange candidate is
    there, otherwise missed. Two or more shots is wrong (double count).
    A/B/C/D/F/H: any shot is wrong; otherwise correct. When both an orange
    and a not_a_shot candidate are present, the detail says orange.
    G_unclear: any shot is shot_on_unclear (not counted wrong), even if an
    orange candidate is also there; else orange is correct; else gone.
    Any other label uses the A–H rule.
    """
    window = int(window_ms)
    rows: List[Dict[str, Any]] = []
    by_label: Dict[str, Any] = {}
    totals = _blank_truth_counts()
    for entry in entries:
        t_ms = int(entry["t_ms"])
        label = str(entry["label"])
        near = [
            moment
            for moment in candidates
            if abs(int(moment["t_ms"]) - t_ms) <= window
        ]
        shots = [moment for moment in near if shot_call_of(moment) == "shot"]
        oranges = [moment for moment in near if shot_call_of(moment) == "orange"]
        nots = [moment for moment in near if shot_call_of(moment) == "not_a_shot"]
        group = _truth_group(label)
        if group == "E":
            if len(shots) == 1:
                verdict, detail = "correct", "one shot"
            elif len(shots) >= 2:
                verdict, detail = "wrong", "double count"
            elif oranges:
                verdict, detail = "orange", "orange"
            else:
                verdict, detail = "missed", "no shot"
        elif group == "G":
            if shots:
                verdict, detail = "shot_on_unclear", "shot"
            elif oranges:
                verdict, detail = "correct", "orange"
            else:
                verdict, detail = "gone", ("not_a_shot" if nots else "none")
        elif shots:
            verdict, detail = "wrong", "shot"
        else:
            if oranges:
                detail = "orange"
            elif nots:
                detail = "not_a_shot"
            else:
                detail = "none"
            verdict = "correct"
        row = {
            "n": entry.get("n"),
            "t_ms": t_ms,
            "label": label,
            "verdict": verdict,
            "detail": detail,
            "n_shot": len(shots),
            "n_orange": len(oranges),
            "n_not_a_shot": len(nots),
        }
        rows.append(row)
        bucket = by_label.setdefault(
            label, {"n": 0, "rows": [], **_blank_truth_counts()}
        )
        bucket["n"] += 1
        bucket[verdict] += 1
        bucket["rows"].append(row)
        totals[verdict] += 1

    new_extras: List[Dict[str, Any]] = []
    for moment in candidates:
        if shot_call_of(moment) != "shot":
            continue
        t_ms = int(moment["t_ms"])
        if any(abs(t_ms - int(entry["t_ms"])) <= window for entry in entries):
            continue
        new_extras.append(
            {"t_ms": t_ms, "frame": moment.get("frame"), "shot_call": "shot"}
        )
    new_extras.sort(key=lambda row: (int(row["t_ms"]), row.get("frame") or 0))
    totals["new_extra"] = len(new_extras)
    return {
        "window_ms": window,
        "by_label": by_label,
        "rows": rows,
        "totals": totals,
        "new_extras": new_extras,
    }


def _none_key(value: Any) -> str:
    if value is None:
        return "none"
    return str(value)


def _count_map(values: Sequence[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        key = _none_key(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def floor_spot_hoop_widths(
    moment: Dict[str, Any],
) -> Optional[Tuple[float, float]]:
    """Floor spot relative to this moment's hoop, in hoop widths.

    ((fx - hx) / hw, (fy - hy) / hw). Picture pixels stay out of the report
    because the camera pans and zooms.
    """
    hoop = moment.get("hoop")
    spot = moment.get("floor_spot")
    if not isinstance(hoop, dict) or not isinstance(spot, dict):
        return None
    if "w" not in hoop or "x" not in hoop or "y" not in hoop:
        return None
    if spot.get("x") is None or spot.get("y") is None:
        return None
    hw = float(hoop["w"])
    if hw == 0.0:
        return None
    return (
        (float(spot["x"]) - float(hoop["x"])) / hw,
        (float(spot["y"]) - float(hoop["y"])) / hw,
    )


def _median_float(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def _distance_summary(values: Sequence[float]) -> Dict[str, Any]:
    """Median and quartiles. Quartiles need at least two distances."""
    vals = [float(v) for v in values]
    summary: Dict[str, Any] = {
        "n": len(vals),
        "median": _median_float(vals),
        "q1": None,
        "q3": None,
    }
    if len(vals) < 2:
        return summary
    try:
        q1, _q2, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    except TypeError:
        q1, _q2, q3 = statistics.quantiles(vals, n=4)
    summary["q1"] = float(q1)
    summary["q3"] = float(q3)
    return summary


def _release_to_trigger_s(moment: Dict[str, Any], fps: Optional[float]) -> Optional[float]:
    if fps is None or float(fps) == 0.0:
        return None
    if moment.get("release_frame") is None or moment.get("frame") is None:
        return None
    return (int(moment["frame"]) - int(moment["release_frame"])) / float(fps)


def _seconds_bucket(values: Sequence[float]) -> Dict[str, Any]:
    return {
        "n": len(values),
        "median_s": _median_float(values),
        "values_s": [float(v) for v in values],
    }


def _ft_spot_groups(
    pairs: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """FT floor spots with a spot, grouped by moment series.

    The group median is the median x and the median y in hoop widths.
    Pass when that FT's distance from the median is <= FT_SPOT_PASS_WIDTHS.
    """
    grouped: Dict[Any, List[Tuple[Dict[str, Any], Tuple[float, float]]]] = {}
    for pair in pairs:
        tag = pair["tag"]
        if tag.get("eventtype") != "FT":
            continue
        moment = pair["moment"]
        spot = floor_spot_hoop_widths(moment)
        if spot is None:
            continue
        grouped.setdefault(moment.get("series"), []).append((moment, spot))
    groups: List[Dict[str, Any]] = []
    for series in sorted(grouped, key=lambda key: (key is None, str(key))):
        items = grouped[series]
        med_x = float(statistics.median([spot[0] for _moment, spot in items]))
        med_y = float(statistics.median([spot[1] for _moment, spot in items]))
        rows: List[Dict[str, Any]] = []
        distances: List[float] = []
        passes = 0
        for moment, spot in items:
            dist = math.hypot(spot[0] - med_x, spot[1] - med_y)
            ok = dist <= FT_SPOT_PASS_WIDTHS
            if ok:
                passes += 1
            distances.append(dist)
            rows.append(
                {
                    "t_ms": int(moment["t_ms"]),
                    "distance_widths": dist,
                    "pass": ok,
                }
            )
        groups.append(
            {
                "series": series,
                "n": len(items),
                "pass_count": passes,
                "median_distance_widths": float(statistics.median(distances)),
                "median_spot_widths": {"x": med_x, "y": med_y},
                "pass_widths": FT_SPOT_PASS_WIDTHS,
                "rows": rows,
            }
        )
    return groups


def _shot_distance_by_kind(
    pairs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Report only. Distance of the floor spot from the moment hoop, in hoop widths."""
    by_kind: Dict[str, List[float]] = {"2PT": [], "3PT": []}
    for pair in pairs:
        kind = pair["tag"].get("eventtype")
        if kind not in by_kind:
            continue
        spot = floor_spot_hoop_widths(pair["moment"])
        if spot is None:
            continue
        by_kind[kind].append(math.hypot(spot[0], spot[1]))
    return {kind: _distance_summary(values) for kind, values in by_kind.items()}


def _review_rows(pairs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pair in pairs:
        tag = pair["tag"]
        moment = pair["moment"]
        spot = floor_spot_hoop_widths(moment)
        rows.append(
            {
                "t_ms": int(moment["t_ms"]),
                "eventtype": tag.get("eventtype"),
                "result": tag.get("result"),
                "player": tag.get("player"),
                "status": moment.get("status"),
                "reason": moment.get("reason"),
                "floor_spot_widths": (
                    None if spot is None else {"x": spot[0], "y": spot[1]}
                ),
            }
        )
    rows.sort(key=lambda row: (int(row["t_ms"]), str(row.get("eventtype") or "")))
    return rows


# Spec 42 M3: duplicate of a found FT within this window is not counted false.
FT_DUPLICATE_WINDOW_MS = 1000


def ft_section(
    moments: Sequence[Dict[str, Any]],
    pairs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Free-throw flags against the tags already matched to shot moments.

    FT tag and flag: found. FT tag and no flag: missed. Non-FT tag and flag:
    false, unless within FT_DUPLICATE_WINDOW_MS of a flagged FT-tag match
    (listed as duplicate_of_found_ft, not false). orange_ft_line_not_found
    counts every moment with that reason. too_far_from_hoop, no_lane_lines,
    release_not_shooter, and maybe_free_throw count ft_reason. flagged lists
    every moment with free_throw true, and the matched tag's eventtype when
    this moment is one of the pairs. maybe lists every maybe_free_throw
    moment with its tag eventtype. non_ft_flagged lists every non-FT-tag
    moment flagged free_throw with t_ms that is not a duplicate_of_found_ft
    (spec 41 L8 / spec 42 M3).
    """
    tag_by_moment = {id(pair["moment"]): pair["tag"] for pair in pairs}
    found_ft_times: List[int] = []
    for pair in pairs:
        is_ft = pair["tag"].get("eventtype") == "FT"
        flag = bool(pair["moment"].get("free_throw"))
        if is_ft and flag:
            found_ft_times.append(int(pair["moment"]["t_ms"]))

    def _is_duplicate_of_found_ft(t_ms: int) -> bool:
        return any(
            abs(int(t_ms) - found_t) <= FT_DUPLICATE_WINDOW_MS
            for found_t in found_ft_times
        )

    found = 0
    missed = 0
    false_flags = 0
    for pair in pairs:
        is_ft = pair["tag"].get("eventtype") == "FT"
        flag = bool(pair["moment"].get("free_throw"))
        if is_ft and flag:
            found += 1
        elif is_ft and not flag:
            missed += 1
        elif flag and not is_ft:
            if not _is_duplicate_of_found_ft(int(pair["moment"]["t_ms"])):
                false_flags += 1
    orange = sum(
        1 for moment in moments if moment.get("reason") == "ft_line_not_found"
    )
    too_far = sum(
        1
        for moment in moments
        if moment.get("ft_reason") == "too_far_from_hoop"
    )
    no_lane = sum(
        1
        for moment in moments
        if moment.get("ft_reason") == "no_lane_lines"
    )
    release_not = sum(
        1
        for moment in moments
        if moment.get("ft_reason") == "release_not_shooter"
    )
    maybe_count = sum(
        1
        for moment in moments
        if moment.get("ft_reason") == "maybe_free_throw"
    )
    flagged: List[Dict[str, Any]] = []
    for moment in moments:
        if not moment.get("free_throw"):
            continue
        tag = tag_by_moment.get(id(moment))
        flagged.append(
            {
                "t_ms": int(moment["t_ms"]),
                "eventtype": None if tag is None else tag.get("eventtype"),
            }
        )
    flagged.sort(key=lambda row: (int(row["t_ms"]), str(row.get("eventtype") or "")))
    maybe: List[Dict[str, Any]] = []
    for moment in moments:
        if moment.get("ft_reason") != "maybe_free_throw":
            continue
        tag = tag_by_moment.get(id(moment))
        maybe.append(
            {
                "t_ms": int(moment["t_ms"]),
                "eventtype": None if tag is None else tag.get("eventtype"),
            }
        )
    maybe.sort(key=lambda row: (int(row["t_ms"]), str(row.get("eventtype") or "")))
    duplicate_of_found_ft: List[Dict[str, Any]] = []
    non_ft_flagged: List[Dict[str, Any]] = []
    for row in flagged:
        if row.get("eventtype") == "FT":
            continue
        if _is_duplicate_of_found_ft(int(row["t_ms"])):
            duplicate_of_found_ft.append({"t_ms": int(row["t_ms"])})
        else:
            non_ft_flagged.append({"t_ms": int(row["t_ms"])})
    return {
        "found": found,
        "missed": missed,
        "false": false_flags,
        "orange_ft_line_not_found": orange,
        "too_far_from_hoop": too_far,
        "no_lane_lines": no_lane,
        "release_not_shooter": release_not,
        "maybe_free_throw": maybe_count,
        "flagged": flagged,
        "maybe": maybe,
        "non_ft_flagged": non_ft_flagged,
        "duplicate_of_found_ft": duplicate_of_found_ft,
    }


def shooter_section(
    moments: Sequence[Dict[str, Any]],
    pairs: Sequence[Dict[str, Any]],
    fps: Optional[float],
) -> Dict[str, Any]:
    """Shooter counts, FT spot, 3PT vs 2PT distance, and the review list.

    pairs are the existing tag matches (shot moments inside the match window).
    """
    found_series = [
        moment.get("series") for moment in moments if moment.get("status") == "found"
    ]
    release_values: Dict[str, List[float]] = {"found": [], "orange": []}
    for pair in pairs:
        moment = pair["moment"]
        status = moment.get("status")
        if status not in release_values:
            continue
        seconds = _release_to_trigger_s(moment, fps)
        if seconds is None:
            continue
        release_values[status].append(seconds)
    return {
        "by_status": _count_map([moment.get("status") for moment in moments]),
        "by_reason": _count_map([moment.get("reason") for moment in moments]),
        "found_by_series": _count_map(found_series),
        "release_to_trigger_s": {
            "found": _seconds_bucket(release_values["found"]),
            "orange": _seconds_bucket(release_values["orange"]),
        },
        "ft_spot": _ft_spot_groups(pairs),
        "shot_distance_widths": _shot_distance_by_kind(pairs),
        "review": _review_rows(pairs),
    }


def build_report(
    moments: Sequence[Dict[str, Any]],
    tags: Sequence[Dict[str, Any]],
    window_ms: int,
    truth: Any = None,
    truth_run: Optional[str] = None,
    extra_window_ms: int = EXTRA_MATCH_WINDOW_MS,
    fps: Optional[float] = None,
) -> Dict[str, Any]:
    """Q4 tags out first, then match_shots against shot_call shot moments only.

    Moments with no shot_call field count as shot. found/missed/extra stay
    the shot-only match. hidden lists tags that miss that match but hit some
    moment. truth is set only when a truth document is passed.
    """
    tags_in = list(tags)
    kept = filter_out_q4(tags_in)
    moments_in = list(moments)
    tag_times = [int(tag["t"]) for tag in kept]
    shot_indexes = [
        i for i, moment in enumerate(moments_in) if shot_call_of(moment) == "shot"
    ]
    shot_moments = [moments_in[i] for i in shot_indexes]
    finder_times = [int(moment["t_ms"]) for moment in shot_moments]
    timed = match_shots(tag_times, finder_times, int(window_ms))
    indexed = match_shot_indices(tag_times, finder_times, int(window_ms))

    matches: List[Dict[str, Any]] = []
    matched_pairs: List[Dict[str, Any]] = []
    for ti, fi, delta in indexed["matches"]:
        tag = kept[ti]
        moment = shot_moments[fi]
        matched_pairs.append({"tag": tag, "moment": moment})
        matches.append(
            {
                "tag_t_ms": int(tag["t"]),
                "moment_t_ms": int(moment["t_ms"]),
                "delta_ms": int(delta),
                "eventtype": tag.get("eventtype"),
                "result": tag.get("result"),
                "start": tag.get("start"),
                "player": tag.get("player"),
                "quarter": tag.get("quarter"),
            }
        )
    got = sorted(
        (row["tag_t_ms"], row["moment_t_ms"], row["delta_ms"]) for row in matches
    )
    exp = sorted((int(a), int(b), int(c)) for a, b, c in timed["matches"])
    if got != exp:
        raise RuntimeError("match_shots disagreed with match_shot_indices")
    if len(timed["unmatched_tags"]) != len(indexed["unmatched_tags"]):
        raise RuntimeError("match_shots unmatched tags disagreed")
    if len(timed["unmatched_finder"]) != len(indexed["unmatched_finder"]):
        raise RuntimeError("match_shots unmatched moments disagreed")

    missed_tags = [kept[i] for i in indexed["unmatched_tags"]]
    extra_moments = [shot_moments[i] for i in indexed["unmatched_finder"]]
    misses = [
        {
            "t_ms": int(tag["t"]),
            "start": tag.get("start"),
            "eventtype": tag.get("eventtype"),
            "result": tag.get("result"),
            "player": tag.get("player"),
            "quarter": tag.get("quarter"),
        }
        for tag in missed_tags
    ]
    extras = [
        {
            "t_ms": int(moment["t_ms"]),
            "kind_hint": moment.get("kind_hint"),
            "frame": moment.get("frame"),
            "status": moment.get("status"),
            "shot_call": shot_call_of(moment),
            "shot_reason": moment.get("shot_reason"),
        }
        for moment in extra_moments
    ]
    misses.sort(key=lambda row: int(row["t_ms"]))
    extras.sort(key=lambda row: int(row["t_ms"]))

    by_kind: Dict[str, Any] = {}
    for kind in KINDS:
        kind_matches = [row for row in matches if row["eventtype"] == kind]
        kind_misses = [row for row in misses if row["eventtype"] == kind]
        deltas = [abs(int(row["delta_ms"])) for row in kind_matches]
        by_kind[kind] = _kind_row(len(kind_matches), len(kind_misses), None, deltas)
    all_deltas = [abs(int(row["delta_ms"])) for row in matches]
    by_kind["all"] = _kind_row(len(matches), len(misses), len(extras), all_deltas)

    n_moments = len(moments_in)
    trace_found = sum(1 for moment in moments_in if moment.get("status") == "found")
    orange_count = sum(1 for moment in moments_in if moment.get("status") == "orange")

    all_times = [int(moment["t_ms"]) for moment in moments_in]
    all_indexed = match_shot_indices(tag_times, all_times, int(window_ms))
    missed_tag_indexes = set(indexed["unmatched_tags"])
    hidden_rows: List[Dict[str, Any]] = []
    for ti, fi, delta in all_indexed["matches"]:
        if ti not in missed_tag_indexes:
            continue
        tag = kept[ti]
        moment = moments_in[fi]
        hidden_rows.append(
            {
                "tag_t_ms": int(tag["t"]),
                "moment_t_ms": int(moment["t_ms"]),
                "delta_ms": int(delta),
                "eventtype": tag.get("eventtype"),
                "result": tag.get("result"),
                "start": tag.get("start"),
                "player": tag.get("player"),
                "quarter": tag.get("quarter"),
                "shot_call": shot_call_of(moment),
                "shot_reason": moment.get("shot_reason"),
            }
        )
    hidden_rows.sort(key=lambda row: int(row["tag_t_ms"]))
    hidden_by_reason: Dict[str, int] = {}
    for row in hidden_rows:
        key = "none" if row["shot_reason"] is None else str(row["shot_reason"])
        hidden_by_reason[key] = hidden_by_reason.get(key, 0) + 1

    matched_moment_indexes = {shot_indexes[fi] for _ti, fi, _delta in indexed["matches"]}
    candidates = [
        moments_in[i]
        for i in range(len(moments_in))
        if i not in matched_moment_indexes
    ]
    report: Dict[str, Any] = {
        "window_ms": int(window_ms),
        "n_tags_in": len(tags_in),
        "n_tags": len(kept),
        "n_q4_removed": len(tags_in) - len(kept),
        "n_moments": n_moments,
        "by_kind": by_kind,
        "trace_found": trace_found,
        "trace_total": n_moments,
        "trace_found_rate": (trace_found / n_moments) if n_moments else None,
        "orange_count": orange_count,
        "matches": matches,
        "extras": extras,
        "misses": misses,
        "shot_calls": shot_call_counts(moments_in),
        "hidden": {
            "n": len(hidden_rows),
            "by_reason": hidden_by_reason,
            "rows": hidden_rows,
        },
    }
    if truth is not None:
        if not truth_run:
            raise ValueError("truth_run is required when truth is given")
        entries = truth_entries_for_run(truth, truth_run)
        truth_report = score_truth(candidates, entries, int(extra_window_ms))
        truth_report["run"] = truth_run
        report["truth"] = truth_report
    report["shooter"] = shooter_section(moments_in, matched_pairs, fps)
    report["ft"] = ft_section(moments_in, matched_pairs)
    return report


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render_summary(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Rim-first measure")
    lines.append("")
    lines.append(
        f"Window: **{report['window_ms']} ms** (`find_shots_measure.match_shots`)."
    )
    lines.append("")
    lines.append(
        f"Adrian Q4 tags removed before matching: **{report['n_q4_removed']}** "
        f"(tags used {report['n_tags']} of {report['n_tags_in']})."
    )
    lines.append("")
    lines.append(
        "Finder moments have no 2PT/3PT/FT label, so extras are counted on the all row."
    )
    lines.append("")
    lines.append("| kind | found | missed | extra | timing median ms | timing max ms |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for kind in ("2PT", "3PT", "FT", "all"):
        row = report["by_kind"][kind]
        lines.append(
            "| {kind} | {found} | {missed} | {extra} | {med} | {mx} |".format(
                kind=kind,
                found=row["found"],
                missed=row["missed"],
                extra=_fmt(row["extra"]),
                med=_fmt(row["median_abs_delta_ms"]),
                mx=_fmt(row["max_abs_delta_ms"]),
            )
        )
    lines.append("")
    total = report["trace_total"]
    if total:
        rate = 100.0 * float(report["trace_found_rate"])
        trace = f"{report['trace_found']}/{total} ({rate:.1f}%)"
    else:
        trace = "—"
    lines.append(f"Trace found rate: **{trace}**")
    lines.append("")
    lines.append(f"Orange count: **{report['orange_count']}**")
    lines.append("")
    lines.append("## Extras")
    lines.append("")
    if not report["extras"]:
        lines.append("None.")
    else:
        for row in report["extras"]:
            lines.append(
                f"- {row['t_ms']} ms kind_hint={row.get('kind_hint')} "
                f"frame={row.get('frame')} status={row.get('status')}"
            )
    lines.append("")
    lines.append("## Misses")
    lines.append("")
    if not report["misses"]:
        lines.append("None.")
    else:
        for row in report["misses"]:
            lines.append(
                f"- {row['t_ms']} ms {row.get('start') or ''} "
                f"{row.get('eventtype')} {row.get('result')} "
                f"Q={row.get('quarter')} player={row.get('player') or ''}".rstrip()
            )
    lines.append("")
    calls = report["shot_calls"]["by_call"]
    lines.append("## Shot calls")
    lines.append("")
    lines.append(
        "Moments by call: shot {shot}, orange {orange}, not a shot {not_a_shot}.".format(
            shot=calls.get("shot", 0),
            orange=calls.get("orange", 0),
            not_a_shot=calls.get("not_a_shot", 0),
        )
    )
    reason_bits = [
        f"{reason} {n}"
        for reason, n in sorted(report["shot_calls"]["by_reason"].items())
    ]
    lines.append(
        "Moments by reason: " + (", ".join(reason_bits) if reason_bits else "none") + "."
    )
    lines.append("")
    lines.append("## Hidden tagged shots")
    lines.append("")
    lines.append(
        "A tag that matched some moment, but not a moment counted as a shot. "
        "The fix hid that tagged shot."
    )
    lines.append("")
    hidden = report.get("hidden") or {"rows": [], "by_reason": {}}
    if not hidden["rows"]:
        lines.append("None.")
    else:
        for row in hidden["rows"]:
            lines.append(
                f"- tag {row['tag_t_ms']} ms {row.get('eventtype') or ''} "
                f"matched moment {row['moment_t_ms']} ms "
                f"call {row.get('shot_call')} reason {row.get('shot_reason')}".rstrip()
            )
        bits = [
            f"{reason} {n}" for reason, n in sorted(hidden["by_reason"].items())
        ]
        lines.append("")
        lines.append("Hidden by reason: " + ", ".join(bits) + ".")
    lines.append("")
    if "truth" in report:
        truth = report["truth"]
        lines.append(f"## Truth check ({truth.get('run')})")
        lines.append("")
        lines.append(
            f"Each truth row looks at moments that were not matched to a tag, "
            f"within {truth['window_ms']} ms. "
            "A put-back is correct with one shot, missed with none, orange when an "
            "orange moment is there instead, and wrong when two shots land on it. "
            "Labels A, B, C, D, F, and H are correct with no shot "
            "(orange, not a shot, or nothing) and wrong when a shot is there. "
            "An unclear row is correct when orange, gone when it is missing or not a shot, "
            "and listed as shot on unclear when a shot is there (that one is not counted wrong). "
            "A shot near no truth row is a new extra."
        )
        lines.append("")
        for label, bucket in truth["by_label"].items():
            lines.append(
                f"- {label}: correct {bucket['correct']}, wrong {bucket['wrong']}, "
                f"missed {bucket['missed']}, orange {bucket['orange']}, "
                f"gone {bucket['gone']}, shot on unclear {bucket['shot_on_unclear']}"
            )
            for row in bucket["rows"]:
                lines.append(
                    f"  - n={row.get('n')} {row['t_ms']} ms {row['verdict']} ({row['detail']})"
                )
        totals = truth["totals"]
        lines.append("")
        lines.append(
            "Totals: correct {correct}, wrong {wrong}, missed {missed}, "
            "orange {orange}, gone {gone}, shot on unclear {shot_on_unclear}, "
            "new extra {new_extra}.".format(**totals)
        )
        lines.append("")
        lines.append("Shots near no truth row:")
        lines.append("")
        if not truth["new_extras"]:
            lines.append("None.")
        else:
            for row in truth["new_extras"]:
                lines.append(f"- {row['t_ms']} ms frame {row.get('frame')}")
        lines.append("")
    if "shooter" in report:
        lines.extend(_render_shooter(report["shooter"]))
    if "ft" in report:
        lines.extend(_render_ft(report["ft"]))
    return "\n".join(lines)


def _render_ft(ft: Dict[str, Any]) -> List[str]:
    lines = ["## Free throw line", ""]
    lines.append(
        "Matched tags: found {found}, missed {missed}, false {false}.".format(**ft)
    )
    lines.append(
        f"Orange ft_line_not_found: {ft['orange_ft_line_not_found']}."
    )
    lines.append(f"too_far_from_hoop: {ft.get('too_far_from_hoop', 0)}.")
    lines.append(f"no_lane_lines: {ft.get('no_lane_lines', 0)}.")
    lines.append(f"release_not_shooter: {ft.get('release_not_shooter', 0)}.")
    lines.append(f"maybe_free_throw: {ft.get('maybe_free_throw', 0)}.")
    lines.append("")
    lines.append("Flagged moments:")
    lines.append("")
    if not ft["flagged"]:
        lines.append("None.")
    else:
        for row in ft["flagged"]:
            lines.append(
                f"- {row['t_ms']} ms {row.get('eventtype') or ''}".rstrip()
            )
    lines.append("")
    lines.append("Maybe free throw moments:")
    lines.append("")
    if not ft.get("maybe"):
        lines.append("None.")
    else:
        for row in ft["maybe"]:
            lines.append(
                f"- {row['t_ms']} ms {row.get('eventtype') or ''}".rstrip()
            )
    lines.append("")
    lines.append("Non-FT moments flagged free_throw:")
    lines.append("")
    if not ft.get("non_ft_flagged"):
        lines.append("None.")
    else:
        for row in ft["non_ft_flagged"]:
            lines.append(f"- {row['t_ms']} ms")
    lines.append("")
    lines.append("duplicate_of_found_ft:")
    lines.append("")
    if not ft.get("duplicate_of_found_ft"):
        lines.append("None.")
    else:
        for row in ft["duplicate_of_found_ft"]:
            lines.append(f"- {row['t_ms']} ms")
    lines.append("")
    return lines


def _render_shooter(shooter: Dict[str, Any]) -> List[str]:
    lines: List[str] = ["## Shooter", ""]
    status_bits = [
        f"{key} {n}" for key, n in sorted(shooter["by_status"].items())
    ]
    reason_bits = [
        f"{key} {n}" for key, n in sorted(shooter["by_reason"].items())
    ]
    series_bits = [
        f"{key} {n}" for key, n in sorted(shooter["found_by_series"].items())
    ]
    lines.append(
        "Moments by shooter status: " + (", ".join(status_bits) if status_bits else "none") + "."
    )
    lines.append(
        "Moments by shooter reason: " + (", ".join(reason_bits) if reason_bits else "none") + "."
    )
    lines.append(
        "Found by series: " + (", ".join(series_bits) if series_bits else "none") + "."
    )
    lines.append("")
    release = shooter["release_to_trigger_s"]
    lines.append(
        "Release to trigger, tag-matched shots: "
        f"found n={release['found']['n']} median {_fmt(release['found']['median_s'])} s; "
        f"orange n={release['orange']['n']} median {_fmt(release['orange']['median_s'])} s."
    )
    lines.append("")
    lines.append("### FT spot")
    lines.append("")
    lines.append(
        f"Pass line **{FT_SPOT_PASS_WIDTHS}** hoop widths from the median FT spot of that series."
    )
    lines.append("")
    if not shooter["ft_spot"]:
        lines.append("None.")
    else:
        for group in shooter["ft_spot"]:
            lines.append(
                f"- series {group['series']}: n {group['n']}, "
                f"pass {group['pass_count']}, "
                f"median distance {_fmt(group['median_distance_widths'])}"
            )
    lines.append("")
    lines.append("### 3PT vs 2PT")
    lines.append("")
    lines.append(
        "Floor-spot distance from the moment hoop, in hoop widths. "
        "Report only. The camera pans and zooms, so this is a picture distance, not a court distance."
    )
    lines.append("")
    for kind in ("2PT", "3PT"):
        row = shooter["shot_distance_widths"][kind]
        lines.append(
            f"- {kind}: n {row['n']}, median {_fmt(row['median'])}, "
            f"q1 {_fmt(row['q1'])}, q3 {_fmt(row['q3'])}"
        )
    lines.append("")
    lines.append("### Shooter review")
    lines.append("")
    if not shooter["review"]:
        lines.append("None.")
    else:
        for row in shooter["review"]:
            spot = row.get("floor_spot_widths")
            if spot is None:
                spot_txt = "—"
            else:
                spot_txt = f"({_fmt(spot['x'])}, {_fmt(spot['y'])})"
            lines.append(
                f"- {row['t_ms']} ms {row.get('eventtype') or ''} "
                f"{row.get('result') or ''} player={row.get('player') or ''} "
                f"status={row.get('status')} reason={row.get('reason')} "
                f"floor={spot_txt}".rstrip()
            )
    lines.append("")
    return lines


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure rim-first moments.json against tags."
    )
    parser.add_argument("--moments", required=True, type=Path)
    parser.add_argument("--tags", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--truth", type=Path, default=None)
    parser.add_argument("--truth-run", choices=("adrian", "notus"), default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    refuse_existing_out_dir(args.out_dir)
    tags = load_shot_tags(Path(args.tags))
    doc = json.loads(Path(args.moments).read_text(encoding="utf-8"))
    fps = None
    if isinstance(doc, dict):
        moments = doc.get("moments")
        if moments is None:
            raise SystemExit("moments.json has no moments list")
        if doc.get("fps") is not None:
            fps = float(doc["fps"])
    elif isinstance(doc, list):
        moments = doc
    else:
        raise SystemExit("moments.json is not an object or list")
    if (args.truth is None) ^ (args.truth_run is None):
        raise SystemExit("Pass both --truth and --truth-run, or neither.")
    truth = None
    if args.truth is not None:
        truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))
    report = build_report(
        moments,
        tags,
        MATCH_WINDOW_MS,
        truth=truth,
        truth_run=args.truth_run,
        extra_window_ms=EXTRA_MATCH_WINDOW_MS,
        fps=fps,
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True)
    results_path = out / "results.json"
    summary_path = out / "summary.md"
    results_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(render_summary(report), encoding="utf-8")
    all_row = report["by_kind"]["all"]
    print(
        f"found {all_row['found']} missed {all_row['missed']} extra {all_row['extra']} "
        f"orange {report['orange_count']} "
        f"trace {report['trace_found']}/{report['trace_total']} "
        f"hidden {report['hidden']['n']}",
        flush=True,
    )
    if "truth" in report:
        totals = report["truth"]["totals"]
        print(
            "truth correct {correct} wrong {wrong} missed {missed} "
            "orange {orange} gone {gone} shot_on_unclear {shot_on_unclear} "
            "new_extra {new_extra}".format(**totals),
            flush=True,
        )
    print(f"Wrote {results_path} and {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
