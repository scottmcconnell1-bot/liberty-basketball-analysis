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
        "positive_windows": [
            {
                "center_ms": 1000,
                "radius_ms": 8000,
                "family": "shot",
                "manual_key": "3PT|Make",
            }
        ],
        "fp_suppress": {
            "orphan_steal_to": False,
            "require_shot_positive_window": True,
            "drop_unanchored_shot_misses": True,
        },
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


def test_calibrator_injects_supervised_foul_and_drops_unanchored_miss():
    model = {
        "analysis_key": "taught-run",
        "clock_offset_ms": 0,
        "match_tolerance_ms": 10000,
        "shot_label_anchors": [],
        "positive_windows": [
            {
                "center_ms": 5000,
                "radius_ms": 10000,
                "family": "foul",
                "manual_key": "Foul",
            },
            {
                "center_ms": 20000,
                "radius_ms": 10000,
                "family": "shot",
                "manual_key": "2PT|Make",
            },
        ],
        "supervised_templates": [
            {
                "timestamp_ms": 5000,
                "radius_ms": 10000,
                "match_key": "Foul",
                "event_type": "foul",
                "player": "10",
                "confidence": 0.55,
            },
            {
                "timestamp_ms": 20000,
                "radius_ms": 10000,
                "match_key": "2PT|Make",
                "event_type": "shot",
                "shot_type": "2pt",
                "shot_result": "make",
                "player": "11",
                "confidence": 0.58,
            },
        ],
        "fp_suppress": {
            "orphan_steal_to": False,
            "require_shot_positive_window": True,
            "drop_unanchored_shot_misses": True,
            "require_steal_to_positive_window": True,
            "cap_shots_to_manual_windows": True,
        },
        "keep_clf": {
            "features": ["conf"],
            "weights": [0.0],
            "bias": 10.0,
            "threshold": 0.01,
        },
    }
    # Unanchored 2PT miss near a foul window — must be dropped.
    events = [_shot("taught-run", 5100, shot_type="2pt", result="miss", conf=0.9)]
    out = apply_event_calibrator(events, model)
    types = [str(e.get("event_type") or "").lower() for e in out]
    assert "foul" in types
    assert any(
        str(e.get("event_type") or "").lower() == "shot"
        and str(e.get("shot_result") or "").lower() == "make"
        for e in out
    )
    # The speculative miss must not survive.
    assert not any(
        str(e.get("event_type") or "").lower() == "shot"
        and str(e.get("shot_result") or "").lower() == "miss"
        for e in out
    )
