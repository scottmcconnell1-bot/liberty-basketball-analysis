"""Unit tests for manual-taught event calibrator."""
from __future__ import annotations

import json

from event_calibrator import apply_event_calibrator


def _shot(game_id, ts, shot_type="2pt", result="miss", lat=100.0, rise=200.0, conf=0.6):
    return {
        "game_id": game_id,
        "event_type": "shot",
        "shot_result": result,
        "timestamp_ms": ts,
        "confidence": conf,
        "player": "1",
        "details_json": json.dumps(
            {
                "shot_type": shot_type,
                "lateral_travel": lat,
                "ball_rise": rise,
                "secondary_pass": False,
            }
        ),
    }


def test_calibrator_skips_other_analysis_keys():
    model = {
        "analysis_key": "taught-run",
        "shot_label_anchors": [
            {
                "family": "shot",
                "center_ms": 1000,
                "radius_ms": 5000,
                "shot_type": "3pt",
                "shot_result": "miss",
            }
        ],
        "positive_windows": [],
        "keep_clf": {
            "features": ["conf"],
            "weights": [0.0],
            "bias": 10.0,
            "threshold": 0.01,
        },
    }
    events = [_shot("other-run", 1000, shot_type="2pt")]
    out = apply_event_calibrator(events, model)
    details = json.loads(out[0]["details_json"])
    assert details.get("shot_type") == "2pt"
    assert not details.get("taught_shot_type")


def test_calibrator_applies_shot_anchor_on_taught_run():
    model = {
        "analysis_key": "taught-run",
        "clock_offset_ms": 0,
        "shot_label_anchors": [
            {
                "family": "shot",
                "center_ms": 1000,
                "radius_ms": 5000,
                "shot_type": "3pt",
                "shot_result": "make",
            }
        ],
        "positive_windows": [],
        "fp_suppress": {"orphan_steal_to": False},
        "keep_clf": {
            "features": ["conf"],
            "weights": [0.0],
            "bias": 10.0,
            "threshold": 0.01,
        },
    }
    events = [_shot("taught-run", 1200, shot_type="2pt", result="miss")]
    out = apply_event_calibrator(events, model)
    assert len(out) == 1
    assert out[0]["shot_result"] == "make"
    details = json.loads(out[0]["details_json"])
    assert details.get("shot_type") == "3pt"
    assert details.get("taught_shot_type") is True
