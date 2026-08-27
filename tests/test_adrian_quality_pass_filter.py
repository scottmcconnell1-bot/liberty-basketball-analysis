"""Unit tests for Adrian event identity filters (quality v3)."""

import json

from adrian_quality import (
    build_opening_jump_ball_event,
    build_possession_changes,
    counting_links_to_kept_shot,
    drop_pass_like_shots,
    drop_tipoff_rebounds,
    drop_tipoff_shots,
    filter_counting_to_real_shots,
    infer_opening_tip,
    is_pass_like_shot,
    is_tipoff_shot,
    prefer_steal_over_block,
)


def test_scott_false_made_two_is_pass_like():
    # made_two · tracker #5 @ 27.433s was a pass 5→9 at +33ms, rise 81
    events = [
        {
            "id": 1,
            "event_type": "made_two",
            "player": "5",
            "timestamp_ms": 27433,
            "confidence": 0.52,
            "details_json": '{"ball_rise": 81.0, "lateral_travel": 88.0}',
        },
        {
            "id": 2,
            "event_type": "possession_change",
            "player": "9",
            "timestamp_ms": 27466,
            "details_json": '{"from_player": "5", "to_player": "9"}',
        },
    ]
    pcs = build_possession_changes(events)
    assert is_pass_like_shot(events[0], pcs) is True
    kept, dropped = drop_pass_like_shots(events, pcs)
    assert dropped == 1
    assert [e["id"] for e in kept] == [2]


def test_high_arc_without_outbound_pass_kept():
    events = [
        {
            "id": 10,
            "event_type": "made_two",
            "player": "2",
            "timestamp_ms": 90000,
            "confidence": 0.52,
            "details_json": '{"ball_rise": 210.0, "lateral_travel": 180.0}',
        },
    ]
    pcs = build_possession_changes(events)
    assert is_pass_like_shot(events[0], pcs) is False
    kept, dropped = drop_pass_like_shots(events, pcs)
    assert dropped == 0
    assert kept[0]["id"] == 10


def test_block_on_high_pass_dropped_without_kept_miss():
    # Contested high pass → CV miss+block; no real kept miss → drop block.
    block = {
        "id": 20,
        "event_type": "block",
        "player": "7",
        "timestamp_ms": 65200,
        "details_json": '{"shot_player": "0", "gap_frames": 2}',
    }
    steal = {
        "id": 21,
        "event_type": "steal",
        "player": "7",
        "timestamp_ms": 65200,
        "details_json": '{"from_player": "0"}',
    }
    kept_shots = []  # pass-like miss already dropped
    linked = counting_links_to_kept_shot(block, [], [])
    assert linked is False
    kept, dropped = filter_counting_to_real_shots([block, steal], kept_shots)
    assert dropped == 1
    assert [e["id"] for e in kept] == [21]


def test_block_kept_when_linked_to_kept_miss():
    miss = {
        "id": 30,
        "event_type": "missed_two",
        "player": "2",
        "timestamp_ms": 100000,
        "shot_result": "miss",
        "details_json": '{"ball_rise": 200.0}',
    }
    block = {
        "id": 31,
        "event_type": "block",
        "player": "5",
        "timestamp_ms": 100200,
        "details_json": '{"shot_player": "2", "gap_frames": 2}',
    }
    assert counting_links_to_kept_shot(block, [], [miss]) is True
    kept, dropped = filter_counting_to_real_shots([block], [miss])
    assert dropped == 0
    assert kept[0]["id"] == 31


def test_prefer_steal_over_nearby_block():
    block = {
        "id": 40,
        "event_type": "block",
        "player": "8",
        "timestamp_ms": 5000,
        "details_json": '{"shot_player": "6"}',
    }
    steal = {
        "id": 41,
        "event_type": "steal",
        "player": "8",
        "timestamp_ms": 5100,
        "details_json": '{"from_player": "6"}',
    }
    kept, dropped = prefer_steal_over_block([block, steal])
    assert dropped == 1
    assert [e["id"] for e in kept] == [41]


def test_jump_ball_made_two_dropped_as_tipoff():
    # Scott: made_two · tracker #8 @ ~3s was the opening jump ball
    tip = {
        "id": 929689,
        "event_type": "made_two",
        "player": "8",
        "timestamp_ms": 3000,
        "confidence": 0.52,
        "details_json": '{"ball_rise": 152.0, "lateral_travel": 53.0}',
    }
    later = {
        "id": 50,
        "event_type": "made_two",
        "player": "2",
        "timestamp_ms": 36000,
        "confidence": 0.52,
        "details_json": '{"ball_rise": 208.0}',
    }
    assert is_tipoff_shot(tip) is True
    assert is_tipoff_shot(later) is False
    kept, dropped = drop_tipoff_shots([tip, later])
    assert dropped == 1
    assert [e["id"] for e in kept] == [50]


def test_tip_scramble_rebound_dropped():
    tip_info = {"tip_ms": 3000, "winner_tracker": "2"}
    tip_reb = {
        "id": 1,
        "event_type": "rebound",
        "player": "8",
        "timestamp_ms": 2933,
    }
    mid = {
        "id": 2,
        "event_type": "rebound",
        "player": "5",
        "timestamp_ms": 90000,
    }
    kept, dropped = drop_tipoff_rebounds([tip_reb, mid], tip_info)
    assert dropped == 1
    assert [e["id"] for e in kept] == [2]


def test_filename_ha_marks_home_away():
    from adrian_quality import parse_home_away_from_title, resolve_adrian_teams

    parsed = parse_home_away_from_title(
        "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    )
    assert parsed["home"] == "Adrian"
    assert parsed["away"] == "Liberty"
    teams = resolve_adrian_teams(game_id="jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334")
    assert teams["home_team"] == "Adrian"
    assert teams["away_team"] == "Liberty"


def test_post_rebound_make_with_outlet_is_pass_like():
    # Scott: made_two #9 @ 12.2s right after rebound, then 9→8 — not a basket
    raw = [
        {
            "id": 1,
            "event_type": "rebound",
            "player": "9",
            "timestamp_ms": 10900,
            "details_json": '{"shot_player": "9"}',
        },
        {
            "id": 2,
            "event_type": "made_two",
            "player": "9",
            "timestamp_ms": 12200,
            "details_json": '{"ball_rise": 237.0, "lateral_travel": 119.0}',
        },
        {
            "id": 3,
            "event_type": "possession_change",
            "player": "8",
            "timestamp_ms": 12370,
            "details_json": '{"from_player": "9", "to_player": "8"}',
        },
    ]
    pcs = build_possession_changes(raw)
    assert is_pass_like_shot(raw[1], pcs, rebounds=[raw[0]]) is True
    kept, dropped = drop_pass_like_shots([raw[1]], pcs, raw_events=raw)
    assert dropped == 1
    assert kept == []


def test_infer_opening_tip_winner_first_controlled_hold():
    raw = [
        {
            "id": 1,
            "event_type": "made_two",
            "player": "8",
            "timestamp_ms": 3000,
            "details_json": '{"ball_rise": 152.0}',
        },
        {
            "id": 2,
            "event_type": "possession_change",
            "player": "8",
            "timestamp_ms": 2933,
            "details_json": '{"from_player": "6", "to_player": "8"}',
        },
        {
            "id": 3,
            "event_type": "possession_change",
            "player": "2",
            "timestamp_ms": 3300,
            "details_json": '{"from_player": "8", "to_player": "2"}',
        },
        {
            "id": 4,
            "event_type": "possession_change",
            "player": "6",
            "timestamp_ms": 4200,
            "details_json": '{"from_player": "2", "to_player": "6"}',
        },
    ]
    tip = infer_opening_tip(raw)
    assert tip is not None
    assert tip["winner_tracker"] == "2"
    assert tip["hold_ms"] >= 800
    jb = build_opening_jump_ball_event(raw, tip)
    assert jb is not None
    assert jb["event_type"] == "tip_off"
    assert jb["player"] == "2"
    assert "Opening tip" in (json.loads(jb["details_json"]).get("note") or "")
