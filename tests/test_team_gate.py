"""Tests for scripts/team_gate.py (the free team gate)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import team_gate  # noqa: E402


def test_changed_file_outside_plan_fails():
    failures = team_gate.check_files(
        ["scripts/allowed.py", "scripts/not_allowed.py"],
        ["scripts/allowed.py"],
    )

    assert any("scripts/not_allowed.py" in failure for failure in failures)


def test_team_files_and_log_are_allowed():
    failures = team_gate.check_files(
        [
            ".team/baseline_score.json",
            "docs/agent_handoffs/TEAM_LOG.md",
            "NEXT_TASK.md",
        ],
        [],
    )

    assert failures == []


def test_protected_file_fails():
    failures = team_gate.check_protected(["ai_bridge.py", "ai_analyzer.py"])

    assert any("ai_analyzer.py" in failure for failure in failures)


def test_already_changed_file_unchanged_passes():
    failures = team_gate.check_files(
        ["scratch.txt"],
        [],
        round_start={"scratch.txt": "aaa"},
        current_hashes={"scratch.txt": "aaa"},
    )

    assert failures == []


def test_already_changed_file_with_new_content_fails():
    failures = team_gate.check_files(
        ["scratch.txt"],
        [],
        round_start={"scratch.txt": "aaa"},
        current_hashes={"scratch.txt": "bbb"},
    )

    assert any("scratch.txt" in failure for failure in failures)


def test_new_file_since_round_start_fails():
    failures = team_gate.check_files(
        ["new.py"],
        [],
        round_start={},
        current_hashes={"new.py": "aaa"},
    )

    assert any("new.py" in failure for failure in failures)


def test_protected_unchanged_since_round_start_passes():
    failures = team_gate.check_protected(
        ["ai_analyzer.py"],
        round_start={"ai_analyzer.py": "aaa"},
        current_hashes={"ai_analyzer.py": "aaa"},
    )

    assert failures == []


def test_protected_hash_change_fails():
    failures = team_gate.check_protected(
        ["ai_analyzer.py"],
        round_start={"ai_analyzer.py": "aaa"},
        current_hashes={"ai_analyzer.py": "bbb"},
    )

    assert any("ai_analyzer.py" in failure for failure in failures)


def test_protected_changed_vs_head_not_at_round_start_fails():
    failures = team_gate.check_protected(
        ["ai_analyzer.py"],
        round_start={},
        current_hashes={"ai_analyzer.py": "aaa"},
    )

    assert any("ai_analyzer.py" in failure for failure in failures)


def test_removed_ai_bridge_line_fails():
    diff = (
        "--- a/ai_bridge.py\n"
        "+++ b/ai_bridge.py\n"
        "@@ -1 +1 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )

    assert team_gate.check_ai_bridge_diff(diff)


def test_pure_addition_to_ai_bridge_passes():
    diff = (
        "--- a/ai_bridge.py\n"
        "+++ b/ai_bridge.py\n"
        "@@ -1,0 +2 @@\n"
        "+y = 2\n"
    )

    assert team_gate.check_ai_bridge_diff(diff) == []


def test_applied_to_core_true_fails():
    diff = (
        "--- a/scripts/example.py\n"
        "+++ b/scripts/example.py\n"
        "@@ -1,0 +2 @@\n"
        "+applied_to_core = True\n"
    )

    assert team_gate.check_applied_to_core(diff)


def test_applied_to_core_false_passes():
    diff = (
        "--- a/scripts/example.py\n"
        "+++ b/scripts/example.py\n"
        "@@ -1,0 +2 @@\n"
        "+applied_to_core = False\n"
    )

    assert team_gate.check_applied_to_core(diff) == []


def test_score_drop_fails():
    baseline = {
        "notus": {"right": 24},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {
        "notus": {"right": 23},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }

    assert team_gate.check_scores(current, baseline)


def test_equal_score_passes():
    baseline = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }

    assert team_gate.check_scores(current, baseline) == []


def test_misses_called_makes_fails():
    baseline = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 1},
    }

    assert team_gate.check_scores(current, baseline)


def test_missing_film_fails():
    baseline = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {"adrian": {"right": 99, "misses_called_makes": 0}}

    assert any("notus" in failure for failure in team_gate.check_scores(current, baseline))


def test_missing_right_fails():
    baseline = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {
        "notus": {"misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }

    assert any(
        "notus.right" in failure
        for failure in team_gate.check_scores(current, baseline)
    )


def test_missing_misses_called_makes_fails():
    baseline = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {
        "notus": {"right": 24},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }

    assert any(
        "notus.misses_called_makes" in failure
        for failure in team_gate.check_scores(current, baseline)
    )


def test_notus_misses_called_makes_higher_fails():
    baseline = {
        "notus": {"right": 24, "misses_called_makes": 0},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }
    current = {
        "notus": {"right": 24, "misses_called_makes": 1},
        "adrian": {"right": 99, "misses_called_makes": 0},
    }

    assert team_gate.check_scores(current, baseline)


def test_parse_plan_files():
    plan = (
        "# Task\n\n"
        "## Files\n"
        "- `team_loop.ps1` (edit)\n"
        "- `scripts/team_gate.py` (new)\n"
        "\n"
        "## Other\n"
        "- `not_this.py`\n"
    )

    assert team_gate.parse_plan_files(plan) == [
        "team_loop.ps1",
        "scripts/team_gate.py",
    ]


def test_parse_status_lines_handles_rename():
    status = " M ai_bridge.py\n?? scripts/new.py\nR  old.py -> new.py\n"

    assert team_gate.parse_status_lines(status) == [
        "ai_bridge.py",
        "scripts/new.py",
        "new.py",
    ]
