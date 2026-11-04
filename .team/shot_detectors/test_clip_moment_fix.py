"""Tests for clip_moment_fix (pure functions only; no video)."""

from __future__ import annotations

import copy

import pytest

from clip_moment_fix import (
    CONFLICT_FRAMES,
    count_summary_makes,
    duplicate_calls_for_group,
    group_clip_extent,
    group_flagged_chains,
    resolve_clip_centres,
    review_storage_key,
    seconds_to_frames,
    too_short_conflict_note,
)


def _shot(t: int, anchor: int, fps: float = 25.0) -> dict:
    return {"t": t, "anchor_frame": anchor, "fps": fps}


def test_shared_moment_flags_earlier_only():
    """|100-110|=10 <= 23: earlier flagged at tag frame; later keeps anchor."""
    shots = [_shot(1000, 100), _shot(2000, 110)]
    centres, flags, _ = resolve_clip_centres(shots)
    assert flags[1000] == "clip_moment_conflict"
    assert centres[1000] == round(1000 / 1000.0 * 25.0)
    assert flags[2000] == "ok"
    assert centres[2000] == 110


def test_far_apart_both_ok():
    """|100-150|=50 > 23: both keep anchor, both ok."""
    shots = [_shot(1000, 100), _shot(5000, 150)]
    centres, flags, extents = resolve_clip_centres(shots)
    assert flags[1000] == "ok"
    assert centres[1000] == 100
    assert flags[5000] == "ok"
    assert centres[5000] == 150
    assert extents == {}


def test_last_shot_ok():
    """Sole / last shot: clip_centre = anchor, flag ok; no clip_end."""
    shots = [_shot(9000, 250)]
    centres, flags, extents = resolve_clip_centres(shots)
    assert flags[9000] == "ok"
    assert centres[9000] == 250
    assert 9000 not in extents


def test_equal_anchors_conflict():
    """|100-100|=0 <= 23: earlier flagged; later keeps 100."""
    shots = [_shot(1000, 100), _shot(2000, 100)]
    centres, flags, _ = resolve_clip_centres(shots)
    assert flags[1000] == "clip_moment_conflict"
    assert centres[1000] == round(1000 / 1000.0 * 25.0)
    assert flags[2000] == "ok"
    assert centres[2000] == 100


def test_negative_gap_conflict():
    """Next anchor earlier: |100-80|=20 <= 23. Earlier flagged."""
    shots = [_shot(1000, 100), _shot(2000, 80)]
    centres, flags, _ = resolve_clip_centres(shots)
    assert flags[1000] == "clip_moment_conflict"
    assert centres[1000] == round(1000 / 1000.0 * 25.0)
    assert flags[2000] == "ok"
    assert centres[2000] == 80


def test_input_not_mutated():
    """Input list and dicts are not mutated; order inside is independent."""
    shots = [_shot(2000, 110), _shot(1000, 100)]
    original = copy.deepcopy(shots)
    resolve_clip_centres(shots)
    assert shots == original


def test_flagged_clip_centre_equals_tag_frame():
    """Flagged shot's clip centre is round(t/1000*fps)."""
    t, fps = 39400, 25.0
    shots = [_shot(t, 1045, fps), _shot(41900, 1048, fps)]
    centres, flags, _ = resolve_clip_centres(shots)
    assert flags[t] == "clip_moment_conflict"
    assert centres[t] == round(t / 1000.0 * fps)


def test_conflict_frames_constant():
    assert CONFLICT_FRAMES == 23


def test_flagged_clip_end_is_next_anchor_minus_one():
    """Flagged shot: clip_end = next shot's anchor_frame - 1."""
    shots = [_shot(39400, 1045), _shot(41900, 1048)]
    _, flags, extents = resolve_clip_centres(shots)
    assert flags[39400] == "clip_moment_conflict"
    assert extents[39400]["clip_end"] == 1048 - 1


def test_flagged_next_gap_s():
    """Flagged shot: next_gap_s = (t_next - t) / 1000."""
    shots = [_shot(2753100, 68828), _shot(2753200, 68836)]
    _, flags, extents = resolve_clip_centres(shots)
    assert flags[2753100] == "clip_moment_conflict"
    assert extents[2753100]["next_gap_s"] == pytest.approx(0.1)
    assert extents[2753100]["clip_end"] == 68835


def test_unflagged_has_no_clip_end():
    """Unflagged (and last) shots are absent from extents."""
    shots = [_shot(1000, 100), _shot(5000, 200), _shot(9000, 400)]
    _, flags, extents = resolve_clip_centres(shots)
    assert flags[1000] == "ok"
    assert flags[5000] == "ok"
    assert flags[9000] == "ok"
    assert extents == {}


def test_too_short_conflict_note():
    assert too_short_conflict_note(0.1) == (
        " - next tag only 0.1 s later - may be the same shot tagged twice"
    )
    assert too_short_conflict_note(1.25) == (
        " - next tag only 1.2 s later - may be the same shot tagged twice"
    )


def test_review_storage_key_uses_folder_name():
    assert review_storage_key("C:/out/page_v3") == "coach_review_page_v3"
    assert review_storage_key("/tmp/review_queue/page") == "coach_review_page"
    assert review_storage_key("page_v2") != review_storage_key("page_v3")


def test_group_flagged_chains_pair():
    """One conflicting pair → one group of 2."""
    shots = [_shot(39400, 1045), _shot(41900, 1048), _shot(90000, 3000)]
    groups = group_flagged_chains(shots)
    assert len(groups) == 2
    assert [s["t"] for s in groups[0]] == [39400, 41900]
    assert [s["t"] for s in groups[1]] == [90000]


def test_group_flagged_chains_of_three():
    """A-B and B-C both within CONFLICT_FRAMES → one group of 3."""
    shots = [_shot(1000, 100), _shot(2000, 110), _shot(3000, 120), _shot(9000, 400)]
    groups = group_flagged_chains(shots)
    assert len(groups) == 2
    assert [s["t"] for s in groups[0]] == [1000, 2000, 3000]
    assert [s["t"] for s in groups[1]] == [9000]


def test_group_flagged_chains_none():
    """No adjacent anchors within CONFLICT_FRAMES → each shot alone."""
    shots = [_shot(1000, 100), _shot(5000, 200), _shot(9000, 400)]
    groups = group_flagged_chains(shots)
    assert len(groups) == 3
    assert all(len(g) == 1 for g in groups)


def test_group_clip_extent_basic():
    """Group 1 arithmetic: first tag - before .. max(anchor) + after."""
    group = [_shot(39400, 1045), _shot(41900, 1048)]
    first, last = group_clip_extent(group, fps=25.0, before=8, after=14)
    assert first == 977
    assert last == 1062
    assert last - first + 1 == 86


def test_group_clip_extent_first_shot_has_larger_anchor():
    """End uses max(anchor), not the last shot's anchor (spec 28 correction 1)."""
    # 2417100 anchor 60501 > 2419200 anchor 60483
    group = [_shot(2417100, 60501), _shot(2419200, 60483)]
    first, last = group_clip_extent(group, fps=25.0, before=8, after=14)
    assert first == 60420
    assert last == 60515
    assert last - first + 1 == 96


def test_seconds_to_frames():
    """Spec 30: 2.0 s / 1.5 s at 25 fps -> 50 / 38 (Python round half-even on 37.5)."""
    assert seconds_to_frames(2.0, 25) == 50
    assert seconds_to_frames(1.5, 25) == 38


def test_group_clip_extent_spec30_before50_after38():
    """Spec 30 combined extents with before=50, after=38."""
    g1 = [_shot(39400, 1045), _shot(41900, 1048)]
    first, last = group_clip_extent(g1, fps=25.0, before=50, after=38)
    assert first == 935
    assert last == 1086
    assert last - first + 1 == 152

    g2 = [_shot(2417100, 60501), _shot(2419200, 60483)]
    first, last = group_clip_extent(g2, fps=25.0, before=50, after=38)
    assert first == 60378
    assert last == 60539
    assert last - first + 1 == 162

    g3 = [_shot(2753100, 68836), _shot(2753200, 68836)]
    first, last = group_clip_extent(g3, fps=25.0, before=50, after=38)
    assert first == 68778
    assert last == 68874
    assert last - first + 1 == 97


def test_duplicate_calls_for_group():
    """Earlier shots become duplicate; last keeps its Make/Miss."""
    assert duplicate_calls_for_group(2, "make") == ["duplicate", "make"]
    assert duplicate_calls_for_group(3, "miss") == ["duplicate", "duplicate", "miss"]
    assert duplicate_calls_for_group(1, "make") == ["make"]


def test_count_summary_makes_ignores_duplicate():
    """Duplicate adds nothing; each make counts once."""
    assert count_summary_makes(["make", "miss", "duplicate", "make"]) == 2
    assert count_summary_makes(["duplicate", "duplicate", "miss"]) == 0
    assert count_summary_makes([]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
