"""Clip moment fix: a moment cannot belong to two shots.

When two consecutive shots (by tag time) have anchor_frames within
CONFLICT_FRAMES of each other, the earlier shot's clip is recentred on
its tag frame and flagged. The later shot is unchanged. Make/miss is
not touched — only which frames the review clip shows.

Spec 27: a flagged shot's clip also ends at (next anchor_frame - 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

# Page clip is 8 before + 14 after + 1 centre = 23 frames (spec 26 §1).
CONFLICT_FRAMES = 23

PathLike = Union[str, Path]


def seconds_to_frames(seconds: float, fps: float) -> int:
    """Convert a duration in seconds to a frame count at the film's fps."""
    return round(seconds * fps)


def too_short_conflict_note(next_gap_s: float) -> str:
    """Suffix when a flagged clip ends at or before the usual AFTER window."""
    return (
        f" - next tag only {next_gap_s:.1f} s later"
        " - may be the same shot tagged twice"
    )


def review_storage_key(out_dir: PathLike) -> str:
    """localStorage key for one built page (folder name keeps pages apart)."""
    return "coach_review_" + Path(out_dir).name


def resolve_clip_centres(
    shots: List[Dict[str, Any]],
    conflict_frames: int = CONFLICT_FRAMES,
) -> Tuple[Dict[int, int], Dict[int, str], Dict[int, Dict[str, Any]]]:
    """Pick a clip centre and flag for each shot in one film.

    Args:
        shots: One film's shot dicts with keys t (ms), anchor_frame, fps.
               Sorted by t inside; the input list is not mutated.
        conflict_frames: Max |anchor_i - anchor_{i+1}| that counts as a
                         shared moment (inclusive).

    Returns:
        (clip_centres, flags, extents) keyed by tag time ms.
        clip_centres[t] is the frame to centre the review clip on.
        flags[t] is "clip_moment_conflict" or "ok".
        extents[t] is present only for flagged shots:
          {"clip_end": next_anchor - 1, "next_gap_s": (t_next - t) / 1000}.
        The later shot of a conflicting pair is never changed by that pair.
    """
    ordered = sorted(shots, key=lambda s: int(s["t"]))
    clip_centres: Dict[int, int] = {}
    flags: Dict[int, str] = {}
    extents: Dict[int, Dict[str, Any]] = {}

    for i, shot in enumerate(ordered):
        t = int(shot["t"])
        anchor = int(shot["anchor_frame"])
        if i + 1 < len(ordered):
            nxt = ordered[i + 1]
            next_anchor = int(nxt["anchor_frame"])
            if abs(anchor - next_anchor) <= conflict_frames:
                fps = float(shot["fps"])
                clip_centres[t] = round(t / 1000.0 * fps)
                flags[t] = "clip_moment_conflict"
                extents[t] = {
                    "clip_end": next_anchor - 1,
                    "next_gap_s": (int(nxt["t"]) - t) / 1000.0,
                }
            else:
                clip_centres[t] = anchor
                flags[t] = "ok"
        else:
            clip_centres[t] = anchor
            flags[t] = "ok"

    return clip_centres, flags, extents


def group_flagged_chains(
    shots: List[Dict[str, Any]],
    conflict_frames: int = CONFLICT_FRAMES,
) -> List[List[Dict[str, Any]]]:
    """Group consecutive shots whose anchors share a moment.

    Returns list of groups; each group is consecutive shots where each
    adjacent pair has |anchor_i - anchor_{i+1}| <= conflict_frames.
    A shot not in any conflict is a group of length 1.
    """
    ordered = sorted(shots, key=lambda s: int(s["t"]))
    if not ordered:
        return []
    groups: List[List[Dict[str, Any]]] = [[ordered[0]]]
    for shot in ordered[1:]:
        prev = groups[-1][-1]
        if abs(int(prev["anchor_frame"]) - int(shot["anchor_frame"])) <= conflict_frames:
            groups[-1].append(shot)
        else:
            groups.append([shot])
    return groups


def group_clip_extent(
    group: List[Dict[str, Any]],
    fps: float,
    before: int,
    after: int,
) -> Tuple[int, int]:
    """Inclusive (first, last) frame for a combined-card clip.

    first = round(t_first/1000*fps) - before
    last  = max(anchor_frame over the group) + after
    """
    ordered = sorted(group, key=lambda s: int(s["t"]))
    t_first = int(ordered[0]["t"])
    first = round(t_first / 1000.0 * fps) - before
    last = max(int(s["anchor_frame"]) for s in ordered) + after
    return first, last


def duplicate_calls_for_group(n_shots: int, last_call: str) -> List[str]:
    """coach_call list after 'Same shot, tagged twice' (last keeps its call)."""
    if n_shots < 1:
        return []
    if n_shots == 1:
        return [last_call]
    return ["duplicate"] * (n_shots - 1) + [last_call]


def count_summary_makes(coach_calls: List[str]) -> int:
    """Summary make count: each shot once; duplicate (and miss) add nothing."""
    return sum(1 for c in coach_calls if c == "make")
