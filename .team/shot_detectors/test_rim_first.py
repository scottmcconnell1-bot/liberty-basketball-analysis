"""Pure tests for the rim-first finder. No video, no model."""
from __future__ import annotations

import ast
import inspect
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# is_make lives in collect_q4_bodd, which imports ultralytics at load.
# The function does not call it. Stub only when this interpreter has no install
# so the real is_make can be imported. No weights are loaded.
try:
    import ultralytics  # noqa: F401
except ModuleNotFoundError:
    _ultra = types.ModuleType("ultralytics")
    _ultra.YOLO = None  # type: ignore[attr-defined]
    sys.modules["ultralytics"] = _ultra

import collect_q4_bodd  # noqa: E402
import collect_flight_tracks as cft  # noqa: E402
import find_shots_measure as fsm  # noqa: E402
import rim_first_finder as rff  # noqa: E402
import rim_first_measure as rfm  # noqa: E402
import shot_rules_measure as srm  # noqa: E402

FINDER_PATH = HERE / "rim_first_finder.py"
HOOP = (960.0, 400.0, 98.0, 40.0)


def _v6_ball_oracle(boxes, x0, y0, hoop, prev):
    """collect_q4_bodd.v6_ball lines 129–145, literals 220 and 0.35."""
    hx, hy = hoop[0], hoop[1]
    picks = []
    for box in boxes:
        a, b, c, d = [float(v) for v in box]
        cx, cy = x0 + (a + c) / 2, y0 + (b + d) / 2
        if abs(cx - hx) > 220 or abs(cy - hy) > 220:
            continue
        dist = (cx - hx) ** 2 + (cy - hy) ** 2
        if prev is not None:
            dist += ((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) * 0.35
        picks.append((dist, cx, cy))
    if not picks:
        return None
    picks.sort()
    return picks[0][1], picks[0][2]


def _xyxy(px, py, x0, y0, side=5.0):
    cx = px - x0
    cy = py - y0
    return (cx - side, cy - side, cx + side, cy + side)


def _make_ball():
    """Drops through the hoop and falls 180 px: is_make's own shape."""
    hx, hy = HOOP[0], HOOP[1]
    return [
        (0, hx, hy - 20.0),
        (1, hx, hy + 20.0),
        (2, hx, hy + 100.0),
        (3, hx, hy + 180.0),
    ]


def _emit(series, balls=(), players=(), referees=(), film_hoop_w=None):
    if film_hoop_w is None:
        film_hoop_w = rff.ADRIAN_MEDIAN_HOOP_W
    return rff.emit_moments(
        series,
        balls,
        players,
        25.0,
        rff.MAKE_HALF,
        rff.MAKE_DROP_PX,
        rff.MAKE_GAP_FRAMES,
        rff.MISS_RIM_ZONE_WIDTHS,
        rff.ABOVE_HOOP_PX,
        rff.ABOVE_X_WIDTHS,
        rff.RIM_BAND_PX,
        rff.ADRIAN_MEDIAN_HOOP_W,
        rff.MAKE_GAP_FRAMES,
        rff.TRACE_BEFORE_MS,
        rff.RIM_R_PX,
        rff.RELEASE_TRACE_FACTOR,
        film_hoop_w,
        rff.HOOP_W_MIN_WIDTHS,
        rff.HOOP_W_MAX_WIDTHS,
        rff.MIN_SERIES_V6_POINTS,
        rff.SHOOT_AROUND_MIN_BALLS,
        rff.MISS_RIM_ZONE_WIDTHS,
        rff.SHOOT_AROUND_MIN_FRAMES,
        referees,
        True,
    )


def _miss(ball, hoop):
    return rff.miss_trigger_frame(
        ball,
        hoop,
        rff.MISS_RIM_ZONE_WIDTHS,
        rff.ABOVE_HOOP_PX,
        rff.ABOVE_X_WIDTHS,
        rff.RIM_BAND_PX,
        rff.ADRIAN_MEDIAN_HOOP_W,
        rff.MAKE_GAP_FRAMES,
    )


def test_constants_match_cited_sources():
    assert rff.BODD_CONF == 0.12
    assert rff.BODD_IMGSZ == 960
    assert rff.BODD_CLASSES == ("basketball", "hoop", "player")
    assert rff.V6_CROP_HX_PX == 260
    assert rff.V6_CROP_HY_ABOVE_PX == 200
    assert rff.V6_CROP_HY_BELOW_PX == 240
    assert rff.V6_CONF == 0.28
    assert rff.V6_IMGSZ == 640
    assert rff.V6_PICK_RADIUS_PX == 220
    assert rff.V6_CONTINUITY == 0.35
    assert rff.MAKE_HALF == 0.55
    assert rff.MAKE_DROP_PX == 180
    assert rff.MAKE_GAP_FRAMES == 8
    assert rff.ABOVE_X_WIDTHS == 2.2
    assert rff.ABOVE_HOOP_PX == 6
    assert rff.MISS_RIM_ZONE_WIDTHS == 0.735
    assert rff.RIM_BAND_PX == 40
    assert rff.ADRIAN_MEDIAN_HOOP_W == 98.0
    assert rff.RIM_R_PX == 72.0
    assert rff.TRACE_BEFORE_MS == 3000
    assert rff.RELEASE_TRACE_FACTOR == 0.6
    assert rff.HOOP_X_BUCKET_PX == 80
    assert "collect_q4_bodd.py:40" in FINDER_PATH.read_text(encoding="utf-8")
    assert rfm.MATCH_WINDOW_MS == 8000


def test_v6_pick_matches_v6_ball_choice_including_continuity():
    hx, hy = 500.0, 400.0
    hoop = (hx, hy, 98.0, 40.0)
    x0, y0 = hx - 260.0, hy - 200.0
    # 140 px from the hoop vs 160 px. Continuity at the farther ball flips the pick.
    near = _xyxy(640.0, 400.0, x0, y0)
    far = _xyxy(500.0, 560.0, x0, y0)
    outside = _xyxy(500.0 + 300.0, 400.0, x0, y0)
    boxes = [far, near, outside]

    no_prev = rff.v6_pick(boxes, x0, y0, hoop, None)
    assert no_prev == _v6_ball_oracle(boxes, x0, y0, hoop, None)
    assert no_prev == (640.0, 400.0)

    prev = (500.0, 560.0)
    with_prev = rff.v6_pick(boxes, x0, y0, hoop, prev)
    assert with_prev == _v6_ball_oracle(boxes, x0, y0, hoop, prev)
    assert with_prev == (500.0, 560.0)
    assert with_prev != no_prev

    assert rff.v6_pick([], x0, y0, hoop, None) is None
    assert rff.v6_pick([outside], x0, y0, hoop, prev) is None
    assert _v6_ball_oracle([outside], x0, y0, hoop, prev) is None


def test_run_splits_when_missing_more_than_8_frames():
    assert rff.MAKE_GAP_FRAMES == 8
    # frames 0 and 9: missing 1..8 (8 frames) stays one run
    assert len(rff.split_runs([(0, 1.0, 2.0), (9, 1.0, 2.0)], 8)) == 1
    # frames 0 and 10: missing 9 frames splits
    split = rff.split_runs([(0, 1.0, 2.0), (10, 1.0, 2.0)], 8)
    assert len(split) == 2
    assert [int(pt[0]) for pt in split[0]] == [0]
    assert [int(pt[0]) for pt in split[1]] == [10]
    three = rff.split_runs([(0, 0.0, 0.0), (5, 0.0, 0.0), (15, 0.0, 0.0)], 8)
    assert [[int(pt[0]) for pt in run] for run in three] == [[0, 5], [15]]


def test_make_trigger_uses_is_make_on_a_hand_track():
    ball = _make_ball()
    assert rff.is_make is collect_q4_bodd.is_make
    assert rff.is_make(ball, HOOP, 0.55, 180, 8) is True
    assert rff.make_trigger_frame(ball, HOOP, 0.55, 180, 8) == 3
    assert rff.is_make(ball[:2], HOOP, 0.55, 180, 8) is False
    assert rff.make_trigger_frame(ball[:2], HOOP, 0.55, 180, 8) is None


def test_miss_trigger_on_rim_and_not_on_the_two_rejects():
    hx, hy, hw, _hh = HOOP
    dropping = [(0, hx, hy - 20.0), (1, hx, hy)]
    assert _miss(dropping, HOOP) == 1

    never_above = [(0, hx, hy), (1, hx, hy)]
    assert _miss(never_above, HOOP) is None

    beside = [(0, hx, hy - 20.0), (1, hx + 0.8 * hw, hy)]
    assert _miss(beside, HOOP) is None
    assert rff.distance_hoop_widths(0.8 * hw, 0.0, hw) > 0.735

    # Index gap 9 hides the only above-hoop sample; gap 8 still sees it.
    hidden = [(0, hx, hy - 20.0)]
    hidden += [(i, hx + 3.0 * hw, hy + 100.0) for i in range(1, 9)]
    hidden.append((9, hx, hy))
    assert _miss(hidden, HOOP) is None
    seen = [(0, hx, hy - 20.0)]
    seen += [(i, hx + 3.0 * hw, hy + 100.0) for i in range(1, 8)]
    seen.append((8, hx, hy))
    assert _miss(seen, HOOP) == 8


def test_hoop_widths_equal_on_1920_and_1280_scaled_copies():
    scale = 1280.0 / 1920.0
    hx, hy, hw, hh = HOOP
    dx = 0.5 * hw
    assert abs(
        rff.distance_hoop_widths(dx, 0.0, hw)
        - rff.distance_hoop_widths(dx * scale, 0.0, hw * scale)
    ) < 1e-9
    assert abs(rff.distance_hoop_widths(dx, 0.0, hw) - 0.5) < 1e-9

    def scaled_hoop(s):
        return (hx * s, hy * s, hw * s, hh * s)

    def on_rim(s):
        # 30 px above still clears the 6 px test after * 1280/1920 (20 px).
        ball = [
            (0, hx * s, (hy - 30.0) * s),
            (1, hx * s, hy * s),
        ]
        return _miss(ball, scaled_hoop(s))

    def beside(s):
        ball = [
            (0, hx * s, (hy - 30.0) * s),
            (1, (hx + 0.8 * hw) * s, hy * s),
        ]
        return _miss(ball, scaled_hoop(s))

    assert on_rim(1.0) == 1
    assert on_rim(scale) == 1
    assert beside(1.0) is None
    assert beside(scale) is None


def test_one_moment_per_run_when_both_triggers_fire():
    ball = _make_ball()
    assert rff.is_make(ball, HOOP, 0.55, 180, 8) is True
    assert _miss(ball, HOOP) is not None
    hx, hy, hw, hh = HOOP
    series = [
        {
            "points": [(f, x, y, hx, hy, hw, hh) for f, x, y in ball],
            "hoop_samples": [],
            "ref_x": hx,
        }
    ]
    moments = _emit(series)
    assert len(moments) == 1
    assert moments[0]["kind_hint"] == "make"
    assert moments[0]["frame"] == 3
    assert moments[0]["t_ms"] == rff.frame_to_ms(3, 25.0)
    assert moments[0]["hoop"]["x"] == hx


def test_trace_finds_shooter_and_orange_without_players():
    fps = 25.0
    trigger = 120
    hoops = []
    for frame in (10, 80, 90, 120):
        hoops.append(
            {
                "t": rff.frame_to_ms(frame, fps),
                "x": 960.0,
                "y": 400.0,
                "w": 98.0,
                "h": 40.0,
            }
        )
    balls = [
        [10, 100.0, 100.0],
        [80, 500.0, 450.0],
        [90, 600.0, 300.0],
        [120, 960.0, 400.0],
    ]
    players = [
        {"frame": 10, "x": 100.0, "y": 100.0, "w": 80.0, "h": 80.0},
        {"frame": 80, "x": 550.0, "y": 450.0, "w": 100.0, "h": 80.0},
        {"frame": 90, "x": 600.0, "y": 300.0, "w": 100.0, "h": 80.0},
    ]
    found = rff.trace_shooter(
        balls,
        [],
        hoops,
        players,
        trigger,
        fps,
        rff.TRACE_BEFORE_MS,
        rff.RIM_R_PX,
        rff.RELEASE_TRACE_FACTOR,
        False,
    )
    assert found["status"] == "found"
    assert found["release_frame"] == 80
    assert found["shooter_box"]["frame"] == 80
    assert found["shooter_box"]["x"] == 550.0
    assert found["shooter_box"]["y"] == 450.0
    assert found["floor_spot"] == {"x": 550.0, "y": 490.0}
    assert found["trace_mode"] == "single_frame"
    assert found["reason"] is None
    assert rff.ball_inside_player is srm.ball_inside_player
    assert rff.release_estimate_frame is srm.release_estimate_frame

    orange = rff.trace_shooter(
        balls,
        [],
        hoops,
        [],
        trigger,
        fps,
        rff.TRACE_BEFORE_MS,
        rff.RIM_R_PX,
        rff.RELEASE_TRACE_FACTOR,
        False,
    )
    assert orange["status"] == "orange"
    assert orange["reason"] == "no player at release frame"
    assert orange["trace_mode"] == "single_frame"
    assert orange["shooter_box"] is None
    assert orange["floor_spot"] is None


def test_two_hoops_keep_separate_series():
    samples = [
        {"t": 0, "x": 200.0, "y": 400.0, "w": 98.0, "h": 40.0},
        {"t": 0, "x": 1600.0, "y": 410.0, "w": 90.0, "h": 36.0},
    ]
    detected = [
        {"x": 200.0, "y": 400.0, "w": 98.0, "h": 40.0, "ball": (210.0, 300.0)},
        {"x": 1600.0, "y": 410.0, "w": 90.0, "h": 36.0, "ball": (1610.0, 500.0)},
    ]
    assert rff.hoop_at is srm.hoop_at
    got = rff.resolve_frame_hoops(detected, samples, 0)
    assert [h["x"] for h in got] == [200.0, 1600.0]
    filled = rff.resolve_frame_hoops([], samples, 40)
    assert len(filled) == 1
    assert filled[0]["x"] == 200.0
    assert filled[0] is rff.hoop_at(samples, 40)

    frames = [
        {"frame": 0, "hoops": detected},
        {
            "frame": 1,
            "hoops": [
                {"x": 205.0, "y": 400.0, "w": 98.0, "h": 40.0, "ball": (208.0, 310.0)},
                {"x": 1595.0, "y": 410.0, "w": 90.0, "h": 36.0, "ball": (1590.0, 510.0)},
            ],
        },
        {
            "frame": 2,
            "hoops": [
                {"x": 198.0, "y": 400.0, "w": 98.0, "h": 40.0, "ball": (190.0, 320.0)},
            ],
        },
    ]
    series = rff.accumulate_series(frames)
    assert len(series) == 2
    left = min(series, key=lambda s: s["ref_x"])
    right = max(series, key=lambda s: s["ref_x"])
    assert [int(pt[0]) for pt in left["points"]] == [0, 1, 2]
    assert [int(pt[0]) for pt in right["points"]] == [0, 1]
    assert all(pt[1] < 500 for pt in left["points"])
    assert all(pt[1] > 1000 for pt in right["points"])


def _hoop(t, x, y, w=98.0, h=40.0):
    return {"t": t, "x": x, "y": y, "w": w, "h": h}


def test_hoop_carry_matches_hoop_at_including_before_first():
    samples = [
        _hoop(2000, 200.0, 400.0),
        _hoop(2000, 1600.0, 410.0),
        _hoop(5000, 210.0, 401.0),
        _hoop(5000, 1590.0, 10.0),
        _hoop(8000, 205.0, 402.0),
    ]
    carry = rff.build_hoop_carry(samples)
    for t_ms in (0, 2000, 3000, 5000, 7000, 8000, 9000, 1000):
        assert rff.hoop_from_carry(carry, t_ms) is rff.hoop_at(samples, t_ms)
        assert rff.resolve_frame_hoops([], samples, t_ms)[0] is rff.hoop_at(samples, t_ms)
    # Before the first sample: first row of the first later time, one hoop.
    assert rff.hoop_from_carry(carry, 0) is samples[0]
    assert rff.resolve_frame_hoops([], samples, 0)[0]["x"] == 200.0
    # Exact time keeps hoop_at's last row. A later empty frame keeps the first.
    assert rff.hoop_at(samples, 2000) is samples[1]
    assert rff.hoop_at(samples, 3000) is samples[0]


def test_duplicate_hoop_boxes_one_series_per_end():
    assert int(200 // rff.HOOP_X_BUCKET_PX) == int(230 // rff.HOOP_X_BUCKET_PX)
    assert int(200 // rff.HOOP_X_BUCKET_PX) != int(1700 // rff.HOOP_X_BUCKET_PX)
    frames = [
        {
            "frame": 0,
            "hoops": [
                {
                    "x": 200.0,
                    "y": 400.0,
                    "w": 98.0,
                    "h": 40.0,
                    "c": 0.2,
                    "ball": (200.0, 300.0),
                },
                {
                    "x": 230.0,
                    "y": 405.0,
                    "w": 90.0,
                    "h": 36.0,
                    "c": 0.91,
                    "ball": (230.0, 310.0),
                },
                {
                    "x": 1700.0,
                    "y": 410.0,
                    "w": 90.0,
                    "h": 36.0,
                    "c": 0.5,
                    "ball": (1700.0, 500.0),
                },
            ],
        }
    ]
    series = rff.accumulate_series(frames)
    assert len(series) == 2
    left = min(series, key=lambda s: s["ref_x"])
    right = max(series, key=lambda s: s["ref_x"])
    assert left["ref_x"] == 230.0
    assert left["points"][0][1] == 230.0
    assert right["ref_x"] == 1700.0
    assert [int(pt[0]) for pt in right["points"]] == [0]


def _trace_call(
    balls,
    v6,
    hoops,
    players,
    trigger,
    fps,
    walk_back=False,
    fix_ref=True,
    fix_merge=True,
    refs_by_frame=None,
    players_by_frame=None,
):
    return rff.trace_shooter(
        balls,
        v6,
        hoops,
        players,
        trigger,
        fps,
        rff.TRACE_BEFORE_MS,
        rff.RIM_R_PX,
        rff.RELEASE_TRACE_FACTOR,
        walk_back,
        fix_ref,
        fix_merge,
        players_by_frame,
        refs_by_frame,
    )


def test_trace_window_matches_unsliced_hand_track():
    fps = 25.0
    trigger = 200
    t124 = rff.frame_to_ms(124, fps)
    carry = _hoop(t124, 960.0, 400.0)
    carry_other = _hoop(t124, 100.0, 900.0)
    rise_hoop = _hoop(rff.frame_to_ms(160, fps), 960.0, 900.0)
    hoops = [
        _hoop(rff.frame_to_ms(10, fps), 960.0, 0.0),
        carry,
        carry_other,
        rise_hoop,
        _hoop(rff.frame_to_ms(400, fps), 960.0, 0.0),
    ]
    bodd = [
        [10, 100.0, 100.0, 0.99],
        [124, 100.0, 100.0, 0.99],
        [125, 500.0, 450.0, 0.1],
        [140, 100.0, 100.0, 0.99],
        [150, 560.0, 430.0, 0.2],
        [160, 600.0, 300.0, 0.2],
        [200, 960.0, 400.0, 0.2],
        [201, 100.0, 100.0, 0.99],
    ]
    v6 = [
        (10, 100.0, 50.0),
        (140, 500.0, 450.0),
        (150, 560.0, 430.0),
        (160, 600.0, 300.0),
        (200, 960.0, 400.0),
    ]
    players = [
        {"frame": 10, "x": 100.0, "y": 100.0, "w": 40.0, "h": 40.0},
        {"frame": 150, "x": 560.0, "y": 430.0, "w": 100.0, "h": 100.0},
        {"frame": 201, "x": 100.0, "y": 100.0, "w": 40.0, "h": 40.0},
    ]
    ball_frames, balls_by = rff.index_by_frame(bodd, lambda pt: int(pt[0]))
    player_frames, players_by = rff.index_by_frame(
        players, lambda box: int(box["frame"])
    )
    hoop_times, hoops_by = rff.index_hoop_samples(hoops)
    v6_frames, v6_by = rff.index_by_frame(v6, lambda pt: int(pt[0]))
    win_balls, win_hoops, win_players, win_v6 = rff.slice_trace_window(
        ball_frames,
        balls_by,
        player_frames,
        players_by,
        hoop_times,
        hoops_by,
        v6_frames,
        v6_by,
        trigger,
        fps,
        rff.TRACE_BEFORE_MS,
    )
    assert sorted(int(pt[0]) for pt in win_balls) == [125, 140, 150, 160, 200]
    assert sorted(int(pt[0]) for pt in win_v6) == [140, 150, 160, 200]
    assert [int(box["frame"]) for box in win_players] == [150]
    assert win_hoops[0] is carry
    assert [h["t"] for h in win_hoops] == [t124, rise_hoop["t"]]
    assert carry_other not in win_hoops
    full = _trace_call(bodd, v6, hoops, players, trigger, fps)
    sliced = _trace_call(win_balls, win_v6, win_hoops, win_players, trigger, fps)
    assert sliced == full
    assert sliced["status"] == "found"
    assert sliced["release_frame"] == 150
    assert sliced["shooter_box"]["x"] == 560.0


def test_trace_v6_beats_spare_bodd_ball():
    fps = 25.0
    trigger = 120
    hoops = [_hoop(rff.frame_to_ms(80, fps), 960.0, 400.0)]
    bodd = [
        [80, 100.0, 100.0, 0.95],
        [100, 600.0, 300.0, 0.4],
        [120, 960.0, 400.0, 0.4],
    ]
    v6 = [(80, 500.0, 450.0), (100, 600.0, 300.0), (120, 960.0, 400.0)]
    players = [
        {"frame": 80, "x": 100.0, "y": 100.0, "w": 40.0, "h": 40.0},
        {"frame": 80, "x": 550.0, "y": 450.0, "w": 100.0, "h": 100.0},
    ]
    with_v6 = _trace_call(bodd, v6, hoops, players, trigger, fps)
    no_v6 = _trace_call(bodd, [], hoops, players, trigger, fps)
    assert with_v6["status"] == "found"
    assert with_v6["release_frame"] == 80
    assert with_v6["shooter_box"]["x"] == 550.0
    assert no_v6["status"] == "found"
    assert no_v6["release_frame"] == 80
    assert no_v6["shooter_box"]["x"] == 100.0
    combined = rff.combine_ball_track(v6, bodd)
    assert combined[0][1] == 500.0
    assert combined[0][2] == 450.0


def _imported_names(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
                if alias.asname:
                    names.append(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
            for alias in node.names:
                names.append(alias.name)
                if alias.asname:
                    names.append(alias.asname)
    return names


def test_finder_imports_nothing_that_reads_tags_or_db():
    names = _imported_names(FINDER_PATH)
    banned = (
        "film_tags",
        "sqlite3",
        "find_shots_measure",
        "load_shot_tags",
        "scoreboard",
        "collect_flight_tracks",
        "rim_first_measure",
    )
    for name in names:
        low = name.lower()
        for item in banned:
            assert item not in low, name
    assert "is_make" in names
    assert "hoop_at" in names
    assert "combine_ball_track" in names
    assert "release_estimate_frame" in names
    assert "ball_inside_player" in names
    assert rff.is_make is collect_q4_bodd.is_make
    assert rff.combine_ball_track is srm.combine_ball_track


def test_measure_filters_adrian_q4_first():
    assert rfm.filter_out_q4 is cft.filter_out_q4
    assert rfm.load_shot_tags is cft.load_shot_tags
    assert rfm.match_shots is fsm.match_shots
    tags = [
        {
            "t": 1000,
            "quarter": "Q1",
            "eventtype": "3PT",
            "result": "Miss",
            "start": "0:01.0",
            "player": "A",
        },
        {
            "t": 50000,
            "quarter": "Q4",
            "eventtype": "FT",
            "result": "Make",
            "start": "55:20.0",
            "player": "B",
        },
        {
            "t": 80000,
            "quarter": "Q2",
            "eventtype": "2PT",
            "result": "Make",
            "start": "20:00.0",
            "player": "C",
        },
    ]
    moments = [
        {"t_ms": 1000, "status": "found", "kind_hint": "make", "frame": 25},
        {"t_ms": 50000, "status": "orange", "kind_hint": "rim", "frame": 1250},
    ]
    report = rfm.build_report(moments, tags, rfm.MATCH_WINDOW_MS)
    assert report["n_q4_removed"] == 1
    assert report["n_tags"] == 2
    assert report["by_kind"]["3PT"]["found"] == 1
    assert report["by_kind"]["3PT"]["missed"] == 0
    assert report["by_kind"]["FT"]["found"] == 0
    assert report["by_kind"]["FT"]["missed"] == 0
    assert report["by_kind"]["2PT"]["missed"] == 1
    assert report["by_kind"]["all"]["found"] == 1
    assert report["by_kind"]["all"]["missed"] == 1
    assert report["by_kind"]["all"]["extra"] == 1
    assert report["by_kind"]["3PT"]["median_abs_delta_ms"] == 0
    assert report["by_kind"]["3PT"]["max_abs_delta_ms"] == 0
    assert report["extras"][0]["t_ms"] == 50000
    assert report["misses"][0]["t_ms"] == 80000
    assert report["trace_found"] == 1
    assert report["orange_count"] == 1
    text = rfm.render_summary(report)
    assert "50000" in text
    assert "80000" in text
    assert "3PT" in text
    assert "Orange count" in text

    at_window = rfm.build_report(
        [{"t_ms": 8000, "status": "found"}],
        [{"t": 0, "quarter": "Q1", "eventtype": "2PT", "result": "Miss"}],
        8000,
    )
    past_window = rfm.build_report(
        [{"t_ms": 8001, "status": "found"}],
        [{"t": 0, "quarter": "Q1", "eventtype": "2PT", "result": "Miss"}],
        8000,
    )
    assert at_window["by_kind"]["all"]["found"] == 1
    assert past_window["by_kind"]["all"]["found"] == 0
    assert past_window["by_kind"]["all"]["extra"] == 1
    assert past_window["by_kind"]["2PT"]["missed"] == 1


def test_out_dir_refuses_if_it_exists(tmp_path):
    fresh = tmp_path / "new-out"
    rff.refuse_existing_out_dir(fresh)
    rfm.refuse_existing_out_dir(fresh)
    existing = tmp_path / "already"
    existing.mkdir()
    for refuse in (rff.refuse_existing_out_dir, rfm.refuse_existing_out_dir):
        raised = False
        try:
            refuse(existing)
        except SystemExit as exc:
            raised = True
            assert "Refuse" in str(exc)
        assert raised


def test_moments_json_omits_frames_and_frames_json_is_compact(tmp_path):
    doc = {
        "video": "v.mp4",
        "start_ms": 0,
        "end_ms": 1000,
        "frames_read": 2,
        "fps": 25.0,
        "size": {"width": 1920, "height": 1080},
        "moments": [{"frame": 3, "t_ms": 120}],
        "frames": [{"f": 3, "b": [[1, 2, 3, 4, 0.5]], "h": [], "p": []}],
        "applied_to_core": False,
        "run_time_s": 1.5,
    }
    moments_path, frames_path = rff.write_span_outputs(tmp_path, doc)
    raw_moments = moments_path.read_text(encoding="utf-8")
    raw_frames = frames_path.read_text(encoding="utf-8")
    loaded = json.loads(raw_moments)
    assert "frames" not in loaded
    assert loaded["moments"] == doc["moments"]
    assert loaded["video"] == "v.mp4"
    assert "\n  " in raw_moments
    assert raw_frames == json.dumps(doc["frames"], separators=(",", ":"))
    assert "\n" not in raw_frames
    span = inspect.getsource(rff.detect_span)
    assert "hoop_at(" not in span
    assert "build_hoop_carry" in span
    assert "ESTIMATE" in span
    assert "done == 500" in span
    assert "slice_trace_window" in inspect.getsource(rff.emit_moments)
    assert rff.both_passes_estimate_s(10.0, 500, 83000) == 10.0 * 2.0 * 83000 / 500.0


def _moment(frame, series=0, kind="make", fps=25.0):
    return {
        "frame": frame,
        "t_ms": rff.frame_to_ms(frame, fps),
        "series": series,
        "kind_hint": kind,
        "status": "found",
        "reason": None,
    }


def _box(frame, x, y, w=100.0, h=100.0):
    return {"frame": frame, "x": x, "y": y, "w": w, "h": h}


def _assign(
    moments,
    series_ok,
    balls=(),
    refs=(),
    players=(),
    v6=None,
    fps=25.0,
    film_hoop_w=None,
    same_hoop_widths=None,
    gap=None,
    min_frames=None,
):
    if v6 is None:
        v6 = [[] for _ in series_ok]
    if film_hoop_w is None:
        film_hoop_w = rff.ADRIAN_MEDIAN_HOOP_W
    if same_hoop_widths is None:
        same_hoop_widths = rff.MISS_RIM_ZONE_WIDTHS
    if gap is None:
        gap = rff.MAKE_GAP_FRAMES
    if min_frames is None:
        min_frames = rff.SHOOT_AROUND_MIN_FRAMES
    return rff.assign_shot_calls(
        moments,
        series_ok,
        balls,
        refs,
        players,
        v6,
        fps,
        rff.RELEASE_TRACE_FACTOR,
        rff.TRACE_BEFORE_MS,
        rff.SHOOT_AROUND_MIN_BALLS,
        film_hoop_w,
        same_hoop_widths,
        gap,
        min_frames,
    )


def test_hoop_series_ok_size_traffic_and_kept_bounds():
    assert rff.HOOP_W_MIN_WIDTHS == 0.5
    assert rff.HOOP_W_MAX_WIDTHS == 1.5
    assert rff.MIN_SERIES_V6_POINTS == 3
    assert rff.SHOOT_AROUND_MIN_BALLS == 3
    assert rff.SHOOT_AROUND_MIN_FRAMES == 12
    assert "Scott decided 2026-11-06, spec 37" in FINDER_PATH.read_text(encoding="utf-8")
    assert not hasattr(rff, "FOUL_REF_WINDOW_MS")
    assert rfm.EXTRA_MATCH_WINDOW_MS == 1500
    text = FINDER_PATH.read_text(encoding="utf-8")
    assert text.count("spec 36 K8, Scott approved 2026-11-05") >= 4
    assert "merge_window" not in text
    w_min, w_max, min_points = 0.5, 1.5, 3
    too_small = rff.hoop_series_ok(40.0, 98.0, 5, w_min, w_max, min_points)
    too_big = rff.hoop_series_ok(200.0, 98.0, 5, w_min, w_max, min_points)
    too_few = rff.hoop_series_ok(98.0, 98.0, 2, w_min, w_max, min_points)
    ok = rff.hoop_series_ok(98.0, 98.0, 3, w_min, w_max, min_points)
    assert too_small == (False, "not_a_hoop_size")
    assert too_big == (False, "not_a_hoop_size")
    assert too_few == (False, "not_a_hoop_traffic")
    assert ok == (True, None)
    # Equal to either width bound is still ok. Both failures report size.
    assert rff.hoop_series_ok(49.0, 98.0, 3, w_min, w_max, min_points)[0] is True
    assert rff.hoop_series_ok(147.0, 98.0, 3, w_min, w_max, min_points)[0] is True
    assert rff.hoop_series_ok(20.0, 98.0, 1, w_min, w_max, min_points) == (
        False,
        "not_a_hoop_size",
    )
    # No hoop_samples width cannot pass the size check.
    assert rff.hoop_series_ok(None, 98.0, 5, w_min, w_max, min_points) == (
        False,
        "not_a_hoop_size",
    )
    raw = [
        {
            "hoops": [
                {"x": 200.0, "y": 1.0, "w": 50.0, "h": 10.0, "c": 0.2},
                {"x": 230.0, "y": 1.0, "w": 90.0, "h": 10.0, "c": 0.9},
                {"x": 1700.0, "y": 1.0, "w": 110.0, "h": 10.0, "c": 0.5},
            ]
        }
    ]
    assert rff.film_median_hoop_w(raw) == 100.0
    series = [
        {
            "ref_x": 10.0,
            "hoop_samples": [{"w": 20.0}],
            "points": [(1, 2.0, 3.0)],
        }
    ]
    row = rff.series_payload(series, 98.0, w_min, w_max, min_points)[0]
    assert row["kept"] is False
    assert row["drop_reason"] == "not_a_hoop_size"
    assert row["n_v6_points"] == 1
    assert row["points"] == [[1, 2.0, 3.0]]
    assert row["median_hoop_w"] == 20.0


def test_not_ok_series_keeps_the_moment_and_does_not_trace():
    ball = _make_ball()
    hx, hy, hw, hh = HOOP
    series = [
        {
            "points": [(f, x, y, hx, hy, hw, hh) for f, x, y in ball],
            "hoop_samples": [{"t": 0, "x": hx, "y": hy, "w": 20.0, "h": 8.0}],
            "ref_x": hx,
        }
    ]
    moments = _emit(series)
    assert len(moments) == 1
    moment = moments[0]
    assert moment["kind_hint"] == "make"
    assert moment["shot_call"] == "not_a_shot"
    assert moment["shot_reason"] == "not_a_hoop"
    assert moment["status"] == "orange"
    assert moment["reason"] == "not_a_hoop"
    assert moment["shooter"] == "orange"
    assert moment["shooter_reason"] == "not_a_hoop"
    assert moment["shooter_box"] is None
    assert moment["release_frame"] is None
    assert moment["flags"] == ["not_a_hoop"]


def test_ok_series_still_traces_and_calls_a_shot():
    ball = _make_ball()
    hx, hy, hw, hh = HOOP
    series = [
        {
            "points": [(f, x, y, hx, hy, hw, hh) for f, x, y in ball],
            "hoop_samples": [{"t": 0, "x": hx, "y": hy, "w": hw, "h": hh}],
            "ref_x": hx,
        }
    ]
    moment = _emit(series)[0]
    assert moment["shot_call"] == "shot"
    assert moment["shot_reason"] is None
    assert moment["flags"] == []
    assert moment["run_first_frame"] == ball[0][0]
    assert moment["run_last_frame"] == ball[-1][0]
    assert moment["status"] == "orange"
    assert moment["reason"] != "not_a_hoop"
    assert moment["shooter"] == moment["status"]
    assert moment["shooter_reason"] == moment["reason"]


def test_referee_only_frame_is_saved_apart_from_players():
    row = rff._compact_frame(
        4, [], [], [], [{"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0, "c": 0.5}]
    )
    assert row == {
        "f": 4,
        "b": [],
        "h": [],
        "p": [],
        "r": [[1.0, 2.0, 3.0, 4.0, 0.5]],
    }
    assert rff._compact_frame(4, [], [], [], []) is None


def test_same_shot_merged_unless_a_player_holds_the_ball_between():
    bare = [_moment(100), _moment(200), _moment(150, series=1)]
    _assign(bare, [True, True])
    assert bare[0]["shot_call"] == "shot"
    assert bare[0]["shot_reason"] is None
    assert "merged_into_frame" not in bare[0]
    assert bare[1]["shot_call"] == "not_a_shot"
    assert bare[1]["shot_reason"] == "same_shot_merged"
    assert bare[1]["merged_into_frame"] == 100
    assert bare[1]["flags"] == ["same_shot_merged"]
    assert bare[2]["shot_call"] == "shot"
    assert bare[2]["flags"] == []

    held = [_moment(100), _moment(200)]
    _assign(
        held,
        [True],
        players=[_box(150, 500.0, 400.0)],
        v6=[[[150, 500.0, 400.0]]],
    )
    assert [m["shot_call"] for m in held] == ["shot", "shot"]
    assert held[1]["flags"] == []

    on_trigger = [_moment(100), _moment(200)]
    _assign(
        on_trigger,
        [True],
        players=[_box(100, 500.0, 400.0), _box(200, 500.0, 400.0)],
        v6=[[[100, 500.0, 400.0], [200, 500.0, 400.0]]],
    )
    assert on_trigger[1]["shot_call"] == "not_a_shot"
    assert on_trigger[1]["shot_reason"] == "same_shot_merged"
    assert on_trigger[1]["merged_into_frame"] == 100


def _balls_on(frames, n=3):
    balls = []
    for frame in frames:
        for i in range(n):
            balls.append([frame, float(i), float(i), 0.5])
    return balls


def test_referee_boxes_present_no_longer_change_shot_call():
    """A referee box holding the ball used to change the call. It does not."""
    holding = [_moment(100, kind="rim")]
    _assign(
        holding,
        [True],
        refs=[_box(100, 0.0, 0.0)],
        v6=[[[100, 0.0, 0.0]]],
    )
    bare = [_moment(100, kind="rim")]
    _assign(bare, [True], v6=[[[100, 0.0, 0.0]]])
    assert holding[0]["shot_call"] == bare[0]["shot_call"] == "shot"
    assert holding[0]["flags"] == []
    assert "referee_holding" not in holding[0]["flags"]

    # Ball inside a referee box after the trigger, the old fouled-miss shape.
    after = [_moment(100, kind="rim")]
    _assign(
        after,
        [True],
        balls=[[125, 0.0, 0.0]],
        refs=[_box(125, 0.0, 0.0)],
    )
    assert after[0]["shot_call"] == "shot"
    assert after[0]["flags"] == []
    assert after[0]["shot_reason"] is None


def test_shoot_around_counts_bodd_balls_in_the_lookback():
    # One frame with three balls is not 12. Two balls on a frame never count.
    one = [_moment(100)]
    _assign(
        one,
        [True],
        balls=[[50, 1.0, 1.0], [50, 2.0, 2.0], [50, 3.0, 3.0]],
    )
    assert one[0]["shot_call"] == "shot"
    assert one[0]["flags"] == []

    two = [_moment(100)]
    _assign(two, [True], balls=[[50, 1.0, 1.0], [50, 2.0, 2.0]])
    assert two[0]["shot_call"] == "shot"
    assert two[0]["flags"] == []

    # fps 25 -> 40 ms/frame. Trigger 200 is 8000 ms. Window is [5000, 8000].
    trigger = 200
    inside = list(range(125, 125 + rff.SHOOT_AROUND_MIN_FRAMES - 1))
    assert len(inside) == 11
    eleven = [_moment(trigger)]
    _assign(eleven, [True], balls=_balls_on(inside))
    assert eleven[0]["shot_call"] == "shot"
    assert eleven[0]["flags"] == []

    twelve_frames = list(range(125, 125 + rff.SHOOT_AROUND_MIN_FRAMES))
    assert len(twelve_frames) == 12
    twelve = [_moment(trigger)]
    _assign(twelve, [True], balls=_balls_on(twelve_frames))
    assert twelve[0]["shot_call"] == "orange"
    assert twelve[0]["shot_reason"] == "possible_shoot_around"
    assert twelve[0]["flags"] == ["possible_shoot_around"]

    # Twelve frames of three balls after the trigger stay a shot.
    after_frames = list(range(trigger + 1, trigger + 1 + rff.SHOOT_AROUND_MIN_FRAMES))
    after = [_moment(trigger)]
    _assign(after, [True], balls=_balls_on(after_frames))
    assert after[0]["shot_call"] == "shot"
    assert after[0]["flags"] == []


def _hoop_moment(frame, series, hx, hy, run_first, run_last):
    moment = _moment(frame, series=series)
    moment["hoop"] = {"x": hx, "y": hy, "w": 98.0, "h": 40.0}
    moment["run_first_frame"] = run_first
    moment["run_last_frame"] = run_last
    return moment


def test_cross_series_same_shot_and_run_gap():
    film_w = rff.ADRIAN_MEDIAN_HOOP_W
    # Overlapping runs, same hoop: the later moment merges into the earlier.
    close = [
        _hoop_moment(100, 0, 500.0, 400.0, 90, 110),
        _hoop_moment(120, 1, 500.0, 400.0, 100, 140),
    ]
    _assign(close, [True, True], film_hoop_w=film_w)
    assert close[0]["shot_call"] == "shot"
    assert close[1]["shot_call"] == "not_a_shot"
    assert close[1]["shot_reason"] == "same_shot_merged"
    assert close[1]["merged_into_frame"] == 100
    assert close[1]["flags"] == ["same_shot_merged"]

    # One film-hoop width apart is a different hoop.
    apart = [
        _hoop_moment(100, 0, 500.0, 400.0, 90, 110),
        _hoop_moment(120, 1, 500.0 + film_w, 400.0, 100, 140),
    ]
    _assign(apart, [True, True], film_hoop_w=film_w)
    assert apart[1]["shot_call"] == "shot"
    assert apart[1]["flags"] == []
    assert "merged_into_frame" not in apart[1]

    # Runs 9 frames apart do not merge. 8 frames apart do. gap is 8.
    far_runs = [
        _hoop_moment(100, 0, 500.0, 400.0, 90, 100),
        _hoop_moment(130, 1, 500.0, 400.0, 109, 140),
    ]
    _assign(far_runs, [True, True], film_hoop_w=film_w)
    assert far_runs[1]["shot_call"] == "shot"
    assert far_runs[1]["flags"] == []

    near_runs = [
        _hoop_moment(100, 0, 500.0, 400.0, 90, 100),
        _hoop_moment(130, 1, 500.0, 400.0, 108, 140),
    ]
    _assign(near_runs, [True, True], film_hoop_w=film_w)
    assert near_runs[1]["shot_call"] == "not_a_shot"
    assert near_runs[1]["merged_into_frame"] == 100

    # B matches A, C matches B only. C's merged_into_frame is A's trigger.
    chain = [
        _hoop_moment(100, 0, 0.0, 400.0, 90, 150),
        _hoop_moment(120, 1, 60.0, 400.0, 100, 150),
        _hoop_moment(140, 2, 120.0, 400.0, 110, 150),
    ]
    _assign(chain, [True, True, True], film_hoop_w=film_w)
    assert chain[1]["merged_into_frame"] == 100
    assert chain[2]["shot_call"] == "not_a_shot"
    assert chain[2]["shot_reason"] == "same_shot_merged"
    assert chain[2]["merged_into_frame"] == 100


def test_width_band_and_same_hoop_collapse_before_a_series():
    normal = {"x": 200.0, "y": 400.0, "w": 100.0, "h": 40.0, "c": 0.8}
    wide = {"x": 900.0, "y": 400.0, "w": 170.0, "h": 40.0, "c": 0.95}
    raw = [
        {"frame": 0, "hoops": [dict(normal)]},
        {"frame": 1, "hoops": [dict(normal)]},
        {"frame": 2, "hoops": [dict(normal), dict(wide)]},
    ]
    film_w = rff.film_median_hoop_w(raw)
    assert film_w == 100.0
    assert wide["w"] / film_w == 1.7
    kept_raw = []
    for fr in raw:
        original = fr["hoops"]
        kept = rff.filter_frame_hoops(
            original,
            film_w,
            rff.HOOP_W_MIN_WIDTHS,
            rff.HOOP_W_MAX_WIDTHS,
            rff.MISS_RIM_ZONE_WIDTHS,
        )
        assert 170.0 not in [h["w"] for h in kept]
        kept_raw.append({"frame": fr["frame"], "hoops": kept})
    assert rff.kept_hoop_indices(raw[2]["hoops"], kept_raw[2]["hoops"]) == [0]
    samples = rff._hoop_samples_from_raw(kept_raw, 25.0)
    assert samples
    assert all(row["w"] != 170.0 and row["x"] != 900.0 for row in samples)
    carry = rff.build_hoop_carry(samples)
    assert all(row["w"] != 170.0 for row in carry["first"].values())
    series = rff.accumulate_series(
        [
            {
                "frame": fr["frame"],
                "hoops": [{**h, "ball": (h["x"], h["y"] - 80.0)} for h in fr["hoops"]],
            }
            for fr in kept_raw
        ]
    )
    assert len(series) == 1
    assert series[0]["ref_x"] == 200.0
    only_wide = rff.filter_frame_hoops(
        [dict(wide)],
        film_w,
        rff.HOOP_W_MIN_WIDTHS,
        rff.HOOP_W_MAX_WIDTHS,
        rff.MISS_RIM_ZONE_WIDTHS,
    )
    assert only_wide == []
    assert rff.accumulate_series([{"frame": 3, "hoops": only_wide}]) == []
    assert rff._hoop_samples_from_raw([{"frame": 3, "hoops": only_wide}], 25.0) == []
    # None skips the band and the collapse: both boxes survive dedupe.
    unfiltered = rff.filter_frame_hoops(
        [dict(normal), dict(wide)],
        None,
        rff.HOOP_W_MIN_WIDTHS,
        rff.HOOP_W_MAX_WIDTHS,
        rff.MISS_RIM_ZONE_WIDTHS,
    )
    assert len(unfiltered) == 2
    span = inspect.getsource(rff.detect_span)
    assert span.index("_compact_frame") < span.index("film_median_hoop_w")
    assert span.index("film_median_hoop_w") < span.index("filter_frame_hoops")
    assert span.index("filter_frame_hoops") < span.index("_hoop_samples_from_raw")
    assert '"hk"' in span

    # 0.73 widths is inside 0.735 and collapses to one series.
    # 0.74 is outside. x values sit in different 80 px buckets, so the
    # bucket dedupe is not what joins or splits them.
    film = 1000.0
    inside_dx = 0.73 * film
    outside_dx = 0.74 * film
    assert int(0 // rff.HOOP_X_BUCKET_PX) != int(inside_dx // rff.HOOP_X_BUCKET_PX)
    assert int(0 // rff.HOOP_X_BUCKET_PX) != int(outside_dx // rff.HOOP_X_BUCKET_PX)

    def series_at(dx):
        hoops = [
            {
                "x": 0.0,
                "y": 400.0,
                "w": film,
                "h": 40.0,
                "c": 0.4,
                "ball": (0.0, 300.0),
            },
            {
                "x": dx,
                "y": 400.0,
                "w": film,
                "h": 40.0,
                "c": 0.9,
                "ball": (dx, 300.0),
            },
        ]
        kept = rff.filter_frame_hoops(
            hoops,
            film,
            rff.HOOP_W_MIN_WIDTHS,
            rff.HOOP_W_MAX_WIDTHS,
            rff.MISS_RIM_ZONE_WIDTHS,
        )
        return rff.accumulate_series([{"frame": 0, "hoops": kept}])

    assert len(series_at(inside_dx)) == 1
    assert len(series_at(outside_dx)) == 2


def test_not_a_hoop_wins_and_flags_keep_every_rule():
    moments = [_moment(100, kind="rim"), _moment(130, kind="rim")]
    # Twelve hot frames sit in both triggers' 3000 ms windows (fps 25).
    hot = list(range(89, 89 + rff.SHOOT_AROUND_MIN_FRAMES))
    _assign(
        moments,
        [False],
        balls=_balls_on(hot),
        refs=[_box(130, 0.0, 0.0), _box(140, 0.0, 0.0)],
        v6=[[[130, 0.0, 0.0]]],
    )
    assert moments[0]["flags"] == ["not_a_hoop", "possible_shoot_around"]
    assert moments[0]["shot_call"] == "not_a_shot"
    assert moments[0]["shot_reason"] == "not_a_hoop"
    assert moments[1]["flags"] == [
        "not_a_hoop",
        "same_shot_merged",
        "possible_shoot_around",
    ]
    assert "referee_holding" not in moments[1]["flags"]
    assert "possible_fouled_miss" not in moments[1]["flags"]
    assert moments[1]["shot_call"] == "not_a_shot"
    assert moments[1]["shot_reason"] == "not_a_hoop"
    assert moments[1]["merged_into_frame"] == 100
    assert moments[1]["shooter"] == "found"
    assert moments[1]["shooter_reason"] is None


def _tag(t, kind, quarter="Q1", result="Miss"):
    return {
        "t": t,
        "quarter": quarter,
        "eventtype": kind,
        "result": result,
        "start": "0:00.0",
        "player": "A",
    }


def test_measure_shot_call_hidden_truth_and_old_moments():
    tags = [
        _tag(1000, "2PT"),
        _tag(5000, "3PT", result="Make"),
        _tag(50000, "FT", quarter="Q4", result="Make"),
        _tag(130000, "FT"),
    ]
    moments = [
        {
            "t_ms": 1000,
            "frame": 25,
            "status": "orange",
            "kind_hint": "rim",
            "shot_call": "orange",
            "shot_reason": "possible_shoot_around",
        },
        {
            "t_ms": 5000,
            "frame": 125,
            "status": "found",
            "kind_hint": "make",
            "shot_call": "shot",
            "shot_reason": None,
        },
        {
            "t_ms": 9000,
            "frame": 225,
            "status": "orange",
            "kind_hint": "rim",
            "shot_call": "not_a_shot",
            "shot_reason": "not_a_hoop",
        },
        {"t_ms": 20000, "frame": 500, "shot_call": "shot", "shot_reason": None},
        {"t_ms": 30000, "frame": 750, "shot_call": "shot", "shot_reason": None},
        {"t_ms": 31000, "frame": 775, "shot_call": "shot", "shot_reason": None},
        {
            "t_ms": 40000,
            "frame": 1000,
            "shot_call": "orange",
            "shot_reason": "possible_shoot_around",
        },
        {
            "t_ms": 50000,
            "frame": 1250,
            "shot_call": "not_a_shot",
            "shot_reason": "not_a_hoop",
        },
        {"t_ms": 60000, "frame": 1500, "shot_call": "shot", "shot_reason": None},
        {"t_ms": 65100, "frame": 1627, "shot_call": "shot", "shot_reason": None},
        {
            "t_ms": 70000,
            "frame": 1750,
            "shot_call": "orange",
            "shot_reason": "possible_fouled_miss",
        },
        {
            "t_ms": 75000,
            "frame": 1875,
            "shot_call": "not_a_shot",
            "shot_reason": "referee_holding",
        },
        {
            "t_ms": 80000,
            "frame": 2000,
            "shot_call": "orange",
            "shot_reason": "possible_shoot_around",
        },
        {
            "t_ms": 85000,
            "frame": 2125,
            "shot_call": "not_a_shot",
            "shot_reason": "same_shot_merged",
        },
        {"t_ms": 95000, "frame": 2375, "shot_call": "shot", "shot_reason": None},
        {"t_ms": 101500, "frame": 2537, "shot_call": "shot", "shot_reason": None},
        {"t_ms": 101501, "frame": 2538, "shot_call": "shot", "shot_reason": None},
        {"t_ms": 110000, "frame": 2750, "shot_call": "shot", "shot_reason": None},
        {
            "t_ms": 130000,
            "frame": 3250,
            "status": "found",
            "shot_call": "shot",
            "shot_reason": None,
        },
    ]
    truth = {
        "extras": [
            {"n": 1, "run": "adrian", "t_ms": 20000, "label": "E_putback_real_shot"},
            {"n": 2, "run": "adrian", "t_ms": 30000, "label": "E_putback_real_shot"},
            {"n": 3, "run": "adrian", "t_ms": 40000, "label": "E_putback_real_shot"},
            {"n": 4, "run": "adrian", "t_ms": 45000, "label": "E_putback_real_shot"},
            {"n": 5, "run": "adrian", "t_ms": 50000, "label": "A_not_a_hoop"},
            {"n": 6, "run": "adrian", "t_ms": 55000, "label": "B_not_game_time"},
            {"n": 7, "run": "adrian", "t_ms": 60000, "label": "C_fouled_shot"},
            {"n": 8, "run": "adrian", "t_ms": 65000, "label": "D_blocked"},
            {"n": 9, "run": "adrian", "t_ms": 70000, "label": "F_same_shot_twice"},
            {"n": 10, "run": "adrian", "t_ms": 75000, "label": "H_referee_holding"},
            {"n": 11, "run": "adrian", "t_ms": 80000, "label": "G_unclear_orange"},
            {"n": 12, "run": "adrian", "t_ms": 85000, "label": "G_unclear_orange"},
            {"n": 13, "run": "adrian", "t_ms": 90000, "label": "G_unclear_orange"},
            {"n": 14, "run": "adrian", "t_ms": 95000, "label": "G_unclear_orange"},
            {"n": 15, "run": "adrian", "t_ms": 100000, "label": "B_not_game_time"},
            {"n": 16, "run": "adrian", "t_ms": 101501, "label": "Q4_not_examined"},
            {"n": 17, "run": "notus", "t_ms": 101501, "label": "D_blocked"},
        ]
    }
    report = rfm.build_report(
        moments,
        tags,
        rfm.MATCH_WINDOW_MS,
        truth=truth,
        truth_run="adrian",
        extra_window_ms=rfm.EXTRA_MATCH_WINDOW_MS,
    )
    assert report["n_q4_removed"] == 1
    assert report["by_kind"]["2PT"]["found"] == 0
    assert report["by_kind"]["2PT"]["missed"] == 1
    assert report["by_kind"]["3PT"]["found"] == 1
    assert report["by_kind"]["FT"]["found"] == 1
    assert report["by_kind"]["FT"]["missed"] == 0
    extra_times = [row["t_ms"] for row in report["extras"]]
    assert 1000 not in extra_times
    assert 9000 not in extra_times
    assert 40000 not in extra_times
    assert 50000 not in extra_times
    assert report["hidden"]["n"] == 1
    hidden = report["hidden"]["rows"][0]
    assert hidden["tag_t_ms"] == 1000
    assert hidden["shot_call"] == "orange"
    assert hidden["shot_reason"] == "possible_shoot_around"
    assert report["hidden"]["by_reason"] == {"possible_shoot_around": 1}
    assert report["misses"][0]["t_ms"] == 1000

    by_label = report["truth"]["by_label"]
    assert by_label["E_putback_real_shot"]["correct"] == 1
    assert by_label["E_putback_real_shot"]["wrong"] == 1
    assert by_label["E_putback_real_shot"]["orange"] == 1
    assert by_label["E_putback_real_shot"]["missed"] == 1
    e_rows = {row["n"]: row for row in by_label["E_putback_real_shot"]["rows"]}
    assert e_rows[2]["detail"] == "double count"
    assert e_rows[2]["verdict"] == "wrong"
    assert by_label["A_not_a_hoop"]["correct"] == 1
    assert by_label["A_not_a_hoop"]["rows"][0]["detail"] == "not_a_shot"
    assert by_label["B_not_game_time"]["correct"] == 1
    assert by_label["B_not_game_time"]["wrong"] == 1
    assert by_label["C_fouled_shot"]["wrong"] == 1
    assert by_label["D_blocked"]["wrong"] == 1
    assert by_label["F_same_shot_twice"]["correct"] == 1
    assert by_label["F_same_shot_twice"]["rows"][0]["detail"] == "orange"
    assert by_label["H_referee_holding"]["correct"] == 1
    g_rows = {row["n"]: row for row in by_label["G_unclear_orange"]["rows"]}
    assert g_rows[11]["verdict"] == "correct"
    assert g_rows[12]["verdict"] == "gone"
    assert g_rows[12]["detail"] == "not_a_shot"
    assert g_rows[13]["verdict"] == "gone"
    assert g_rows[13]["detail"] == "none"
    assert g_rows[14]["verdict"] == "shot_on_unclear"
    totals = report["truth"]["totals"]
    assert totals["shot_on_unclear"] == 1
    assert totals["new_extra"] == 2
    assert [row["t_ms"] for row in report["truth"]["new_extras"]] == [101501, 110000]
    assert totals["wrong"] == 4
    assert "Q4_not_examined" not in by_label
    assert report["truth"]["run"] == "adrian"
    text = rfm.render_summary(report)
    assert "possible_shoot_around" in text
    assert "double count" in text
    assert "new extra" in text
    assert "101501" in text
    assert "Hidden tagged shots" in text
    assert "Shot calls" in text

    old = rfm.build_report(
        [{"t_ms": 1000, "status": "found"}],
        [_tag(1000, "2PT")],
        8000,
    )
    assert old["by_kind"]["all"]["found"] == 1
    assert old["by_kind"]["all"]["missed"] == 0
    assert old["shot_calls"]["by_call"]["shot"] == 1
    assert old["hidden"]["n"] == 0
    assert "truth" not in old
    assert "shooter" in old


def _close(got, exp):
    assert abs(float(got) - float(exp)) < 1e-9, (got, exp)


def _walk(balls, players, trigger, fps=25.0, fix_ref=False, fix_merge=False, referees=()):
    """Spec 38 walk. Pass fix_ref and fix_merge to turn spec 39 on."""
    frames = {int(pt[0]) for pt in balls}
    frames.add(int(trigger))
    hoops = [
        _hoop(rff.frame_to_ms(frame, fps), 960.0, 400.0) for frame in sorted(frames)
    ]
    refs_by = None
    if referees:
        _ref_frames, refs_by = rff.index_by_frame(
            referees, lambda box: int(box["frame"])
        )
    return _trace_call(
        balls,
        [],
        hoops,
        players,
        trigger,
        fps,
        walk_back=True,
        fix_ref=fix_ref,
        fix_merge=fix_merge,
        refs_by_frame=refs_by,
    )


def test_walk_back_finds_a_hold_20_frames_before_the_inflight_start():
    fps = 25.0
    trigger = 140
    frames = [100, 104, 108, 112, 116, 120, 130, 140]
    balls = []
    for frame in frames:
        if frame == 100:
            balls.append([frame, 200.0, 450.0])
        elif frame == 130:
            balls.append([frame, 800.0, 200.0])
        else:
            balls.append([frame, 800.0, 400.0])
    players = [{"frame": 100, "x": 200.0, "y": 450.0, "w": 100.0, "h": 120.0}]
    got = _walk(balls, players, trigger, fps)
    assert got["status"] == "found"
    assert got["reason"] is None
    assert got["release_frame"] == 100
    assert got["trace_mode"] == "walk_back"
    assert got["shooter_box"]["frame"] == 100
    assert got["floor_spot"] == {"x": 200.0, "y": 510.0}
    single = _trace_call(
        balls,
        [],
        [_hoop(rff.frame_to_ms(frame, fps), 960.0, 400.0) for frame in frames],
        players,
        trigger,
        fps,
        False,
    )
    assert single["trace_mode"] == "single_frame"
    assert single["release_frame"] == 120
    assert single["status"] == "orange"
    assert single["reason"] == "no player at release frame"


def test_walk_back_gap_of_9_frames_breaks_and_gap_of_8_continues():
    assert rff.TRACK_BREAK_GAP_FRAMES == rff.MAKE_GAP_FRAMES == 8
    assert "spec 38 S8, Scott approved 2026-11-06" in FINDER_PATH.read_text(
        encoding="utf-8"
    )
    # Missing frames, the same count split_runs uses for MAKE_GAP_FRAMES.
    # Frames 30 and 40: missing 9 -> broken. Frames 31 and 40: missing 8 -> stays.
    assert (
        len(rff.split_runs([(30, 0.0, 0.0), (40, 0.0, 0.0)], rff.TRACK_BREAK_GAP_FRAMES))
        == 2
    )
    assert (
        len(rff.split_runs([(31, 0.0, 0.0), (40, 0.0, 0.0)], rff.TRACK_BREAK_GAP_FRAMES))
        == 1
    )
    broken = _walk(
        [[30, 500.0, 500.0], [40, 10.0, 500.0]],
        [{"frame": 30, "x": 500.0, "y": 500.0, "w": 100.0, "h": 100.0}],
        40,
    )
    assert broken["status"] == "orange"
    assert broken["reason"] == "track broken"
    assert broken["release_frame"] is None
    assert broken["shooter_box"] is None
    assert broken["floor_spot"] is None
    assert broken["last_checked_frame"] == 40
    assert broken["trace_mode"] == "walk_back"
    held = _walk(
        [[31, 500.0, 500.0], [40, 10.0, 500.0]],
        [{"frame": 31, "x": 500.0, "y": 500.0, "w": 80.0, "h": 80.0}],
        40,
    )
    assert held["status"] == "found"
    assert held["release_frame"] == 31
    assert held["floor_spot"] == {"x": 500.0, "y": 540.0}
    assert held["reason"] is None


def test_walk_back_two_players_hold_and_a_referee_is_never_chosen():
    balls = [[40, 500.0, 500.0]]
    players = [
        {"frame": 40, "x": 500.0, "y": 500.0, "w": 100.0, "h": 100.0},
        {"frame": 40, "x": 510.0, "y": 500.0, "w": 100.0, "h": 100.0},
    ]
    two = _walk(balls, players, 40)
    assert two["status"] == "orange"
    assert two["reason"] == "two players hold"
    assert two["shooter_box"] is None
    assert two["floor_spot"] is None
    assert two["release_frame"] is None
    assert two["last_checked_frame"] == 40
    assert [box["x"] for box in two["hold_boxes"]] == [500.0, 510.0]

    referee = {
        "frame": 40,
        "x": 500.0,
        "y": 500.0,
        "w": 100.0,
        "h": 100.0,
        "class": "referee",
    }
    player = {"frame": 40, "x": 500.0, "y": 500.0, "w": 90.0, "h": 90.0}
    both = _walk(balls, [referee, player], 40)
    assert both["status"] == "found"
    assert both["shooter_box"]["w"] == 90.0
    assert both["reason"] is None
    only_ref = _walk(balls, [referee], 40)
    assert only_ref["status"] == "orange"
    assert only_ref["reason"] == "ball not inside a player box"
    assert only_ref["shooter_box"] is None
    assert only_ref["last_checked_frame"] == 40


def test_walk_back_without_a_rise_starts_at_the_latest_point_at_or_before_the_trigger():
    players = [
        {"frame": 30, "x": 500.0, "y": 500.0, "w": 100.0, "h": 80.0},
        {"frame": 50, "x": 500.0, "y": 500.0, "w": 100.0, "h": 80.0},
    ]
    got = _walk(
        [[10, 10.0, 500.0], [30, 500.0, 500.0], [50, 500.0, 500.0]],
        players,
        40,
    )
    assert got["status"] == "found"
    assert got["release_frame"] == 30
    assert got["trace_mode"] == "walk_back"
    assert got["floor_spot"] == {"x": 500.0, "y": 540.0}
    empty = _walk([], [], 40)
    assert empty["status"] == "orange"
    assert empty["reason"] == "no release frame"
    assert empty["last_checked_frame"] is None


def _saved_shooter_run(tmp_path):
    """One kept series whose single-frame trace finds the shooter at frame 80."""
    fps = 25.0
    trigger = 120
    samples = [
        (10, 100.0, 100.0),
        (80, 500.0, 450.0),
        (90, 600.0, 300.0),
        (120, 960.0, 400.0),
    ]
    frames = []
    for frame, x, y in samples:
        players = []
        if frame == 80:
            players = [[550.0, 450.0, 100.0, 80.0]]
        frames.append(
            {
                "f": frame,
                "b": [[x, y, 20.0, 20.0, 0.5]],
                "h": [[960.0, 400.0, 98.0, 40.0, 0.9]],
                "p": players,
                # Referee sits on the ball. It must not become a second holder.
                "r": [[550.0, 450.0, 100.0, 80.0, 0.4]],
            }
        )
    series = [
        {
            "series": 0,
            "ref_x": 960.0,
            "median_hoop_w": 98.0,
            "n_v6_points": 4,
            "kept": True,
            "drop_reason": None,
            "points": [[frame, x, y] for frame, x, y in samples],
        }
    ]
    hoops = [
        _hoop(rff.frame_to_ms(frame, fps), 960.0, 400.0) for frame, _x, _y in samples
    ]
    players = [{"frame": 80, "x": 550.0, "y": 450.0, "w": 100.0, "h": 80.0}]
    balls = [[frame, x, y, 0.5] for frame, x, y in samples]
    traced = _trace_call(balls, series[0]["points"], hoops, players, trigger, fps, False)
    assert traced["status"] == "found"
    assert traced["release_frame"] == 80
    moment = {
        "frame": trigger,
        "t_ms": rff.frame_to_ms(trigger, fps),
        "series": 0,
        "kind_hint": "make",
        "hoop": {"x": 960.0, "y": 400.0, "w": 98.0, "h": 40.0},
        "shot_call": "shot",
        "shot_reason": None,
        "marker": "keep-me",
    }
    moment.update(traced)
    moment["shooter"] = traced["status"]
    moment["shooter_reason"] = traced["reason"]
    src = tmp_path / "run"
    src.mkdir(parents=True)
    doc = {
        "fps": fps,
        "video": "saved.mp4",
        "moments": [moment],
        "applied_to_core": False,
    }
    (src / "moments.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (src / "frames.json").write_text(
        json.dumps({"frames": frames, "series": series}, separators=(",", ":")),
        encoding="utf-8",
    )
    return src


def test_retrace_walk_off_reproduces_the_saved_moments(tmp_path):
    src = _saved_shooter_run(tmp_path)
    saved = json.loads((src / "moments.json").read_text(encoding="utf-8"))
    frames_bytes = (src / "frames.json").read_bytes()
    out = tmp_path / "out"
    code = rff.main(
        ["--retrace-from", str(src), "--out-dir", str(out), "--walk-off"]
    )
    assert code == 0
    loaded = json.loads((out / "moments.json").read_text(encoding="utf-8"))
    assert loaded["moments"] == saved["moments"]
    assert loaded["moments"][0]["marker"] == "keep-me"
    assert loaded["moments"][0]["shot_call"] == "shot"
    assert loaded["retrace_from"] == str(src.resolve())
    assert loaded["video"] == "saved.mp4"
    assert loaded["applied_to_core"] is False
    assert (out / "frames.json").read_bytes() == frames_bytes


def test_retrace_series_mismatch_exits_2(tmp_path):
    src = _saved_shooter_run(tmp_path / "src")
    frames_doc = json.loads((src / "frames.json").read_text(encoding="utf-8"))
    frames_doc["series"][0]["ref_x"] = 1.0
    (src / "frames.json").write_text(json.dumps(frames_doc), encoding="utf-8")
    code = rff.main(
        ["--retrace-from", str(src), "--out-dir", str(tmp_path / "out"), "--walk-off"]
    )
    assert code == 2


def test_ft_spot_passes_at_1_5_widths_and_fails_at_1_51():
    assert rfm.FT_SPOT_PASS_WIDTHS == 1.5
    measure_text = (HERE / "rim_first_measure.py").read_text(encoding="utf-8")
    assert "spec 38 S8, Scott approved" in measure_text
    hoop = {"x": 0.0, "y": 0.0, "w": 100.0, "h": 40.0}
    spots = [(0.0, 0.0), (150.0, 0.0), (0.0, 151.0)]
    moments = []
    tags = []
    for i, (fx, fy) in enumerate(spots):
        t_ms = 10000 + i * 1000
        moments.append(
            {
                "t_ms": t_ms,
                "frame": 100,
                "release_frame": 50 if i == 0 else None,
                "series": 0,
                "status": "found",
                "reason": None,
                "shot_call": "shot",
                "hoop": dict(hoop),
                "floor_spot": {"x": fx, "y": fy},
            }
        )
        tags.append(_tag(t_ms, "FT", result="Make"))
    moments.append(
        {
            "t_ms": 40000,
            "frame": 100,
            "release_frame": 40,
            "series": 1,
            "status": "orange",
            "reason": "ball not inside a player box",
            "shot_call": "shot",
            "hoop": dict(hoop),
            "floor_spot": {"x": 200.0, "y": 0.0},
        }
    )
    tags.append(_tag(40000, "2PT"))
    moments.append(
        {
            "t_ms": 50000,
            "frame": 100,
            "release_frame": 25,
            "series": 1,
            "status": "found",
            "reason": None,
            "shot_call": "shot",
            "hoop": dict(hoop),
            "floor_spot": {"x": 400.0, "y": 0.0},
        }
    )
    tags.append(_tag(50000, "3PT", result="Make"))
    report = rfm.build_report(moments, tags, rfm.MATCH_WINDOW_MS, fps=25.0)
    assert report["by_kind"]["FT"]["found"] == 3
    assert report["by_kind"]["all"]["found"] == 5
    group = report["shooter"]["ft_spot"][0]
    assert group["n"] == 3
    assert group["pass_count"] == 2
    assert group["series"] == 0
    assert group["pass_widths"] == 1.5
    by_t = {row["t_ms"]: row for row in group["rows"]}
    assert by_t[11000]["pass"] is True
    _close(by_t[11000]["distance_widths"], 1.5)
    assert by_t[12000]["pass"] is False
    _close(by_t[12000]["distance_widths"], 1.51)
    assert by_t[10000]["pass"] is True
    release = report["shooter"]["release_to_trigger_s"]
    assert release["found"]["n"] == 2
    _close(release["found"]["median_s"], 2.5)
    assert release["orange"]["n"] == 1
    _close(release["orange"]["values_s"][0], 2.4)
    distance = report["shooter"]["shot_distance_widths"]
    assert distance["2PT"]["n"] == 1
    _close(distance["2PT"]["median"], 2.0)
    assert distance["3PT"]["n"] == 1
    _close(distance["3PT"]["median"], 4.0)
    assert report["shooter"]["found_by_series"] == {"0": 3, "1": 1}
    assert report["shooter"]["by_status"]["found"] == 4
    assert report["shooter"]["by_reason"]["ball not inside a player box"] == 1
    review = report["shooter"]["review"]
    assert [row["t_ms"] for row in review] == [10000, 11000, 12000, 40000, 50000]
    assert review[0]["eventtype"] == "FT"
    assert review[0]["player"] == "A"
    assert review[0]["status"] == "found"
    assert review[3]["eventtype"] == "2PT"
    assert review[3]["reason"] == "ball not inside a player box"
    _close(review[3]["floor_spot_widths"]["x"], 2.0)
    text = rfm.render_summary(report)
    assert "FT spot" in text
    assert "3PT vs 2PT" in text
    assert "Shooter review" in text
    assert "40000" in text


def test_spec39_iou_inside_fraction_and_same_body_merge():
    finder = FINDER_PATH.read_text(encoding="utf-8")
    assert "spec 39, fixed by Claude Code 2026-11-06" in finder
    assert rff.REF_INSIDE == 0.5
    assert rff.REF_WINDOW_FRAMES == 12
    assert rff.REF_MIN_FRAMES == 5
    assert rff.MERGE_IOU == 0.5

    # Centers. small [0,10]x[0,10], larger [1.75,13.75]x[0,10]. IoU 82.5/137.5.
    small = {"x": 5.0, "y": 5.0, "w": 10.0, "h": 10.0}
    larger = {"x": 7.75, "y": 5.0, "w": 12.0, "h": 10.0}
    _close(rff.box_iou(small, larger), 0.6)
    assert rff.merge_same_body([small, larger], rff.MERGE_IOU) == [larger]
    assert rff.merge_same_body([larger, small], rff.MERGE_IOU) == [larger]

    # Same heights, overlap width 44/7. IoU 0.4, so the boxes stay two.
    far = {"x": 68.0 / 7.0, "y": 5.0, "w": 12.0, "h": 10.0}
    _close(rff.box_iou(small, far), 0.4)
    assert rff.merge_same_body([far, small], rff.MERGE_IOU) == [small, far]

    body = {"x": 500.0, "y": 450.0, "w": 100.0, "h": 100.0}
    inner = {"x": 500.0, "y": 450.0, "w": 40.0, "h": 40.0}
    _close(rff.inside_fraction(body, inner), 1.0)
    _close(rff.inside_fraction(body, {"x": 900.0, "y": 900.0, "w": 10.0, "h": 10.0}), 0.0)
    # The player sits in the top of a taller referee. Intersection / ref area = 0.3.
    tall_ref = {"x": 500.0, "y": 1700.0 / 3.0, "w": 100.0, "h": 1000.0 / 3.0}
    _close(rff.inside_fraction(body, tall_ref), 0.3)


def _refs_only(ref_frames, ref_box):
    """Referee boxes on ref_frames. No player box on those frames."""
    refs = {}
    for frame in ref_frames:
        refs[frame] = [dict(ref_box, frame=frame)]
    return refs


def test_referee_player_needs_five_frames_and_ignores_a_partial_ref():
    # The tested box stays fixed. These frames have a referee box and no player box.
    box = {"x": 500.0, "y": 450.0, "w": 100.0, "h": 100.0}
    inner = {"x": 500.0, "y": 450.0, "w": 40.0, "h": 40.0}
    refs5 = _refs_only((100, 101, 102, 103, 104), inner)
    assert rff.is_referee_player(
        box,
        100,
        refs5,
        rff.REF_WINDOW_FRAMES,
        rff.REF_MIN_FRAMES,
        rff.REF_INSIDE,
    )
    refs4 = _refs_only((100, 101, 102, 103), inner)
    assert not rff.is_referee_player(
        box,
        100,
        refs4,
        rff.REF_WINDOW_FRAMES,
        rff.REF_MIN_FRAMES,
        rff.REF_INSIDE,
    )
    # Overlap width 40 of a 100-wide referee: inside_fraction 0.4, so not counted.
    half_out = {"x": 560.0, "y": 450.0, "w": 100.0, "h": 100.0}
    window = range(100 - rff.REF_WINDOW_FRAMES, 100 + rff.REF_WINDOW_FRAMES + 1)
    refs_partial = _refs_only(window, half_out)
    _close(rff.inside_fraction(box, half_out), 0.4)
    assert not rff.is_referee_player(
        box,
        100,
        refs_partial,
        rff.REF_WINDOW_FRAMES,
        rff.REF_MIN_FRAMES,
        rff.REF_INSIDE,
    )


def test_fixes_walk_past_a_referee_and_merge_one_body():
    real = {"frame": 42, "x": 200.0, "y": 450.0, "w": 100.0, "h": 120.0}
    ref_player = {"x": 500.0, "y": 450.0, "w": 100.0, "h": 100.0}
    inner = {"x": 500.0, "y": 450.0, "w": 40.0, "h": 40.0}
    players = [real]
    refs5 = []
    for frame in (48, 49, 50, 51, 52):
        players.append(dict(ref_player, frame=frame))
        refs5.append(dict(inner, frame=frame))
    balls = [[42, 200.0, 450.0], [50, 500.0, 450.0], [58, 800.0, 200.0]]
    stopped = _walk(balls, players, 70, referees=refs5)
    assert stopped["status"] == "found"
    assert stopped["release_frame"] == 50
    assert stopped["shooter_box"]["x"] == 500.0
    assert stopped["shooter_fixes"] == []
    carried = _walk(
        balls, players, 70, fix_ref=True, fix_merge=True, referees=refs5
    )
    assert carried["status"] == "found"
    assert carried["reason"] is None
    assert carried["release_frame"] == 42
    assert carried["shooter_box"]["x"] == 200.0
    assert carried["shooter_fixes"] == ["ref", "merge"]

    refs4 = [dict(inner, frame=frame) for frame in (48, 49, 50, 51)]
    kept = _walk(balls, players, 70, fix_ref=True, fix_merge=True, referees=refs4)
    assert kept["status"] == "found"
    assert kept["release_frame"] == 50
    assert kept["shooter_box"]["x"] == 500.0

    one_body = [
        {"frame": 40, "x": 5.0, "y": 5.0, "w": 10.0, "h": 10.0},
        {"frame": 40, "x": 7.75, "y": 5.0, "w": 12.0, "h": 10.0},
    ]
    hold_ball = [[40, 6.0, 5.0]]
    two = _walk(hold_ball, one_body, 40)
    assert two["status"] == "orange"
    assert two["reason"] == "two players hold"
    one = _walk(hold_ball, one_body, 40, fix_ref=True, fix_merge=True)
    assert one["status"] == "found"
    assert one["reason"] is None
    assert one["shooter_box"]["w"] == 12.0
    assert one["shooter_fixes"] == ["ref", "merge"]


def _spec39_saved_run(tmp_path):
    """Tiny run whose spec-38 walk stops on a player box that covers a referee."""
    fps = 25.0
    ref_player = [500.0, 450.0, 100.0, 100.0]
    real_player = [200.0, 450.0, 100.0, 120.0]
    inner_ref = [500.0, 450.0, 40.0, 40.0, 0.4]
    hoop = [960.0, 400.0, 98.0, 40.0, 0.9]
    ref_frames = (48, 49, 50, 51, 52)
    ball_at = {42: (200.0, 450.0), 50: (500.0, 450.0), 58: (800.0, 200.0)}
    frames = []
    for frame in sorted(set(ref_frames) | set(ball_at)):
        players = []
        refs = []
        if frame == 42:
            players.append(real_player)
        if frame in ref_frames:
            players.append(ref_player)
            refs.append(inner_ref)
        ball = ball_at.get(frame)
        balls = [[ball[0], ball[1], 20.0, 20.0, 0.5]] if ball else []
        frames.append(
            {"f": frame, "b": balls, "h": [hoop], "p": players, "r": refs}
        )
    series = [
        {
            "series": 0,
            "ref_x": 960.0,
            "median_hoop_w": 98.0,
            "n_v6_points": 3,
            "kept": True,
            "drop_reason": None,
            "points": [
                [frame, ball_at[frame][0], ball_at[frame][1]]
                for frame in (42, 50, 58)
            ],
        }
    ]
    moment = {
        "frame": 70,
        "t_ms": rff.frame_to_ms(70, fps),
        "series": 0,
        "kind_hint": "make",
        "hoop": {"x": 960.0, "y": 400.0, "w": 98.0, "h": 40.0},
        "shot_call": "shot",
        "shot_reason": None,
        "marker": "keep-me",
        "status": "orange",
        "reason": "placeholder",
        "shooter_box": None,
        "floor_spot": None,
        "release_frame": None,
    }
    src = tmp_path / "run"
    src.mkdir(parents=True)
    doc = {"fps": fps, "video": "saved.mp4", "moments": [moment], "applied_to_core": False}
    (src / "moments.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (src / "frames.json").write_text(
        json.dumps({"frames": frames, "series": series}, separators=(",", ":")),
        encoding="utf-8",
    )
    return src


def test_fixes_off_retrace_matches_the_spec38_walk(tmp_path):
    src = _spec39_saved_run(tmp_path)
    moments_doc = json.loads((src / "moments.json").read_text(encoding="utf-8"))
    frames_doc = json.loads((src / "frames.json").read_text(encoding="utf-8"))
    spec38, _series, differ = rff.retrace_moments(
        moments_doc["moments"],
        frames_doc["frames"],
        frames_doc["series"],
        float(moments_doc["fps"]),
        True,
        False,
        False,
    )
    assert differ is False
    assert spec38[0]["status"] == "found"
    assert spec38[0]["reason"] is None
    assert spec38[0]["release_frame"] == 50
    assert spec38[0]["shooter_box"]["x"] == 500.0
    assert spec38[0]["shooter_fixes"] == []
    assert spec38[0]["marker"] == "keep-me"
    assert spec38[0]["shot_call"] == "shot"

    out = tmp_path / "off"
    code = rff.main(
        ["--retrace-from", str(src), "--out-dir", str(out), "--fixes-off"]
    )
    assert code == 0
    loaded = json.loads((out / "moments.json").read_text(encoding="utf-8"))
    assert loaded["moments"] == json.loads(json.dumps(spec38))
    assert loaded["retrace_from"] == str(src.resolve())

    on_dir = tmp_path / "on"
    code_on = rff.main(["--retrace-from", str(src), "--out-dir", str(on_dir)])
    assert code_on == 0
    turned_on = json.loads((on_dir / "moments.json").read_text(encoding="utf-8"))
    assert turned_on["moments"][0]["status"] == "found"
    assert turned_on["moments"][0]["release_frame"] == 42
    assert turned_on["moments"][0]["shooter_box"]["x"] == 200.0
    assert turned_on["moments"][0]["shooter_fixes"] == ["ref", "merge"]
    assert turned_on["moments"][0]["marker"] == "keep-me"
    assert turned_on["moments"][0]["shot_call"] == "shot"
