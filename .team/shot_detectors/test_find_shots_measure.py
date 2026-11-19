"""Pure-function tests for find_shots_measure (no video, no DB, no core imports)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import find_shots_measure as fsm  # noqa: E402


def test_exact_match():
    r = fsm.match_shots([1000], [1000], 8000)
    assert r["matches"] == [(1000, 1000, 0)]
    assert r["unmatched_tags"] == []
    assert r["unmatched_finder"] == []


def test_inside_window():
    r = fsm.match_shots([1000], [5000], 8000)
    assert r["matches"] == [(1000, 5000, 4000)]
    assert r["unmatched_tags"] == []
    assert r["unmatched_finder"] == []


def test_outside_window():
    r = fsm.match_shots([1000], [10000], 8000)
    assert r["matches"] == []
    assert r["unmatched_tags"] == [1000]
    assert r["unmatched_finder"] == [10000]


def test_two_finder_near_one_tag_closer_wins():
    r = fsm.match_shots([5000], [4000, 5500], 8000)
    assert r["matches"] == [(5000, 5500, 500)]
    assert r["unmatched_finder"] == [4000]


def test_one_finder_near_two_tags_closer_tag_wins():
    r = fsm.match_shots([4000, 5500], [5000], 8000)
    assert r["matches"] == [(5500, 5000, -500)]
    assert r["unmatched_tags"] == [4000]


def test_empty_lists():
    r = fsm.match_shots([], [], 8000)
    assert r["matches"] == []
    assert r["unmatched_tags"] == []
    assert r["unmatched_finder"] == []
    r2 = fsm.match_shots([1000], [], 8000)
    assert r2["matches"] == [] and r2["unmatched_tags"] == [1000]
    r3 = fsm.match_shots([], [1000], 8000)
    assert r3["matches"] == [] and r3["unmatched_finder"] == [1000]


def test_span_bounds_and_filter():
    assert fsm.span_bounds([], 8000) is None
    assert fsm.span_bounds([1000, 5000], 8000) == (-7000, 13000)
    rows = [{"t": 0}, {"t": 1000}, {"t": 5000}, {"t": 20000}]
    kept = fsm.filter_by_span(rows, 1000, 5000, time_key="t")
    assert [r["t"] for r in kept] == [1000, 5000]


def test_summarize_maths():
    matches = [(0, 500, 500), (1000, 1000, 0), (2000, 4500, 2500)]
    s = fsm.summarize(matches, n_tagged=5, n_extra=2)
    assert s["tagged"] == 5
    assert s["found"] == 3
    assert s["extra"] == 2
    assert s["recall"] == 3 / 5
    assert s["precision"] == 3 / 5
    assert s["median_abs_delta_ms"] == 500
    assert s["max_abs_delta_ms"] == 2500
    assert s["n_abs_delta_le_1000"] == 2
    assert s["n_abs_delta_le_3000"] == 3

    empty = fsm.summarize([], n_tagged=0, n_extra=0)
    assert empty["recall"] is None and empty["precision"] is None
    assert empty["median_abs_delta_ms"] is None
    assert empty["max_abs_delta_ms"] is None
