"""Hybrid pull (spec 49). Rules keep their call; a second score pulls likely hidden makes.

NEW file only. Settings H1-H8 fixed; add no other number.
Scoring from model.json uses stored mean/scale/coef/intercept (no sklearn pickle).
Never reads the two rules-copy features. applied_to_core stays false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_session import in_session  # noqa: E402
import mm_learned as mml  # noqa: E402

# H4 / H5 — fixed
FILMS = ("adrian", "notus", "gv")
DEFAULT_THRESHOLD = 0.70
LR_C = 1.0
LR_MAX_ITER = 1000
LR_CLASS_WEIGHT = "balanced"

PULL_FEATURE_NAMES = [
    "F4_crossing_x_hw",
    "F5_max_depth_hw",
    "F6_in_column_count",
    "F12_net_motion_after",
]

FT_REASONS = frozenset({"free_throw_line", "maybe_free_throw"})

# H8 expected pulled/caught at T 0.70, real shots only (design48)
SEEN_EXPECTED = {
    "adrian": (12, 7),
    "notus": (3, 0),
    "gv": (41, 17),
}


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Features / F12 film-median scaling
# ---------------------------------------------------------------------------


def feature_index_map(feature_names: Sequence[str]) -> Dict[str, int]:
    return {str(n): i for i, n in enumerate(feature_names)}


def f12_film_median(features_doc: Dict[str, Any]) -> float:
    """Median of F12 over ALL feature rows for this film; 1.0 if median is 0."""
    names = list(features_doc["feature_names"])
    idx = feature_index_map(names)
    f12_i = idx[PULL_FEATURE_NAMES[3]]
    vals = [float(r["features"][f12_i]) for r in features_doc["rows"]]
    if not vals:
        return 1.0
    med = float(statistics.median(vals))
    return med if med != 0.0 else 1.0


def pull_x_from_features(
    features: Sequence[float],
    feature_names: Sequence[str],
    f12_median: float,
) -> List[float]:
    """Four pull features; F12 divided by this film's median (already 1.0 if 0)."""
    idx = feature_index_map(feature_names)
    out: List[float] = []
    for name in PULL_FEATURE_NAMES:
        v = float(features[idx[name]])
        if name == PULL_FEATURE_NAMES[3]:
            v = v / float(f12_median)
        out.append(v)
    return out


def build_film_xy(
    labels_doc: Dict[str, Any],
    features_doc: Dict[str, Any],
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """Label 0/1 rows joined to features by moment_t_ms. X uses film F12 median."""
    med = f12_film_median(features_doc)
    names = list(features_doc["feature_names"])
    feat_by_t = {
        int(r["moment_t_ms"]): [float(v) for v in r["features"]]
        for r in features_doc["rows"]
    }
    xs: List[List[float]] = []
    ys: List[int] = []
    kept: List[Dict[str, Any]] = []
    for row in labels_doc["rows"]:
        label = row.get("label")
        if label not in (0, 1):
            continue
        mt = int(row["moment_t_ms"])
        if mt not in feat_by_t:
            raise SystemExit(f"label moment_t_ms={mt} missing from features")
        xs.append(pull_x_from_features(feat_by_t[mt], names, med))
        ys.append(int(label))
        kept.append(row)
    if not xs:
        return (
            np.zeros((0, len(PULL_FEATURE_NAMES)), dtype=float),
            np.zeros((0,), dtype=int),
            [],
        )
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=int), kept


# ---------------------------------------------------------------------------
# Model fit + pickle-free scoring
# ---------------------------------------------------------------------------


def make_pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    C=LR_C,
                    class_weight=LR_CLASS_WEIGHT,
                    max_iter=LR_MAX_ITER,
                ),
            ),
        ]
    )


def model_dict_from_pipeline(
    pipe,
    *,
    train_counts: Dict[str, int],
    frozen_json_sha256: str,
) -> Dict[str, Any]:
    import sklearn

    scaler = pipe.named_steps["scaler"]
    clf = pipe.named_steps["clf"]
    classes = [int(c) for c in clf.classes_]
    if 1 not in classes:
        raise SystemExit("fitted classifier has no class 1")
    # binary: coef_/intercept_ are for classes_[1] when both present
    if classes == [0, 1]:
        coef = [float(v) for v in np.asarray(clf.coef_).reshape(-1)]
        intercept = float(np.asarray(clf.intercept_).reshape(-1)[0])
    else:
        # multi-class fallback: take the row for class 1
        ci = classes.index(1)
        coef = [float(v) for v in np.asarray(clf.coef_)[ci]]
        intercept = float(np.asarray(clf.intercept_)[ci])
    return {
        "feature_names": list(PULL_FEATURE_NAMES),
        "scaler_mean": [float(v) for v in np.asarray(scaler.mean_).reshape(-1)],
        "scaler_scale": [float(v) for v in np.asarray(scaler.scale_).reshape(-1)],
        "coef": coef,
        "intercept": intercept,
        "sklearn_version": str(sklearn.__version__),
        "train_counts": {f: int(train_counts.get(f, 0)) for f in FILMS},
        "frozen_json_sha256": str(frozen_json_sha256),
    }


def predict_proba_from_model(model: Dict[str, Any], X: np.ndarray) -> np.ndarray:
    """P(make) from stored scaler + logistic numbers. No sklearn required."""
    if X.size == 0:
        return np.zeros((0,), dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    mean = np.asarray(model["scaler_mean"], dtype=float)
    scale = np.asarray(model["scaler_scale"], dtype=float)
    coef = np.asarray(model["coef"], dtype=float).reshape(-1)
    intercept = float(model["intercept"])
    # mirror StandardScaler: zero-scale -> 1.0
    scale_safe = np.where(scale == 0.0, 1.0, scale)
    Xs = (X - mean) / scale_safe
    logits = Xs @ coef + intercept
    # stable sigmoid
    out = np.empty(logits.shape, dtype=float)
    for i, z in enumerate(logits):
        if z >= 0:
            ez = math.exp(-z)
            out[i] = 1.0 / (1.0 + ez)
        else:
            ez = math.exp(z)
            out[i] = ez / (1.0 + ez)
    return out


def predict_proba_pipeline(pipe, X: np.ndarray) -> np.ndarray:
    """Pipeline P(class=1); used to prove model.json matches fit to 1e-9."""
    if X.size == 0:
        return np.zeros((0,), dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    proba = pipe.predict_proba(X)
    classes = [int(c) for c in pipe.named_steps["clf"].classes_]
    if 1 not in classes:
        return np.zeros((X.shape[0],), dtype=float)
    return np.asarray(proba[:, classes.index(1)], dtype=float)


# ---------------------------------------------------------------------------
# FT moments / vote helpers
# ---------------------------------------------------------------------------


def load_ft_reasons(path: Path) -> Dict[int, Optional[str]]:
    """Map moment t_ms -> ft_reason from a spec-43 FT moments.json."""
    doc = _load_json(path)
    moments = doc.get("moments") if isinstance(doc, dict) else doc
    out: Dict[int, Optional[str]] = {}
    if isinstance(moments, list):
        for m in moments:
            t = int(m.get("t_ms", m.get("moment_t_ms", m.get("t"))))
            out[t] = m.get("ft_reason")
    elif isinstance(moments, dict):
        for k, v in moments.items():
            if isinstance(v, dict):
                t = int(v.get("t_ms", v.get("moment_t_ms", k)))
                out[t] = v.get("ft_reason")
            else:
                out[int(k)] = None
    else:
        raise SystemExit(f"ft-moments must be a list or moments dict: {path}")
    return out


def load_vote_rows(path: Path) -> List[Dict[str, Any]]:
    doc = _load_json(path)
    if isinstance(doc, list):
        return doc
    rows = doc.get("rows") or doc.get("shots")
    if not isinstance(rows, list):
        raise SystemExit(f"make_miss json must be a list of rows: {path}")
    return rows


def load_rule_calls(path: Path) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for row in load_vote_rows(path):
        out[int(row["moment_t_ms"])] = str(row["call"])
    return out


def moment_is_ft(ft_reason: Optional[str]) -> bool:
    return ft_reason in FT_REASONS


# ---------------------------------------------------------------------------
# train (H4)
# ---------------------------------------------------------------------------


def cmd_train(args: argparse.Namespace) -> int:
    frozen_dir = Path(args.frozen_dir)
    frozen_path = frozen_dir / "frozen.json"
    if not frozen_path.exists():
        raise SystemExit(f"missing {frozen_path}")
    frozen_sha = _sha256_file(frozen_path)

    Xs: List[np.ndarray] = []
    ys: List[np.ndarray] = []
    train_counts: Dict[str, int] = {}
    for film in FILMS:
        labels_doc = _load_json(frozen_dir / f"labels_{film}.json")
        features_doc = _load_json(frozen_dir / f"features_{film}.json")
        X, y, _rows = build_film_xy(labels_doc, features_doc)
        train_counts[film] = int(y.shape[0])
        Xs.append(X)
        ys.append(y)
        print(f"train {film}: rows={train_counts[film]}")

    X_all = np.concatenate(Xs, axis=0)
    y_all = np.concatenate(ys, axis=0)
    pipe = make_pipeline()
    pipe.fit(X_all, y_all)

    # prove pickle-free scoring matches the fitted pipeline
    p_pipe = predict_proba_pipeline(pipe, X_all)
    model = model_dict_from_pipeline(
        pipe, train_counts=train_counts, frozen_json_sha256=frozen_sha
    )
    p_model = predict_proba_from_model(model, X_all)
    max_diff = float(np.max(np.abs(p_pipe - p_model))) if p_pipe.size else 0.0
    if max_diff > 1e-9:
        raise SystemExit(f"model.json scoring mismatch vs pipeline: max_diff={max_diff}")

    out = Path(args.out)
    _write_json(out, model)
    digest = _sha256_file(out)
    print(f"wrote {out} sha256={digest}")
    return 0


# ---------------------------------------------------------------------------
# features (H3)
# ---------------------------------------------------------------------------


def cmd_features(args: argparse.Namespace) -> int:
    """Same call pattern as mm_learned.cmd_features -> build_features_doc."""
    tracks = _load_json(args.tracks_json)
    if not isinstance(tracks, list):
        raise SystemExit("tracks-json must be a list")
    v6 = _load_json(args.v6_results)
    d2 = _load_json(args.d2v1_results)
    fps, read_frame, close = mml.open_video_reader(Path(args.video))
    try:
        doc = mml.build_features_doc(
            tracks,
            fps=fps,
            read_frame=read_frame,
            v6_results=v6,
            d2_results=d2,
        )
    finally:
        close()
    out = Path(args.out)
    _write_json(out, doc)
    print(f"wrote {out} rows={len(doc['rows'])} sha256={_sha256_file(out)}")
    return 0


# ---------------------------------------------------------------------------
# pull (H5)
# ---------------------------------------------------------------------------


def build_pull_rows(
    *,
    vote_rows: Sequence[Dict[str, Any]],
    features_doc: Dict[str, Any],
    session: Dict[str, Any],
    ft_reasons: Dict[int, Optional[str]],
    model: Dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
) -> List[Dict[str, Any]]:
    med = f12_film_median(features_doc)
    names = list(features_doc["feature_names"])
    feat_by_t = {
        int(r["moment_t_ms"]): [float(v) for v in r["features"]]
        for r in features_doc["rows"]
    }
    out: List[Dict[str, Any]] = []
    for row in vote_rows:
        t_ms = int(row["moment_t_ms"])
        rules_call = str(row["call"])
        is_ft = moment_is_ft(ft_reasons.get(t_ms))
        sess = bool(in_session(t_ms, session, is_ft=is_ft))
        p: Optional[float] = None
        if sess and t_ms in feat_by_t:
            x = pull_x_from_features(feat_by_t[t_ms], names, med)
            p = float(predict_proba_from_model(model, np.asarray([x], dtype=float))[0])
        pulled = bool(
            sess and rules_call == "miss" and p is not None and p >= float(threshold)
        )
        out.append(
            {
                "t_ms": t_ms,
                "in_session": sess,
                "rules_call": rules_call,
                "p": p,
                "pulled": pulled,
            }
        )
    return out


def cmd_pull(args: argparse.Namespace) -> int:
    vote_rows = load_vote_rows(Path(args.make_miss))
    features_doc = _load_json(Path(args.features))
    session = _load_json(Path(args.session))
    ft_reasons = load_ft_reasons(Path(args.ft_moments))
    model = _load_json(Path(args.model))
    threshold = float(args.threshold)
    rows = build_pull_rows(
        vote_rows=vote_rows,
        features_doc=features_doc,
        session=session,
        ft_reasons=ft_reasons,
        model=model,
        threshold=threshold,
    )
    out = Path(args.out)
    _write_json(out, rows)
    n_pulled = sum(1 for r in rows if r["pulled"])
    print(f"wrote {out} rows={len(rows)} pulled={n_pulled} sha256={_sha256_file(out)}")
    return 0


# ---------------------------------------------------------------------------
# seen-check (H8) — leave-one-game-out at T 0.70, real shots only
# ---------------------------------------------------------------------------


def seen_check_counts(
    *,
    frozen_dir: Path,
    rules_paths: Dict[str, Path],
    threshold: float = DEFAULT_THRESHOLD,
) -> Dict[str, Dict[str, int]]:
    data: Dict[str, Dict[str, Any]] = {}
    for film in FILMS:
        labels_doc = _load_json(frozen_dir / f"labels_{film}.json")
        features_doc = _load_json(frozen_dir / f"features_{film}.json")
        X, y, label_rows = build_film_xy(labels_doc, features_doc)
        rules = load_rule_calls(rules_paths[film])
        rule_list = [rules[int(r["moment_t_ms"])] for r in label_rows]
        data[film] = {
            "X": X,
            "y": y,
            "label_rows": label_rows,
            "rule": rule_list,
        }

    results: Dict[str, Dict[str, int]] = {}
    for hold in FILMS:
        train_films = [f for f in FILMS if f != hold]
        X_train = np.concatenate([data[g]["X"] for g in train_films], axis=0)
        y_train = np.concatenate([data[g]["y"] for g in train_films], axis=0)
        pipe = make_pipeline()
        pipe.fit(X_train, y_train)
        p = predict_proba_pipeline(pipe, data[hold]["X"])
        # real shots only: matched_tag_t_ms not null, rules miss
        hidden = 0
        pulled = 0
        caught = 0
        for i, row in enumerate(data[hold]["label_rows"]):
            if row.get("matched_tag_t_ms") is None:
                continue
            if data[hold]["rule"][i] != "miss":
                continue
            yi = int(data[hold]["y"][i])
            hidden += yi
            if float(p[i]) >= float(threshold):
                pulled += 1
                caught += yi
        results[hold] = {"hidden": hidden, "pulled": pulled, "caught": caught}
    return results


def cmd_seen_check(args: argparse.Namespace) -> int:
    frozen_dir = Path(args.frozen_dir)
    rules_paths = {
        "adrian": Path(args.rules_adrian),
        "notus": Path(args.rules_notus),
        "gv": Path(args.rules_gv),
    }
    results = seen_check_counts(frozen_dir=frozen_dir, rules_paths=rules_paths)
    ok = True
    for film in FILMS:
        r = results[film]
        exp_pulled, exp_caught = SEEN_EXPECTED[film]
        print(
            f"{film}: hidden {r['hidden']}, pulled {r['pulled']}, caught {r['caught']}"
        )
        if r["pulled"] != exp_pulled or r["caught"] != exp_caught:
            ok = False
            print(
                f"  FAIL expected pulled {exp_pulled} caught {exp_caught}"
            )
    if not ok:
        return 1
    print("seen-check PASS")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hybrid pull (spec 49)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_tr = sub.add_parser("train", help="Fit H4 model on frozen 3-film set")
    p_tr.add_argument("--frozen-dir", type=Path, required=True)
    p_tr.add_argument("--out", type=Path, required=True)
    p_tr.set_defaults(func=cmd_train)

    p_feat = sub.add_parser("features", help="Build features json (H3)")
    p_feat.add_argument("--tracks-json", type=Path, required=True)
    p_feat.add_argument("--video", type=Path, required=True)
    p_feat.add_argument("--v6-results", type=Path, required=True)
    p_feat.add_argument("--d2v1-results", type=Path, required=True)
    p_feat.add_argument("--out", type=Path, required=True)
    p_feat.set_defaults(func=cmd_features)

    p_pull = sub.add_parser("pull", help="Build pull.json (H5)")
    p_pull.add_argument("--make-miss", type=Path, required=True)
    p_pull.add_argument("--features", type=Path, required=True)
    p_pull.add_argument("--session", type=Path, required=True)
    p_pull.add_argument("--ft-moments", type=Path, required=True)
    p_pull.add_argument("--model", type=Path, required=True)
    p_pull.add_argument("--out", type=Path, required=True)
    p_pull.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"pull threshold (default {DEFAULT_THRESHOLD})",
    )
    p_pull.set_defaults(func=cmd_pull)

    p_seen = sub.add_parser("seen-check", help="H8 leave-one-game-out gate")
    p_seen.add_argument("--frozen-dir", type=Path, required=True)
    p_seen.add_argument("--rules-adrian", type=Path, required=True)
    p_seen.add_argument("--rules-notus", type=Path, required=True)
    p_seen.add_argument("--rules-gv", type=Path, required=True)
    p_seen.set_defaults(func=cmd_seen_check)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
