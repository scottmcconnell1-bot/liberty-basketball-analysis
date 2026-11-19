"""Tests for double_count_fix module."""

from __future__ import annotations

import copy
import pytest

from double_count_fix import apply_double_count_cut, next_shot_cuts, SHOT_KINDS


def test_next_shot_cuts_basic():
    """Basic next_shot_cuts with distinct times."""
    times = [1000, 3000, 5000]  # ms
    fps = 25.0
    cuts = next_shot_cuts(times, fps)
    # 1000 -> 3000: 2000ms = 2s * 25 = 50 frames
    # 3000 -> 5000: 2000ms = 2s * 25 = 50 frames
    # 5000 -> None
    assert cuts[1000] == 50
    assert cuts[3000] == 50
    assert cuts[5000] is None


def test_next_shot_cuts_equal_times():
    """Shots with the same tag time use the next strictly greater time."""
    times = [1000, 1000, 3000, 5000]
    fps = 25.0
    cuts = next_shot_cuts(times, fps)
    # All 1000s map to next strictly greater (3000): 2000ms = 50 frames
    assert cuts[1000] == 50
    assert cuts[3000] == 50
    assert cuts[5000] is None


def test_next_shot_cuts_last_shot():
    """Last shot in film gets None cut."""
    times = [1000, 2000]
    fps = 25.0
    cuts = next_shot_cuts(times, fps)
    assert cuts[2000] is None


def test_next_shot_cuts_empty():
    """Empty list returns empty dict."""
    cuts = next_shot_cuts([], 25.0)
    assert cuts == {}


def test_apply_double_count_cut_none_unchanged():
    """cut_offset=None returns deep copy unchanged."""
    track = {
        "ball": [[0, 100.0, 200.0], [1, 101.0, 201.0]],
        "bodd": [[2, 102.0, 202.0]],
        "hoop": [100.0, 200.0, 50.0, 1000.0],
        "result": "Make",
    }
    result = apply_double_count_cut(track, None)
    assert result == track
    # Should be a deep copy, not the same object
    assert result is not track
    assert result["ball"] is not track["ball"]
    assert result["bodd"] is not track["bodd"]


def test_apply_double_count_cut_removes_ge_cut():
    """Points with frame_offset >= cut_offset are removed; < cut kept."""
    track = {
        "ball": [[0, 100.0, 200.0], [1, 101.0, 201.0], [2, 102.0, 202.0], [3, 103.0, 203.0]],
        "bodd": [[1, 101.0, 201.0], [2, 102.0, 202.0], [3, 103.0, 203.0]],
        "hoop": [100.0, 200.0, 50.0, 1000.0],
    }
    # cut at offset 2: keep offsets 0,1; drop 2,3
    result = apply_double_count_cut(track, 2)
    assert result["ball"] == [[0, 100.0, 200.0], [1, 101.0, 201.0]]
    assert result["bodd"] == [[1, 101.0, 201.0]]
    # hoop and other keys preserved
    assert result["hoop"] == track["hoop"]


def test_apply_double_count_cut_bodd_too():
    """bodd points are also filtered by frame_offset >= cut_offset."""
    track = {
        "ball": [[0, 100.0, 200.0]],
        "bodd": [[0, 100.0, 200.0], [1, 101.0, 201.0], [2, 102.0, 202.0]],
        "hoop": [100.0, 200.0, 50.0, 1000.0],
    }
    result = apply_double_count_cut(track, 1)
    assert result["ball"] == [[0, 100.0, 200.0]]
    assert result["bodd"] == [[0, 100.0, 200.0]]


def test_apply_double_count_cut_input_not_mutated():
    """Original track is not mutated."""
    track = {
        "ball": [[0, 100.0, 200.0], [1, 101.0, 201.0]],
        "bodd": [[2, 102.0, 202.0]],
        "hoop": [100.0, 200.0, 50.0, 1000.0],
    }
    original_ball = copy.deepcopy(track["ball"])
    original_bodd = copy.deepcopy(track["bodd"])
    apply_double_count_cut(track, 1)
    assert track["ball"] == original_ball
    assert track["bodd"] == original_bodd


def test_handmade_pair_2_5s_apart():
    """Synthetic two shots 2.5s apart (62 frames at 25 fps).
    First is a miss with long track reaching into next shot's make frames.
    With cut, the false make disappears.
    """
    fps = 25.0
    t1 = 39400  # ms
    t2 = 41900  # ms  (2.5s = 2500ms later)
    times = [t1, t2]
    cuts = next_shot_cuts(times, fps)
    # 2500ms / 1000 * 25 = 62.5 -> round = 62 or 63? round(2.5*25) = round(62.5) = 62 (banker's rounding)
    # Actually Python round(62.5) = 62
    cut_offset = cuts[t1]
    assert cut_offset == 62

    # Miss track with ball points extending to frame 70 (would reach next shot)
    miss_track = {
        "ball": [[i, 100.0 + i * 0.1, 200.0 + i * 0.5] for i in range(80)],  # 80 frames
        "bodd": [[i, 100.0 + i * 0.1, 200.0 + i * 0.5] for i in range(80)],
        "hoop": [100.0, 200.0, 50.0, 1000.0],
        "result": "Miss",
    }

    # Without cut, decide_shot would see frames up to 79
    # With cut at 62, frames 62+ are dropped
    cut_track = apply_double_count_cut(miss_track, cut_offset)
    assert len(cut_track["ball"]) == 62  # offsets 0..61
    assert len(cut_track["bodd"]) == 62
    assert all(pt[0] < 62 for pt in cut_track["ball"])
    assert all(pt[0] < 62 for pt in cut_track["bodd"])


def test_shot_kinds_constant():
    """SHOT_KINDS matches what load_shot_tags filters."""
    assert SHOT_KINDS == {"2PT", "3PT", "FT"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])