"""Pure-function tests for shot flight rules (spec 33). No video, no model."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_flight_tracks as cft  # noqa: E402
import shot_rules_measure as srm  # noqa: E402

# Scott-approved numbers — passed explicitly (C7: no defaults in rule fns).
RIM_C = 0.735
NEAR = 1.833
CATCH_F = 0.5
RELEASE_F = 0.6
GAP_N = 3
RIM_R = 72.0
FPS = 25.0
HOOP_W = 98.0  # Adrian median
HOOP = {"t": 0, "x": 960.0, "y": 400.0, "w": HOOP_W, "h": 40.0}


def _hoops(n: int = 40) -> list:
    """Hoop sample every frame for 0..n-1."""
    return [
        {"t": int(round(1000.0 * f / FPS)), "x": HOOP["x"], "y": HOOP["y"], "w": HOOP_W, "h": 40.0}
        for f in range(n)
    ]


def _hoops_sparse(frames_with_hoop, n: int = 40) -> list:
    """Hoop only on listed frames (carry-over tested via hoop_for_frame)."""
    want = set(frames_with_hoop)
    return [
        {"t": int(round(1000.0 * f / FPS)), "x": HOOP["x"], "y": HOOP["y"], "w": HOOP_W, "h": 40.0}
        for f in range(n)
        if f in want
    ]


def _classify(ball, players, hoops=None):
    return srm.classify_flight(
        ball,
        players,
        hoops if hoops is not None else _hoops(200),
        RIM_C,
        NEAR,
        RIM_R,
        CATCH_F,
        GAP_N,
        FPS,
    )


def _player(frame, x, y, w=60.0, h=120.0):
    return {"frame": frame, "x": x, "y": y, "w": w, "h": h}


def _scale_track(ball, hoops, scale: float):
    ball_s = [[f, x * scale, y * scale, c] for f, x, y, c in ball]
    hoops_s = [
        {
            "t": h["t"],
            "x": h["x"] * scale,
            "y": h["y"] * scale,
            "w": h["w"] * scale,
            "h": h["h"] * scale,
        }
        for h in hoops
    ]
    return ball_s, hoops_s


# ---------------------------------------------------------------------------
# Spec / Muse cases
# ---------------------------------------------------------------------------


def test_shooters_own_hands_at_release_is_not_a_catch():
    """Ball starts in shooter box, leaves, never re-enters → not PASS."""
    # Rise above rim then land near hoop (~1.0 hoop_w), no catcher.
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    ball = []
    # Frames 0-2: in shooter hands (below/at side)
    for f in range(0, 3):
        ball.append([f, hx - 150, hy + 80, 0.9])
    # Frames 3-8: in flight, rising then falling near hoop (not rim zone)
    land_x = hx + 1.0 * hw  # ~1.0 hoop widths — near, not rim
    for f, y in enumerate([hy - 100, hy - 120, hy - 80, hy - 40, hy + 10, hy + 30], start=3):
        # interpolate x toward land
        t = (f - 3) / 5.0
        x = (hx - 150) * (1 - t) + land_x * t
        ball.append([f, x, y, 0.9])
    # Final landing near hoop
    ball.append([9, land_x, hy + 50, 0.9])

    shooter = [_player(f, hx - 150, hy + 80) for f in range(0, 3)]
    decision = _classify(ball, shooter)
    assert decision["rule"] != srm.RULE_PASS
    assert not srm.is_caught_near_hoop(
        ball, shooter, _hoops(20), NEAR, RIM_C, RIM_R, CATCH_F, FPS
    )


def test_ball_in_rim_zone_with_overlapping_player_is_shot():
    """Rim zone → SHOT even if a player box overlaps the hoop (C2)."""
    hx, hy = HOOP["x"], HOOP["y"]
    ball = [
        [0, hx - 100, hy - 100, 0.9],
        [1, hx - 50, hy - 80, 0.9],
        [2, hx, hy - 20, 0.9],
        [3, hx + 5, hy + 10, 0.9],  # in rim zone, at rim-height band
    ]
    # Player box centered on hoop (overlap in 2D)
    players = [_player(3, hx, hy, w=80.0, h=100.0)]
    decision = _classify(ball, players)
    assert decision["rule"] == srm.RULE_SHOT
    hit, _ = srm.hits_rim(ball, _hoops(10), RIM_C, RIM_R, FPS)
    assert hit is True


def test_pass_caught_under_basket_is_pass():
    """Near hoop (not rim), leave shooter, enter catcher → PASS."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    # Stay outside rim_contact (0.735 hw) for the whole flight; land ~1.0 hw out.
    land_x = hx + 1.0 * hw
    ball = []
    for f in range(0, 3):
        ball.append([f, hx - 200, hy + 60, 0.9])  # shooter
    # Arc that never enters the rim zone (horizontal offset stays >= 1.0 hw).
    for f, y in enumerate([hy - 90, hy - 110, hy - 70, hy - 30], start=3):
        ball.append([f, land_x, y, 0.9])  # flight above the catch spot
    ball.append([7, land_x, hy - 10, 0.9])
    ball.append([8, land_x, hy + 20, 0.9])
    ball.append([9, land_x, hy + 55, 0.9])  # landing near

    players = [_player(f, hx - 200, hy + 60) for f in range(0, 3)]
    players += [_player(7, land_x, hy - 10, w=70.0, h=130.0)]
    players += [_player(8, land_x, hy + 20, w=70.0, h=130.0)]

    decision = _classify(ball, players)
    assert decision["rule"] == srm.RULE_PASS


def test_same_flight_no_catch_is_airball():
    """Same near-hoop landing, no catcher → AIRBALL."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    land_x = hx + 1.0 * hw
    ball = []
    for f in range(0, 3):
        ball.append([f, hx - 180, hy + 60, 0.9])
    # Keep x at land_x so landing-at-hoop_y stays ~1.0 hw (not rim zone).
    for f, y in enumerate([hy - 90, hy - 110, hy - 70, hy - 30, hy + 10, hy + 55], start=3):
        ball.append([f, land_x, y, 0.9])
    players = [_player(f, hx - 180, hy + 60) for f in range(0, 3)]
    decision = _classify(ball, players)
    assert decision["rule"] == srm.RULE_AIRBALL


def test_pass_caught_on_wing_far_is_not_a_shot():
    """land_dist > near_hoop → NOT A SHOT; catch never checked (v3)."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    land_x = hx + 3.0 * hw  # well past near_hoop (1.833)
    ball = []
    for f in range(0, 3):
        ball.append([f, hx - 200, hy + 80, 0.9])
    for f, y in enumerate([hy - 40, hy - 20, hy + 40, hy + 100], start=3):
        t = (f - 3) / 3.0
        x = (hx - 200) * (1 - t) + land_x * t
        ball.append([f, x, y, 0.9])
    # A "catch" on the wing — must NOT flip this to PASS.
    players = [_player(f, hx - 200, hy + 80) for f in range(0, 3)]
    players += [_player(5, land_x, hy + 40, w=70.0, h=130.0)]
    players += [_player(6, land_x, hy + 100, w=70.0, h=130.0)]

    decision = _classify(ball, players)
    assert decision["rule"] == srm.RULE_NOT_A_SHOT
    assert not srm.is_caught_near_hoop(
        ball, players, _hoops(20), NEAR, RIM_C, RIM_R, CATCH_F, FPS
    )


def test_gap_mid_flight_reported_no_fill():
    """Gap > 3 frames during flight → reported; track not filled; ORANGE."""
    hx, hy = HOOP["x"], HOOP["y"]
    # Rise, then 10-frame gap, then landing near
    ball = [
        [0, hx - 100, hy + 40, 0.9],
        [1, hx - 80, hy - 90, 0.9],  # above rim
        [2, hx - 60, hy - 110, 0.9],
        # gap frames 3..12 missing (10 frames)
        [13, hx + 90, hy + 50, 0.9],
    ]
    gaps = srm.gap_report(ball, GAP_N)
    assert gaps["longest_gap_frames"] == 10
    assert gaps["gap_exceeds_threshold"] is True
    # No fill: only 4 detections
    assert gaps["frames_seen"] == 4
    decision = _classify(ball, [])
    assert decision["rule"] == srm.RULE_ORANGE
    assert "gap" in decision["reason"]


def test_unclear_orange_with_reason():
    """Empty / incomplete → ORANGE with a reason string."""
    decision = _classify([], [])
    assert decision["rule"] == srm.RULE_ORANGE
    assert decision["reason"]

    # Track ends still above rim after a rise → descent not seen
    hx, hy = HOOP["x"], HOOP["y"]
    ball = [
        [0, hx - 50, hy + 20, 0.9],
        [1, hx - 40, hy - 100, 0.9],
        [2, hx - 30, hy - 120, 0.9],
    ]
    # No large gap; still ends above rim
    orange, reason = srm.is_orange_card(
        ball, _hoops(10), [], NEAR, RIM_R, GAP_N, FPS
    )
    assert orange is True
    assert "descent not seen" in reason


def test_window_merge_two_moments_2000_ms_apart():
    """before=3000 after=2000: tags 2000 ms apart → one merged range, two slices."""
    moments = [
        {"tag_t_ms": 100_000, "moment_id": "a"},
        {"tag_t_ms": 102_000, "moment_id": "b"},
    ]
    merged = cft.merge_overlapping_windows(moments, 3000, 2000)
    assert len(merged) == 1
    assert merged[0]["moment_indices"] == [0, 1]
    assert merged[0]["start_ms"] == 100_000 - 3000
    assert merged[0]["end_ms"] == 102_000 + 2000

    # Slice identity: each moment keeps its own window bounds.
    per_frame = {}
    for f in range(cft.ms_to_frame(97000, FPS), cft.ms_to_frame(104000, FPS) + 1):
        per_frame[f] = {
            "ball_bodd": [f, 1.0, 2.0, 0.5],
            "ball_v6": None,
            "hoop": None,
            "players": [],
        }
    s0 = cft.slice_moment(moments[0], per_frame, FPS, 3000, 2000)
    s1 = cft.slice_moment(moments[1], per_frame, FPS, 3000, 2000)
    assert s0["window_ms"]["lo"] == 97000
    assert s0["window_ms"]["hi"] == 102000
    assert s1["window_ms"]["lo"] == 99000
    assert s1["window_ms"]["hi"] == 104000
    assert s0["moment_id"] == "a" and s1["moment_id"] == "b"


def test_hoop_width_units_same_on_1920_and_1280_scaled_copy():
    """Same track scaled 1280/1920 with hoop_w scaled → same rule (rim_r unscaled)."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    ball_1920 = [
        [0, hx - 100, hy - 100, 0.9],
        [1, hx - 40, hy - 90, 0.9],
        [2, hx + 5, hy + 5, 0.9],
    ]
    hoops_1920 = _hoops(10)
    d1 = srm.classify_flight(
        ball_1920, [], hoops_1920, RIM_C, NEAR, RIM_R, CATCH_F, GAP_N, FPS
    )

    scale = 1280.0 / 1920.0
    ball_1280, hoops_1280 = _scale_track(ball_1920, hoops_1920, scale)
    # rim_r_px stays 72; rim_r_at_hoop scales with hoop_w (F3)
    d2 = srm.classify_flight(
        ball_1280,
        [],
        hoops_1280,
        RIM_C,
        NEAR,
        RIM_R,
        CATCH_F,
        GAP_N,
        FPS,
    )
    assert d1["rule"] == d2["rule"] == srm.RULE_SHOT


def test_q4_filter_drops_q4_moments():
    moments = [
        {"quarter": "Q1", "tag_t_ms": 1},
        {"quarter": "Q4", "tag_t_ms": 2},
        {"quarter": "Q3", "tag_t_ms": 3},
        {"quarter": "Q4", "tag_t_ms": 4},
    ]
    kept = cft.filter_out_q4(moments)
    assert [m["tag_t_ms"] for m in kept] == [1, 3]
    assert all(m["quarter"] != "Q4" for m in kept)


# ---------------------------------------------------------------------------
# Additional spec section 9 cases
# ---------------------------------------------------------------------------


def test_clean_shot_hits_rim():
    hx, hy = HOOP["x"], HOOP["y"]
    # Stay outside rim_contact until the final frame.
    ball = [
        [0, hx - 200, hy - 100, 0.9],
        [1, hx - 150, hy - 80, 0.9],
        [2, hx, hy, 0.9],
    ]
    hit, frame = srm.hits_rim(ball, _hoops(10), RIM_C, RIM_R, FPS)
    assert hit is True and frame == 2
    assert _classify(ball, [])["rule"] == srm.RULE_SHOT


def test_airball_short():
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    land_x = hx + 1.2 * hw
    ball = [
        [0, hx - 120, hy + 40, 0.9],
        [1, hx - 60, hy - 100, 0.9],
        [2, hx, hy - 80, 0.9],
        [3, land_x, hy + 40, 0.9],
    ]
    assert srm.is_airball_near_hoop(
        ball, _hoops(10), NEAR, RIM_C, RIM_R, FPS
    )
    assert _classify(ball, [])["rule"] == srm.RULE_AIRBALL


def test_overthrown_pass_never_rises_is_bad_pass():
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    ball = [
        [0, hx - 300, hy + 100, 0.9],
        [1, hx - 200, hy + 110, 0.9],
        [2, hx + 3 * hw, hy + 150, 0.9],
    ]
    assert srm.is_bad_pass(ball, _hoops(10), NEAR, RIM_R, FPS)
    assert _classify(ball, [])["rule"] == srm.RULE_NOT_A_SHOT


def test_combine_ball_prefers_v6_no_average_no_fill():
    v6 = [[5, 10.0, 20.0, 0.9]]
    bodd = [[5, 11.0, 21.0, 0.8], [6, 12.0, 22.0, 0.7]]
    combined = srm.combine_ball_track(v6, bodd)
    assert combined[0] == [5.0, 10.0, 20.0, 0.9]  # v6 wins frame 5
    assert combined[1] == [6.0, 12.0, 22.0, 0.7]  # bodd only on 6
    assert len(combined) == 2  # no fill for missing frames


def test_trace_release_finds_player_box():
    ball = [
        [0, 100.0, 200.0, 0.9],
        [1, 110.0, 180.0, 0.9],
        [2, 200.0, 100.0, 0.9],
    ]
    players = [_player(0, 100.0, 200.0, w=50.0, h=100.0)]
    ok, rf, box = srm.trace_release(ball, players, 2, RELEASE_F)
    assert ok is True and rf == 0 and box is not None


def test_rim_height_pad_scales_with_hoop_w():
    assert srm.rim_height_pad_px(98.0) == 40.0
    assert abs(srm.rim_height_pad_px(49.0) - 20.0) < 1e-9


def test_rim_r_at_hoop_scales_like_pad():
    """F3: court_memory.py:165 rim_r=72 scaled by hoop_w / 98.0."""
    assert srm.rim_r_at_hoop(72.0, 98.0) == 72.0
    assert abs(srm.rim_r_at_hoop(72.0, 49.0) - 36.0) < 1e-9


# ---------------------------------------------------------------------------
# F6 — realistic full-window tracks
# ---------------------------------------------------------------------------


def _make_through_rim_full_window():
    """Dribble (6-frame gap) → release → rise → peak → through rim → floor 2 s."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    ball = []
    # Dribble below rim, frames 0..19, with a 6-frame gap (10..15 missing).
    for f in list(range(0, 10)) + list(range(16, 20)):
        ball.append([f, hx - 180, hy + 120 + (f % 3) * 5, 0.9])
    # Gather / release just below rim (last ball before rise).
    ball.append([20, hx - 120, hy + 50, 0.9])
    # Rise above rim (y < hoop_y - rim_r_at_hoop ≈ hoop_y - 72), peak, through rim.
    flight_ys = [
        hy - 80,   # 21 — first above rim
        hy - 110,  # 22
        hy - 150,  # 23 peak
        hy - 100,  # 24
        hy - 50,   # 25
        hy - 10,   # 26 still above hoop_y
        hy + 5,    # 27 landing at/through rim
    ]
    for i, y in enumerate(flight_ys):
        f = 21 + i
        x = hx - 20 + i * 3  # stays in rim zone at landing
        ball.append([f, x, y, 0.9])
    # Net / floor for ~2 s (50 frames at 25 fps) after landing — must NOT move landing.
    land_f = 27
    for f in range(land_f + 1, land_f + 1 + 50):
        # Fall toward floor well below hoop
        y = hy + 40 + (f - land_f) * 8
        ball.append([f, hx + 10, min(y, hy + 450), 0.9])
    return ball, _hoops(land_f + 60)


def test_f6a_make_dribble_gap_then_through_rim_is_shot():
    """(a) Dribble gap before release + through rim + floor 2 s → SHOT, not ORANGE."""
    ball, hoops = _make_through_rim_full_window()
    decision = _classify(ball, [], hoops)
    assert decision["rule"] == srm.RULE_SHOT
    assert decision["rule"] != srm.RULE_ORANGE
    assert decision["rule"] != srm.RULE_NOT_A_SHOT
    # Pre-flight 6-frame gap must not trip the flight gap flag.
    assert decision["gaps"]["gap_exceeds_threshold"] is False
    assert decision["gaps"]["pre_flight_longest_gap_frames"] >= 6
    # Landing is at hoop height, not the floor.
    assert decision["landing"]["y"] < HOOP["y"] + 30


def test_f6b_miss_off_rim_then_floor_is_shot():
    """(b) Miss off the rim then rebound to the floor → SHOT."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    ball = []
    for f in range(0, 5):
        ball.append([f, hx - 160, hy + 80, 0.9])
    # Rise, peak, come down at rim (small offset still in rim zone), then floor.
    path = [
        (5, hx - 40, hy - 50),
        (6, hx - 20, hy - 110),
        (7, hx - 5, hy - 130),  # peak
        (8, hx + 10, hy - 60),
        (9, hx + 20, hy - 5),
        (10, hx + 25, hy + 2),  # landing near rim (within rim_contact)
    ]
    for f, x, y in path:
        ball.append([f, x, y, 0.9])
    # Rebound / floor for ~1 s
    for f in range(11, 40):
        ball.append([f, hx + 40 + (f - 11) * 3, hy + 80 + (f - 11) * 10, 0.9])
    decision = _classify(ball, [], _hoops(50))
    assert decision["rule"] == srm.RULE_SHOT


def test_f6c_airball_short_then_floor_is_airball():
    """(c) Airball short landing 1.5 hoop widths out then rolling on floor → AIRBALL."""
    hx, hy, hw = HOOP["x"], HOOP["y"], HOOP_W
    land_x = hx + 1.5 * hw
    ball = []
    for f in range(0, 4):
        ball.append([f, hx - 200, hy + 70, 0.9])
    path = [
        (4, hx - 80, hy - 40),
        (5, hx - 20, hy - 100),
        (6, hx + 40, hy - 120),  # peak
        (7, hx + 80, hy - 50),
        (8, land_x, hy - 5),
        (9, land_x, hy + 2),  # landing 1.5 hw out
    ]
    for f, x, y in path:
        ball.append([f, x, y, 0.9])
    # Rolling on the floor after landing
    for f in range(10, 45):
        ball.append([f, land_x + (f - 10) * 2, hy + 200 + (f - 10) * 3, 0.9])
    decision = _classify(ball, [], _hoops(50))
    assert decision["rule"] == srm.RULE_AIRBALL
    land_hw = decision["landing"]["land_dist_px"] / decision["landing"]["hoop_w"]
    assert abs(land_hw - 1.5) < 0.15


def test_f6d_lost_after_peak_is_orange_descent_not_seen():
    """(d) Ball lost after the peak, never seen back at hoop_y → ORANGE."""
    hx, hy = HOOP["x"], HOOP["y"]
    ball = [
        [0, hx - 100, hy + 40, 0.9],
        [1, hx - 60, hy - 50, 0.9],
        [2, hx - 30, hy - 110, 0.9],
        [3, hx - 10, hy - 140, 0.9],  # peak — then gone
    ]
    decision = _classify(ball, [], _hoops(20))
    assert decision["rule"] == srm.RULE_ORANGE
    assert decision["reason"] == "descent not seen"
    landing = srm.find_landing(ball, _hoops(20), RIM_R, FPS)
    assert landing is not None and landing["descent_not_seen"] is True


def test_f6e_1280_scaled_copy_same_rule():
    """(e) Same track on 1280-wide copy (all px and hoop_w × 2/3) → same rule."""
    ball, hoops = _make_through_rim_full_window()
    d1 = _classify(ball, [], hoops)
    scale = 1280.0 / 1920.0  # 2/3
    ball_s, hoops_s = _scale_track(ball, hoops, scale)
    d2 = srm.classify_flight(
        ball_s, [], hoops_s, RIM_C, NEAR, RIM_R, CATCH_F, GAP_N, FPS
    )
    assert d1["rule"] == d2["rule"] == srm.RULE_SHOT


def test_f6f_missing_hoop_uses_previous_frame_hoop():
    """(f) A frame with no hoop uses the previous frame's hoop."""
    hx, hy = HOOP["x"], HOOP["y"]
    # Hoop only on even frames; odd frames must carry earlier.
    hoops = _hoops_sparse([0, 2, 4, 6, 8, 10], n=12)
    # Frame 5 has no hoop sample — carry frame 4.
    got = srm.hoop_for_frame(hoops, 5, FPS)
    assert got is not None
    assert int(got["t"]) == int(round(1000.0 * 4 / FPS))
    # And a through-rim classify still works with sparse hoops.
    ball = [
        [0, hx - 100, hy + 40, 0.9],
        [1, hx - 60, hy - 80, 0.9],
        [2, hx - 20, hy - 120, 0.9],
        [3, hx, hy - 40, 0.9],
        [4, hx + 5, hy + 5, 0.9],
    ]
    decision = _classify(ball, [], hoops)
    assert decision["rule"] == srm.RULE_SHOT


def test_f6a_coverage_uses_release_to_landing_span():
    """Coverage / gap_exceeds only count release..landing (F2)."""
    ball, hoops = _make_through_rim_full_window()
    cov = srm.flight_coverage(ball, hoops, RIM_R, FPS, GAP_N)
    assert cov["release_frame"] is not None
    assert cov["landing_frame"] is not None
    assert cov["gap_exceeds_threshold"] is False
    # Floor frames after landing are not in frames_seen for the flight span.
    assert cov["landing_frame"] < ball[-1][0]
    assert cov["frames_seen"] < len(ball)
