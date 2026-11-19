"""Synthetic tests for mm_learned (spec 47). No video, no models."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import mm_learned as mml  # noqa: E402


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------


def test_label_match_make_and_miss():
    moments = [1000, 5000, 9000]
    tags = [
        {"t": 1100, "result": "Make"},
        {"t": 5200, "result": "Miss"},
    ]
    out = mml.label_moments_from_tags(moments, tags)
    by_t = {r["moment_t_ms"]: r for r in out["rows"]}
    assert by_t[1000]["label"] == 1
    assert by_t[1000]["matched_tag_t_ms"] == 1100
    assert by_t[5000]["label"] == 0
    assert by_t[5000]["matched_tag_t_ms"] == 5200
    assert by_t[9000]["label"] == 0
    assert by_t[9000]["matched_tag_t_ms"] is None
    assert out["counts"]["label_1"] == 1
    assert out["counts"]["label_0"] == 2
    assert out["counts"]["finder_missed"] == 0


def test_label_unmatched_near_make_excluded():
    moments = [1000, 2500]  # 2500 within 4000 of Make at 1000 but unmatched
    tags = [{"t": 1000, "result": "Make"}]
    out = mml.label_moments_from_tags(moments, tags, window_ms=4000)
    by_t = {r["moment_t_ms"]: r for r in out["rows"]}
    assert by_t[1000]["label"] == 1
    assert by_t[2500]["label"] is None
    assert by_t[2500]["excluded_reason"] == "near_make_tag"
    assert out["counts"]["excluded"] == 1
    assert out["excluded"][0]["moment_t_ms"] == 2500
    assert out["excluded"][0]["nearest_make_tag_t_ms"] == 1000


def test_label_unmatched_far_is_zero():
    moments = [1000, 20000]
    tags = [{"t": 1000, "result": "Make"}]
    out = mml.label_moments_from_tags(moments, tags, window_ms=4000)
    by_t = {r["moment_t_ms"]: r for r in out["rows"]}
    assert by_t[20000]["label"] == 0
    assert by_t[20000]["excluded_reason"] is None
    assert out["counts"]["excluded"] == 0


def test_label_span_filter():
    moments = [100, 500, 900]
    tags = [
        {"t": 100, "result": "Make"},
        {"t": 500, "result": "Miss"},
        {"t": 900, "result": "Make"},
    ]
    out = mml.label_moments_from_tags(
        moments, tags, span_start_ms=200, span_end_ms=800
    )
    times = [r["moment_t_ms"] for r in out["rows"]]
    assert times == [500]
    assert out["rows"][0]["label"] == 0
    # tag at 100 and 900 are outside span -> not finder_missed inside span
    assert out["counts"]["finder_missed"] == 0


def test_label_tag_with_no_moment_finder_missed():
    moments = [1000]
    tags = [
        {"t": 1000, "result": "Make"},
        {"t": 8000, "result": "Miss"},
    ]
    out = mml.label_moments_from_tags(moments, tags, window_ms=4000)
    assert out["counts"]["finder_missed"] == 1
    assert out["finder_missed"][0]["tag_t_ms"] == 8000
    assert out["finder_missed"][0]["result"] == "Miss"


def test_label_gv_make_miss_nonshot_unclear():
    moments = [10, 20, 30, 40]
    gv = {
        "moments": {
            "10": {"shot": "yes", "result": "make"},
            "20": {"shot": "yes", "result": "miss"},
            "30": {"shot": "no", "result": None},
            "40": {"shot": "unclear", "result": None},
        }
    }
    out = mml.label_moments_from_gv(moments, gv)
    by_t = {r["moment_t_ms"]: r for r in out["rows"]}
    assert by_t[10]["label"] == 1 and by_t[10]["matched_tag_t_ms"] == 10
    assert by_t[20]["label"] == 0 and by_t[20]["matched_tag_t_ms"] == 20
    assert by_t[30]["label"] == 0 and by_t[30]["matched_tag_t_ms"] is None
    assert by_t[40]["label"] is None
    assert out["counts"]["label_1_from_gv"] == 1


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------


def _track_with_crossing():
    # hoop at (100, 50), width 10
    # ball crosses hy=50 between frames 3 (y=40) and 4 (y=55, x=103)
    return {
        "t": 1000,
        "moment_t_ms": 2000,
        "hoop": [100.0, 50.0, 10.0, 8.0],
        "ball": [
            [1, 100.0, 30.0],
            [2, 101.0, 40.0],
            [3, 102.0, 45.0],
            [4, 103.0, 55.0],  # crossing second point
            [5, 104.0, 65.0],  # depth 1.5, |x-hx|=0.4 < 0.6
            [6, 105.0, 70.0],
            [8, 110.0, 60.0],  # upward from 70->60
            [12, 106.0, 80.0],  # within 10 frames after cross (4+10=14)
            [20, 100.0, 90.0],  # outside 10-frame window
        ],
        "bodd": [
            [4, 100.0, 40.0],
            [5, 100.0, 55.0],  # crossing
            [6, 101.0, 66.0],  # depth 1.6
        ],
    }


def test_features_f1_to_f15_handmade():
    track = _track_with_crossing()
    # no video reader -> F12/F13 = 0
    feats = mml.compute_features_for_track(
        track, fps=25.0, read_frame=None, v6_pred=1.0, d2_pred=0.0
    )
    assert len(feats) == 15
    assert feats[0] == 9.0  # F1
    assert feats[1] == 3.0  # F2
    assert feats[2] == 1.0  # F3 has crossing
    # F4: |103-100|/10 = 0.3
    assert feats[3] == pytest.approx(0.3)
    # F5: after crossing idx, points with |x-hx|<6: (65-50)/10=1.5, (70-50)/10=2.0,
    # (60-50)/10=1.0 (x=110 -> |10|=10 not <6), (80-50)/10=3.0 (x=106 |6|=6 not <6),
    # (90-50)/10 with x=100 ok -> 4.0. Max among |x-hx|<0.6*hw=6:
    # f5: 65->1.5 (dx=4), 70->2.0 (dx=5), 60 skipped dx=10, 80 skipped dx=6 (not <),
    # 90->4.0 (dx=0). Max=4.0
    assert feats[4] == pytest.approx(4.0)
    # F6: 0 < depth < 2.5 and |x-hx|<6
    # pts: 55 d=0.5 dx=3; 65 d=1.5; 70 d=2.0; 60 d=1.0 dx=10 no; 80 d=3.0 no; 90 d=4 no
    # also before crossing? Spec does not restrict to after. 30,40,45 have depth<=0 or
    # depth negative relative to hy? (30-50)/10=-2 not in (0,2.5)
    # So 55,65,70 = 3
    assert feats[5] == 3.0
    # F7: after crossing points from idx: 55,65,70,60,80,90
    # ups: 55-65=-1, 65-70=-0.5, 70-60=1.0, 60-80=-2, 80-90=-1  (in hw: /10)
    # wait ups are (y_prev-y_next)/hw: (55-65)/10=-1, (65-70)/10=-0.5,
    # (70-60)/10=1.0, (60-80)/10=-2, (80-90)/10=-1 -> max=1.0
    assert feats[6] == pytest.approx(1.0)
    # F8: frames in (4, 14]: f=5,6,8,12 -> |x-hx|/hw = 0.4,0.5,1.0,0.6 -> max 1.0
    assert feats[7] == pytest.approx(1.0)
    # F9-F11 bodd
    assert feats[8] == 1.0
    assert feats[9] == pytest.approx(0.0)  # x=100
    assert feats[10] == pytest.approx(1.6)  # (66-50)/10
    assert feats[11] == 0.0  # F12 no reader
    assert feats[12] == 0.0
    assert feats[13] == 1.0  # F14
    assert feats[14] == 0.0  # F15


def test_features_no_hoop_sentinels_v4():
    track = {
        "t": 1000,
        "moment_t_ms": 2000,
        "hoop": None,
        "ball": [[0, 1.0, 2.0], [1, 2.0, 3.0]],
        "bodd": [[0, 1.0, 2.0]],
    }
    feats = mml.compute_features_for_track(
        track, fps=25.0, read_frame=None, v6_pred=1.0, d2_pred=1.0
    )
    assert feats[0] == 2.0
    assert feats[1] == 1.0
    assert feats[2] == 0.0
    assert feats[3] == 3.0
    assert feats[4] == 0.0
    assert feats[5] == 0.0
    assert feats[6] == 0.0
    assert feats[7] == 3.0
    assert feats[8] == 0.0
    assert feats[9] == 3.0
    assert feats[10] == 0.0
    assert feats[11] == 0.0
    assert feats[12] == 0.0
    assert feats[13] == 0.0  # F14 forced 0
    assert feats[14] == 0.0


def test_features_no_crossing():
    track = {
        "t": 1000,
        "moment_t_ms": 2000,
        "hoop": [100.0, 50.0, 10.0, 8.0],
        "ball": [[0, 100.0, 60.0], [1, 100.0, 70.0]],  # already below, no cross
        "bodd": [],
    }
    feats = mml.compute_features_for_track(
        track, fps=25.0, read_frame=None, v6_pred=0.0, d2_pred=1.0
    )
    assert feats[2] == 0.0  # F3
    assert feats[3] == 3.0  # F4
    assert feats[4] == 0.0
    assert feats[6] == 0.0  # F7
    assert feats[7] == 3.0  # F8 sentinel
    assert feats[13] == 0.0
    assert feats[14] == 1.0


def test_net_motion_ratio_injectable_reader():
    # 20x20 frames; primary box gets a bright flash; side stays flat
    hx, hy, hw = 5.0, 5.0, 4.0
    # primary: x 3..7, y 5..9.8 -> about cols 3-7, rows 5-10
    # side center x= hx+1.5*hw=11, box x 9..13

    def make_frame(level_primary: float, level_side: float) -> np.ndarray:
        fr = np.zeros((20, 20, 3), dtype=np.uint8)
        fr[5:10, 3:7, :] = int(level_primary)
        fr[5:10, 9:13, :] = int(level_side)
        return fr

    sequence = {
        100: make_frame(10, 10),
        101: make_frame(200, 10),  # big primary change
        102: make_frame(10, 10),
        103: make_frame(10, 12),  # tiny side change
    }

    def reader(idx: int):
        return sequence.get(int(idx))

    # after: frames 100..112 but only 100-103 exist
    r_after = mml.net_motion_ratio(
        reader, hx=hx, hy=hy, hw=hw, center_frame=100, after=True
    )
    assert r_after > 1.0

    # empty box -> 0
    r_empty = mml.net_motion_ratio(
        reader, hx=1000.0, hy=1000.0, hw=4.0, center_frame=100, after=True
    )
    assert r_empty == 0.0


def test_f14_f15_matched_by_track_t():
    tracks = [
        {
            "t": 1000,
            "moment_t_ms": 2000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [],
            "bodd": [],
        },
        {
            "t": 3000,
            "moment_t_ms": 4000,
            "hoop": [1.0, 2.0, 3.0, 4.0],
            "ball": [],
            "bodd": [],
        },
    ]
    v6 = {"shots": [{"t": 1000, "new_pred": True}, {"t": 3000, "new_pred": False}]}
    d2 = {"shots": [{"t": 1000, "new_pred": False}]}  # 3000 absent -> 0
    doc = mml.build_features_doc(
        tracks, fps=25.0, read_frame=None, v6_results=v6, d2_results=d2
    )
    assert doc["rows"][0]["features"][13] == 1.0
    assert doc["rows"][0]["features"][14] == 0.0
    assert doc["rows"][1]["features"][13] == 0.0
    assert doc["rows"][1]["features"][14] == 0.0


# ---------------------------------------------------------------------------
# band mapping
# ---------------------------------------------------------------------------


def test_band_mapping_edges():
    assert mml.band_call(0.80) == "make"
    assert mml.band_call(0.81) == "make"
    assert mml.band_call(0.20) == "miss"
    assert mml.band_call(0.19) == "miss"
    assert mml.band_call(0.50) == "coach"
    assert mml.band_call(0.799999) == "coach"
    assert mml.band_call(0.200001) == "coach"


# ---------------------------------------------------------------------------
# counting
# ---------------------------------------------------------------------------


def test_counting_identical_rules_vs_learned_toy():
    label_rows = [
        {"moment_t_ms": 1, "label": 1, "matched_tag_t_ms": 1, "source": "tag"},
        {"moment_t_ms": 2, "label": 0, "matched_tag_t_ms": 2, "source": "tag"},  # miss
        {"moment_t_ms": 3, "label": 0, "matched_tag_t_ms": None, "source": "tag"},  # non
        {"moment_t_ms": 4, "label": 1, "matched_tag_t_ms": 4, "source": "tag"},
        {"moment_t_ms": 5, "label": None, "matched_tag_t_ms": None, "source": "tag"},
    ]
    calls = {
        1: "make",
        2: "make",  # real miss called make
        3: "make",  # non-shot called make
        4: "miss",  # silent make
        5: "make",  # excluded — not scored
    }
    c = mml.count_side(calls, label_rows)
    assert c["makes_found"] == 1
    assert c["real_makes"] == 2
    assert c["real_misses_called_make"] == 1
    assert c["non_shots_called_make"] == 1
    assert c["false_makes"] == 2
    assert c["silent_makes"] == 1
    assert c["coach_load"] == 0

    # no_track counts as coach
    c2 = mml.count_side({1: "no_track", 2: "coach", 3: "miss", 4: "make"}, label_rows)
    assert c2["coach_load"] == 2  # moments 1 and 2
    assert c2["makes_found"] == 1  # moment 4


# ---------------------------------------------------------------------------
# LOGO / freeze / final
# ---------------------------------------------------------------------------


def _write_film_bundle(dir_path: Path, film: str, n: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    rows_lab = []
    rows_feat = []
    for i in range(n):
        mt = (i + 1) * 1000 + seed
        # separable-ish: label from first feature
        label = 1 if (i % 3 == 0) else 0
        feats = rng.normal(0, 1, size=15).tolist()
        feats[0] = 5.0 if label == 1 else 1.0
        rows_lab.append(
            {
                "moment_t_ms": mt,
                "label": label,
                "source": "tag" if film != "gv" else "gv_labels",
                "matched_tag_t_ms": mt if label == 1 or i % 2 == 0 else None,
                "excluded_reason": None,
            }
        )
        rows_feat.append({"moment_t_ms": mt, "features": feats})
    # one excluded row
    rows_lab.append(
        {
            "moment_t_ms": 999999 + seed,
            "label": None,
            "source": "tag",
            "matched_tag_t_ms": None,
            "excluded_reason": "near_make_tag",
        }
    )
    lab = {
        "film": film,
        "rows": rows_lab,
        "counts": {
            "label_1": sum(1 for r in rows_lab if r["label"] == 1),
            "label_0": sum(1 for r in rows_lab if r["label"] == 0),
            "excluded": 1,
            "finder_missed": 0,
            "label_1_from_tag": 0,
            "label_1_from_gv": 0,
        },
        "excluded": [],
        "finder_missed": [],
    }
    feat = {"feature_names": list(mml.FEATURE_NAMES), "rows": rows_feat}
    (dir_path / f"labels_{film}.json").write_text(
        json.dumps(lab, indent=2), encoding="utf-8"
    )
    (dir_path / f"features_{film}.json").write_text(
        json.dumps(feat, indent=2), encoding="utf-8"
    )


def _write_rules(path: Path, labels_path: Path, *, weak: bool) -> None:
    lab = json.loads(labels_path.read_text(encoding="utf-8"))
    rows = []
    for r in lab["rows"]:
        if r["label"] not in (0, 1):
            continue
        if weak:
            # weak rules: miss everything (low makes_found, low false, low coach)
            call = "miss"
        else:
            call = "make" if r["label"] == 1 else "miss"
        rows.append({"moment_t_ms": r["moment_t_ms"], "call": call})
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def test_logo_trains_other_two_games_scaler_no_holdout(tmp_path: Path):
    for i, film in enumerate(mml.FILMS):
        _write_film_bundle(tmp_path, film, n=12, seed=10 + i)
    mml.cmd_freeze(argparse_ns(dir=tmp_path))

    data = {}
    for film in mml.FILMS:
        labels_doc = json.loads((tmp_path / f"labels_{film}.json").read_text())
        features_doc = json.loads((tmp_path / f"features_{film}.json").read_text())
        X, y, times, label_rows = mml.load_scored_xy(labels_doc, features_doc)
        data[film] = {
            "X": X,
            "y": y,
            "times": times,
            "label_rows": label_rows,
        }

    # monkeypatch make_pipeline to capture train X
    captured = {}
    real_make = mml.make_pipeline

    def wrapping_make():
        pipe = real_make()
        orig_fit = pipe.fit

        def fit(X, y=None):
            captured["X"] = np.asarray(X)
            captured["y"] = np.asarray(y)
            return orig_fit(X, y)

        pipe.fit = fit  # type: ignore[method-assign]
        return pipe

    rule_calls = {}
    for film in mml.FILMS:
        rules_path = tmp_path / f"rules_{film}.json"
        _write_rules(rules_path, tmp_path / f"labels_{film}.json", weak=True)
        rule_calls[film] = mml.load_rule_calls(rules_path)

    hold = "notus"
    train_films = [f for f in mml.FILMS if f != hold]
    X_train = np.concatenate([data[f]["X"] for f in train_films], axis=0)
    y_train = np.concatenate([data[f]["y"] for f in train_films], axis=0)
    X_test = data[hold]["X"]

    mml.make_pipeline = wrapping_make  # type: ignore[assignment]
    try:
        pipe = mml.make_pipeline()
        pipe.fit(X_train, y_train)
        assert captured["X"].shape[0] == X_train.shape[0]
        # scaler must not have seen hold-out rows
        scaler = pipe.named_steps["scaler"]
        assert int(scaler.n_samples_seen_) == X_train.shape[0]
        assert np.allclose(scaler.mean_, X_train.mean(axis=0))
        # hold-out mean differs or at least hold-out size not in n_samples
        assert X_test.shape[0] > 0
        assert int(scaler.n_samples_seen_) != X_train.shape[0] + X_test.shape[0]
    finally:
        mml.make_pipeline = real_make  # type: ignore[assignment]

    # full LOGO: train films exclude hold-out times
    result = mml.run_logo(data=data, rule_calls=rule_calls)
    for fold in result["folds"]:
        hold_out = fold["hold_out"]
        assert hold_out not in fold["train_films"]
        assert set(fold["train_films"]) == set(f for f in mml.FILMS if f != hold_out)
        assert fold["scaler_n_samples_seen"] == fold["n_train"]


def argparse_ns(**kwargs):
    return type("NS", (), kwargs)()


def test_logo_refuses_on_sha256_change(tmp_path: Path):
    for i, film in enumerate(mml.FILMS):
        _write_film_bundle(tmp_path, film, n=6, seed=20 + i)
    mml.cmd_freeze(argparse_ns(dir=tmp_path))
    # tamper features
    path = tmp_path / "features_adrian.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["rows"][0]["features"][0] += 1.0
    path.write_text(json.dumps(doc), encoding="utf-8")
    for film in mml.FILMS:
        _write_rules(
            tmp_path / f"rules_{film}.json",
            tmp_path / f"labels_{film}.json",
            weak=True,
        )
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        mml.cmd_logo(
            argparse_ns(
                dir=tmp_path,
                rules_adrian=tmp_path / "rules_adrian.json",
                rules_notus=tmp_path / "rules_notus.json",
                rules_gv=tmp_path / "rules_gv.json",
                out=tmp_path / "out",
            )
        )


def test_final_refuses_when_fold_failed(tmp_path: Path):
    report = {
        "all_pass": False,
        "folds": [{"hold_out": "adrian", "pass": False}],
    }
    (tmp_path / "logo_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="all_pass is false"):
        mml.cmd_final(argparse_ns(dir=tmp_path, out_dir=tmp_path / "final"))


def test_match_label_ms_constant():
    assert mml.MATCH_LABEL_MS == 4000


def test_pass_bar():
    rules = {"makes_found": 5, "false_makes": 3, "coach_load": 10}
    assert mml.pass_bar(
        {"makes_found": 5, "false_makes": 3, "coach_load": 10}, rules
    )
    assert mml.pass_bar(
        {"makes_found": 6, "false_makes": 2, "coach_load": 9}, rules
    )
    assert not mml.pass_bar(
        {"makes_found": 4, "false_makes": 3, "coach_load": 10}, rules
    )
    assert not mml.pass_bar(
        {"makes_found": 5, "false_makes": 4, "coach_load": 10}, rules
    )
    assert not mml.pass_bar(
        {"makes_found": 5, "false_makes": 3, "coach_load": 11}, rules
    )
