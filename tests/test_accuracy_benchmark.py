"""Accuracy benchmark: the event generator must not score worse than the committed baseline.

Scores frozen real detections against the coach's tags (scripts/accuracy_benchmark.py,
benchmarks/accuracy/). A drop below benchmarks/accuracy/baseline.json fails the suite;
raise the baseline in the PR that improves accuracy (--update-baseline).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import accuracy_benchmark as bench  # noqa: E402

FIXTURES = bench.fixtures()


@pytest.mark.skipif(not FIXTURES, reason="no accuracy fixtures committed")
@pytest.mark.parametrize("fixture", FIXTURES, ids=[f.name for f in FIXTURES])
def test_event_accuracy_does_not_regress(fixture):
    baseline = json.loads(bench.BASELINE_PATH.read_text(encoding="utf-8"))
    result = bench.score_fixture(fixture)
    assert result["truth_events"] > 0 and result["detections"] > 0
    assert bench.regressions(result, baseline) == []


SHOTS = {"tags": 10, "right": 6, "makes_missed": 3, "misses_called_makes": 1}


def test_regression_check_flags_a_drop():
    baseline = {"clip": {"precision_exact": 0.10, "recall_exact": 0.50, "f1_exact": 0.17,
                         "shots": SHOTS}}
    same = {"fixture": "clip", "precision_exact": 0.10, "recall_exact": 0.50,
            "f1_exact": 0.17, "shots": dict(SHOTS)}
    worse = dict(same, recall_exact=0.40)
    assert bench.regressions(same, baseline) == []
    assert bench.regressions(worse, baseline) == ["clip: recall_exact 0.4000 < baseline 0.5000"]
    assert bench.regressions(dict(same, fixture="new"), baseline)  # unknown fixture needs a baseline


def test_a_fixture_without_a_shot_floor_is_not_quietly_ungated():
    """Precision and recall can hold steady while makes go missing. The shot floor is
    the part that notices, so a baseline that lacks one is treated as incomplete."""
    baseline = {"clip": {"precision_exact": 0.10, "recall_exact": 0.50, "f1_exact": 0.17}}
    result = {"fixture": "clip", "precision_exact": 0.10, "recall_exact": 0.50,
              "f1_exact": 0.17, "shots": dict(SHOTS)}
    problems = bench.regressions(result, baseline)
    assert problems and "no shot-tag floor" in problems[0]


def test_losing_a_made_basket_fails_even_when_precision_holds():
    baseline = {"clip": {"precision_exact": 0.10, "recall_exact": 0.50, "f1_exact": 0.17,
                         "shots": SHOTS}}
    lost_a_make = {"fixture": "clip", "precision_exact": 0.10, "recall_exact": 0.50,
                   "f1_exact": 0.17,
                   "shots": {"tags": 10, "right": 5, "makes_missed": 4,
                             "misses_called_makes": 1}}
    assert bench.regressions(lost_a_make, baseline)


def test_a_fixture_waiting_on_detections_is_listed_not_hidden():
    """benchmarks/accuracy/adrian_q1/ has tags and no detections; it must be visible."""
    waiting = [p.name for p in bench.waiting_on_detections()]
    scored = [p.name for p in bench.fixtures()]
    assert not set(waiting) & set(scored)
    for name in waiting:
        assert (bench.BENCH_DIR / name / "README.md").is_file(), \
            f"{name} waits on detections but does not say how to build them"


def test_truth_files_carry_no_player_names():
    for fixture in FIXTURES:
        rows = json.loads((fixture / "truth.json").read_text(encoding="utf-8"))["rows"]
        assert all(set(r) <= {"quarter", "start", "category", "eventtype", "result", "side"} for r in rows)


def test_ai_rows_use_typed_shots_and_both_rebound_kinds():
    events = [
        {"id": 1, "event_type": "shot", "shot_result": "miss", "timestamp_ms": 1000},
        {"id": 2, "event_type": "missed_free_throw", "shot_result": "miss", "timestamp_ms": 1000},
        {"id": 3, "event_type": "shot", "shot_result": "make", "timestamp_ms": 5000},
        {"id": 4, "event_type": "made_three", "shot_result": "make", "timestamp_ms": 5000},
        {"id": 5, "event_type": "rebound_offensive", "timestamp_ms": 6000},
        {"id": 6, "event_type": "rebound_defensive", "timestamp_ms": 7000},
        {"id": 7, "event_type": "possession_change", "timestamp_ms": 8000},
    ]
    rows = bench.ai_stat_rows(events)
    assert [(r["eventtype"], r["result"]) for r in rows] == [
        ("FT", "Miss"), ("3PT", "Make"), ("OffRebound", "NA"), ("DefRebound", "NA")]


def test_ai_rows_fall_back_to_generic_shots_without_typed_rows():
    events = [{"id": 1, "event_type": "shot", "shot_result": "make", "timestamp_ms": 1000,
               "details_json": '{"shot_type": "3pt"}'}]
    assert [(r["eventtype"], r["result"]) for r in bench.ai_stat_rows(events)] == [("3PT", "Make")]
