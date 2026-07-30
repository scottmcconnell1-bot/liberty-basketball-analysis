"""Lightweight tests for full-film panel targets + config keys."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from score_full_film_panel import (  # noqa: E402
    DEFAULT_TARGETS,
    PANEL_GAMES,
    evaluate_gates,
    load_targets,
)


def test_default_targets_match_scott_criteria():
    assert DEFAULT_TARGETS["final_score_exact"] == 1.0
    assert DEFAULT_TARGETS["player_points_exact"] == 1.0
    assert DEFAULT_TARGETS["event_precision_min"] == 0.90
    assert DEFAULT_TARGETS["event_recall_min"] == 0.90


def test_targets_file_parses_and_has_required_keys(tmp_path: Path):
    path = tmp_path / "full_film_panel_targets.json"
    path.write_text(
        json.dumps(
            {
                "final_score_exact": 1.0,
                "player_points_exact": 1.0,
                "event_precision_min": 0.90,
                "event_recall_min": 0.90,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_targets(path)
    for key in DEFAULT_TARGETS:
        assert key in loaded
        assert loaded[key] == DEFAULT_TARGETS[key]


def test_panel_games_have_required_keys():
    assert len(PANEL_GAMES) == 6
    names = {g["name"] for g in PANEL_GAMES}
    assert names == {"Idaho City", "Harper", "Burns", "Nyssa", "Melba", "Camas"}
    for g in PANEL_GAMES:
        assert g["film_id"]
        assert g["analysis_key"]
        assert "film_id" in g and "analysis_key" in g and "name" in g


def test_evaluate_gates_with_mock_compare_results():
    targets = dict(DEFAULT_TARGETS)
    # Mock six games that would PASS event P/R but fail exact score gates
    games = [
        {
            "name": f"G{i}",
            "precision": 0.91,
            "recall": 0.92,
            "final_score_exact": False,
            "player_points_exact": False,
        }
        for i in range(6)
    ]
    ev = evaluate_gates(games, targets)
    assert ev["gates"]["event_precision_min"]["pass"] is True
    assert ev["gates"]["event_recall_min"]["pass"] is True
    assert ev["gates"]["final_score_exact"]["pass"] is False
    assert ev["gates"]["player_points_exact"]["pass"] is False
    assert ev["overall_pass"] is False

    perfect = [
        {
            "name": f"G{i}",
            "precision": 0.95,
            "recall": 0.95,
            "final_score_exact": True,
            "player_points_exact": True,
        }
        for i in range(6)
    ]
    ev2 = evaluate_gates(perfect, targets)
    assert ev2["overall_pass"] is True
