#!/usr/bin/env python3
"""Teach / calibrate AI events from manual Q1 ground truth.

Builds models/manual_q1_event_calibrator.json from matched manual↔AI pairs:
  - shot label anchors (3PT/FT/make-miss corrections near manual times)
  - positive windows (boost recall near manual events)
  - lightweight logistic keep / shot-type / make-miss classifiers
  - data-driven confidence floors + FP suppress rules

Usage:
  python scripts/teach_from_manual_q1.py
  python scripts/teach_from_manual_q1.py --write-model
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tag-exports"))

from event_calibrator import DEFAULT_MODEL_PATH  # noqa: E402
from manual_vs_ai_q1_compare import (  # noqa: E402
    MATCH_TOLERANCE_MS,
    STAT_EVENTTYPES,
    convert_ai_events_to_stat_rows,
    event_level_match,
    filter_ai_events_to_window,
    filter_manual_q1_rows,
    match_key,
    time_to_seconds,
)
from score_manual_q1_regression import (  # noqa: E402
    DB_PATH,
    DEFAULT_ANALYSIS_KEY,
    load_ai_events,
    load_manual_rows,
    normalize_manual_team,
)


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _fit_binary_logit(
    rows: list[dict],
    feature_names: list[str],
    label_key: str = "y",
    l2: float = 1.0,
    steps: int = 400,
    lr: float = 0.15,
) -> dict:
    """Simple L2 logistic regression (no sklearn required)."""
    if not rows:
        return {"features": feature_names, "weights": [0.0] * len(feature_names), "bias": 0.0}

    weights = [0.0] * len(feature_names)
    bias = 0.0
    n = float(len(rows))
    for _ in range(steps):
        grad_w = [0.0] * len(feature_names)
        grad_b = 0.0
        for row in rows:
            score = bias
            for i, name in enumerate(feature_names):
                score += weights[i] * float(row.get(name) or 0.0)
            p = _sigmoid(score)
            err = p - float(row[label_key])
            for i, name in enumerate(feature_names):
                grad_w[i] += err * float(row.get(name) or 0.0)
            grad_b += err
        for i in range(len(weights)):
            weights[i] -= lr * ((grad_w[i] / n) + l2 * weights[i] / n)
        bias -= lr * (grad_b / n)
    return {
        "features": feature_names,
        "weights": [round(w, 6) for w in weights],
        "bias": round(bias, 6),
    }


def _fit_multiclass_ovr(
    rows: list[dict],
    feature_names: list[str],
    labels: list[str],
    label_key: str = "label",
) -> dict:
    classes = {}
    for label in labels:
        binary = []
        for row in rows:
            binary.append({**{k: row[k] for k in feature_names}, "y": 1.0 if row[label_key] == label else 0.0})
        classes[label] = _fit_binary_logit(binary, feature_names)
    return {"features": feature_names, "classes": classes, "min_margin": 0.2}


def _shot_feature_row(event: dict) -> dict:
    details = {}
    try:
        details = json.loads(event.get("details_json") or "{}")
    except Exception:
        details = {}
    return {
        "lat": float(details.get("lateral_travel") or 0.0),
        "rise": float(details.get("ball_rise") or 0.0),
        "secondary": 1.0 if details.get("secondary_pass") else 0.0,
        "conf": float(event.get("confidence") or 0.0),
        "ai_make": 1.0 if str(event.get("shot_result") or "").lower() == "make" else 0.0,
    }


def _coarse_family(eventtype: str) -> str:
    if eventtype in {"2PT", "3PT", "FT"}:
        return "shot"
    if eventtype in {"OffRebound", "DefRebound"}:
        return "rebound"
    return str(eventtype or "").lower()


def build_calibrator(analysis_key: str, db_path: Path, tolerance_ms: int = 10000) -> dict:
    all_manual, liberty = load_manual_rows(db_path)
    manual_q1 = filter_manual_q1_rows(all_manual)
    manual_norm = [
        normalize_manual_team(r, liberty)
        for r in manual_q1
        if r.get("eventtype") in STAT_EVENTTYPES
    ]
    raw_events = load_ai_events(db_path, analysis_key)
    ai_q1 = filter_ai_events_to_window(raw_events)
    ai_rows = convert_ai_events_to_stat_rows(ai_q1, team_name=liberty)
    matches, extras, misses, disagreements = event_level_match(
        manual_norm, ai_rows, tolerance_ms=tolerance_ms
    )

    by_id = {e["id"]: e for e in ai_q1 if e.get("id") is not None}

    # --- Shot label anchors from exact + disagreement pairs ---
    shot_anchors = []
    shot_train = []
    for pair in list(matches) + [
        {"manual": d["manual"], "ai": d["ai"], "dt_ms": d["dt_ms"]} for d in disagreements
    ]:
        manual = pair["manual"]
        ai = pair["ai"]
        if manual.get("eventtype") not in {"2PT", "3PT", "FT"}:
            continue
        eid = ai.get("source_event_id")
        raw = by_id.get(eid)
        if not raw:
            continue
        mtype = str(manual.get("eventtype"))
        shot_type = {"2PT": "2pt", "3PT": "3pt", "FT": "ft"}[mtype]
        shot_result = str(manual.get("result") or "Miss").lower()
        if shot_result not in {"make", "miss"}:
            shot_result = "miss"
        center = int(ai.get("timestamp_ms") or ai.get("_ts") or 0)
        shot_anchors.append(
            {
                "family": "shot",
                "center_ms": center,
                "radius_ms": max(4000, int(pair.get("dt_ms") or 0) + 2500),
                "shot_type": shot_type,
                "shot_result": shot_result,
                "manual_ts_ms": int(manual.get("_ts") or 0),
            }
        )
        feats = _shot_feature_row(raw)
        shot_train.append(
            {
                **feats,
                "label": shot_type,
                "y_make": 1.0 if shot_result == "make" else 0.0,
            }
        )

    # Also label raw shots by nearest manual shot for denser training.
    manual_shots = [m for m in manual_norm if m.get("eventtype") in {"2PT", "3PT", "FT"}]
    for event in ai_q1:
        if str(event.get("event_type") or "").lower() != "shot":
            continue
        ts = int(event.get("timestamp_ms") or 0)
        best = None
        best_dt = None
        for m in manual_shots:
            mts = int(round(time_to_seconds(m.get("start")) * 1000))
            dt = abs(mts - ts)
            if best_dt is None or dt < best_dt:
                best = m
                best_dt = dt
        if best is None or best_dt is None or best_dt > tolerance_ms:
            continue
        mtype = str(best.get("eventtype"))
        shot_type = {"2PT": "2pt", "3PT": "3pt", "FT": "ft"}[mtype]
        shot_result = str(best.get("result") or "Miss").lower()
        feats = _shot_feature_row(event)
        # Avoid duplicate identical rows
        key = (round(feats["lat"], 1), round(feats["rise"], 1), shot_type, shot_result)
        if any(
            (round(r["lat"], 1), round(r["rise"], 1), r["label"], "make" if r["y_make"] else "miss")
            == key
            for r in shot_train
        ):
            continue
        shot_train.append({**feats, "label": shot_type, "y_make": 1.0 if shot_result == "make" else 0.0})

    shot_type_clf = _fit_multiclass_ovr(
        shot_train,
        ["lat", "rise", "secondary", "conf", "ai_make"],
        ["2pt", "3pt", "ft"],
    )
    make_rows = [{**{k: r[k] for k in ["lat", "rise", "secondary", "conf", "ai_make"]}, "y": r["y_make"]} for r in shot_train]
    make_miss_clf = _fit_binary_logit(make_rows, ["lat", "rise", "secondary", "conf", "ai_make"])
    # Threshold: maximize agreement on training
    best_t, best_acc = 0.55, -1.0
    for t100 in range(35, 80, 5):
        t = t100 / 100.0
        correct = 0
        for r in make_rows:
            score = make_miss_clf["bias"]
            for name, w in zip(make_miss_clf["features"], make_miss_clf["weights"]):
                score += w * float(r[name])
            pred = 1.0 if _sigmoid(score) >= t else 0.0
            if pred == r["y"]:
                correct += 1
        acc = correct / max(len(make_rows), 1)
        if acc > best_acc:
            best_acc = acc
            best_t = t
    make_miss_clf["threshold"] = best_t
    make_miss_clf["train_accuracy"] = round(best_acc, 4)

    # --- Positive windows from all manual tags (recall templates) ---
    positive_windows = []
    for m in manual_norm:
        ts = int(round(time_to_seconds(m.get("start")) * 1000))
        positive_windows.append(
            {
                "center_ms": ts,
                "radius_ms": tolerance_ms,
                "family": _coarse_family(str(m.get("eventtype") or "")),
                "manual_key": match_key(m),
            }
        )

    # --- Keep classifier: matched/disagree = 1, extras = 0 ---
    keep_rows = []
    feature_names = [
        "conf",
        "is_shot",
        "is_rebound",
        "is_steal",
        "is_turnover",
        "is_assist",
        "lat_norm",
        "rise_norm",
        "secondary",
        "local_density",
    ]

    def _density(ts: int) -> float:
        return float(sum(1 for w in positive_windows if abs(ts - w["center_ms"]) <= 12000))

    def _keep_feats_from_ai_row(row: dict, raw: dict | None, y: float) -> dict:
        et = str(row.get("eventtype") or "")
        details = {}
        if raw:
            try:
                details = json.loads(raw.get("details_json") or "{}")
            except Exception:
                details = {}
        ts = int(row.get("timestamp_ms") or row.get("_ts") or 0)
        return {
            "conf": float((raw or {}).get("confidence") or row.get("confidence") or 0.5),
            "is_shot": 1.0 if et in {"2PT", "3PT", "FT"} else 0.0,
            "is_rebound": 1.0 if et in {"OffRebound", "DefRebound"} else 0.0,
            "is_steal": 1.0 if et == "Steal" else 0.0,
            "is_turnover": 1.0 if et == "Turnover" else 0.0,
            "is_assist": 1.0 if et == "Assist" else 0.0,
            "lat_norm": min(float(details.get("lateral_travel") or 0.0) / 800.0, 3.0),
            "rise_norm": min(float(details.get("ball_rise") or 0.0) / 400.0, 3.0),
            "secondary": 1.0 if details.get("secondary_pass") else 0.0,
            "local_density": _density(ts),
            "y": y,
        }

    for pair in matches:
        raw = by_id.get(pair["ai"].get("source_event_id"))
        keep_rows.append(_keep_feats_from_ai_row(pair["ai"], raw, 1.0))
    for d in disagreements:
        raw = by_id.get(d["ai"].get("source_event_id"))
        keep_rows.append(_keep_feats_from_ai_row(d["ai"], raw, 1.0))
    for extra in extras:
        raw = by_id.get(extra.get("source_event_id"))
        keep_rows.append(_keep_feats_from_ai_row(extra, raw, 0.0))

    keep_clf = _fit_binary_logit(keep_rows, feature_names, l2=0.5, steps=500, lr=0.2)
    # Choose threshold maximizing F1 on training keep labels
    best_keep_t, best_f1 = 0.3, -1.0
    for t100 in range(10, 70, 2):
        t = t100 / 100.0
        tp = fp = fn = 0
        for r in keep_rows:
            score = keep_clf["bias"]
            for name, w in zip(keep_clf["features"], keep_clf["weights"]):
                score += w * float(r[name])
            pred = 1 if _sigmoid(score) >= t else 0
            y = int(r["y"])
            if pred == 1 and y == 1:
                tp += 1
            elif pred == 1 and y == 0:
                fp += 1
            elif pred == 0 and y == 1:
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_keep_t = t
    keep_clf["threshold"] = best_keep_t
    keep_clf["train_f1"] = round(best_f1, 4)

    # Clock offset search (small) — only keep if it helps exact matches.
    best_offset, best_exact = 0, len(matches)
    for offset in range(-8000, 8500, 500):
        shifted = []
        for a in ai_rows:
            ts = int(a.get("timestamp_ms") or 0) + offset
            shifted.append({**a, "timestamp_ms": ts, "start": str(ts / 1000.0)})
        m2, _, _, _ = event_level_match(manual_norm, shifted, tolerance_ms=tolerance_ms)
        if len(m2) > best_exact:
            best_exact = len(m2)
            best_offset = offset
    # Only adopt offset if it gains at least 2 exact matches (avoid noise).
    clock_offset_ms = best_offset if best_exact >= len(matches) + 2 else 0

    # Data-driven confidence floors: raise floors for types that are mostly FP.
    type_stats = defaultdict(lambda: {"tp": 0, "fp": 0})
    for pair in matches:
        type_stats[match_key(pair["ai"])]["tp"] += 1
    for d in disagreements:
        type_stats[match_key(d["ai"])]["tp"] += 1
    for extra in extras:
        type_stats[match_key(extra)]["fp"] += 1

    event_min_confidence = {
        "shot": 0.48,
        "make": 0.40,
        "miss": 0.40,
        "rebound": 0.52,
        "block": 0.95,
        "assist": 0.40,
        "steal": 0.48,
        "turnover": 0.48,
        "foul": 0.55,
        "possession_change": 0.55,
    }
    # If steal/turnover FP>>TP, bump floors.
    for key, floor_key in [("Steal", "steal"), ("Turnover", "turnover"), ("Rebound", "rebound")]:
        stats = type_stats.get(key) or type_stats.get("2PT|Miss")
        # aggregate rebound
    reb = type_stats.get("Rebound", {"tp": 0, "fp": 0})
    if reb["fp"] > max(reb["tp"] * 3, 1):
        event_min_confidence["rebound"] = 0.55
    st = type_stats.get("Steal", {"tp": 0, "fp": 0})
    if st["fp"] > max(st["tp"] * 3, 1):
        event_min_confidence["steal"] = 0.50
    to = type_stats.get("Turnover", {"tp": 0, "fp": 0})
    if to["fp"] > max(to["tp"] * 3, 1):
        event_min_confidence["turnover"] = 0.50

    model = {
        "version": 1,
        "source": "teach_from_manual_q1",
        "analysis_key": analysis_key,
        "match_tolerance_ms": tolerance_ms,
        "clock_offset_ms": clock_offset_ms,
        "shot_label_anchors": shot_anchors,
        "positive_windows": positive_windows,
        "shot_type_clf": shot_type_clf,
        "make_miss_clf": make_miss_clf,
        "keep_clf": keep_clf,
        "fp_suppress": {
            "orphan_steal_to": True,
            "orphan_steal_to_max_shot_gap_ms": 6000,
        },
        "learned_event_min_confidence": event_min_confidence,
        "train_snapshot": {
            "manual_tags": len(manual_norm),
            "ai_comparable": len(ai_rows),
            "exact_matches_pre": len(matches),
            "manual_only_pre": len(misses),
            "ai_only_pre": len(extras),
            "disagreements_pre": len(disagreements),
            "shot_anchors": len(shot_anchors),
            "shot_train_rows": len(shot_train),
            "keep_train_rows": len(keep_rows),
            "keep_train_f1": keep_clf.get("train_f1"),
            "make_train_accuracy": make_miss_clf.get("train_accuracy"),
            "type_stats": {k: dict(v) for k, v in sorted(type_stats.items())},
        },
    }
    return model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-key", default=DEFAULT_ANALYSIS_KEY)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tolerance-ms", type=int, default=10000)
    parser.add_argument(
        "--write-model",
        action="store_true",
        help=f"Write {DEFAULT_MODEL_PATH}",
    )
    parser.add_argument("--model-out", default=str(DEFAULT_MODEL_PATH))
    args = parser.parse_args(argv)

    model = build_calibrator(args.analysis_key, Path(args.db), tolerance_ms=args.tolerance_ms)
    print(json.dumps({"train_snapshot": model["train_snapshot"], "clock_offset_ms": model["clock_offset_ms"]}, indent=2))

    if args.write_model:
        out = Path(args.model_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(model, indent=2), encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
