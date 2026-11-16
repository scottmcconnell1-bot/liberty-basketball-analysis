"""Pure-function tests for ball_track_check (spec 34 / D3). No video."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ball_track_check as btc  # noqa: E402

FPS = 25.0
HOOP_W = 100.0
HOOP = {"t": 0, "x": 960.0, "y": 400.0, "w": HOOP_W, "h": 40.0}


def _hoops_for_frames(frames, scale: float = 1.0) -> list:
    return [
        {
            "t": btc.frame_to_ms(f, FPS),
            "x": HOOP["x"] * scale,
            "y": HOOP["y"] * scale,
            "w": HOOP_W * scale,
            "h": 40.0 * scale,
        }
        for f in frames
    ]


def _scale_track(track, scale: float):
    return [[f, x * scale, y * scale, c] for f, x, y, c in track]


# ---------------------------------------------------------------------------
# Hoop-width units invariant under 1920 vs 1280 scale
# ---------------------------------------------------------------------------


def test_hoop_width_units_equal_on_1920_and_1280_scaled_copy():
    """Same geometry at scale 1.0 (1920) and 1280/1920 must match in hoop_w."""
    # Ball 2 hoop_w above hoop, 1.5 hoop_w to the right of centre.
    track = [
        [10, HOOP["x"] + 1.5 * HOOP_W, HOOP["y"] - 2.0 * HOOP_W, 0.9],
        [11, HOOP["x"] + 1.5 * HOOP_W, HOOP["y"] - 1.5 * HOOP_W, 0.9],
        [12, HOOP["x"] + 0.5 * HOOP_W, HOOP["y"] - 0.5 * HOOP_W, 0.9],
    ]
    frames = [10, 11, 12]
    scale = 1280.0 / 1920.0

    hoops_a = _hoops_for_frames(frames, 1.0)
    hoops_b = _hoops_for_frames(frames, scale)
    track_b = _scale_track(track, scale)

    a = btc.track_height_and_distance(track, hoops_a, FPS)
    b = btc.track_height_and_distance(track_b, hoops_b, FPS)
    assert len(a["height_above_hoop_w"]) == 3
    for ha, hb in zip(a["height_above_hoop_w"], b["height_above_hoop_w"]):
        assert abs(ha - hb) < 1e-9
    for da, db in zip(a["dist_from_hoop_w"], b["dist_from_hoop_w"]):
        assert abs(da - db) < 1e-9

    ja = btc.track_jumps(track, hoops_a, FPS)
    jb = btc.track_jumps(track_b, hoops_b, FPS)
    assert len(ja) == len(jb) == 2
    for xa, xb in zip(ja, jb):
        assert abs(xa["jump_hoop_w"] - xb["jump_hoop_w"]) < 1e-9
        assert xa["frame_gap"] == xb["frame_gap"]


# ---------------------------------------------------------------------------
# Jump stats on a hand track
# ---------------------------------------------------------------------------


def test_jump_stats_on_hand_track():
    """Raw jump in hoop_w and frame_gap; jump is NOT divided by gap."""
    # Two detections 5 frames apart, 200 px apart, hoop_w=100 → jump_hw=2.0
    track = [
        [0, 960.0, 400.0, 0.9],
        [5, 1160.0, 400.0, 0.9],  # +200 px in x
    ]
    hoops = _hoops_for_frames([0, 5])
    jumps = btc.track_jumps(track, hoops, FPS)
    assert len(jumps) == 1
    j = jumps[0]
    assert j["frame_gap"] == 5
    assert abs(j["jump_px"] - 200.0) < 1e-9
    assert abs(j["jump_hoop_w"] - 2.0) < 1e-9
    # Must NOT be jump/gap (=0.4)
    assert abs(j["jump_hoop_w"] - 0.4) > 0.5

    summary = btc.summarize_values([j["jump_hoop_w"]])
    assert summary["n"] == 1
    assert summary["median"] == 2.0
    assert summary["p90"] == 2.0
    assert summary["max"] == 2.0


# ---------------------------------------------------------------------------
# Missing run count
# ---------------------------------------------------------------------------


def test_missing_run_count():
    # Window 0..9 (10 frames). Detections at 0,1,5,9 → missing 2,3,4,6,7,8
    # Longest run = 3 (frames 2-4) and also 3 (6-8) → 3
    track = [
        [0, 100.0, 100.0, 0.9],
        [1, 100.0, 100.0, 0.9],
        [5, 100.0, 100.0, 0.9],
        [9, 100.0, 100.0, 0.9],
    ]
    window = {
        "before": 0,
        "after": 0,
        "lo": btc.frame_to_ms(0, FPS),
        "hi": btc.frame_to_ms(9, FPS),
    }
    miss = btc.missing_in_window(track, window, FPS)
    assert miss["window_frames"] == 10
    assert miss["detected_frames"] == 4
    assert miss["missing_frames"] == 6
    assert miss["longest_missing_run"] == 3
    assert abs(miss["missing_ratio"] - 0.6) < 1e-12


# ---------------------------------------------------------------------------
# Failure-frame lookup: right frame and source (v6-first)
# ---------------------------------------------------------------------------


def test_failure_frame_lookup_picks_peak_and_v6_source():
    # Combined track: BODD alone on frame 10, v6+bodd on frame 20 (peak), landing 30
    v6 = [[20, 960.0, 100.0, 0.9]]  # at peak
    bodd = [
        [10, 500.0, 500.0, 0.5],
        [20, 961.0, 101.0, 0.5],  # would lose to v6
        [30, 960.0, 400.0, 0.5],
    ]
    combined = btc.combine_ball_track(v6, bodd)
    # peak_idx=1 → frame 20 (combined order: 10, 20, 30)
    measured = {
        "rule": "ORANGE",
        "reason": "descent not seen",
        "landing": {
            "frame": 20,
            "peak_idx": 1,
            "rose_above_rim": True,
            "descent_not_seen": True,
            "x": 960.0,
            "y": 100.0,
        },
        "coverage": {},
    }
    frame, field = btc.resolve_failure_frame(measured, combined)
    assert frame == 20
    assert field == "landing.peak_idx"
    source, pt = btc.ball_source_at_frame(v6, bodd, frame)
    assert source == "v6"
    assert pt is not None
    assert abs(pt[1] - 960.0) < 1e-9


def test_failure_frame_lookup_landing_and_bodd_only():
    v6: list = []
    bodd = [[40, 200.0, 50.0, 0.4]]
    combined = btc.combine_ball_track(v6, bodd)
    measured = {
        "rule": "NOT_A_SHOT",
        "reason": "",
        "landing": {
            "frame": 40,
            "peak_idx": 0,
            "rose_above_rim": True,
            "descent_not_seen": False,
            "x": 200.0,
            "y": 50.0,
        },
        "coverage": {},
    }
    frame, field = btc.resolve_failure_frame(measured, combined)
    assert frame == 40
    assert field == "landing.frame"
    source, pt = btc.ball_source_at_frame(v6, bodd, frame)
    assert source == "bodd"
    assert pt is not None


# ---------------------------------------------------------------------------
# Even selection k for 57 and 20 failures
# ---------------------------------------------------------------------------


def test_even_selection_k_for_57_and_20_failures():
    fails_57 = [{"moment_id": f"m{i}", "i": i} for i in range(57)]
    sel = btc.even_select(fails_57, 20)
    assert len(sel) == 20
    k = 57 // 20  # 2
    assert k == 2
    assert [s["i"] for s in sel] == [i * k for i in range(20)]

    fails_20 = [{"moment_id": f"n{i}", "i": i} for i in range(20)]
    sel20 = btc.even_select(fails_20, 20)
    assert len(sel20) == 20
    assert [s["i"] for s in sel20] == list(range(20))  # k = 1


# ---------------------------------------------------------------------------
# Coverage > 1 detection
# ---------------------------------------------------------------------------


def test_coverage_gt1_detection():
    measured_ok = {
        "coverage": {
            "coverage_ratio": 1.0,
            "frames_seen": 10,
            "frames_in_flight_estimate": 10,
        }
    }
    measured_bug = {
        "moment_id": "tag_x",
        "coverage": {
            "coverage_ratio": 1.317,
            "frames_seen": 54,
            "frames_in_flight_estimate": 41,
            "release_frame": None,
            "release_frame_estimate": 16862,
            "landing_frame": None,
            "frames_span": 115,
            "longest_gap_frames": 18,
        },
    }
    assert btc.coverage_bug_check(measured_ok) is False
    assert btc.coverage_bug_check(measured_bug) is True
    fields = btc.coverage_bug_fields(measured_bug["coverage"])
    assert fields is not None
    assert fields["frames_seen"] == 54
    assert fields["frames_in_flight_estimate"] == 41
    assert fields["coverage_ratio"] > 1


# ---------------------------------------------------------------------------
# Q4 filter
# ---------------------------------------------------------------------------


def test_q4_filter():
    moments = [
        {"moment_id": "a", "quarter": "Q1"},
        {"moment_id": "b", "quarter": "Q4"},
        {"moment_id": "c", "quarter": "Q3"},
        {"moment_id": "d", "quarter": None},  # fakes
        {"moment_id": "e", "quarter": "Q4"},
    ]
    kept = btc.filter_out_q4(moments)
    assert [m["moment_id"] for m in kept] == ["a", "c", "d"]


def test_pct90_and_summarize_empty():
    assert btc.summarize_values([]) == {"n": 0, "median": None, "p90": None, "max": None}
    # 10 values 1..10 → 90th nearest-rank = ceil(9)=9 → value 9
    s = btc.summarize_values(list(range(1, 11)))
    assert s["n"] == 10
    assert s["p90"] == 9
    assert s["max"] == 10
    assert s["median"] == 5.5
