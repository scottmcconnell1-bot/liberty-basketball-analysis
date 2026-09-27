"""Build the Film Tool event calibrator from sidecar tags + nearby AI shots.

This is the transferable learning pass: shot type (2pt/3pt/ft), make/miss,
and keep/drop. It does not retrain YOLO or the ball detector.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from event_calibrator import film_tool_model_path
from film_tool_tags import load_manual_tags
from helpers import normalize_analysis_game_id
from manual_tag_teach import STAT_EVENTTYPES, time_to_ms

ROOT = Path(__file__).resolve().parent
DEFAULT_GAME_ID = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
DEFAULT_DB = ROOT / "film_analysis.db"
Q1_END_MS = 960700


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
        binary = [
            {**{k: row[k] for k in feature_names}, "y": 1.0 if row[label_key] == label else 0.0}
            for row in rows
        ]
        classes[label] = _fit_binary_logit(binary, feature_names)
    return {"features": feature_names, "classes": classes, "min_margin": 0.2}


def _shot_feature_row(event: dict) -> dict:
    details = {}
    try:
        details = json.loads(event.get("details_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
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


def _family_from_ai(event_type: str) -> str:
    et = str(event_type or "").lower()
    if et in {
        "shot",
        "make",
        "miss",
        "made_two",
        "missed_two",
        "made_three",
        "missed_three",
        "made_free_throw",
        "missed_free_throw",
        "free_throw",
    }:
        return "shot"
    if et in {"rebound", "offensive_rebound", "defensive_rebound"}:
        return "rebound"
    return et


def _load_ai_events(db_path: Path, game_id: str) -> list[dict]:
    want = normalize_analysis_game_id(game_id)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, game_id, player, event_type, shot_result, timestamp_ms,
                   details_json, confidence, source_type
            FROM events
            WHERE game_id = ? OR game_id LIKE ?
            ORDER BY timestamp_ms
            """,
            (want, want + "%"),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        item = dict(row)
        if item.get("source_type") == "manual":
            continue
        out.append(item)
    return out


def _nearest(events: list[dict], ts: int, family: str, tolerance_ms: int) -> dict | None:
    best = None
    best_dt = None
    for event in events:
        if _family_from_ai(event.get("event_type")) != family:
            continue
        dt = abs(int(event.get("timestamp_ms") or 0) - ts)
        if dt > tolerance_ms:
            continue
        if best_dt is None or dt < best_dt:
            best = event
            best_dt = dt
    return best


def build_film_tool_calibrator(
    game_id: str,
    db_path: Path | None = None,
    tolerance_ms: int = 10000,
    window_end_ms: int = Q1_END_MS,
) -> dict:
    payload = load_manual_tags(game_id)
    if not payload:
        raise FileNotFoundError(f"No Film Tool sidecar for {game_id}")
    rows = [r for r in (payload.get("rows") or []) if isinstance(r, dict)]
    manual = []
    for row in rows:
        et = str(row.get("eventtype") or "").strip()
        if et not in STAT_EVENTTYPES:
            continue
        ts = time_to_ms(row.get("start"))
        if ts > window_end_ms:
            continue
        manual.append({**row, "eventtype": et, "_ts": ts})
    if not manual:
        raise ValueError("No stat tags in the taught window")

    ai_events = _load_ai_events(db_path or DEFAULT_DB, game_id)
    ai_window = [e for e in ai_events if int(e.get("timestamp_ms") or 0) <= window_end_ms]

    shot_anchors = []
    shot_train = []
    seen_train = set()
    for row in manual:
        if row["eventtype"] not in {"2PT", "3PT", "FT"}:
            continue
        shot_type = {"2PT": "2pt", "3PT": "3pt", "FT": "ft"}[row["eventtype"]]
        shot_result = "make" if str(row.get("result") or "") == "Make" else "miss"
        raw = _nearest(ai_window, row["_ts"], "shot", tolerance_ms)
        center = int(raw.get("timestamp_ms") or row["_ts"]) if raw else row["_ts"]
        dt = abs(center - row["_ts"]) if raw else 0
        shot_anchors.append(
            {
                "family": "shot",
                "center_ms": center,
                "radius_ms": max(4000, dt + 2500),
                "shot_type": shot_type,
                "shot_result": shot_result,
                "manual_ts_ms": row["_ts"],
            }
        )
        if not raw:
            continue
        feats = _shot_feature_row(raw)
        key = (
            round(feats["lat"], 1),
            round(feats["rise"], 1),
            shot_type,
            shot_result,
        )
        if key in seen_train:
            continue
        seen_train.add(key)
        shot_train.append({**feats, "label": shot_type, "y_make": 1.0 if shot_result == "make" else 0.0})

    shot_type_clf = _fit_multiclass_ovr(
        shot_train,
        ["lat", "rise", "secondary", "conf", "ai_make"],
        ["2pt", "3pt", "ft"],
    )
    make_rows = [
        {**{k: r[k] for k in ["lat", "rise", "secondary", "conf", "ai_make"]}, "y": r["y_make"]}
        for r in shot_train
    ]
    make_miss_clf = _fit_binary_logit(make_rows, ["lat", "rise", "secondary", "conf", "ai_make"])
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

    positive_windows = []
    supervised_templates = []
    for row in manual:
        et = row["eventtype"]
        ts = row["_ts"]
        key = f"{et}|{row.get('result') or 'NA'}"
        family = _coarse_family(et)
        positive_windows.append(
            {
                "center_ms": ts,
                "radius_ms": tolerance_ms,
                "family": family,
                "manual_key": key,
            }
        )
        template = {
            "timestamp_ms": ts,
            "radius_ms": tolerance_ms,
            "match_key": key,
            "player": str(row.get("player") or "Unknown"),
            "team": str(row.get("team") or ""),
            "confidence": 0.58,
        }
        if et in {"2PT", "3PT", "FT"}:
            template["event_type"] = "shot"
            template["shot_type"] = {"2PT": "2pt", "3PT": "3pt", "FT": "ft"}[et]
            template["shot_result"] = "make" if str(row.get("result") or "") == "Make" else "miss"
        elif et in {"OffRebound", "DefRebound"}:
            template["event_type"] = "rebound"
            template["rebound_type"] = "offensive" if et == "OffRebound" else "defensive"
        elif et == "Assist":
            template["event_type"] = "assist"
        elif et == "Steal":
            template["event_type"] = "steal"
        elif et == "Turnover":
            template["event_type"] = "turnover"
        elif et == "Foul":
            template["event_type"] = "foul"
            template["confidence"] = 0.55
        elif et == "Block":
            template["event_type"] = "block"
        else:
            continue
        supervised_templates.append(template)

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

    for event in ai_window:
        ts = int(event.get("timestamp_ms") or 0)
        family = _family_from_ai(event.get("event_type"))
        details = {}
        try:
            details = json.loads(event.get("details_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        near = any(
            w["family"] == family and abs(ts - w["center_ms"]) <= tolerance_ms
            for w in positive_windows
        )
        keep_rows.append(
            {
                "conf": float(event.get("confidence") or 0.5),
                "is_shot": 1.0 if family == "shot" else 0.0,
                "is_rebound": 1.0 if family == "rebound" else 0.0,
                "is_steal": 1.0 if family == "steal" else 0.0,
                "is_turnover": 1.0 if family == "turnover" else 0.0,
                "is_assist": 1.0 if family == "assist" else 0.0,
                "lat_norm": min(float(details.get("lateral_travel") or 0.0) / 800.0, 3.0),
                "rise_norm": min(float(details.get("ball_rise") or 0.0) / 400.0, 3.0),
                "secondary": 1.0 if details.get("secondary_pass") else 0.0,
                "local_density": _density(ts),
                "y": 1.0 if near else 0.0,
            }
        )
    keep_clf = _fit_binary_logit(keep_rows, feature_names, l2=0.5, steps=500, lr=0.2)
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

    type_counts = defaultdict(int)
    for row in manual:
        type_counts[row["eventtype"]] += 1

    return {
        "version": 1,
        "source": "teach_from_film_tags",
        "analysis_key": normalize_analysis_game_id(game_id),
        "match_tolerance_ms": tolerance_ms,
        "clock_offset_ms": 0,
        "window_end_ms": window_end_ms,
        "shot_label_anchors": shot_anchors,
        "positive_windows": positive_windows,
        "shot_type_clf": shot_type_clf,
        "make_miss_clf": make_miss_clf,
        "keep_clf": keep_clf,
        "fp_suppress": {
            "orphan_steal_to": True,
            "orphan_steal_to_max_shot_gap_ms": 6000,
            "require_shot_positive_window": True,
            "drop_unanchored_shot_misses": True,
            "require_steal_to_positive_window": True,
            "cap_shots_to_manual_windows": True,
        },
        "supervised_templates": supervised_templates,
        "learned_event_min_confidence": {
            "shot": 0.48,
            "make": 0.40,
            "miss": 0.40,
            "rebound": 0.52,
            "block": 0.95,
            "assist": 0.40,
            "steal": 0.48,
            "turnover": 0.48,
            "foul": 0.55,
        },
        "train_snapshot": {
            "manual_tags": len(manual),
            "ai_window": len(ai_window),
            "shot_anchors": len(shot_anchors),
            "shot_train_rows": len(shot_train),
            "keep_train_rows": len(keep_rows),
            "keep_train_f1": keep_clf.get("train_f1"),
            "make_train_accuracy": make_miss_clf.get("train_accuracy"),
            "manual_type_counts": dict(type_counts),
        },
    }


def write_film_tool_calibrator(model: dict, path: Path | None = None) -> Path:
    game_id = str((model or {}).get("analysis_key") or DEFAULT_GAME_ID)
    out = Path(path) if path else film_tool_model_path(game_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return out


def rebuild_film_tool_calibrator(game_id: str, db_path: Path | None = None) -> dict:
    model = build_film_tool_calibrator(game_id, db_path=db_path)
    write_film_tool_calibrator(model)
    from event_calibrator import clear_calibrator_cache

    clear_calibrator_cache()
    return model.get("train_snapshot") or {}
