"""NFHS stat rules + court memory (FT lane, assist, TO/steal, O/D reb, block, paint)."""

from court_memory import (
    FrameCourtMemory,
    KeyPolygon,
    ball_through_rim,
    classify_zoom,
    detect_ft_formation,
    key_from_people,
)
from stat_rules import (
    classify_rebound,
    classify_shot_kind,
    classify_turnover_kind,
    credit_assist,
    credit_block,
    credit_steal,
    points_for_kind,
    scoring_event_type,
    second_chance_make,
)


def test_assist_requires_made_fg_short_hold_not_ft():
    assert credit_assist(
        shot_made=True, shot_kind="2", passer_id="1", scorer_id="2",
        pass_gap_frames=8, scorer_hold_ms=900,
    )
    assert not credit_assist(
        shot_made=True, shot_kind="ft", passer_id="1", scorer_id="2",
        pass_gap_frames=8, scorer_hold_ms=400,
    )
    assert not credit_assist(
        shot_made=True, shot_kind="2", passer_id="1", scorer_id="2",
        pass_gap_frames=8, scorer_hold_ms=4000,
    )
    assert not credit_assist(
        shot_made=False, shot_kind="2", passer_id="1", scorer_id="2",
        pass_gap_frames=8, scorer_hold_ms=400,
    )


def test_rebound_same_color_is_offensive():
    assert classify_rebound(shooter_team="white", rebounder_team="white") == "oreb"
    assert classify_rebound(shooter_team="white", rebounder_team="black") == "dreb"
    assert classify_rebound(shooter_team=None, rebounder_team=None, shooter_id="4", rebounder_id="4") == "oreb"
    assert classify_rebound(
        shooter_team=None, rebounder_team=None, shooter_id="4", rebounder_id="9",
        offense_ids=["4", "11", "9"],
    ) == "oreb"
    assert classify_rebound(
        shooter_team=None, rebounder_team=None, shooter_id="4", rebounder_id="2",
        offense_ids=["4", "11"],
    ) == "dreb"


def test_steal_not_on_dead_ball_or_loose_pickup():
    assert credit_steal(after_shot=False, dead_ball=False, next_ball_distance=20, prev_lost_abruptly=True)
    assert not credit_steal(after_shot=False, dead_ball=True, next_ball_distance=20, prev_lost_abruptly=True)
    assert not credit_steal(after_shot=False, dead_ball=False, next_ball_distance=120, prev_lost_abruptly=True)
    assert classify_turnover_kind(dead_ball=True, after_shot=False) == "dead"
    assert classify_turnover_kind(dead_ball=False, after_shot=False) == "live"
    assert classify_turnover_kind(dead_ball=True, after_shot=True) is None


def test_block_deflection_not_a_make():
    assert credit_block(
        shot_went_in=False, defender_is_shooter=False, gap_frames=2,
        ball_deflected_away=True, defender_near_ball=True,
    )
    assert not credit_block(
        shot_went_in=True, defender_is_shooter=False, gap_frames=2,
        ball_deflected_away=True, defender_near_ball=True,
    )


def test_shot_kind_ft_wins_then_paint_then_three():
    assert classify_shot_kind(ft_formation="lane", in_paint=True, dist_from_basket=0.8) == "ft"
    assert classify_shot_kind(ft_formation=None, in_paint=True, dist_from_basket=0.2) == "2"
    assert classify_shot_kind(ft_formation=None, in_paint=False, dist_from_basket=1.6) == "3"
    assert scoring_event_type("ft", True) == "made_free_throw"
    assert points_for_kind("3", True) == 3


def test_second_chance_only_after_oreb():
    assert second_chance_make(previous_rebound_kind="oreb", same_team_still_offense=True, made=True)
    assert not second_chance_make(previous_rebound_kind="dreb", same_team_still_offense=True, made=True)


def test_zoom_out_is_dead_ball_and_ft_lane_locks_key():
    assert classify_zoom(80, 140) == "out"
    assert classify_zoom(135, 140) == "in"
    left = [{"x": 200, "y": 400, "height": 120} for _ in range(3)]
    right = [{"x": 500, "y": 400, "height": 120} for _ in range(3)]
    shooter = {"x": 350, "y": 250, "height": 140}
    people = left + right + [shooter]
    ball = {"x": 350, "y": 220}
    assert detect_ft_formation(people, ball, pan_abs=1, dead_ball=True) == "lane"
    assert detect_ft_formation(people, ball, pan_abs=40, dead_ball=True) is None
    assert detect_ft_formation(
        [{"x": 350, "y": 300, "height": 140}],
        {"x": 350, "y": 200},
        pan_abs=0,
        dead_ball=False,
    ) is None
    assert detect_ft_formation(
        [{"x": 350, "y": 300, "height": 140}],
        {"x": 350, "y": 200},
        pan_abs=0,
        dead_ball=True,
    ) == "technical"
    assert detect_ft_formation(people, ball, pan_abs=1, dead_ball=False) is None
    assert detect_ft_formation(
        people, ball, pan_abs=1, prev_people=people, dead_ball=False
    ) == "lane"
    key = key_from_people(people, ball)
    assert key is not None and key.contains(350, 300)
    mem = FrameCourtMemory()
    mem.observe(people, ball)
    mem.observe(people, ball)
    assert mem.key is not None
    assert isinstance(mem.key, KeyPolygon)
    shifted = [{"x": p["x"] + 4, "y": p["y"], "height": p["height"]} for p in people]
    mem.observe(shifted, {"x": 354, "y": 220})
    assert mem.in_paint(354, 300)


def test_technical_requires_empty_space_around_shooter():
    shooter = {"x": 350, "y": 240, "height": 140}
    friend = {"x": 370, "y": 250, "height": 120}
    assert detect_ft_formation(
        [shooter, friend], {"x": 350, "y": 200}, pan_abs=0, dead_ball=True
    ) is None
    assert detect_ft_formation(
        [shooter], {"x": 350, "y": 200}, pan_abs=0, dead_ball=True
    ) == "technical"
    spread = [
        shooter,
        {"x": 120, "y": 500, "height": 120},
        {"x": 700, "y": 500, "height": 120},
    ]
    assert detect_ft_formation(spread, {"x": 350, "y": 200}, pan_abs=0, dead_ball=True) is None


def test_near_basket_is_the_hoop_not_a_sideline_peak():
    mem = FrameCourtMemory()
    mem.key = KeyPolygon(300, 200, 500, 500)
    assert mem.near_basket(400, 180)
    assert not mem.near_basket(50, 80)
    assert not mem.near_basket(400, 700)
    assert mem.aimed_at_hoop(400, 180)
    assert not mem.aimed_at_hoop(20, 80)
    assert not mem.aimed_at_hoop(1700, 180)
    assert mem.close_to_rim(400, 210)
    assert not mem.close_to_rim(50, 80)


def test_ball_through_rim_is_net_column_not_a_clank():
    import pandas as pd

    hoop = (400.0, 200.0)
    swish = pd.DataFrame({
        "frame_number": list(range(10, 28)),
        "x_center": [400.0] * 18,
        "y_center": [190.0 + i * 8.0 for i in range(18)],
        "confidence": [0.8] * 18,
    })
    clank = pd.DataFrame({
        "frame_number": list(range(10, 28)),
        "x_center": [400.0 + i * 20.0 for i in range(18)],
        "y_center": [190.0 + i * 8.0 for i in range(18)],
        "confidence": [0.8] * 18,
    })
    fake = pd.DataFrame({
        "frame_number": list(range(10, 28)),
        "x_center": [80.0] * 18,
        "y_center": [40.0 + i * 8.0 for i in range(18)],
        "confidence": [0.3] * 18,
    })
    assert ball_through_rim(swish, 12, hoop)
    assert not ball_through_rim(clank, 12, hoop)
    assert not ball_through_rim(fake, 12, hoop)


def test_ft_lane_ignores_frame_edge_boxes():
    left = [{"x": 220, "y": 400, "height": 120} for _ in range(3)]
    right = [{"x": 520, "y": 400, "height": 120} for _ in range(3)]
    shooter = {"x": 370, "y": 250, "height": 140}
    junk = [{"x": 1919, "y": 400, "height": 80} for _ in range(6)]
    people = left + right + [shooter] + junk
    assert detect_ft_formation(people, {"x": 370, "y": 220}, pan_abs=1, dead_ball=True) == "lane"
