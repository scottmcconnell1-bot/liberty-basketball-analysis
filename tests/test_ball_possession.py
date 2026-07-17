"""Tests for enhanced ball possession scoring."""

import pandas as pd

from ball_possession import (
    apply_temporal_possession_filter,
    assign_ball_possession,
    ball_containment_ratio,
)


def _player(frame, x, y, tracker_id=1, width=80, height=120):
    return {
        "frame_number": frame,
        "timestamp_ms": frame * 33,
        "class_name": "person",
        "x_center": x,
        "y_center": y,
        "width": width,
        "height": height,
        "tracker_id": tracker_id,
        "cluster_id": 0,
    }


def _ball(frame, x, y, width=20, height=20):
    return {
        "frame_number": frame,
        "timestamp_ms": frame * 33,
        "class_name": "ball",
        "x_center": x,
        "y_center": y,
        "width": width,
        "height": height,
        "tracker_id": None,
        "cluster_id": -1,
    }


def test_ball_containment_ratio_full_overlap():
    player = pd.Series(_player(0, 100, 100))
    ball = pd.Series(_ball(0, 100, 100, width=20, height=20))
    assert ball_containment_ratio(player, ball) == 1.0


def test_temporal_filter_requires_consecutive_frames():
    identities = ["t:2", "t:2", "t:2", None, "t:9", "t:9", "t:9", "t:9"]
    confirmed = apply_temporal_possession_filter(identities, min_consecutive_frames=3)
    assert confirmed == {0, 1, 2, 4, 5, 6, 7}


def test_assign_ball_possession_prefers_containment_over_distant_player():
    rows = []
    for frame in range(6):
        rows.append(_player(frame, 200, 400, tracker_id=1))
        rows.append(_player(frame, 205, 405, tracker_id=2))
        rows.append(_ball(frame, 204, 404))

    df = pd.DataFrame(rows)
    result = assign_ball_possession(
        df,
        possession_threshold=120,
        containment_threshold=0.2,
        min_consecutive_frames=3,
    )

    holder = result[(result["class_name"] == "person") & (result["has_ball"])]
    assert not holder.empty
    assert set(holder["tracker_id"].astype(int)) == {2}


def test_assign_ball_possession_rejects_one_frame_flicker():
    rows = []
    for frame in range(5):
        rows.append(_player(frame, 200, 400, tracker_id=1))
        rows.append(_player(frame, 205, 405, tracker_id=2))
        rows.append(_ball(frame, 204, 404))
    # One-frame flicker to the wrong player
    rows.append(_player(5, 500, 500, tracker_id=9))
    rows.append(_ball(5, 505, 505))

    df = pd.DataFrame(rows)
    result = assign_ball_possession(
        df,
        possession_threshold=200,
        containment_threshold=0.2,
        min_consecutive_frames=3,
    )
    flicker_holder = result[(result["frame_number"] == 5) & (result["has_ball"])]
    assert flicker_holder.empty
