"""Synthetic tests for hybrid_pull (spec 49). No video."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hybrid_pull as hp  # noqa: E402


# Full 15-name list (features doc shape from mm_learned); pull indexes by name.
_ALL_NAMES = [
    "F1_v6_count",
    "F2_bodd_count",
    "F3_has_crossing",
    "F4_crossing_x_hw",
    "F5_max_depth_hw",
    "F6_in_column_count",
    "F7_max_upward_hw",
    "F8_max_x_10f_hw",
    "F9_bodd_has_crossing",
    "F10_bodd_crossing_x_hw",
    "F11_bodd_max_depth_hw",
    "F12_net_motion_after",
    "F13_net_motion_before",
    "F14_v6_new_pred",
    "F15_d2v1_new_pred",
]


def _feat_row(f4, f5, f6, f12, t_ms=0):
    feats = [0.0] * 15
    feats[3] = float(f4)
    feats[4] = float(f5)
    feats[5] = float(f6)
    feats[11] = float(f12)
    return {"moment_t_ms": int(t_ms), "features": feats}


def _features_doc(rows):
    return {"feature_names": list(_ALL_NAMES), "rows": rows}


def _session(intervals=None, ft_windows=None):
    return {
        "intervals": intervals or [],
        "ft_windows": ft_windows or [],
    }


def _tiny_model():
    """Hand model: p = sigmoid(coef · scaled_x + intercept) with identity scale."""
    return {
        "feature_names": list(hp.PULL_FEATURE_NAMES),
        "scaler_mean": [0.0, 0.0, 0.0, 0.0],
        "scaler_scale": [1.0, 1.0, 1.0, 1.0],
        "coef": [0.0, 0.0, 0.0, 0.0],
        "intercept": 0.0,  # sigmoid 0 -> p = 0.5
        "sklearn_version": "test",
        "train_counts": {"adrian": 0, "notus": 0, "gv": 0},
        "frozen_json_sha256": "x",
    }


def _model_with_p(target_p: float):
    """Intercept-only model so every row gets the same p = target_p."""
    # sigmoid(z) = target_p -> z = log(p/(1-p))
    p = float(target_p)
    if p <= 0.0 or p >= 1.0:
        raise ValueError("target_p must be in (0,1)")
    z = float(np.log(p / (1.0 - p)))
    m = _tiny_model()
    m["intercept"] = z
    return m


# ---------------------------------------------------------------------------
# F12 film-median scaling
# ---------------------------------------------------------------------------


def test_f12_film_median_scales_and_zero_median():
    doc = _features_doc(
        [
            _feat_row(0.1, 0.2, 1.0, 2.0, t_ms=1),
            _feat_row(0.1, 0.2, 1.0, 4.0, t_ms=2),
            _feat_row(0.1, 0.2, 1.0, 6.0, t_ms=3),
        ]
    )
    med = hp.f12_film_median(doc)
    assert med == 4.0
    x = hp.pull_x_from_features(doc["rows"][0]["features"], doc["feature_names"], med)
    assert x[0] == pytest.approx(0.1)
    assert x[1] == pytest.approx(0.2)
    assert x[2] == pytest.approx(1.0)
    assert x[3] == pytest.approx(2.0 / 4.0)

    zero_doc = _features_doc(
        [
            _feat_row(0.0, 0.0, 0.0, 0.0, t_ms=1),
            _feat_row(0.0, 0.0, 0.0, 0.0, t_ms=2),
        ]
    )
    assert hp.f12_film_median(zero_doc) == 1.0
    xz = hp.pull_x_from_features(
        zero_doc["rows"][0]["features"], zero_doc["feature_names"], 1.0
    )
    assert xz[3] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# model.json round-trip == pipeline predict_proba to 1e-9
# ---------------------------------------------------------------------------


def test_model_json_scoring_matches_pipeline_to_1e_9():
    rng = np.random.default_rng(49)
    X = rng.normal(size=(40, 4))
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(int)
    # ensure both classes
    y[0] = 0
    y[1] = 1
    pipe = hp.make_pipeline()
    pipe.fit(X, y)
    model = hp.model_dict_from_pipeline(
        pipe,
        train_counts={"adrian": 10, "notus": 10, "gv": 20},
        frozen_json_sha256="abc",
    )
    p_pipe = hp.predict_proba_pipeline(pipe, X)
    p_model = hp.predict_proba_from_model(model, X)
    assert float(np.max(np.abs(p_pipe - p_model))) <= 1e-9


# ---------------------------------------------------------------------------
# pull rules
# ---------------------------------------------------------------------------


def test_pull_only_in_session_miss_at_threshold_edges():
    # one interval covering 1000-2000; features for three vote rows
    session = _session(intervals=[{"start_ms": 1000, "end_ms": 2000}])
    feats = _features_doc(
        [
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=1000),
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=1500),
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=1800),
        ]
    )
    votes = [
        {"moment_t_ms": 1000, "call": "miss"},
        {"moment_t_ms": 1500, "call": "miss"},
        {"moment_t_ms": 1800, "call": "miss"},
    ]
    # p = 0.6999 -> not pulled; p = 0.70 -> pulled
    rows_lo = hp.build_pull_rows(
        vote_rows=votes,
        features_doc=feats,
        session=session,
        ft_reasons={},
        model=_model_with_p(0.6999),
        threshold=0.70,
    )
    assert all(r["in_session"] for r in rows_lo)
    assert all(r["p"] == pytest.approx(0.6999) for r in rows_lo)
    assert all(r["pulled"] is False for r in rows_lo)

    rows_hi = hp.build_pull_rows(
        vote_rows=votes,
        features_doc=feats,
        session=session,
        ft_reasons={},
        model=_model_with_p(0.70),
        threshold=0.70,
    )
    assert all(r["pulled"] is True for r in rows_hi)


def test_make_and_coach_not_pulled_even_with_high_p():
    session = _session(intervals=[{"start_ms": 0, "end_ms": 10_000}])
    feats = _features_doc(
        [
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=100),
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=200),
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=300),
        ]
    )
    votes = [
        {"moment_t_ms": 100, "call": "make"},
        {"moment_t_ms": 200, "call": "coach"},
        {"moment_t_ms": 300, "call": "miss"},
    ]
    rows = hp.build_pull_rows(
        vote_rows=votes,
        features_doc=feats,
        session=session,
        ft_reasons={},
        model=_model_with_p(0.95),
        threshold=0.70,
    )
    by_t = {r["t_ms"]: r for r in rows}
    assert by_t[100]["rules_call"] == "make" and by_t[100]["pulled"] is False
    assert by_t[200]["rules_call"] == "coach" and by_t[200]["pulled"] is False
    assert by_t[300]["rules_call"] == "miss" and by_t[300]["pulled"] is True
    # p still scored for in-session rows with features
    assert by_t[100]["p"] == pytest.approx(0.95)
    assert by_t[200]["p"] == pytest.approx(0.95)


def test_out_of_session_has_null_p_and_not_pulled():
    session = _session(intervals=[{"start_ms": 1000, "end_ms": 2000}])
    feats = _features_doc([_feat_row(0.0, 0.0, 0.0, 1.0, t_ms=500)])
    votes = [{"moment_t_ms": 500, "call": "miss"}]
    rows = hp.build_pull_rows(
        vote_rows=votes,
        features_doc=feats,
        session=session,
        ft_reasons={},
        model=_model_with_p(0.99),
        threshold=0.70,
    )
    assert rows[0]["in_session"] is False
    assert rows[0]["p"] is None
    assert rows[0]["pulled"] is False


def test_ft_window_only_for_ft_flagged_moments():
    # t=1500 only inside an FT window (not a regular interval)
    session = _session(
        intervals=[],
        ft_windows=[{"start_ms": 1000, "end_ms": 2000}],
    )
    feats = _features_doc(
        [
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=1500),
            _feat_row(0.0, 0.0, 0.0, 1.0, t_ms=1600),
        ]
    )
    votes = [
        {"moment_t_ms": 1500, "call": "miss"},
        {"moment_t_ms": 1600, "call": "miss"},
    ]
    model = _model_with_p(0.90)

    # FT-flagged -> in session via ft_window
    rows_ft = hp.build_pull_rows(
        vote_rows=votes[:1],
        features_doc=feats,
        session=session,
        ft_reasons={1500: "free_throw_line"},
        model=model,
        threshold=0.70,
    )
    assert rows_ft[0]["in_session"] is True
    assert rows_ft[0]["p"] == pytest.approx(0.90)
    assert rows_ft[0]["pulled"] is True

    rows_maybe = hp.build_pull_rows(
        vote_rows=[{"moment_t_ms": 1500, "call": "miss"}],
        features_doc=feats,
        session=session,
        ft_reasons={1500: "maybe_free_throw"},
        model=model,
        threshold=0.70,
    )
    assert rows_maybe[0]["in_session"] is True

    # not FT-flagged -> out of session even though inside ft_window
    rows_no = hp.build_pull_rows(
        vote_rows=[{"moment_t_ms": 1600, "call": "miss"}],
        features_doc=feats,
        session=session,
        ft_reasons={1600: "not_still"},
        model=model,
        threshold=0.70,
    )
    assert rows_no[0]["in_session"] is False
    assert rows_no[0]["p"] is None
    assert rows_no[0]["pulled"] is False


def test_in_session_without_features_has_null_p():
    session = _session(intervals=[{"start_ms": 0, "end_ms": 10_000}])
    feats = _features_doc([_feat_row(0.0, 0.0, 0.0, 1.0, t_ms=999)])  # different t
    votes = [{"moment_t_ms": 100, "call": "miss"}]
    rows = hp.build_pull_rows(
        vote_rows=votes,
        features_doc=feats,
        session=session,
        ft_reasons={},
        model=_model_with_p(0.99),
        threshold=0.70,
    )
    assert rows[0]["in_session"] is True
    assert rows[0]["p"] is None
    assert rows[0]["pulled"] is False


# ---------------------------------------------------------------------------
# F14/F15 never read (source check)
# ---------------------------------------------------------------------------


def test_source_never_mentions_f14_or_f15():
    src = (HERE / "hybrid_pull.py").read_text(encoding="utf-8")
    assert "F14" not in src
    assert "F15" not in src


# ---------------------------------------------------------------------------
# CLI smoke: train writes model.json; pull writes pull.json
# ---------------------------------------------------------------------------


def test_cmd_train_and_pull_roundtrip(tmp_path: Path):
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    # tiny balanced synthetic frozen set (3 films)
    for film, base in (("adrian", 0), ("notus", 100), ("gv", 200)):
        labels = {
            "film": film,
            "rows": [
                {
                    "moment_t_ms": base + 1,
                    "label": 1,
                    "matched_tag_t_ms": base + 1,
                },
                {
                    "moment_t_ms": base + 2,
                    "label": 0,
                    "matched_tag_t_ms": base + 2,
                },
                {
                    "moment_t_ms": base + 3,
                    "label": 0,
                    "matched_tag_t_ms": None,
                },
            ],
        }
        features = _features_doc(
            [
                _feat_row(1.0, 0.5, 3.0, 2.0, t_ms=base + 1),
                _feat_row(-1.0, -0.5, 0.0, 2.0, t_ms=base + 2),
                _feat_row(0.0, 0.0, 1.0, 2.0, t_ms=base + 3),
            ]
        )
        (frozen / f"labels_{film}.json").write_text(
            json.dumps(labels), encoding="utf-8"
        )
        (frozen / f"features_{film}.json").write_text(
            json.dumps(features), encoding="utf-8"
        )
    # frozen.json hashes (content does not need to match real frozen)
    frozen_map = {
        p.name: hp._sha256_file(p)
        for p in sorted(frozen.glob("*.json"))
        if p.name != "frozen.json"
    }
    (frozen / "frozen.json").write_text(json.dumps(frozen_map), encoding="utf-8")

    model_path = tmp_path / "model.json"
    rc = hp.main(["train", "--frozen-dir", str(frozen), "--out", str(model_path)])
    assert rc == 0
    model = json.loads(model_path.read_text(encoding="utf-8"))
    assert model["feature_names"] == list(hp.PULL_FEATURE_NAMES)
    assert "scaler_mean" in model and "scaler_scale" in model
    assert "coef" in model and "intercept" in model
    assert "sklearn_version" in model
    assert model["train_counts"] == {"adrian": 3, "notus": 3, "gv": 3}
    assert model["frozen_json_sha256"] == hp._sha256_file(frozen / "frozen.json")

    # pull CLI
    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(_session(intervals=[{"start_ms": 0, "end_ms": 10}])),
        encoding="utf-8",
    )
    mm_path = tmp_path / "make_miss.json"
    mm_path.write_text(
        json.dumps([{"moment_t_ms": 1, "call": "miss"}]),
        encoding="utf-8",
    )
    feat_path = tmp_path / "features.json"
    feat_path.write_text(
        json.dumps(_features_doc([_feat_row(1.0, 0.5, 3.0, 2.0, t_ms=1)])),
        encoding="utf-8",
    )
    ft_path = tmp_path / "ft_moments.json"
    ft_path.write_text(
        json.dumps({"moments": [{"t_ms": 1, "ft_reason": None}]}),
        encoding="utf-8",
    )
    pull_path = tmp_path / "pull.json"
    rc2 = hp.main(
        [
            "pull",
            "--make-miss",
            str(mm_path),
            "--features",
            str(feat_path),
            "--session",
            str(session_path),
            "--ft-moments",
            str(ft_path),
            "--model",
            str(model_path),
            "--out",
            str(pull_path),
        ]
    )
    assert rc2 == 0
    pull = json.loads(pull_path.read_text(encoding="utf-8"))
    assert len(pull) == 1
    assert set(pull[0].keys()) == {
        "t_ms",
        "in_session",
        "rules_call",
        "p",
        "pulled",
    }
    assert pull[0]["in_session"] is True
    assert isinstance(pull[0]["p"], float)
