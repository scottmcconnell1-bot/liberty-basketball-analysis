"""Tests for scripts/team_score.py (the team loop make/miss score)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import team_score  # noqa: E402


def test_notus_score_matches_saved_v6_rule():
    score = team_score.score_tracks(team_score.NOTUS_TRACKS)

    assert score["right"] == 24
    assert score["total"] == 31
    assert score["makes_missed"] == 7
    assert score["misses_called_makes"] == 0


def test_goal_is_not_reached_on_saved_tracks():
    if team_score.adrian_tracks_path() is None:
        pytest.skip("Adrian v6 tracks are not present on this machine")

    result = team_score.build_score()

    assert result["notus"] == {
        "right": 24,
        "total": 31,
        "makes_missed": 7,
        "misses_called_makes": 0,
    }
    assert result["goal_reached"] is False
