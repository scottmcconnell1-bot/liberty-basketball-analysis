"""Spec 41/42 free-throw line. Hand-made arrays. No video and no model."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import ultralytics  # noqa: F401
except ModuleNotFoundError:
    _ultra = types.ModuleType("ultralytics")
    _ultra.YOLO = None  # type: ignore[attr-defined]
    sys.modules["ultralytics"] = _ultra

import cv2  # noqa: E402

import ft_half_circle as ft  # noqa: E402
import rim_first_finder as rff  # noqa: E402
import rim_first_measure as rfm  # noqa: E402
import test_rim_first as trf  # noqa: E402


def test_spec41_constants_are_the_fixed_settings():
    text = (HERE / "ft_half_circle.py").read_text(encoding="utf-8")
    assert text.count("spec 41, fixed by Claude Code 2026-11-08") >= 9
    assert text.count("spec 42, fixed by Claude Code 2026-11-08") >= 8
    assert text.count("spec 43, fixed by Claude Code 2026-11-08") == 2
    assert "remove_straight" not in text
    assert "ransac_ellipse" not in text
    assert "feet_inside" not in text
    assert ft.STILL_BEFORE_MS == 3000
    assert ft.STILL_UNTIL_MS == 1000
    assert ft.STILL_GAP_FRAMES == 25
    assert ft.STILL_EVERY_FRAMES == 5
    assert ft.STILL_MOVE_MAX == 0.15
    assert ft.MAYBE_STILL_MAX == 0.25
    assert ft.RELEASE_DX_MAX == 0.8
    assert ft.BALL_RELEASE_FACTOR == 0.6
    assert ft.LINE_NEAR == 0.25
    assert ft.END_PAD == 0.5
    assert ft.ANGLE_MIN == 60.0
    assert ft.DARK_MIN == 10.0
    assert ft.DARK_OFFSET_AT_1280 == 8.0
    assert ft.DARK_SAMPLES == 20
    assert ft.GROUP_DEG == 5.0
    assert ft.BAND_FRONT == 0.0
    assert ft.BAND_BACK == 0.35
    assert ft.HOOP_DIST_MAX == 3.8
    assert ft.LANE_ANGLE_MIN == 30.0
    assert ft.LANE_HOOP_SIDE == 0.15
    assert ft.LANE_GAP == 1.0
    assert ft.LANE_REACH == 2.5
    assert ft.LANE_MIN_OFF == 0.2
    assert ft.ERASE_PAD == 3
    assert ft.FRAME_WIDTH_REF == 1280.0
    assert rfm.FT_DUPLICATE_WINDOW_MS == 1000


def _sample_frames():
    """trigger 100 at 25 fps: window frames 25..75, every 5."""
    return list(range(25, 76, 5))


def _boxes(frames, x_at, h=100.0):
    by_frame = {}
    for frame in frames:
        by_frame[frame] = [
            {"x": float(x_at(frame)), "y": 200.0, "w": 40.0, "h": h}
        ]
    return by_frame


def test_stillness_is_the_median_over_players():
    frames = _sample_frames()
    still = _boxes(frames, lambda frame: 100.0)
    assert ft.stillness(still, 100, 25.0) == 0.0
    assert ft.is_still(still, 100, 25.0)

    moving = _boxes(frames, lambda frame: 100.0 + (frame - 25) * 4.0)
    move = ft.stillness(moving, 100, 25.0)
    assert move == pytest.approx(1.0)
    assert not ft.is_still(moving, 100, 25.0)

    both = {}
    for frame in frames:
        both[frame] = [
            {"x": 100.0, "y": 200.0, "w": 40.0, "h": 100.0},
            {"x": 400.0 + (frame - 25) * 4.0, "y": 200.0, "w": 40.0, "h": 100.0},
        ]
    assert ft.stillness(both, 100, 25.0) == pytest.approx(0.5)
    assert not ft.is_still(both, 100, 25.0)

    crowd = {}
    for frame in frames:
        crowd[frame] = [
            {"x": 100.0, "y": 180.0, "w": 40.0, "h": 100.0},
            {"x": 220.0, "y": 180.0, "w": 40.0, "h": 100.0},
            {"x": 340.0, "y": 180.0, "w": 40.0, "h": 100.0},
            {"x": 700.0 + (frame - 25) * 4.0, "y": 180.0, "w": 40.0, "h": 100.0},
        ]
    assert ft.stillness(crowd, 100, 25.0) == pytest.approx(0.0)
    assert ft.is_still(crowd, 100, 25.0)


def test_region_for_clips_to_the_frame():
    interior = {"x": 400.0, "y": 300.0, "w": 40.0, "h": 100.0}
    assert ft.region_for(interior, 1280, 720) == (200, 150, 600, 550)
    corner = {"x": 5.0, "y": 5.0, "w": 40.0, "h": 100.0}
    assert ft.region_for(corner, 100, 80) == (0, 0, 100, 80)


def _player(x, feet_y, h, w=40.0):
    return {"x": float(x), "y": float(feet_y) - h / 2.0, "w": float(w), "h": float(h)}


def _hoop(x=640.0, y=200.0):
    return {"x": float(x), "y": float(y), "w": 98.0, "h": 40.0}


def _horizontal_mask(y=500, x0=400, x1=880, shape=(720, 1280), thickness=3):
    mask = np.zeros(shape, np.uint8)
    cv2.line(mask, (x0, y), (x1, y), 255, thickness)
    return mask


def _ft_mask_with_lanes(
    y=500,
    x0=400,
    x1=880,
    left_x=540,
    right_x=740,
    shape=(720, 1280),
    thickness=3,
):
    """Horizontal FT line plus vertical lane stubs on the hoop side."""
    mask = _horizontal_mask(y=y, x0=x0, x1=x1, shape=shape, thickness=thickness)
    cv2.line(mask, (left_x, y - 50), (left_x, y - 10), 255, thickness)
    cv2.line(mask, (right_x, y - 50), (right_x, y - 10), 255, thickness)
    return mask


def _decide(
    mask,
    players,
    ball_at,
    still=True,
    gym="liberty",
    hoop=None,
    frame=None,
    ball_points=None,
    collect_debug=False,
    release_frame=None,
    stillness=None,
):
    players_by = {75: players}
    ball = ball_points if ball_points is not None else [[75, ball_at[0], ball_at[1]]]
    return ft.decide_ft(
        still=still,
        frame=frame,
        players_by_frame=players_by,
        refs_by_frame={},
        ball_points=ball,
        trigger=100,
        fps=25.0,
        gym=gym,
        cfg=ft.stage1b_config(),
        still_frame=75,
        hoop=_hoop() if hoop is None else hoop,
        paint_mask=mask,
        collect_debug=collect_debug,
        release_frame=release_frame,
        stillness=stillness,
    )


def _flat_line(y=500.0):
    return {
        "point": (640.0, float(y)),
        "direction": (1.0, 0.0),
        "extent": (-240.0, 240.0),
        "kept": [],
    }


def test_ft_line_found_with_shooter_in_band():
    mask = _ft_mask_with_lanes()
    shooter = _player(640.0, 520.0, 100.0)
    got = _decide(mask, [shooter], (640.0, shooter["y"]))
    assert got["free_throw"] is True
    assert got["ft_reason"] == "free_throw_line"
    assert got["ft_shooter_box"]["x"] == 640.0
    assert got["ft_shooter_box"]["h"] == 100.0


def test_lane_line_at_about_30_deg_is_rejected():
    # Feet->hoop is vertical (90 deg). A segment through the feet at 60 deg
    # is ~30 deg off, under ANGLE_MIN.
    mask = np.zeros((720, 1280), np.uint8)
    cv2.line(mask, (590, 433), (690, 607), 255, 3)
    shooter = _player(640.0, 520.0, 100.0)
    segs = ft.line_segments(mask, ft.stage1b_config(), 1280.0)
    assert segs
    # Distance and projection would pass; angle must reject.
    for x1, y1, x2, y2 in segs:
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        dist = abs(dy * (640.0 - x1) - dx * (520.0 - y1)) / length
        assert dist <= ft.LINE_NEAR * 100.0
        ang = __import__("math").degrees(__import__("math").atan2(dy, dx)) % 180.0
        off = min(abs(ang - 90.0), 180.0 - abs(ang - 90.0))
        assert off < ft.ANGLE_MIN
    kept = ft.keep_segments(
        segs,
        (640.0, 520.0),
        100.0,
        (640.0, 200.0),
        None,
        "liberty",
        1280.0,
    )
    assert kept == []
    got = _decide(mask, [shooter], (640.0, shooter["y"]))
    assert got["free_throw"] is False
    assert got["ft_reason"] == "ft_line_not_found"


def test_adrian_bright_line_with_dark_sides_is_rejected():
    # Bright stripe, dark floor on both sides: not darker-than-both-sides.
    frame = np.full((720, 1280), 40, np.uint8)
    cv2.line(frame, (400, 500), (880, 500), 200, 3)
    mask = _horizontal_mask()
    gray = frame.astype(float)
    kept = ft.keep_segments(
        ft.line_segments(mask, ft.stage1b_config(), 1280.0),
        (640.0, 520.0),
        100.0,
        (640.0, 200.0),
        gray,
        "adrian",
        1280.0,
    )
    assert kept == []
    shooter = _player(640.0, 520.0, 100.0)
    bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    got = _decide(
        mask,
        [shooter],
        (640.0, shooter["y"]),
        gym="adrian",
        frame=bgr,
    )
    assert got["free_throw"] is False
    assert got["ft_reason"] == "ft_line_not_found"


def test_band_counts_zero_one_and_two_players():
    mask = _ft_mask_with_lanes()
    shooter = _player(640.0, 520.0, 100.0)
    one = _decide(mask, [shooter], (640.0, shooter["y"]))
    assert one["free_throw"] is True
    assert one["ft_reason"] == "free_throw_line"

    # Near the line on the hoop side (keeps segments) but s ≈ -0.20 h, out of band.
    near_front = _player(640.0, 480.0, 100.0)
    zero = _decide(mask, [near_front], (640.0, near_front["y"]))
    assert zero["free_throw"] is False
    assert zero["ft_reason"] == "line_not_one"

    # Narrow boxes so Hough keeps line pieces past both players (L8 geometry).
    shooter_n = _player(640.0, 520.0, 100.0, w=20.0)
    other = _player(660.0, 525.0, 100.0, w=20.0)
    two = _decide(mask, [shooter_n, other], (640.0, shooter_n["y"]))
    assert two["free_throw"] is False
    assert two["ft_reason"] == "line_not_one"


def test_band_edges_spec42():
    line = _flat_line()
    hoop_xy = (640.0, 200.0)
    on_line = _player(640.0, 500.0, 100.0)
    assert ft.in_band(line, [on_line], 100.0, hoop_xy) == [on_line]
    at_back = _player(640.0, 535.0, 100.0)
    assert ft.in_band(line, [at_back], 100.0, hoop_xy) == [at_back]
    just_over = _player(640.0, 535.1, 100.0)
    assert ft.in_band(line, [just_over], 100.0, hoop_xy) == []
    hoop_side = _player(640.0, 499.0, 100.0)
    assert ft.in_band(line, [hoop_side], 100.0, hoop_xy) == []


def test_lane_pair_yields_free_throw_line():
    mask = _ft_mask_with_lanes()
    shooter = _player(640.0, 520.0, 100.0)
    got = _decide(mask, [shooter], (640.0, shooter["y"]), collect_debug=True)
    assert got["free_throw"] is True
    assert got["ft_reason"] == "free_throw_line"
    assert got["ft_shooter_box"] is not None
    view = got["views"][-1]
    assert view["hoop_dist_h"] is not None
    assert view["hoop_dist_h"] <= ft.HOOP_DIST_MAX
    assert any(seg[4] < 0 for seg in view["lane_segments"])
    assert any(seg[4] > 0 for seg in view["lane_segments"])


def test_lane_one_side_only_is_no_lane_lines():
    mask = _horizontal_mask()
    cv2.line(mask, (540, 450), (540, 490), 255, 3)
    shooter = _player(640.0, 520.0, 100.0)
    got = _decide(mask, [shooter], (640.0, shooter["y"]))
    assert got["free_throw"] is False
    assert got["ft_reason"] == "no_lane_lines"
    assert got["ft_shooter_box"] is None


def _two_cand_mask(lanes_first=True, lanes_second=True, second_one_side=False):
    """Separate FT paint; hoop-friendly vertical lane stubs per candidate."""
    mask = np.zeros((720, 1280), np.uint8)
    cv2.line(mask, (320, 500), (470, 500), 255, 3)
    cv2.line(mask, (530, 500), (680, 500), 255, 3)
    if lanes_first:
        cv2.line(mask, (350, 450), (350, 490), 255, 3)
        cv2.line(mask, (450, 450), (450, 490), 255, 3)
    if lanes_second:
        cv2.line(mask, (560, 450), (560, 490), 255, 3)
        if not second_one_side:
            cv2.line(mask, (650, 450), (650, 490), 255, 3)
    return mask


def test_next_candidate_after_no_lane_lines():
    # First candidate (box-key order) has an FT line but no lane stubs.
    # Second has lanes and passes. Hoop above mid so both feet->hoop keep
    # the horizontal FT segments (ANGLE_MIN); h=120 keeps hoop dist <= 3.8.
    mask = _two_cand_mask(lanes_first=False, lanes_second=True)
    first = _player(400.0, 520.0, 120.0, w=20.0)
    second = _player(600.0, 520.0, 120.0, w=20.0)
    hoop = _hoop(500.0, 120.0)
    alone_first = _decide(mask, [first], (400.0, first["y"]), hoop=hoop)
    assert alone_first["ft_reason"] == "no_lane_lines"
    alone_second = _decide(mask, [second], (600.0, second["y"]), hoop=hoop)
    assert alone_second["ft_reason"] == "free_throw_line"
    got = _decide(
        mask,
        [first, second],
        None,
        hoop=hoop,
        ball_points=[
            [75, first["x"], first["y"]],
            [75, second["x"], second["y"]],
        ],
    )
    assert got["free_throw"] is True
    assert got["ft_reason"] == "free_throw_line"
    assert got["ft_shooter_box"]["x"] == 600.0


def test_all_candidates_fail_returns_first_failure_reason():
    mask = _two_cand_mask(lanes_first=False, lanes_second=True, second_one_side=True)
    first = _player(400.0, 520.0, 120.0, w=20.0)
    second = _player(600.0, 520.0, 120.0, w=20.0)
    hoop = _hoop(500.0, 120.0)
    alone_first = _decide(mask, [first], (400.0, first["y"]), hoop=hoop)
    assert alone_first["ft_reason"] == "no_lane_lines"
    alone_second = _decide(mask, [second], (600.0, second["y"]), hoop=hoop)
    assert alone_second["ft_reason"] == "no_lane_lines"
    got = _decide(
        mask,
        [first, second],
        None,
        hoop=hoop,
        ball_points=[
            [75, first["x"], first["y"]],
            [75, second["x"], second["y"]],
        ],
    )
    assert got["free_throw"] is False
    assert got["ft_reason"] == "no_lane_lines"


def test_too_far_from_hoop_tries_next_candidate():
    # Separate FT paint so each candidate builds its own local line/extent.
    # Hoop above the first candidate: first is > 3.8 h away; second is taller
    # and passes (N1).
    mask = _two_cand_mask(lanes_first=True, lanes_second=True)
    far = _player(400.0, 520.0, 100.0, w=20.0)
    near = _player(600.0, 520.0, 150.0, w=20.0)
    hoop = _hoop(400.0, 100.0)
    alone = _decide(
        mask,
        [near],
        (600.0, near["y"]),
        hoop=hoop,
    )
    assert alone["ft_reason"] == "free_throw_line"
    got = _decide(
        mask,
        [far, near],
        None,
        hoop=hoop,
        ball_points=[
            [75, far["x"], far["y"]],
            [75, near["x"], near["y"]],
        ],
    )
    assert got["free_throw"] is True
    assert got["ft_reason"] == "free_throw_line"
    assert got["ft_shooter_box"]["x"] == 600.0


def test_release_check_pass_fail_skip_and_tie():
    mask = _ft_mask_with_lanes()
    shooter = _player(640.0, 520.0, 100.0)
    hold = [75, 640.0, shooter["y"]]
    # |dx| = 0.8 h exactly -> pass.
    pass_got = _decide(
        mask,
        [shooter],
        None,
        ball_points=[hold, [80, 640.0 + 80.0, shooter["y"]]],
        release_frame=80,
        collect_debug=True,
    )
    assert pass_got["ft_reason"] == "free_throw_line"
    assert pass_got["views"][-1]["release_checked"] is True
    assert pass_got["views"][-1]["release_dx_h"] == pytest.approx(0.8)
    # |dx| = 1.41 h -> release_not_shooter.
    fail_got = _decide(
        mask,
        [shooter],
        None,
        ball_points=[hold, [80, 640.0 + 141.0, shooter["y"]]],
        release_frame=80,
    )
    assert fail_got["free_throw"] is False
    assert fail_got["ft_reason"] == "release_not_shooter"
    # No release_frame -> check skipped (far ball ignored).
    skip_got = _decide(
        mask,
        [shooter],
        None,
        ball_points=[hold, [80, 640.0 + 141.0, shooter["y"]]],
        release_frame=None,
        collect_debug=True,
    )
    assert skip_got["ft_reason"] == "free_throw_line"
    assert skip_got["views"][-1]["release_checked"] is False
    # Tie in |frame - release_frame| -> earlier frame.
    tie = ft._nearest_ball_at_release(
        [[70, 100.0, 1.0], [90, 900.0, 1.0], [80, 500.0, 1.0]],
        80,
    )
    assert int(tie[0]) == 80
    tie2 = ft._nearest_ball_at_release(
        [[70, 111.0, 1.0], [90, 222.0, 1.0]],
        80,
    )
    assert int(tie2[0]) == 70
    assert float(tie2[1]) == 111.0


def test_release_not_shooter_then_next_candidate():
    mask = _two_cand_mask(lanes_first=True, lanes_second=True)
    first = _player(400.0, 520.0, 120.0, w=20.0)
    second = _player(600.0, 520.0, 120.0, w=20.0)
    hoop = _hoop(500.0, 120.0)
    # Hold both; release ball is > 0.8 h from first centre, near second.
    got = _decide(
        mask,
        [first, second],
        None,
        hoop=hoop,
        ball_points=[
            [75, first["x"], first["y"]],
            [75, second["x"], second["y"]],
            [80, 400.0 + 141.0, first["y"]],
        ],
        release_frame=80,
    )
    assert got["free_throw"] is True
    assert got["ft_reason"] == "free_throw_line"
    assert got["ft_shooter_box"]["x"] == 600.0


def test_stillness_maybe_band_and_old_still_path():
    mask = _ft_mask_with_lanes()
    shooter = _player(640.0, 520.0, 100.0)
    maybe = _decide(mask, [shooter], (640.0, shooter["y"]), stillness=0.2)
    assert maybe["free_throw"] is False
    assert maybe["ft_reason"] == "maybe_free_throw"
    assert maybe["ft_shooter_box"] is None
    assert maybe["ft_maybe_shooter_box"]["x"] == 640.0
    not_still = _decide(mask, [shooter], (640.0, shooter["y"]), stillness=0.3)
    assert not_still["ft_reason"] == "not_still"
    normal = _decide(mask, [shooter], (640.0, shooter["y"]), stillness=0.1)
    assert normal["free_throw"] is True
    assert normal["ft_reason"] == "free_throw_line"
    # Old still-bool path unchanged when stillness is omitted.
    old_false = _decide(mask, [shooter], (640.0, shooter["y"]), still=False)
    assert old_false["ft_reason"] == "not_still"
    old_true = _decide(mask, [shooter], (640.0, shooter["y"]), still=True)
    assert old_true["ft_reason"] == "free_throw_line"
    # Maybe band with a failing geometry -> not_still.
    mask_no_lane = _horizontal_mask()
    maybe_fail = _decide(
        mask_no_lane, [shooter], (640.0, shooter["y"]), stillness=0.2
    )
    assert maybe_fail["ft_reason"] == "not_still"


def test_far_side_segment_not_counted_as_lane():
    line = _flat_line()
    hoop_xy = (640.0, 200.0)
    feet = (640.0, 520.0)
    # Away-from-hoop (positive s) vertical stub; must not count.
    far_seg = [(740.0, 510.0, 740.0, 560.0)]
    left, right = ft.lane_crossings(
        line, feet, 100.0, hoop_xy, far_seg, None, "liberty", 1280.0
    )
    assert left == []
    assert right == []
    # Hoop-side pair still counts.
    good = [(540.0, 450.0, 540.0, 490.0), (740.0, 450.0, 740.0, 490.0)]
    left, right = ft.lane_crossings(
        line, feet, 100.0, hoop_xy, good, None, "liberty", 1280.0
    )
    assert left
    assert right


def test_one_in_band_but_not_a_candidate_is_line_not_one():
    mask = _horizontal_mask()
    # Candidate just on the hoop side of the line (near enough to keep segments,
    # s ≈ -0.20 h, outside the band). Only the other player sits in the band.
    holder = _player(640.0, 480.0, 100.0)
    in_band = _player(700.0, 520.0, 100.0)
    got = _decide(mask, [holder, in_band], (640.0, holder["y"]))
    assert got["free_throw"] is False
    assert got["ft_reason"] == "line_not_one"
    assert got["ft_shooter_box"] is None


def test_no_hoop_reason():
    mask = _horizontal_mask()
    shooter = _player(640.0, 520.0, 100.0)
    got = _decide(mask, [shooter], (640.0, shooter["y"]), hoop={})
    assert got["free_throw"] is False
    assert got["ft_reason"] == "no_hoop"
    got_none = _decide(mask, [shooter], (640.0, shooter["y"]), hoop=False)
    # hoop=False is not a dict -> no_hoop via _hoop_xy
    assert got_none["ft_reason"] == "no_hoop"


def test_not_still_untouched():
    mask = _horizontal_mask()
    shooter = _player(640.0, 520.0, 100.0)
    got = _decide(mask, [shooter], (640.0, shooter["y"]), still=False)
    assert got["free_throw"] is False
    assert got["ft_shooter_box"] is None
    assert got["ft_reason"] == "not_still"


def test_apply_ft_decision_reason_names():
    moment = {
        "status": "found",
        "reason": None,
        "shooter": "found",
        "shooter_reason": None,
        "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
        "floor_spot": {"x": 1.0, "y": 4.0},
    }
    rff._apply_ft_decision(
        moment,
        {
            "free_throw": True,
            "ft_shooter_box": {"frame": 75, "x": 10.0, "y": 20.0, "w": 30.0, "h": 40.0},
            "ft_reason": "free_throw_line",
        },
    )
    assert moment["free_throw"] is True
    assert moment["ft_reason"] == "free_throw_line"
    assert moment["shooter_reason"] == "free_throw_line"
    assert moment["status"] == "found"
    assert moment["reason"] is None
    assert moment["trace_shooter_box"]["x"] == 1.0

    orange = {
        "status": "found",
        "reason": None,
        "shooter": "found",
        "shooter_reason": None,
        "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
        "floor_spot": {"x": 1.0, "y": 4.0},
    }
    rff._apply_ft_decision(
        orange,
        {"free_throw": False, "ft_shooter_box": None, "ft_reason": "ft_line_not_found"},
    )
    assert orange["status"] == "orange"
    assert orange["reason"] == "ft_line_not_found"
    assert orange["shooter_reason"] == "ft_line_not_found"
    assert orange["shooter_box"]["x"] == 1.0

    line_not = {
        "status": "found",
        "reason": None,
        "shooter": "found",
        "shooter_reason": None,
        "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
        "floor_spot": {"x": 1.0, "y": 4.0},
    }
    rff._apply_ft_decision(
        line_not,
        {"free_throw": False, "ft_shooter_box": None, "ft_reason": "line_not_one"},
    )
    assert line_not["status"] == "found"
    assert line_not["reason"] is None
    assert line_not["shooter_box"]["x"] == 1.0
    assert line_not["ft_reason"] == "line_not_one"

    for new_reason in ("too_far_from_hoop", "no_lane_lines", "release_not_shooter"):
        keep = {
            "status": "found",
            "reason": None,
            "shooter": "found",
            "shooter_reason": None,
            "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
            "floor_spot": {"x": 1.0, "y": 4.0},
        }
        rff._apply_ft_decision(
            keep,
            {"free_throw": False, "ft_shooter_box": None, "ft_reason": new_reason},
        )
        assert keep["free_throw"] is False
        assert keep["ft_reason"] == new_reason
        assert keep["status"] == "found"
        assert keep["reason"] is None
        assert keep["shooter_box"]["x"] == 1.0
        assert keep["floor_spot"] == {"x": 1.0, "y": 4.0}

    maybe = {
        "status": "found",
        "reason": None,
        "shooter": "found",
        "shooter_reason": None,
        "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
        "floor_spot": {"x": 1.0, "y": 4.0},
    }
    rff._apply_ft_decision(
        maybe,
        {
            "free_throw": False,
            "ft_shooter_box": None,
            "ft_reason": "maybe_free_throw",
            "ft_maybe_shooter_box": {
                "frame": 75,
                "x": 10.0,
                "y": 20.0,
                "w": 30.0,
                "h": 40.0,
            },
        },
    )
    assert maybe["free_throw"] is False
    assert maybe["ft_reason"] == "maybe_free_throw"
    assert maybe["ft_maybe_shooter_box"]["x"] == 10.0
    assert maybe["flags"] == ["maybe_free_throw"]
    assert maybe["status"] == "found"
    assert maybe["reason"] is None
    assert maybe["shooter_box"]["x"] == 1.0
    assert maybe["floor_spot"] == {"x": 1.0, "y": 4.0}


def test_not_still_does_not_open_video_or_change_the_trace(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("video opened")

    monkeypatch.setattr(cv2, "VideoCapture", boom)
    frames = _sample_frames()
    players = _boxes(frames, lambda frame: 100.0 + (frame - 25) * 4.0)
    moment = {
        "frame": 100,
        "t_ms": 4000,
        "series": 0,
        "status": "found",
        "reason": None,
        "shooter": "found",
        "shooter_reason": None,
        "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
        "floor_spot": {"x": 1.0, "y": 4.0},
        "shot_call": "shot",
        "hoop": _hoop(),
        "release_frame": 80,
    }
    rff.annotate_free_throws(
        [moment],
        players,
        {},
        lambda _moment: [],
        25.0,
        Path("/tmp/not-a-video.mp4"),
        "adrian",
    )
    assert moment["status"] == "found"
    assert moment["shooter_box"]["x"] == 1.0
    assert moment["floor_spot"] == {"x": 1.0, "y": 4.0}
    assert moment["shooter_reason"] is None
    assert moment["free_throw"] is False
    assert moment["ft_reason"] == "not_still"
    assert "trace_shooter_box" not in moment


def test_annotate_stillness_over_maybe_max_skips_frame(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("video opened")

    monkeypatch.setattr(cv2, "VideoCapture", boom)
    monkeypatch.setattr(ft, "stillness", lambda *_a, **_k: 0.3)
    moment = {
        "frame": 100,
        "t_ms": 4000,
        "series": 0,
        "status": "found",
        "reason": None,
        "shooter": "found",
        "shooter_reason": None,
        "shooter_box": {"frame": 80, "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0},
        "floor_spot": {"x": 1.0, "y": 4.0},
        "shot_call": "shot",
        "hoop": _hoop(),
        "release_frame": 80,
    }
    rff.annotate_free_throws(
        [moment],
        {},
        {},
        lambda _moment: [],
        25.0,
        Path("/tmp/not-a-video.mp4"),
        "adrian",
    )
    assert moment["free_throw"] is False
    assert moment["ft_reason"] == "not_still"
    assert moment["shooter_box"]["x"] == 1.0


def test_ft_off_retrace_equals_the_input_trace(tmp_path):
    src = trf._spec39_saved_run(tmp_path / "src")
    moments_doc = json.loads((src / "moments.json").read_text(encoding="utf-8"))
    frames_doc = json.loads((src / "frames.json").read_text(encoding="utf-8"))
    traced, _series, differ = rff.retrace_moments(
        moments_doc["moments"],
        frames_doc["frames"],
        frames_doc["series"],
        float(moments_doc["fps"]),
        True,
        True,
        True,
    )
    assert differ is False
    moments_doc["moments"] = traced
    (src / "moments.json").write_text(
        json.dumps(moments_doc, indent=2) + "\n", encoding="utf-8"
    )
    out = tmp_path / "off"
    code = rff.main(
        [
            "--retrace-from",
            str(src),
            "--out-dir",
            str(out),
            "--ft-off",
            "--video",
            str(tmp_path / "missing.mp4"),
            "--gym",
            "adrian",
        ]
    )
    assert code == 0
    loaded = json.loads((out / "moments.json").read_text(encoding="utf-8"))
    assert loaded["moments"] == json.loads(json.dumps(traced))
    assert "free_throw" not in loaded["moments"][0]
    plain = tmp_path / "plain"
    plain_code = rff.main(
        ["--retrace-from", str(src), "--out-dir", str(plain)]
    )
    assert plain_code == 0
    plain_doc = json.loads((plain / "moments.json").read_text(encoding="utf-8"))
    assert plain_doc["moments"] == loaded["moments"]


def test_ft_debug_dir_is_refused_when_it_exists(tmp_path):
    src = trf._spec39_saved_run(tmp_path / "src")
    debug = tmp_path / "dbg"
    debug.mkdir()
    with pytest.raises(SystemExit):
        rff.main(
            [
                "--retrace-from",
                str(src),
                "--ft-debug-moments",
                "1,2",
                "--ft-debug-dir",
                str(debug),
                "--video",
                str(tmp_path / "missing.mp4"),
                "--gym",
                "liberty",
            ]
        )


def test_ft_section_found_missed_false_and_flagged():
    def moment(t_ms, free_throw=False, reason=None, status="found", ft_reason=None):
        return {
            "t_ms": t_ms,
            "frame": 10,
            "status": status,
            "reason": reason,
            "shot_call": "shot",
            "free_throw": free_throw,
            "ft_reason": ft_reason,
        }

    def tag(t_ms, kind):
        return {
            "t": t_ms,
            "quarter": "Q1",
            "eventtype": kind,
            "result": "Miss",
            "start": "0:00.0",
            "player": "A",
        }

    moments = [
        moment(10000, True, ft_reason="free_throw_line"),
        moment(20000, False, ft_reason="line_not_one"),
        moment(30000, True, ft_reason="free_throw_line"),
        moment(40000, False, reason="ft_line_not_found", status="orange", ft_reason="ft_line_not_found"),
        moment(50000, True, ft_reason="free_throw_line"),
        moment(60000, False, ft_reason="too_far_from_hoop"),
        moment(70000, False, ft_reason="no_lane_lines"),
        moment(80000, False, ft_reason="release_not_shooter"),
        moment(90000, False, ft_reason="maybe_free_throw"),
    ]
    tags = [
        tag(10000, "FT"),
        tag(20000, "FT"),
        tag(30000, "2PT"),
        tag(90000, "FT"),
    ]
    report = rfm.build_report(moments, tags, rfm.MATCH_WINDOW_MS, fps=25.0)
    ft_row = report["ft"]
    assert ft_row["found"] == 1
    assert ft_row["missed"] == 2
    assert ft_row["false"] == 1
    assert ft_row["orange_ft_line_not_found"] == 1
    assert ft_row["too_far_from_hoop"] == 1
    assert ft_row["no_lane_lines"] == 1
    assert ft_row["release_not_shooter"] == 1
    assert ft_row["maybe_free_throw"] == 1
    assert ft_row["flagged"] == [
        {"t_ms": 10000, "eventtype": "FT"},
        {"t_ms": 30000, "eventtype": "2PT"},
        {"t_ms": 50000, "eventtype": None},
    ]
    assert ft_row["maybe"] == [{"t_ms": 90000, "eventtype": "FT"}]
    assert ft_row["non_ft_flagged"] == [
        {"t_ms": 30000},
        {"t_ms": 50000},
    ]
    assert ft_row["duplicate_of_found_ft"] == []
    text = rfm.render_summary(report)
    assert "Free throw line" in text
    assert "ft_line_not_found" in text
    assert "too_far_from_hoop" in text
    assert "no_lane_lines" in text
    assert "release_not_shooter" in text
    assert "maybe_free_throw" in text
    assert "Maybe free throw moments" in text
    assert "90000 ms FT" in text
    assert "Non-FT moments flagged free_throw" in text
    assert "30000 ms" in text


def test_ft_section_duplicate_of_found_ft_not_counted_false():
    def moment(t_ms, free_throw=False, ft_reason=None):
        return {
            "t_ms": t_ms,
            "frame": 10,
            "status": "found",
            "reason": None,
            "shot_call": "shot",
            "free_throw": free_throw,
            "ft_reason": ft_reason,
        }

    def tag(t_ms, kind):
        return {
            "t": t_ms,
            "quarter": "Q1",
            "eventtype": kind,
            "result": "Make",
            "start": "0:00.0",
            "player": "A",
        }

    # 3021000 FT found; 3021480 flagged without FT tag (12 frames later) = duplicate.
    # 3100000 flagged 2PT far from any found FT = false.
    moments = [
        moment(3021000, True, "free_throw_line"),
        moment(3021480, True, "free_throw_line"),
        moment(3100000, True, "free_throw_line"),
    ]
    tags = [tag(3021000, "FT"), tag(3100000, "2PT")]
    report = rfm.build_report(moments, tags, rfm.MATCH_WINDOW_MS, fps=25.0)
    ft_row = report["ft"]
    assert ft_row["found"] == 1
    assert ft_row["false"] == 1
    assert ft_row["duplicate_of_found_ft"] == [{"t_ms": 3021480}]
    assert ft_row["non_ft_flagged"] == [{"t_ms": 3100000}]
    text = rfm.render_summary(report)
    assert "duplicate_of_found_ft" in text
    assert "3021480 ms" in text
