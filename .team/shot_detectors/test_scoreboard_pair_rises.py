"""Tests for Stage C scoreboard pairing (spec .team/specs/20_c_job_spec.md v2)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoreboard_pair_rises as sp  # noqa: E402


def samples(guest_values, home=0, start=0):
    return [{"timestamp_ms": start + i * 1000, "guest": v, "mustangs": home} for i, v in enumerate(guest_values)]


def test_rise_needs_three_samples_and_takes_first_time():
    r = sp.find_rises(samples([0, 0, 2, 2, 2, 2]))
    assert r["rises"] == [{"team": "Liberty", "t": 2000, "from": 0, "to": 2, "points": 2}]


def test_blip_shorter_than_three_is_ignored():
    r = sp.find_rises(samples([0, 0, 8, 8, 0, 0, 0]))
    assert r["rises"] == [] and r["drops"] == []


def test_unreadable_samples_are_skipped():
    r = sp.find_rises(samples([0, None, 3, None, 3, 3]))
    assert [x["points"] for x in r["rises"]] == [3]


def test_window_is_after_the_shot_only():
    assert sp.in_window(10_000, 10_000)
    assert sp.in_window(10_000, 35_000)
    assert not sp.in_window(10_000, 35_001)
    assert not sp.in_window(10_000, 9_999)


def rise(t, points=2, team="Liberty"):
    return {"team": team, "t": t, "from": 0, "to": points, "points": points}


def shot(t, team="Liberty"):
    return {"t": t, "team": team}


def test_one_rise_one_shot_is_clean():
    p = sp.pair([rise(5_000)], [shot(0)], use_team=False)
    assert p["per_shot"][0]["status"] == "CLEAN"


def test_rise_with_two_shots_is_ambiguous_for_both():
    p = sp.pair([rise(20_000)], [shot(0), shot(10_000)], use_team=False)
    assert p["per_shot"][0]["status"] == "AMBIGUOUS"
    assert p["per_shot"][10_000]["status"] == "AMBIGUOUS"
    assert len(p["rises_with_many_shots"]) == 1


def test_and_one_free_throw_makes_the_shot_ambiguous():
    p = sp.pair([rise(5_000), rise(15_000, points=1)], [shot(0)], use_team=False)
    assert p["per_shot"][0]["status"] == "AMBIGUOUS"


def test_one_point_rise_is_never_clean_make():
    p = sp.pair([rise(5_000, points=1)], [shot(0)], use_team=False)
    assert p["per_shot"][0]["status"] == "CLEAN_FT"


def test_team_filter_drops_other_team_rise():
    p = sp.pair([rise(5_000, team="Adrian")], [shot(0, team="Liberty")], use_team=True)
    assert p["per_shot"][0]["status"] == "NO RISE"
    assert len(p["rises_with_no_shot"]) == 1


def test_tally_flags_false_make_and_recovery():
    shots = [dict(shot(0), gt_make=False, new_pred=False), dict(shot(100_000), gt_make=True, new_pred=False)]
    p = sp.pair([rise(5_000), rise(105_000)], shots, use_team=False)
    t = sp.tally(p, shots)
    assert t["false_makes"] == [0]
    assert t["recovered"] == [100_000]


def test_reading_check_stops_on_wrong_count():
    with pytest.raises(SystemExit):
        sp.check_reading({"rises": [rise(1)], "drops": [], "final": {"Liberty": 2, "Adrian": 0}})
