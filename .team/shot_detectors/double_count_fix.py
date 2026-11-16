"""Double-count fix: compute per-shot cut offsets and apply them to tracks.

The saved track for a shot contains up to 80 frames of ball/bodd points starting
at the shot's tag time. When the NEXT tagged shot (2PT/3PT/FT, either team)
occurs within those 80 frames, the current shot's track borrows the next shot's
make frames. This module computes the cut frame offset and drops ball/bodd
points at or beyond that offset.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

# load_shot_tags in measure_net_moved.py already filters to SHOT_KINDS = {"2PT", "3PT", "FT"}
# We reuse that same constant here for computing next-shot cuts.
SHOT_KINDS = {"2PT", "3PT", "FT"}


def next_shot_cuts(film_shot_times_ms: List[int], fps: float) -> Dict[int, Optional[int]]:
    """Compute cut frame offset for each shot time in a film.

    Args:
        film_shot_times_ms: List of shot tag times (ms) for shots in this film
                           whose eventtype is in SHOT_KINDS, sorted ascending.
        fps: Video FPS for this film.

    Returns:
        Dict mapping each shot's tag time (ms) to its cut_offset (frames)
        or None if no next shot exists in the film.
        Shots with the same tag time use the next strictly greater tag time.
    """
    if not film_shot_times_ms:
        return {}

    # Deduplicate and sort
    unique_times = sorted(set(film_shot_times_ms))
    cuts: Dict[int, Optional[int]] = {}

    for i, t in enumerate(unique_times):
        if i + 1 < len(unique_times):
            t_next = unique_times[i + 1]
            delta_ms = t_next - t
            cut_offset = round(delta_ms / 1000.0 * fps)
            cuts[t] = cut_offset
        else:
            cuts[t] = None

    # Map back to original times (including duplicates)
    result: Dict[int, Optional[int]] = {}
    for t in film_shot_times_ms:
        result[t] = cuts[t]
    return result


def apply_double_count_cut(track: Dict[str, Any], cut_offset: Optional[int]) -> Dict[str, Any]:
    """Return a NEW track dict with ball/bodd points at frame_offset >= cut_offset removed.

    Args:
        track: Original track dict with keys "ball", "bodd", "hoop", etc.
        cut_offset: Frame offset (relative to tag frame) at which to cut.
                    Points with frame_offset >= cut_offset are dropped.
                    None means no cut (return deep copy unchanged).

    Returns:
        New track dict (deep copy) with ball and bodd filtered. Other keys
        are preserved as-is (deep copied). Never adds points.
    """
    new_track = copy.deepcopy(track)

    if cut_offset is None:
        return new_track

    for key in ("ball", "bodd"):
        points = new_track.get(key)
        if points is not None:
            new_track[key] = [pt for pt in points if int(pt[0]) < cut_offset]

    return new_track