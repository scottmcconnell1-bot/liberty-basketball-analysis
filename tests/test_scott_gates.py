"""The gate checker: does it catch the changes that are supposed to stop and ask?

Each test here is one of the rules the handoff notes already state in prose. If a
rule is removed from scripts/check_scott_gates.py, one of these fails and says which
promise was dropped.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "check_scott_gates", ROOT / "scripts" / "check_scott_gates.py")
gates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gates)


def run(changed=(), added=(), removed=(), diff="", body="", branch="main",
        diff_file="settings_store.py"):
    """Review one change. ``diff`` is wrapped in a unified-diff header for ``diff_file``.

    The header matters: the checker only reads changed lines from code files, so a
    bare hunk with no ``+++`` line is attributed to nothing and scanned for nothing.
    """
    text = f"diff --git a/{diff_file} b/{diff_file}\n--- a/{diff_file}\n+++ b/{diff_file}\n@@\n{diff}" if diff else ""
    return gates.review(list(changed), list(added), list(removed), text, body, branch)


def rules(findings):
    return sorted(f.rule for f in findings)


def blocking(findings):
    return [f for f in findings if f.blocking]


# --- gated paths -----------------------------------------------------------------

def test_a_schema_change_is_stopped():
    found = run(changed=["schema.sql"])
    assert "gated-path" in rules(found) and blocking(found)


def test_a_model_weights_change_is_stopped():
    assert blocking(run(changed=["models/ball_detector.pt"]))


def test_naming_the_gate_in_the_body_lets_it_through():
    body = "Scott approved: schema.sql — adds the possession index, he said yes 2026-10-11"
    assert not blocking(run(changed=["schema.sql"], body=body))


def test_approving_one_gate_does_not_clear_a_different_one():
    body = "Scott approved: schema.sql — he said yes"
    found = blocking(run(changed=["schema.sql", "models/ball_detector.pt"], body=body))
    assert len(found) == 1 and "models/" in found[0].token


def test_a_workflow_change_is_reported_but_not_refused():
    found = run(changed=[".github/workflows/tests.yml"])
    assert found and not blocking(found)


def test_an_ordinary_change_crosses_nothing():
    assert run(changed=["templates/index.html", "docs/README.md"]) == []


# --- settings that are Scott's call ----------------------------------------------

def test_changing_ball_confidence_is_stopped():
    diff = '-    "ball_confidence": 0.25,\n+    "ball_confidence": 0.15,\n'
    found = run(changed=["settings_store.py"], diff=diff)
    assert any(f.token == "ball_confidence" for f in blocking(found))


def test_touching_the_170_pixel_live_gate_is_stopped():
    """The one Scott refused to drop."""
    diff = '-    "live_shot_min_ball_rise": 170.0,\n+    "live_shot_min_ball_rise": 120.0,\n'
    found = blocking(run(changed=["event_generator.py"], diff=diff, body="right=90 "
                                 "makes_missed=15 misses_called_makes=6"))
    assert any(f.token == "live_shot_min_ball_rise" for f in found)


def test_touching_auto_accept_is_stopped():
    diff = '-    "auto_accept_event_confidence": 0.0,\n+    "auto_accept_event_confidence": 0.85,\n'
    found = blocking(run(changed=["settings_store.py"], diff=diff))
    assert any(f.token == "auto_accept_event_confidence" for f in found)


def test_a_flag_going_false_to_true_is_stopped():
    diff = '-    "emit_fouls": False,\n+    "emit_fouls": True,\n'
    found = blocking(run(changed=["event_generator.py"], diff=diff,
                         body="right=86 makes_missed=19 misses_called_makes=6"))
    assert "flag-flip" in rules(found)


def test_a_plan_document_that_explains_a_gated_setting_is_not_a_change_to_it():
    """The first run of this checker blocked a docs-only branch four times over.

    docs/agent_handoffs/plans/ exists to explain what live_shot_min_ball_rise and
    ball_confidence do. If describing a gate trips the gate, the check gets ignored.
    """
    diff = ("-the 170-pixel rise is one gate\n"
            '+the rise is two gates: shot_min_ball_rise 80 and live_shot_min_ball_rise 170,\n'
            "+and ball_confidence is not to be touched. emit_fouls stays False.\n")
    found = run(changed=["docs/agent_handoffs/plans/00_INDEX.md"], diff=diff,
                diff_file="docs/agent_handoffs/plans/00_INDEX.md")
    assert found == []


def test_the_checker_does_not_block_changes_to_its_own_rule_table():
    """It did, on its first real run: GATED_SETTINGS names all seven settings.

    A check that refuses every edit to itself gets deleted, not obeyed.
    """
    diff = ('+    ("ball_confidence", "the ball detector\'s confidence floor"),\n'
            '+    ("live_shot_min_ball_rise", "the live field-goal gate"),\n')
    found = run(changed=["scripts/check_scott_gates.py"], diff=diff,
                diff_file="scripts/check_scott_gates.py")
    assert [f for f in found if f.rule == "gated-setting"] == []


def test_a_test_file_naming_a_setting_is_not_a_change_to_it():
    diff = '+    diff = \'-    "ball_confidence": 0.25,\\n+    "ball_confidence": 0.15,\\n\'\n'
    found = run(changed=["tests/test_scott_gates.py"], diff=diff,
                diff_file="tests/test_scott_gates.py")
    assert [f for f in found if f.rule == "gated-setting"] == []


def test_a_real_code_change_to_the_same_setting_is_still_caught():
    diff = '-    "live_shot_min_ball_rise": 170.0,\n+    "live_shot_min_ball_rise": 90.0,\n'
    found = blocking(run(changed=["event_generator.py"], diff=diff,
                         diff_file="event_generator.py",
                         body="right=86 makes_missed=19 misses_called_makes=6"))
    assert any(f.token == "live_shot_min_ball_rise" for f in found)


def test_a_flag_going_true_to_false_is_not_a_flag_flip():
    """Turning something off is not the gate; turning it on is."""
    diff = '-    "emit_blocks": True,\n+    "emit_blocks": False,\n'
    found = run(changed=["event_generator.py"], diff=diff,
                body="right=85 makes_missed=20 misses_called_makes=6")
    assert "flag-flip" not in rules(found)


# --- files that must never land ---------------------------------------------------

def test_the_database_cannot_be_committed():
    assert blocking(run(changed=["film_analysis.db"], added=["film_analysis.db"]))


def test_a_credential_file_cannot_be_committed():
    for path in (".env",
                 "scottmcconnell1-bot-liberty-basketball-analysis-abc123.txt"):
        found = blocking(run(changed=[path], added=[path]))
        assert found, path
        assert "never-commit" in rules(found)


def test_the_answer_key_cannot_be_committed():
    """data/film_tags/ holds the tags and the roster. It stays out of git."""
    path = "data/film_tags/jrhigh_adrian.json"
    assert blocking(run(changed=[path], added=[path]))


def test_game_film_cannot_be_committed():
    path = "uploads/nfhs_gam0a66d85e12.mp4"
    assert blocking(run(changed=[path], added=[path]))


def test_a_gitkeep_in_the_tag_folder_is_fine():
    assert run(changed=["data/film_tags/.gitkeep"], added=["data/film_tags/.gitkeep"]) == []


# --- deleting data ---------------------------------------------------------------

def test_deleting_a_review_export_is_stopped():
    found = blocking(run(changed=["tag-exports/adrian_q1_ai_shot_review.csv"],
                         removed=["tag-exports/adrian_q1_ai_shot_review.csv"]))
    assert "deleted-data" in rules(found)


def test_deleting_a_benchmark_fixture_is_stopped():
    assert blocking(run(changed=["benchmarks/accuracy/wilder_q1/truth.json"],
                        removed=["benchmarks/accuracy/wilder_q1/truth.json"]))


# --- a change to how shots are read has to carry a score -------------------------

def test_touching_the_detector_without_a_score_is_stopped():
    found = blocking(run(changed=["net_detector.py"]))
    assert "no-score" in rules(found)


def test_a_pasted_score_line_satisfies_it():
    body = ("Ran scripts/shot_tag_score.py on run 12:\n"
            "right=87 makes_missed=18 misses_called_makes=6 of 111 tags")
    assert "no-score" not in rules(run(changed=["net_detector.py"], body=body))


def test_a_claim_with_no_numbers_does_not_satisfy_it():
    body = "Implemented the 0.45 rim-width rule. It works and beats the 85."
    assert "no-score" in rules(blocking(run(changed=["ai_bridge.py"], body=body)))


def test_a_docs_only_change_needs_no_score():
    assert run(changed=["docs/agent_handoffs/plans/00_INDEX.md"]) == []


# --- the Hermes boundary ---------------------------------------------------------

def test_a_hermes_branch_may_edit_ai_bridge():
    body = "right=85 makes_missed=20 misses_called_makes=6"
    found = run(changed=["ai_bridge.py"], body=body, branch="Scott_Hermes")
    assert "hermes-boundary" not in rules(found)


def test_a_hermes_branch_may_not_edit_the_core_pipeline():
    body = "right=85 makes_missed=20 misses_called_makes=6"
    found = blocking(run(changed=["ai_bridge.py", "event_generator.py"],
                         body=body, branch="Scott_Hermes"))
    assert "hermes-boundary" in rules(found)


def test_the_boundary_only_applies_to_hermes_branches():
    body = "right=85 makes_missed=20 misses_called_makes=6"
    found = run(changed=["event_generator.py"], body=body, branch="cursor/count-roadmap")
    assert "hermes-boundary" not in rules(found)


# --- the approval line -----------------------------------------------------------

def test_approvals_are_read_case_insensitively_and_one_per_line():
    body = "scott approved: schema.sql — yes\nScott Approved: models/ — new weights\n"
    assert len(gates.approvals(body)) == 2


def test_an_empty_body_grants_nothing():
    assert gates.approvals("") == []
