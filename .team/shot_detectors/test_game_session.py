"""Synthetic + reference tests for game_session (spec 48b). No video."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_session as gs  # noqa: E402

REF = Path(__file__).resolve().parents[1] / "design48b" / "reference"


def _home_raw(clocks, start_ms=0, step_ms=1000, read2=None):
    """Build home-style raw rows. clocks: list of seconds or None."""
    out = []
    for i, c in enumerate(clocks):
        if c is None:
            read = "x"
        elif abs(c - round(c)) > 1e-6:
            read = f"{int(c)}.{int(round((c - int(c)) * 10)) % 10}"
        else:
            ci = int(round(c))
            read = f"{ci // 60}:{ci % 60:02d}"
        r2 = None
        if read2 is not None and i < len(read2):
            r2 = read2[i]
        elif c == 0:
            r2 = "0.0"
        out.append(
            {
                "t_ms": start_ms + i * step_ms,
                "read": read,
                "clock_s": c,
                "read2": r2,
            }
        )
    return out


def _run_stop_pattern(run_n, stop_n, clock0, step=1.0):
    """run_n run samples then stop_n stop samples, counting down from clock0 during runs."""
    clocks = []
    c = float(clock0)
    for _ in range(run_n):
        clocks.append(c)
        c -= step
    for _ in range(stop_n):
        clocks.append(c)
    return clocks, c


def _period_segment(L=420.0, stops=3, run_len=8, stop_len=5, end_zero=True):
    """One period-like clock: tip countdown with `stops` stoppages, optional held zero."""
    clocks = [L, L]  # paused at L before tip
    c = L
    for s in range(stops):
        seg, c = _run_stop_pattern(run_len, stop_len, c)
        clocks.extend(seg)
    # final run down near zero
    while c > 0:
        clocks.append(c)
        c -= 1.0
    clocks.append(0.0)
    if end_zero:
        clocks.extend([0.0, 0.0, 0.0])
    return clocks


def test_parse_clock_formats():
    assert gs.parse_clock("7:00") == 420.0
    assert gs.parse_clock("0:00") == 0.0
    assert gs.parse_clock("12:59") == 12 * 60 + 59
    assert gs.parse_clock("13:00") is None
    assert gs.parse_clock("1:60") is None
    assert gs.parse_clock("16.8") == 16.8
    assert gs.parse_clock("60.0") is None
    assert gs.parse_clock(None) is None
    assert gs.norm_read("58:8") == "58.8"
    assert gs.norm_read("5:11") == "5:11"


def test_timeout_excursion_bridged():
    # Leave 100 for a timeout timer, return and hold near 100 -> bridged to None.
    clock = [100.0, 100.0, 50.0, 49.0, 48.0, 47.0, 100.0, 100.0, 99.0, 99.0, 98.0]
    cl, bridged = gs.bridge_excursions(clock)
    assert bridged == [2, 3, 4, 5]
    assert cl[2] is None and cl[5] is None
    assert cl[6] == 100.0


def test_one_sample_spike_not_a_reset():
    clock = [100.0, 100.0, 200.0, 100.0, 99.0, 98.0]
    assert 2 not in gs.resets_full(clock)


def test_real_reset_to_L():
    clock = [10.0, 10.0, 420.0, 420.0, 419.0, 418.0]
    assert 2 in gs.resets_full(clock)


def test_halftime_starting_at_L_with_2_misread_stops_after_period_2_not_a_period():
    # Two full periods (>=3 stops each), then a halftime-like segment at L with only 2 stops.
    q1 = _period_segment(L=420.0, stops=3)
    q2 = _period_segment(L=420.0, stops=3)
    # halftime: tip at L, only 2 stoppages, then to zero
    half = [420.0, 420.0]
    c = 420.0
    for _ in range(2):
        seg, c = _run_stop_pattern(6, 5, c)
        half.extend(seg)
    while c > 0:
        half.append(c)
        c -= 1.0
    half.extend([0.0, 0.0, 0.0])
    clocks = q1 + [None] * 3 + q2 + [None] * 3 + half
    raw = _home_raw(clocks)
    # Mark None clocks with unparseable read so session_from_raw keeps them None after norm.
    for r in raw:
        if r["clock_s"] is None:
            r["read"] = "bad"
            r["read2"] = None
    sess = gs.session_from_raw(raw, "home")
    assert sess["L"] == 420.0
    assert len(sess["periods"]) == 2
    reasons = [d["reason"] for d in sess["dropped_segments"]]
    assert "halftime: 1-2 stops after period 2" in reasons


def test_running_clock_q4_one_stop_after_period_3_partial_is_period():
    # Partial board: three periods with >=3 stops, then Q4 with only 1 stop -> period (count==3).
    def partial_period(stops, seconds_start=40, held_zero=True):
        raw = []
        t = 0
        # tip run
        v = seconds_start
        for _ in range(6):
            raw.append({"t_ms": t, "fmt": "mss", "v": v % 60, "fmt2": None, "v2": None})
            t += 1000
            v -= 1
        for s in range(stops):
            for _ in range(5):
                raw.append(
                    {"t_ms": t, "fmt": "mss", "v": v % 60, "fmt2": None, "v2": None}
                )
                t += 1000
            for _ in range(6):
                raw.append(
                    {"t_ms": t, "fmt": "mss", "v": v % 60, "fmt2": None, "v2": None}
                )
                t += 1000
                v -= 1
        # run into tenths zero hold
        raw.append({"t_ms": t, "fmt": "sst", "v": 3, "fmt2": "sst", "v2": 2})
        t += 1000
        raw.append({"t_ms": t, "fmt": "sst", "v": 1, "fmt2": "sst", "v2": 0})
        t += 1000
        if held_zero:
            for _ in range(4):
                raw.append(
                    {"t_ms": t, "fmt": "sst", "v": 0, "fmt2": None, "v2": None}
                )
                t += 1000
        return raw, t

    raw = []
    t0 = 0
    for stops in (3, 3, 3):
        chunk, _ = partial_period(stops)
        for r in chunk:
            r["t_ms"] += t0
        raw.extend(chunk)
        t0 = raw[-1]["t_ms"] + 5000
    # Q4: only 1 stop
    chunk, _ = partial_period(1, held_zero=False)
    for r in chunk:
        r["t_ms"] += t0
    raw.extend(chunk)
    # end without held zero so last segment ends as "end"
    sess = gs.session_from_raw(raw, "away_adrian")
    assert sess["L"] is None
    assert len(sess["periods"]) == 4
    assert sess["periods"][3]["stops"] == 1
    assert sess["periods"][3]["n_in_game"] == 4


def test_pregame_timer_with_one_pause_not_a_period():
    # Continuous run with a single short pause (1 stoppage) -> timer / not a period.
    clocks = []
    c = 500.0
    for _ in range(20):
        clocks.append(c)
        c -= 1.0
    for _ in range(5):
        clocks.append(c)  # stop
    for _ in range(20):
        clocks.append(c)
        c -= 1.0
    clocks.extend([0.0, 0.0, 0.0])
    raw = _home_raw(clocks)
    sess = gs.session_from_raw(raw, "home")
    assert sess["error"] == "no periods" or len(sess["periods"]) == 0
    assert any(d["reason"] == "timer: 0 stops" or d["stops"] <= 2 for d in sess["dropped_segments"]) or sess["error"] == "no periods"


def test_two_games_eight_min_gap_counts_restart():
    q = _period_segment(L=420.0, stops=3)
    # four periods game 1
    clocks = []
    for i in range(4):
        if i:
            clocks.extend([None] * 3)
        clocks.extend(_period_segment(L=420.0, stops=3))
    # 8+ min gap
    gap_samples = 8 * 60 + 5
    clocks.extend([None] * gap_samples)
    # four periods game 2
    for i in range(4):
        if i:
            clocks.extend([None] * 3)
        clocks.extend(_period_segment(L=420.0, stops=3))
    raw = _home_raw(clocks)
    for r in raw:
        if r["clock_s"] is None:
            r["read"] = "bad"
            r["read2"] = None
    sess = gs.session_from_raw(raw, "home")
    assert len(sess["periods"]) == 8
    assert [p["n_in_game"] for p in sess["periods"]] == [1, 2, 3, 4, 1, 2, 3, 4]


def test_zero_hold_with_two_stray_reads():
    is_zero = [False, True, True, False, False, True, True, True, False]
    # two consecutive strays inside the hold are allowed; hold still counts
    ends = gs.zero_ends(is_zero, list(range(len(is_zero))))
    assert ends == [(1, 7)]


def test_ft_window_after_held_zero():
    clocks = _period_segment(L=420.0, stops=3, end_zero=True)
    # extend zero hold past buzzer pad
    clocks.extend([0.0] * 10)
    raw = _home_raw(clocks)
    # Need enough periods? One period with >=3 stops is enough for L and one period.
    # Add two more so classification is solid.
    more = _period_segment(L=420.0, stops=3) + [None] * 3 + _period_segment(L=420.0, stops=3)
    # Actually one period with >=3 stops is enough: L from conf_starts, is_period True.
    sess = gs.session_from_raw(raw, "home")
    assert sess["periods"]
    assert sess["ft_windows"]
    ft = sess["ft_windows"][0]
    assert ft["end_ms"] > ft["start_ms"]
    # FT window is exclusive at start for in_session
    assert gs.in_session(ft["start_ms"], sess, is_ft=True) is False or gs.in_session(
        ft["start_ms"], sess, is_ft=False
    )
    mid = (ft["start_ms"] + ft["end_ms"]) // 2
    if mid > ft["start_ms"]:
        assert gs.in_session(mid, sess, is_ft=True) is True


def test_no_periods_error():
    clocks = list(range(100, 0, -1)) + [0.0, 0.0, 0.0]  # 0 stops if never stop/run pattern
    # All steadily running -> states are run; 0 stoppages -> timer drop -> no periods
    raw = _home_raw([float(c) for c in clocks])
    sess = gs.session_from_raw(raw, "home")
    assert sess["error"] == "no periods"
    assert sess["periods"] == []


def test_partial_board_sst_mss_states():
    raw = [
        {"t_ms": 0, "fmt": "mss", "v": 10, "fmt2": None, "v2": None},
        {"t_ms": 1000, "fmt": "mss", "v": 9, "fmt2": None, "v2": None},  # run
        {"t_ms": 2000, "fmt": "mss", "v": 9, "fmt2": None, "v2": None},  # stop
        {"t_ms": 3000, "fmt": "sst", "v": 5, "fmt2": "sst", "v2": 4},  # run
        {"t_ms": 4000, "fmt": "sst", "v": 5, "fmt2": "sst", "v2": 5},  # stop (same v as prev sst)
    ]
    # Fix index 4: stop if a is sst and a.v == b.v
    raw[4] = {"t_ms": 4000, "fmt": "sst", "v": 5, "fmt2": "sst", "v2": 5}
    # For stop on sst: need previous also sst with same v, and v2 == v
    raw[3] = {"t_ms": 3000, "fmt": "sst", "v": 5, "fmt2": "sst", "v2": 4}
    st = gs.states_partial(raw)
    assert st[1] == "run"
    assert st[2] == "stop"
    assert st[3] == "run"
    assert st[4] == "stop"
    assert 1 in gs.resets_partial(
        [
            {"fmt": "sst"},
            {"fmt": "mss"},
            {"fmt": "mss"},
            {"fmt": "mss"},
        ]
    )


def test_module_source_has_no_score_reader():
    src = Path(gs.__file__).read_text(encoding="utf-8")
    for name in ("_score_value", "_read_score", "_score_text"):
        assert name not in src
    assert "scoreboard_clock" not in src


def _assert_ref_equal(film_key: str, raw_name: str, board: str):
    raw = json.loads((REF / raw_name).read_text(encoding="utf-8"))
    ref = json.loads((REF / f"session_v3_{film_key}.json").read_text(encoding="utf-8"))
    out = gs.session_from_raw(raw, board)
    for k in ref:
        assert out[k] == ref[k], f"{film_key} key {k}: {out[k]!r} != {ref[k]!r}"


def test_reference_notus():
    _assert_ref_equal("notus", "home_raw48_notus.json", "home")


def test_reference_gv():
    _assert_ref_equal("gv", "home_raw48_gv.json", "home")


def test_reference_idaho():
    _assert_ref_equal("idaho", "home_raw48_idaho.json", "home")


def test_reference_adrian():
    _assert_ref_equal("adrian", "adrian_raw48.json", "away_adrian")
