"""GPU-free unit tests for spec 52 deliverables (R1, R6, R7, R8) + 52a/52b/52c/52d."""
import inspect
import json
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shot_detectors"))

import ensemble_predict as ep  # noqa: E402
import extract_clips as ec  # noqa: E402
import gate52 as g52  # noqa: E402
import game_session as gs  # noqa: E402
import train_clip as tc  # noqa: E402


# --- R1: tagmatch / tags unmatched -> -1 ------------------------------------

def test_labels_tagmatch_unmatched_near_and_far_are_minus1():
    tags = [
        {"t": 10_000, "result": "make"},
        {"t": 30_000, "result": "miss"},
    ]
    moments = [
        {"t_ms": 10_000},   # match make
        {"t_ms": 10_500},   # near-tag duplicate unmatched
        {"t_ms": 50_000},   # far-from-tag unmatched
        {"t_ms": 30_200},   # match miss
    ]
    # Force match_shot_indices: pair nearest within window one-to-one
    fake_fsm = mock.MagicMock()
    fake_fsm.load_shot_tags.return_value = tags
    fake_fsm.match_shot_indices.return_value = {
        "matches": [(0, 0, 0), (1, 3, 200)],
        "unmatched_tags": [],
        "unmatched_finder": [1, 2],
    }
    with mock.patch.dict(sys.modules, {"find_shots_measure": fake_fsm}):
        # re-import path uses local import inside function — patch the name it binds
        with mock.patch("find_shots_measure.load_shot_tags", fake_fsm.load_shot_tags), \
             mock.patch("find_shots_measure.match_shot_indices", fake_fsm.match_shot_indices):
            out = ec.labels_tagmatch("dummy.json", moments, window_ms=4000)
    assert out[0] == 2
    assert out[3] == 1
    assert out[1] == -1  # near duplicate
    assert out[2] == -1  # far unknown
    assert 0 not in out


def test_labels_tags_unmatched_is_minus1():
    rows = {
        "rows": [
            {"moment_t_ms": 1000, "matched_tag_t_ms": 1000},
            {"moment_t_ms": 2000, "matched_tag_t_ms": None},
            {"moment_t_ms": 3000, "excluded_reason": "x"},
        ]
    }
    tags = [{"t": 1000, "result": "Miss"}, {"t": 5000, "result": "Make"}]
    moments = [{"t_ms": 1000}, {"t_ms": 2000}, {"t_ms": 3000}, {"t_ms": 9999}]
    fake_fsm = mock.MagicMock()
    fake_fsm.load_shot_tags.return_value = tags
    with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(rows))):
        with mock.patch.dict(sys.modules, {"find_shots_measure": fake_fsm}):
            with mock.patch("find_shots_measure.load_shot_tags", fake_fsm.load_shot_tags):
                out = ec.labels_tags("rows.json", "tags.json", moments)
    assert out[0] == 1
    assert out[1] == -1  # unmatched
    assert out[2] == -1  # excluded
    assert out[3] == -1  # no row
    assert 0 not in out


# --- R7: postproc52 schema ---------------------------------------------------

REQUIRED_POSTPROC52 = {
    "shot_thr": 0.5,
    "dedup_ms": 800,
    "session_filter": False,
    "review": {
        "flag_below_thr_candidates_with_shot_prob_at_least": 0.2,
        "flag_auto_shots_with_shot_prob_below": 0.65,
        "flag_auto_shots_with_abs_pmake_minus_half_below": 0.3,
        "flag_seed_disagreement": True,
    },
}


def test_postproc52_schema_exact():
    cfg = json.load(open(HERE / "postproc52.json"))
    assert cfg["shot_thr"] == REQUIRED_POSTPROC52["shot_thr"]
    assert cfg["dedup_ms"] == REQUIRED_POSTPROC52["dedup_ms"]
    assert cfg["session_filter"] == REQUIRED_POSTPROC52["session_filter"]
    rev = cfg["review"]
    for k, v in REQUIRED_POSTPROC52["review"].items():
        assert rev[k] == v, f"{k}: {rev.get(k)!r} != {v!r}"
    # ensemble_predict must read this file
    assert ep.CFG_PATH.name == "postproc52.json"
    assert ep.LO == 0.2
    assert ep.THR == 0.5
    assert ep.FLAG_SEED is True


# --- R7: seed-disagreement flag ----------------------------------------------

def test_seed_disagreement_shot_vs_nonshot():
    # M=3: model0/1 call shot, model2 non-shot
    PM = np.zeros((3, 2, 3), np.float32)
    PM[0, 0] = [0.2, 0.4, 0.4]  # P(shot)=0.8
    PM[1, 0] = [0.3, 0.35, 0.35]
    PM[2, 0] = [0.7, 0.15, 0.15]  # P(shot)=0.3
    assert ep.seed_disagreement(PM, 0) is True
    # all agree shot
    PM2 = np.zeros((3, 1, 3), np.float32)
    PM2[:, 0] = [0.2, 0.5, 0.3]
    assert ep.seed_disagreement(PM2, 0) is False


def test_seed_disagreement_make_miss_split():
    PM = np.zeros((3, 1, 3), np.float32)
    PM[0, 0] = [0.1, 0.7, 0.2]  # miss
    PM[1, 0] = [0.1, 0.2, 0.7]  # make
    PM[2, 0] = [0.1, 0.6, 0.3]  # miss
    assert ep.seed_disagreement(PM, 0) is True


def test_shot_list_flags_seed_disagreement():
    T = np.array([1000, 5000], np.int64)
    P = np.array([[0.1, 0.45, 0.45], [0.8, 0.1, 0.1]], np.float32)  # i0 shot, i1 not
    PM = np.zeros((3, 2, 3), np.float32)
    PM[0, 0] = [0.1, 0.7, 0.2]
    PM[1, 0] = [0.1, 0.2, 0.7]
    PM[2, 0] = [0.1, 0.6, 0.3]
    PM[:, 1] = [0.9, 0.05, 0.05]
    shots, extra = ep.shot_list(P, T, PM=PM)
    assert len(shots) == 1
    assert shots[0]["check"] is True  # make/miss split among seeds


# --- R6: silent-reject -------------------------------------------------------

def test_silent_reject_count():
    Y = np.array([0, 1, 1, 2], np.int64)
    P = np.array([
        [0.9, 0.05, 0.05],
        [0.85, 0.10, 0.05],  # miss, ens P(shot)=0.15 < 0.2
        [0.4, 0.4, 0.2],     # miss, ens P(shot)=0.6
        [0.1, 0.1, 0.8],
    ], np.float32)
    PM = np.zeros((3, 4, 3), np.float32)
    for s in range(3):
        PM[s] = P
        PM[s, 1] = [0.9, 0.05, 0.05]  # all seeds P(shot)=0.1 < 0.5
    assert ep.silent_reject_count(P, PM, Y, floor=0.2) == 1
    # if one seed calls shot, not silent
    PM[0, 1] = [0.2, 0.5, 0.3]
    assert ep.silent_reject_count(P, PM, Y, floor=0.2) == 0


# --- R8: honest review scoring -----------------------------------------------

def test_honest_review_no_tag_reuse_and_no_truth_insertion():
    # Truth: three shots at 1000, 5000, 9000
    truth = [(1000, 2), (5000, 1), (9000, 2)]
    # Non-flagged auto at 1000 (make) stands and marks tag0 used
    # Flagged auto at 5000 (wrong call make, but cand label miss) -> matches tag1
    # Flagged extra at 7000 with cand label 0 (non-shot) -> removed
    # Unflagged time 9000 has NO auto and is NOT inserted
    shots = [
        {"t_ms": 1000, "call": "make", "check": False, "p_shot": 0.9, "p_make": 0.8},
        {"t_ms": 5050, "call": "make", "check": True, "p_shot": 0.55, "p_make": 0.6},
    ]
    extra = [{"t_ms": 7000, "p_shot": 0.3}]
    cand = {1000: 2, 5050: 1, 7000: 0}
    right, n, false, nck = ep.honest_review_score(shots, extra, truth, cand)
    assert n == 3
    assert nck == 2  # one flagged shot + one extra
    # tag0 matched by non-flagged; tag1 by flagged; tag2 (9000) never inserted
    assert right == 2
    # auto alone finds only the non-flagged make
    a_right, a_n, a_false = ep.auto_score(shots, truth)
    assert a_right == 1
    assert a_n == 3


def test_honest_review_flagged_cannot_reuse_tag():
    truth = [(1000, 2)]
    # Non-flagged already took the only tag; flagged nearby must not reuse it
    shots = [
        {"t_ms": 1000, "call": "make", "check": False, "p_shot": 0.9, "p_make": 0.9},
        {"t_ms": 1200, "call": "miss", "check": True, "p_shot": 0.55, "p_make": 0.1},
    ]
    cand = {1000: 2, 1200: 1}
    right, n, false, nck = ep.honest_review_score(shots, [], truth, cand)
    assert right == 1
    assert n == 1
    # final list may still contain the flagged time as a false if it was a shot label
    # but it must not get a second credit for the same tag — right stays 1
    assert false >= 0


def test_honest_review_never_inserts_at_unflagged_times():
    truth = [(1000, 1), (8000, 2)]
    # Only a flagged non-shot at 1000; nothing at 8000. Must not invent the 8000 make.
    shots = [{"t_ms": 1000, "call": "miss", "check": True, "p_shot": 0.55, "p_make": 0.1}]
    # Wait: flagged with label miss WOULD match tag at 1000. Use non-shot label.
    cand = {1000: 0}
    right, n, false, nck = ep.honest_review_score(shots, [], truth, cand)
    assert right == 0
    assert n == 2


# --- Spec 52a: session_filter (default OFF; omit scoring; logo52 regression) ---

def _toy_session_interval(start_ms, end_ms):
    """Minimal session.json shape for in_session(is_ft=True)."""
    return {
        "intervals": [{"start_ms": int(start_ms), "end_ms": int(end_ms)}],
        "ft_windows": [],
    }


def test_postproc52a_r7_amendment_session_filter_true():
    """R7 amendment for logo52a: postproc52a.json has session_filter true; postproc52 stays false."""
    cfg52 = json.load(open(HERE / "postproc52.json"))
    cfg52a = json.load(open(HERE / "postproc52a.json"))
    assert cfg52["session_filter"] is False
    assert cfg52a["session_filter"] is True
    for k in ("shot_thr", "dedup_ms"):
        assert cfg52a[k] == cfg52[k]
    for k, v in cfg52["review"].items():
        assert cfg52a["review"][k] == v
    # Spec 52b/52c: flat band kept — extras_require_seed_disagreement key ABSENT
    assert "extras_require_seed_disagreement" not in cfg52["review"]
    assert "extras_require_seed_disagreement" not in cfg52a["review"]


def test_postproc52b_schema_extras_require_seed_disagreement():
    """Spec 52c step 4: postproc52b.json exact keys; extras_require_seed_disagreement true."""
    cfg = json.load(open(HERE / "postproc52b.json"))
    assert cfg["shot_thr"] == 0.5
    assert cfg["dedup_ms"] == 800
    assert cfg["session_filter"] is True
    rev = cfg["review"]
    assert rev["flag_below_thr_candidates_with_shot_prob_at_least"] == 0.2
    assert rev["flag_auto_shots_with_shot_prob_below"] == 0.65
    assert rev["flag_auto_shots_with_abs_pmake_minus_half_below"] == 0.3
    assert rev["flag_seed_disagreement"] is True
    assert rev["extras_require_seed_disagreement"] is True
    # load_postproc picks up the flag
    ep.load_postproc(HERE / "postproc52b.json")
    assert ep.EXTRAS_REQUIRE_SEED is True
    # restore default so other tests see postproc52
    ep.load_postproc(HERE / "postproc52.json")
    assert ep.EXTRAS_REQUIRE_SEED is False
    assert "extras_require_seed_disagreement" not in ep.CFG["review"]


def test_session_filter_default_off_ignores_session():
    """Filter OFF (default): session is ignored; shot list matches no-session path."""
    T = np.array([1000, 5000, 9000], np.int64)
    # all three above thr as shots
    P = np.array([
        [0.1, 0.4, 0.5],
        [0.1, 0.5, 0.4],
        [0.1, 0.45, 0.45],
    ], np.float32)
    session = _toy_session_interval(4000, 6000)  # only mid in-session
    shots_off, extra_off = ep.shot_list(P, T, session=session, session_filter=False)
    shots_none, extra_none = ep.shot_list(P, T, session=None, session_filter=False)
    assert [s["t_ms"] for s in shots_off] == [s["t_ms"] for s in shots_none] == [1000, 5000, 9000]
    assert extra_off == extra_none
    # CFG default remains false
    assert ep.CFG["session_filter"] is False
    shots_cfg, _ = ep.shot_list(P, T, session=session)  # session_filter=None -> CFG
    assert [s["t_ms"] for s in shots_cfg] == [1000, 5000, 9000]


def test_session_filter_on_omits_out_of_session():
    """Filter ON: out-of-session candidates omitted from shots and extras."""
    T = np.array([1000, 5000, 9000, 12000], np.int64)
    P = np.array([
        [0.1, 0.4, 0.5],   # shot, oos
        [0.1, 0.5, 0.4],   # shot, in
        [0.6, 0.25, 0.15], # below thr but >= floor extra, oos
        [0.55, 0.3, 0.15], # extra, in
    ], np.float32)
    # Two intervals: mid shot + late extra in-session; 1000 and 9000 out.
    session = {
        "intervals": [
            {"start_ms": 4000, "end_ms": 6000},
            {"start_ms": 11000, "end_ms": 13000},
        ],
        "ft_windows": [],
    }
    assert gs.in_session(1000, session, is_ft=True) is False
    assert gs.in_session(5000, session, is_ft=True) is True
    assert gs.in_session(9000, session, is_ft=True) is False
    assert gs.in_session(12000, session, is_ft=True) is True
    shots, extra = ep.shot_list(P, T, session=session, session_filter=True)
    assert [s["t_ms"] for s in shots] == [5000]
    assert [e["t_ms"] for e in extra] == [12000]
    # without filter, both shots + both extras (thr 0.5; floor 0.2)
    shots_all, extra_all = ep.shot_list(P, T, session=session, session_filter=False)
    assert [s["t_ms"] for s in shots_all] == [1000, 5000]
    assert [e["t_ms"] for e in extra_all] == [9000, 12000]


def test_session_filter_none_session_is_passthrough():
    """Rimrock-type: filter ON but session is None -> no filtering."""
    T = np.array([1000, 5000], np.int64)
    P = np.array([[0.1, 0.4, 0.5], [0.1, 0.5, 0.4]], np.float32)
    shots, _ = ep.shot_list(P, T, session=None, session_filter=True)
    assert [s["t_ms"] for s in shots] == [1000, 5000]


def test_filtered_real_shot_is_recall_miss():
    """Omit scoring: filtered real shot is missing from pred list -> unmatched truth."""
    T = np.array([1000, 5000], np.int64)
    P = np.array([
        [0.1, 0.4, 0.5],  # would match truth at 1000, but oos
        [0.1, 0.5, 0.4],  # in-session
    ], np.float32)
    session = _toy_session_interval(4000, 6000)
    truth = [(1000, 2), (5000, 1)]
    shots, extra = ep.shot_list(P, T, session=session, session_filter=True)
    assert [s["t_ms"] for s in shots] == [5000]
    a_right, a_n, a_false = ep.auto_score(shots, truth)
    assert a_n == 2
    assert a_right == 1  # only 5000 matched; 1000 is recall miss
    # unfiltered would get both
    shots_all, _ = ep.shot_list(P, T, session=session, session_filter=False)
    r2, n2, _ = ep.auto_score(shots_all, truth)
    assert r2 == 2 and n2 == 2


def test_session_path_mapping_pinned():
    assert ep.session_path_for_film("rimrock") is None
    assert ep.SESSION_PATHS["adrian"].name == "session.json"
    assert "game_session_48b" in str(ep.SESSION_PATHS["adrian"])
    assert "game_session_48b" in str(ep.SESSION_PATHS["gvg"])
    assert ep.SESSION_PATHS["gvg"].parent.name == "gv"
    assert "hybrid49" in str(ep.SESSION_PATHS["hsb"])


def _truth_map_same5():
    return {
        "adrian": ep.load_truth_tags(
            REPO / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json"
        ),
        "notus": ep.load_truth_tags(
            REPO / "data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json"
        ),
        "gvg": ep.load_truth_labels(HERE.parent / "review52" / "truth52_gvg.json"),
        "hsb": ep.load_truth_labels(HERE.parent / "review52" / "truth52_hsb.json"),
        "rimrock": ep.load_truth_labels(HERE.parent / "review52" / "truth52_rimrock.json"),
    }


_GATE_KEYS = (
    "n_truth",
    "auto_right",
    "auto_pct",
    "auto_false",
    "seed_auto_pct",
    "seed_spread",
    "review_right",
    "review_pct",
    "review_false",
    "checks",
    "silent_reject",
    "PASS",
)


def test_logo52_gate_byte_identical_with_filter_off():
    """Re-score frozen logo52 preds with filter OFF; numbers match gate52_report.json."""
    logo_dir = Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52")
    preds = logo_dir / "logo_preds.npz"
    report_path = logo_dir / "gate52_report.json"
    if not preds.is_file() or not report_path.is_file():
        pytest.skip("logo52 outputs not present")
    # Ensure default postproc52 (filter OFF) is loaded
    ep.load_postproc(HERE / "postproc52.json")
    assert ep.CFG["session_filter"] is False
    assert ep.EXTRAS_REQUIRE_SEED is False
    report = json.load(open(report_path))
    d = np.load(preds, allow_pickle=True)
    P, PM, Y, T, F = d["P"], d["PM"], d["Y"], d["T"], d["F"]
    truth_map = _truth_map_same5()
    for film, truth in truth_map.items():
        m = F == film
        assert m.any(), film
        # Explicit filter OFF + session loaded (must still ignore session)
        session = ep.load_session_for_film(film)
        r = g52.score_film(
            P[m], PM[:, m], T[m], Y[m], truth, session=session, session_filter=False
        )
        expected = report[film]
        for k in _GATE_KEYS:
            assert r[k] == expected[k], f"{film}.{k}: {r[k]!r} != {expected[k]!r}"
        assert r["conditions"] == expected["conditions"]


def test_logo52a_gate_byte_identical_with_filter_on():
    """Re-score frozen logo52a preds with postproc52a (filter ON); match gate52_report.json."""
    logo_dir = Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52a")
    preds = logo_dir / "logo_preds.npz"
    report_path = logo_dir / "gate52_report.json"
    if not preds.is_file() or not report_path.is_file():
        pytest.skip("logo52a outputs not present")
    ep.load_postproc(HERE / "postproc52a.json")
    assert ep.CFG["session_filter"] is True
    assert ep.EXTRAS_REQUIRE_SEED is False
    report = json.load(open(report_path))
    d = np.load(preds, allow_pickle=True)
    P, PM, Y, T, F = d["P"], d["PM"], d["Y"], d["T"], d["F"]
    truth_map = _truth_map_same5()
    for film, truth in truth_map.items():
        m = F == film
        assert m.any(), film
        session = ep.load_session_for_film(film)
        r = g52.score_film(
            P[m], PM[:, m], T[m], Y[m], truth, session=session, session_filter=True
        )
        expected = report[film]
        for k in _GATE_KEYS:
            assert r[k] == expected[k], f"{film}.{k}: {r[k]!r} != {expected[k]!r}"
        assert r["conditions"] == expected["conditions"]
    # restore default
    ep.load_postproc(HERE / "postproc52.json")


# --- Spec 52b: extras require seed_disagreement --------------------------------

def test_52b_extras_flagged_only_if_seed_disagreement():
    """Below-thr band extra flagged only when seed_disagreement(PM, i) under 52b."""
    T = np.array([1000, 5000, 9000], np.int64)
    # i0 auto shot; i1 band extra WITH seed disagreement; i2 band extra WITHOUT
    P = np.array([
        [0.1, 0.4, 0.5],   # P(shot)=0.9 auto
        [0.6, 0.25, 0.15], # P(shot)=0.4 band
        [0.55, 0.3, 0.15], # P(shot)=0.45 band
    ], np.float32)
    PM = np.zeros((3, 3, 3), np.float32)
    PM[:, 0] = P[0]
    # i1: seed split shot vs non-shot
    PM[0, 1] = [0.2, 0.5, 0.3]   # P(shot)=0.8
    PM[1, 1] = [0.3, 0.4, 0.3]   # P(shot)=0.7
    PM[2, 1] = [0.8, 0.1, 0.1]   # P(shot)=0.2
    # i2: all seeds agree non-shot (below thr)
    PM[0, 2] = [0.55, 0.3, 0.15]
    PM[1, 2] = [0.6, 0.25, 0.15]
    PM[2, 2] = [0.58, 0.22, 0.2]
    assert ep.seed_disagreement(PM, 1) is True
    assert ep.seed_disagreement(PM, 2) is False
    # flat band (52 / 52a): both extras
    shots, extra = ep.shot_list(P, T, PM=PM, extras_require_seed_disagreement=False)
    assert [s["t_ms"] for s in shots] == [1000]
    assert [e["t_ms"] for e in extra] == [5000, 9000]
    # 52b: only corroborated extra
    shots_b, extra_b = ep.shot_list(P, T, PM=PM, extras_require_seed_disagreement=True)
    assert [s["t_ms"] for s in shots_b] == [1000]
    assert [e["t_ms"] for e in extra_b] == [5000]


def test_52b_uncorroborated_band_extra_not_flagged():
    T = np.array([2000], np.int64)
    P = np.array([[0.6, 0.25, 0.15]], np.float32)  # band
    PM = np.zeros((3, 1, 3), np.float32)
    PM[:, 0] = [0.6, 0.25, 0.15]  # all agree non-shot
    assert ep.seed_disagreement(PM, 0) is False
    _, extra = ep.shot_list(P, T, PM=PM, extras_require_seed_disagreement=True)
    assert extra == []
    _, extra_flat = ep.shot_list(P, T, PM=PM, extras_require_seed_disagreement=False)
    assert [e["t_ms"] for e in extra_flat] == [2000]


def test_52b_auto_flags_unchanged():
    """Auto check flags (weak / make-miss / seed) unchanged by extras_require_seed."""
    T = np.array([1000], np.int64)
    P = np.array([[0.1, 0.45, 0.45]], np.float32)  # P(shot)=0.9, p_make=0.5 -> mm flag
    PM = np.zeros((3, 1, 3), np.float32)
    PM[:, 0] = P[0]
    shots_a, _ = ep.shot_list(P, T, PM=PM, extras_require_seed_disagreement=False)
    shots_b, _ = ep.shot_list(P, T, PM=PM, extras_require_seed_disagreement=True)
    assert len(shots_a) == len(shots_b) == 1
    assert shots_a[0]["check"] is True
    assert shots_b[0]["check"] is True


def test_52b_silent_backstop_unchanged():
    """Silent-reject definition unchanged by 52b extras rule."""
    Y = np.array([1], np.int64)
    P = np.array([[0.85, 0.10, 0.05]], np.float32)  # ens P(shot)=0.15 < 0.2
    PM = np.zeros((3, 1, 3), np.float32)
    for s in range(3):
        PM[s, 0] = [0.9, 0.05, 0.05]  # all seeds < 0.5
    assert ep.silent_reject_count(P, PM, Y, floor=0.2) == 1
    # extras rule does not touch silent_reject_count
    ep.load_postproc(HERE / "postproc52b.json")
    assert ep.silent_reject_count(P, PM, Y, floor=0.2) == 1
    ep.load_postproc(HERE / "postproc52.json")


# --- Spec 52c helpers kept (pure); 52d model does not consume seq -----------------

def test_seq_follower_inclusive_window_and_dtype():
    """Flag at t+6000, no flag at t+6001; float32 0/1; pure function."""
    # inclusive end: follower exactly at t+6000 flags
    T3 = np.array([1000, 7000], np.int64)
    s3 = tc.seq_follower(T3, window_ms=6000)
    assert s3.dtype == np.float32
    assert s3.shape == (2, 1)
    assert float(s3[0, 0]) == 1.0  # 7000 in (1000, 7000]
    assert float(s3[1, 0]) == 0.0
    assert set(np.unique(s3).tolist()) <= {0.0, 1.0}
    # exclusive past end: candidate exactly at t+6001 must NOT flag
    T2 = np.array([1000, 7001], np.int64)
    s2 = tc.seq_follower(T2, window_ms=6000)
    assert float(s2[0, 0]) == 0.0
    assert float(s2[1, 0]) == 0.0
    # three-point: 1000 sees 7000; 7000 sees 7001; 7001 sees none
    T = np.array([1000, 7000, 7001], np.int64)
    s = tc.seq_follower(T, window_ms=6000)
    assert float(s[0, 0]) == 1.0
    assert float(s[1, 0]) == 1.0
    assert float(s[2, 0]) == 0.0


def test_seq_follower_per_film_never_across_films():
    """Cross-film concat invents false followers; per-film does not."""
    # film A ends at 1000; film B starts at 2000 — gap 1000 ms < 6000
    T = np.array([1000, 2000], np.int64)
    Fm = np.array(["a", "b"])
    cross = tc.seq_follower(T)  # WRONG if used across films
    assert float(cross[0, 0]) == 1.0
    per = tc.seq_follower_per_film(T, Fm)
    assert float(per[0, 0]) == 0.0
    assert float(per[1, 0]) == 0.0
    # same film: follower kept; includes -1/0 rows in lookup (labels unused)
    T2 = np.array([1000, 2500, 9000], np.int64)
    Fm2 = np.array(["gvg", "gvg", "gvg"])
    # y would be [-1, 0, 1] — function ignores labels
    s = tc.seq_follower_per_film(T2, Fm2)
    assert float(s[0, 0]) == 1.0  # 2500 within 6000
    assert float(s[1, 0]) == 0.0  # 9000 is +6500 > 6000
    assert float(s[2, 0]) == 0.0


# --- Spec 52d: window pin + R4 head + time-shift +-1 + predict bs 8 -------------

def test_52d_window_pin_n44_ktrig6_step016():
    """v3.1 pin: default clips7 unchanged; --window 52d -> N=44 / K_TRIG=6 / STEP=0.16."""
    # default module state = clips7 / clips7a
    assert ec.WINDOWS["clips7"]["N"] == 32
    assert ec.WINDOWS["clips7"]["STEP"] == 0.08
    assert ec.WINDOWS["clips7"]["T0"] == -0.88
    assert ec.WINDOWS["clips7"]["WINDOW_END_S"] == 1.60
    t0, step, end, n, k = ec.set_window("clips7")
    assert (t0, step, end, n, k) == (-0.88, 0.08, 1.60, 32, 11)
    assert ec.N == 32 and ec.K_TRIG == 11 and ec.STEP == 0.08
    # 52d pin
    t0, step, end, n, k = ec.set_window("52d")
    assert t0 == -0.88
    assert step == 0.16
    assert end == 6.0
    assert n == 44
    assert k == 6
    assert ec.N == 44 and ec.K_TRIG == 6 and ec.STEP == 0.16
    assert ec.OUT_W == 96 and ec.OUT_H == 112  # crop unchanged
    assert int(round((6.0 - (-0.88)) / 0.16)) + 1 == 44
    assert int(round(-(-0.88) / 0.16)) == 6
    # restore default so later imports / tests see clips7
    ec.set_window("clips7")


def test_52d_r4_head_dropout_then_linear_512_no_seq():
    """52d head PIN EXACTLY AS R4: Sequential(Dropout(0.5), Linear(512,3)); forward(x) only."""
    torch = pytest.importorskip("torch")
    import torch.nn as nn

    class FakeBB(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(512, 3)

        def forward(self, x):
            # mimic pool -> fc path used by ClipModel
            B = x.shape[0]
            return self.fc(torch.ones(B, 512))

    m = tc.ClipModel(FakeBB())
    assert isinstance(m.backbone.fc, nn.Sequential)
    assert len(m.backbone.fc) == 2
    assert isinstance(m.backbone.fc[0], nn.Dropout)
    assert m.backbone.fc[0].p == 0.5
    assert isinstance(m.backbone.fc[1], nn.Linear)
    assert m.backbone.fc[1].in_features == 512
    assert m.backbone.fc[1].out_features == 3
    # no pool_drop / no concat head
    assert not hasattr(m, "pool_drop") or m.__dict__.get("pool_drop") is None
    # single-input forward (no seq parameter)
    sig = inspect.signature(m.forward)
    assert list(sig.parameters) == ["x"]
    m.eval()
    B = 2
    x = torch.zeros(B, 3, 4, 8, 8)
    logits = m(x)
    assert logits.shape == (B, 3)
    # R4 checkpoint key layout under backbone.fc.*
    keys = set(m.state_dict())
    assert "backbone.fc.1.weight" in keys
    assert "backbone.fc.1.bias" in keys
    assert "backbone.fc.0.weight" not in keys  # Dropout has no weight


def test_52d_time_shift_plus_minus_one_frame():
    """52d aug time-shift pin is +-1 frame (not +-2)."""
    assert tc.TIME_SHIFT_FRAMES == 1
    src = inspect.getsource(tc.augment)
    assert "time_shift_frames" in src
    # default argument on augment matches pin
    assert tc.augment.__defaults__ is not None
    # soft is first default; time_shift_frames last
    assert tc.TIME_SHIFT_FRAMES == 1


def test_52d_predict_bs_forced_to_8():
    """predict default / forced batch size is 8 (overrides old default 16)."""
    assert tc.PREDICT_BS == 8
    # default bs=None resolves to PREDICT_BS inside predict
    sig = inspect.signature(tc.predict)
    assert sig.parameters["bs"].default is None
    assert sig.parameters["seq"].default is None


def test_52d_speed_guard_threshold():
    """G8: STOP when measured s/step > 2x probe 0.53 (= 1.06)."""
    assert tc.SPEED_PROBE_S_PER_STEP == 0.53
    assert abs(tc.SPEED_GUARD_MAX_S_PER_STEP - 1.06) < 1e-9
    with pytest.raises(SystemExit) as ei:
        tc._speed_guard_stop(1.07, spill=False)
    assert "STOP for Scott" in str(ei.value)


def test_predict_all_52d_no_seq_forces_bs8(monkeypatch):
    """predict_all ignores seq and forces predict bs=8 for 52d models."""
    torch = pytest.importorskip("torch")
    captured = {}

    class FakeM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = torch.nn.Sequential(
                torch.nn.Dropout(0.5),
                torch.nn.Linear(512, 3),
            )

        def forward(self, x):
            return torch.zeros(x.shape[0], 3)

        def cuda(self):
            return self

        def eval(self):
            return self

        def load_state_dict(self, *a, **k):
            return None

    def fake_make_model(device="cuda"):
        return FakeM()

    def fake_predict(model, X, bs=None, tta=True, seq=None):
        captured["bs"] = bs
        captured["seq"] = seq
        return np.zeros((len(X), 3), np.float32)

    monkeypatch.setattr(tc, "make_model", fake_make_model)
    monkeypatch.setattr(tc, "predict", fake_predict)
    monkeypatch.setattr(torch, "load", lambda *a, **k: {})
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    X = np.zeros((4, 2, 4, 4, 3), np.uint8)
    PM = ep.predict_all(X, ["dummy.pt"], seq=None)
    assert PM.shape == (1, 4, 3)
    assert captured["bs"] == tc.PREDICT_BS == 8
    assert captured["seq"] is None
    # seq kw accepted but ignored
    ep.predict_all(X, ["dummy.pt"], seq=np.ones((4, 1), np.float32))
    assert captured["seq"] is None
    assert captured["bs"] == 8
