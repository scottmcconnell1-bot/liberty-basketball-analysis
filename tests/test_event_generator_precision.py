"""Precision event generator: fewer, better-supported events than the expanded heuristics."""

import json
import sqlite3

import numpy as np
import pandas as pd

import event_generator as eg


def _seg(player, start, end, mean_ball_distance=10.0):
    return {
        "player": player,
        "start_frame": start,
        "end_frame": end,
        "duration_frames": end - start + 1,
        "frames": list(range(start, end + 1)),
        "start_timestamp_ms": start * 33,
        "end_timestamp_ms": end * 33,
        "mean_ball_distance": mean_ball_distance,
        "player_x_start": 400.0,
        "player_x_end": 400.0,
        "player_y_median": 500.0,
    }


def _flat_ball_track(frames=400):
    # a ball that never rises: the shot detector cannot fire
    return pd.DataFrame({
        "frame_number": range(frames),
        "timestamp_ms": [f * 33 for f in range(frames)],
        "x_center": [400.0] * frames,
        "y_center": [600.0] * frames,
    })


def test_merge_short_segments_drops_flicker_and_merges_same_player():
    segs = [_seg("1", 0, 20), _seg("2", 21, 22), _seg("1", 23, 40), _seg("3", 41, 80)]
    merged = eg._merge_short_segments(segs, min_hold_frames=6)
    assert [s["player"] for s in merged] == ["1", "3"]
    assert merged[0]["start_frame"] == 0 and merged[0]["end_frame"] == 40


def test_precision_emits_far_fewer_possession_changes_than_expanded():
    # tracker flicker: the possessor id flips every 2 frames for 200 frames
    segs = [_seg(str(i % 3), i * 2, i * 2 + 1) for i in range(100)]
    ball = _flat_ball_track()
    expanded = eg.generate_expanded_events_from_segments("g", segs, ball)
    precise = eg.generate_precision_events_from_segments("g", segs, ball)
    n_exp = sum(e["event_type"] == "possession_change" for e in expanded)
    n_pre = sum(e["event_type"] == "possession_change" for e in precise)
    assert n_exp >= 90
    assert n_pre == 0  # every segment is shorter than min_hold_frames


def test_precision_never_emits_blocks_or_fouls_by_default_and_confidences_vary():
    # holds of 15 / 40 / 60 / 80 frames -> possession_change confidences must differ
    segs = [_seg("1", 0, 14), _seg("2", 15, 54), _seg("1", 55, 114), _seg("3", 115, 194)]
    events = eg.generate_precision_events_from_segments("g", segs, _flat_ball_track())
    types = {e["event_type"] for e in events}
    assert "block" not in types and "foul" not in types
    assert "possession_change" in types
    confs = {round(e["confidence"], 3) for e in events if e["event_type"] == "possession_change"}
    assert len(confs) >= 2  # computed from hold length, not a constant
    assert all(0.0 < e["confidence"] <= 0.95 for e in events)


def test_params_override_defaults():
    segs = [_seg("1", 0, 30), _seg("2", 31, 60), _seg("1", 61, 120)]
    strict = eg.generate_precision_events_from_segments("g", segs, _flat_ball_track(), params={"min_hold_frames": 200})
    assert strict == []  # nothing holds the ball for 200 frames


def test_mode_override_routes_to_precision_even_when_rebuild_forces_expanded(monkeypatch, tmp_path):
    calls = []

    def fake_precision(*a, **k):
        calls.append("precision")
        return []

    def fake_expanded(*a, **k):
        calls.append("expanded")
        return []

    df = pd.DataFrame({
        "frame_number": [0, 1], "timestamp_ms": [0, 33], "class_name": ["person", "ball"],
        "x_center": [1.0, 2.0], "y_center": [1.0, 2.0], "width": [10, 5], "height": [20, 5],
        "confidence": [0.9, 0.5], "tracker_id": [1, None],
    })
    monkeypatch.setattr(eg, "generate_precision_events_from_segments", fake_precision)
    monkeypatch.setattr(eg, "generate_expanded_events_from_segments", fake_expanded)
    monkeypatch.setattr(eg, "get_detections", lambda *a, **k: df)
    monkeypatch.setattr(eg, "_cluster_players_spatially", lambda d, **k: d.assign(cluster_id=1))
    monkeypatch.setattr(eg, "find_ball_possession", lambda d, **k: d)
    monkeypatch.setattr(eg, "build_possession_segments", lambda d, **k: [])
    monkeypatch.setattr(eg, "build_ball_track", lambda d: pd.DataFrame())
    monkeypatch.setattr(eg, "persist_events", lambda *a, **k: None)
    monkeypatch.setattr(eg, "load_all_settings", lambda **k: {"ai": {"event_generator_mode": "expanded"}})
    db = tmp_path / "x.db"
    sqlite3.connect(db).close()
    assert eg.main("g", str(db), force_expanded=True, mode_override="precision") is True
    assert calls == ["precision"]


def test_precision_emits_typed_fg_and_nfhs_assist():
    segs = [_seg("1", 0, 20), _seg("2", 21, 40), _seg("3", 170, 200)]
    frames = list(range(0, 55))
    ys = []
    xs = []
    for i in frames:
        if i < 21:
            ys.append(600.0)
            xs.append(400.0)
        elif i < 34:
            ys.append(500.0 - (i - 21) * 18.0)
            xs.append(430.0)
        else:
            ys.append(400.0 + (i - 34) * 8.0)
            xs.append(430.0)
    ball = pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": xs,
        "y_center": ys,
    })
    det_rows = []
    lane = [(300.0, 320.0), (350.0, 450.0), (450.0, 450.0), (500.0, 320.0)]
    for f in frames:
        h = 200.0 if f < 21 else 120.0
        for i, (px, py) in enumerate(lane):
            det_rows.append({
                "frame_number": f, "class_name": "person",
                "x_center": px, "y_center": py, "width": 40.0, "height": h,
                "confidence": 0.9, "tracker_id": i + 1,
            })
        det_rows.append({
            "frame_number": f, "class_name": "ball",
            "x_center": xs[f], "y_center": ys[f], "width": 8.0, "height": 8.0,
            "confidence": 0.8, "tracker_id": None,
        })
    events = eg.generate_precision_events_from_segments(
        "g", segs, ball, detections_df=pd.DataFrame(det_rows),
    )
    types = {e["event_type"] for e in events}
    assert "assist" in types
    assert types & {"made_two", "made_three", "made_free_throw"}
    assert "make" not in types


def test_precision_does_not_count_a_pass_as_a_turnover():
    segs = [
        _seg("1", 0, 40, mean_ball_distance=12.0),
        _seg("2", 42, 90, mean_ball_distance=14.0),
    ]
    events = eg.generate_precision_events_from_segments("g", segs, _flat_ball_track())
    assert not any(e["event_type"] == "turnover" for e in events)


def test_net_motion_makes_a_shot_when_the_ball_box_vanishes(monkeypatch):
    hoop = {"timestamp_ms": 0, "x": 430.0, "y": 250.0, "r": 28.0}
    monkeypatch.setattr("net_detector.load_hoop_track", lambda _gid: [hoop])
    monkeypatch.setattr("net_detector.hoop_at", lambda *_a, **_k: hoop)
    frames = list(range(0, 36))
    ys, xs = [], []
    for i in frames:
        if i <= 20:
            ys.append(500.0 - i * 12.0)
            xs.append(430.0)
        else:
            # Leaves the column before it can be seen in the net.
            ys.append(260.0 + (i - 20) * 6.0)
            xs.append(430.0 + (i - 20) * 50.0)
    ball = pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": xs,
        "y_center": ys,
    })

    def reader(frame_no):
        img = np.zeros((500, 700, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        # Nylon column under the locked rim at (430, 250).
        if frame_no < 26:
            img[257:328, 399:461] = (170, 170, 170)
        else:
            img[300:410, 390:470] = (220, 220, 220)
        return img

    segs = [_seg("1", 0, 30)]
    events = eg.generate_precision_events_from_segments("g", segs, ball, frame_reader=reader)
    shots = [e for e in events if e["event_type"] == "shot"]
    assert shots
    details = json.loads(shots[0]["details_json"])
    assert shots[0]["shot_result"] == "make"
    assert details["net_moved"] is True
    assert details["through_rim"] is False
    assert any(e["event_type"] in {"made_two", "made_three"} for e in events)


def test_precision_defaults_live_shot_to_miss_without_a_stoppage():
    segs = [_seg("1", 0, 40), _seg("2", 41, 70)]
    frames = list(range(0, 80))
    ys = [500.0 - min(i, 20) * 12.0 if i <= 20 else 260.0 + (i - 20) * 8.0 for i in frames]
    ball = pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": [430.0] * len(frames),
        "y_center": ys,
    })
    events = eg.generate_precision_events_from_segments("g", segs, ball)
    shots = [e for e in events if e["event_type"] == "shot"]
    assert shots
    assert all(e.get("shot_result") == "miss" for e in shots)


def test_precision_drops_low_rise_live_arcs_keeps_lane_ft():
    segs = [_seg("1", 0, 40)]
    frames = list(range(0, 50))
    ball = pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": [400.0] * len(frames),
        "y_center": [480.0 - min(i, 8) * 5.0 for i in frames],
    })
    events = eg.generate_precision_events_from_segments("g", segs, ball)
    assert not any(e["event_type"] == "shot" for e in events)


def _high_arc_ball(frames, x=400.0, start=0):
    ys = []
    xs = []
    for i in frames:
        j = i - start
        if j <= 20:
            ys.append(500.0 - j * 12.0)
        else:
            ys.append(260.0 + (j - 20) * 8.0)
        xs.append(x)
    return pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": xs,
        "y_center": ys,
    })


def test_false_lane_ft_at_the_other_end_is_not_a_shot(monkeypatch):
    monkeypatch.setattr("court_memory.detect_ft_formation", lambda *a, **k: "lane")
    hoop = {"timestamp_ms": 0, "x": 1400.0, "y": 80.0, "r": 20.0}

    def _load(_gid):
        return [hoop]

    def _at(_samples, ts, max_dt_ms=4000):
        return hoop

    monkeypatch.setattr("net_detector.load_hoop_track", _load)
    monkeypatch.setattr("net_detector.hoop_at", _at)
    segs = [_seg("1", 0, 40)]
    events = eg.generate_precision_events_from_segments(
        "g", segs, _high_arc_ball(list(range(0, 80)), x=430.0)
    )
    assert not any(e["event_type"] == "shot" for e in events)


def test_lane_fts_share_the_four_second_gap(monkeypatch):
    monkeypatch.setattr("court_memory.detect_ft_formation", lambda *a, **k: "lane")
    hoop = {"timestamp_ms": 0, "x": 430.0, "y": 80.0, "r": 20.0}
    monkeypatch.setattr("net_detector.load_hoop_track", lambda _gid: [hoop])
    monkeypatch.setattr("net_detector.hoop_at", lambda *_a, **_k: hoop)
    segs = [_seg("1", 0, 40), _seg("1", 45, 90)]
    frames = list(range(0, 120))
    ys = []
    for i in frames:
        start = 0 if i < 45 else 45
        j = i - start
        if j <= 20:
            ys.append(500.0 - j * 12.0)
        else:
            ys.append(260.0 + (j - 20) * 8.0)
    ball = pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": [430.0] * len(frames),
        "y_center": ys,
    })
    events = eg.generate_precision_events_from_segments("g", segs, ball)
    shots = [e for e in events if e["event_type"] == "shot"]
    assert len(shots) == 1


def test_dropped_pump_fake_does_not_block_same_players_real_shot():
    """A candidate the live-rise filter drops must not start the 6 s per-player refractory.

    Player 1 pump-fakes (rise 100 px: a candidate, but under the 170 px live floor),
    passes to 2, gets it back and shoots a real 240 px arc ~1.8 s later.
    """

    def arc(j, top):  # rise to `top` over 10 frames, then fall
        return 500.0 - (500.0 - top) * min(j, 10) / 10.0 + max(0, j - 10) * 12.0

    frames = list(range(160))
    ys = []
    for f in frames:
        if 25 <= f < 45:
            ys.append(arc(f - 25, 400.0))
        elif 81 <= f < 106:
            ys.append(arc(f - 81, 260.0))
        else:
            ys.append(500.0)
    ball = pd.DataFrame({
        "frame_number": frames,
        "timestamp_ms": [f * 33 for f in frames],
        "x_center": [430.0] * len(frames),
        "y_center": ys,
    })
    segs = [_seg("1", 0, 24), _seg("2", 46, 64), _seg("1", 66, 80), _seg("2", 125, 159)]
    events = eg.generate_precision_events_from_segments("g", segs, ball)
    shots = [e for e in events if e["event_type"] == "shot"]
    assert [(s["player"], s["timestamp_ms"]) for s in shots] == [("1", 91 * 33)]
