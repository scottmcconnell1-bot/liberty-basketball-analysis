"""Precision event generator: fewer, better-supported events than the expanded heuristics."""

import sqlite3

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
