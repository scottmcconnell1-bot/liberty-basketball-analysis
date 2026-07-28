#!/usr/bin/env python3
"""Teach / calibrate AI events from Hoopsalytics PBP ground truth (multi-game).

Builds models/hoopsalytics_event_calibrator.json from AI↔PBP matches across
every imported Hoopsalytics game that already has AI events:

  - shot label anchors (per-game timestamps)
  - positive windows + supervised templates (per-game)
  - transferable keep / shot-type / make-miss classifiers
  - data-driven confidence floors + FP suppress rules

Also copies transferable pieces into models/manual_q1_event_calibrator.json
(with scope=multi_game) so postprocess_ai_events picks them up.

Usage:
  py -3.12 scripts/teach_from_hoops_pbp.py
  py -3.12 scripts/teach_from_hoops_pbp.py --write-model
  py -3.12 scripts/teach_from_hoops_pbp.py --write-model --end-ms 980000
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tag-exports"))

from event_calibrator import DEFAULT_MODEL_PATH, clear_calibrator_cache  # noqa: E402
from manual_vs_ai_q1_compare import (  # noqa: E402
    STAT_EVENTTYPES,
    convert_ai_events_to_stat_rows,
    event_level_match,
    match_key,
    time_to_seconds,
)

# Sibling scripts (not a package)
sys.path.insert(0, str(ROOT / "scripts"))
from compare_ai_to_hoops_pbp import load_ai_events, load_truth_rows  # noqa: E402
from teach_from_manual_q1 import (  # noqa: E402
    _coarse_family,
    _fit_binary_logit,
    _fit_multiclass_ovr,
    _sigmoid,
)

HOOPS_MODEL_PATH = ROOT / "models" / "hoopsalytics_event_calibrator.json"
DB_PATH = ROOT / "film_analysis.db"

# video_id, film_tool client id, analysis/game_id
HOOPS_GAMES = [
    (17, "hoopsalytics-marsing-2025-12-02", "hoopsalytics_marsing_2025-12-02"),
    (16, "hoopsalytics-nyssa-2025-12-04", "hoopsalytics_nyssa_2025-12-04"),
    (15, "hoopsalytics-harper_or-2025-12-05", "hoopsalytics_harper_or_2025-12-05"),
    (13, "hoopsalytics-burns_or-2025-12-06", "hoopsalytics_burns_or_2025-12-06"),
    (12, "hoopsalytics-melba-2025-12-09", "hoopsalytics_melba_2025-12-09"),
    (14, "hoopsalytics-camas_county-2025-12-13", "hoopsalytics_camas_county_2025-12-13"),
    (20, "hoopsalytics-idaho_city-2026-01-05", "hoopsalytics_idaho_city_2026-01-05"),
    (18, "hoopsalytics-north_star_charter-2026-01-08", "hoopsalytics_north_star_charter_2026-01-08"),
    (19, "hoopsalytics-grace-2026-01-10", "hoopsalytics_grace_2026-01-10"),
]


def base_analysis_key(game_id: str) -> str:
    text = str(game_id or "")
    if "__rerun_" in text:
        return text.split("__rerun_", 1)[0]
    return text


def _shot_feature_row(raw: dict) -> dict:
    details = {}
    try:
        details = json.loads(raw.get("details_json") or "{}")
    except Exception:
        details = {}
    return {
        "lat": float(details.get("lateral_travel") or 0.0),
        "rise": float(details.get("ball_rise") or 0.0),
        "secondary": 1.0 if details.get("secondary_pass") else 0.0,
        "conf": float(raw.get("confidence") or 0.0),
        "ai_make": 1.0 if str(raw.get("shot_result") or "").lower() == "make" else 0.0,
    }


def _discover_ai_keys(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Map base hoops game_id → analysis keys that have AI events."""
    rows = conn.execute(
        """SELECT DISTINCT game_id FROM events
           WHERE game_id LIKE 'hoopsalytics%'
             AND COALESCE(source_type, 'ai') = 'ai'"""
    ).fetchall()
    out: dict[str, list[str]] = defaultdict(list)
    for (gid,) in rows:
        out[base_analysis_key(gid)].append(gid)
    return out


def _filter_truth(rows: list[dict], end_ms: int | None) -> list[dict]:
    out = []
    for row in rows:
        if str(row.get("eventtype") or "") not in STAT_EVENTTYPES:
            continue
        sec = time_to_seconds(row.get("start"))
        ms = int(round(sec * 1000))
        if end_ms is not None and not (0 <= ms <= end_ms):
            continue
        out.append(row)
    return out


def _filter_ai(events: list[dict], end_ms: int | None) -> list[dict]:
    out = []
    for event in events:
        if (event.get("source_type") or "ai") != "ai":
            continue
        ts = int(event.get("timestamp_ms") or 0)
        if end_ms is not None and not (0 <= ts <= end_ms):
            continue
        out.append(event)
    return out


def build_multi_game_calibrator(
    db_path: Path,
    *,
    tolerance_ms: int = 10000,
    end_ms: int | None = None,
    games: list[tuple[int, str, str]] | None = None,
) -> dict:
    conn = sqlite3.connect(str(db_path))
    ai_by_base = _discover_ai_keys(conn)

    shot_anchors: list[dict] = []
    positive_windows: list[dict] = []
    supervised_templates: list[dict] = []
    shot_train: list[dict] = []
    keep_rows: list[dict] = []
    type_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0})
    per_game: list[dict] = []

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

    for video_id, film_id, base_key in games or HOOPS_GAMES:
        keys = ai_by_base.get(base_key) or []
        if not keys:
            continue
        # Prefer primary key if present.
        analysis_key = base_key if base_key in keys else sorted(keys)[-1]
        try:
            truth = _filter_truth(load_truth_rows(conn, film_id), end_ms)
        except SystemExit:
            continue
        ai_raw = _filter_ai(load_ai_events(conn, analysis_key), end_ms)
        if not truth or not ai_raw:
            continue

        ai_rows = convert_ai_events_to_stat_rows(ai_raw, team_name="Liberty")
        ai_rows = [r for r in ai_rows if r.get("eventtype") in STAT_EVENTTYPES]
        matches, extras, misses, disagreements = event_level_match(
            truth, ai_rows, tolerance_ms=tolerance_ms
        )
        by_id = {e["id"]: e for e in ai_raw if e.get("id") is not None}

        game_windows: list[dict] = []
        for m in truth:
            ts = int(round(time_to_seconds(m.get("start")) * 1000))
            et = str(m.get("eventtype") or "")
            key = match_key(m)
            win = {
                "game_id": base_key,
                "center_ms": ts,
                "radius_ms": tolerance_ms,
                "family": _coarse_family(et),
                "manual_key": key,
            }
            game_windows.append(win)
            positive_windows.append(win)

            template = {
                "game_id": base_key,
                "timestamp_ms": ts,
                "radius_ms": tolerance_ms,
                "match_key": key,
                "player": str(m.get("player") or "Unknown"),
                "team": str(m.get("team") or "Liberty"),
                "confidence": 0.58,
            }
            if et in {"2PT", "3PT", "FT"}:
                template["event_type"] = "shot"
                template["shot_type"] = {"2PT": "2pt", "3PT": "3pt", "FT": "ft"}[et]
                result = str(m.get("result") or "Miss").lower()
                template["shot_result"] = "make" if result == "make" else "miss"
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

        def _density(ts: int) -> float:
            return float(sum(1 for w in game_windows if abs(ts - w["center_ms"]) <= 12000))

        def _keep_feats(row: dict, raw: dict | None, y: float) -> dict:
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
                    "game_id": base_key,
                    "family": "shot",
                    "center_ms": center,
                    "radius_ms": max(4000, int(pair.get("dt_ms") or 0) + 2500),
                    "shot_type": shot_type,
                    "shot_result": shot_result,
                    "manual_ts_ms": int(round(time_to_seconds(manual.get("start")) * 1000)),
                }
            )
            feats = _shot_feature_row(raw)
            shot_train.append(
                {**feats, "label": shot_type, "y_make": 1.0 if shot_result == "make" else 0.0}
            )

        for pair in matches:
            raw = by_id.get(pair["ai"].get("source_event_id"))
            keep_rows.append(_keep_feats(pair["ai"], raw, 1.0))
            type_stats[match_key(pair["ai"])]["tp"] += 1
        for d in disagreements:
            raw = by_id.get(d["ai"].get("source_event_id"))
            keep_rows.append(_keep_feats(d["ai"], raw, 1.0))
            type_stats[match_key(d["ai"])]["tp"] += 1
        for extra in extras:
            raw = by_id.get(extra.get("source_event_id"))
            keep_rows.append(_keep_feats(extra, raw, 0.0))
            type_stats[match_key(extra)]["fp"] += 1

        per_game.append(
            {
                "video_id": video_id,
                "film_id": film_id,
                "analysis_key": analysis_key,
                "base_key": base_key,
                "truth": len(truth),
                "ai": len(ai_rows),
                "exact": len(matches),
                "disagree": len(disagreements),
                "miss": len(misses),
                "extra": len(extras),
            }
        )

    conn.close()

    if not keep_rows:
        raise SystemExit("No Hoopsalytics games with AI events + PBP truth found to teach from.")

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
    reb = type_stats.get("Rebound", {"tp": 0, "fp": 0})
    if reb["fp"] > max(reb["tp"] * 3, 1):
        event_min_confidence["rebound"] = 0.58
    st = type_stats.get("Steal", {"tp": 0, "fp": 0})
    if st["fp"] > max(st["tp"] * 3, 1):
        event_min_confidence["steal"] = 0.55
    to = type_stats.get("Turnover", {"tp": 0, "fp": 0})
    if to["fp"] > max(to["tp"] * 3, 1):
        event_min_confidence["turnover"] = 0.55
    # Extra aggressive floors when FP dominates (Grace Q1 pattern).
    for key, floor_key, bump in [
        ("2PT|Make", "shot", 0.55),
        ("2PT|Miss", "shot", 0.52),
        ("Assist", "assist", 0.50),
        ("Foul", "foul", 0.60),
    ]:
        stats = type_stats.get(key, {"tp": 0, "fp": 0})
        if stats["fp"] > max(stats["tp"] * 2, 2):
            event_min_confidence[floor_key] = max(
                event_min_confidence.get(floor_key, 0.4), bump
            )

    model = {
        "version": 3,
        "source": "teach_from_hoops_pbp",
        "scope": "multi_game",
        "analysis_key": None,
        "match_tolerance_ms": tolerance_ms,
        "window_end_ms": end_ms,
        "clock_offset_ms": 0,
        "shot_label_anchors": shot_anchors,
        "positive_windows": positive_windows,
        "shot_type_clf": shot_type_clf,
        "make_miss_clf": make_miss_clf,
        "keep_clf": keep_clf,
        "fp_suppress": {
            "orphan_steal_to": True,
            "orphan_steal_to_max_shot_gap_ms": 6000,
            # Only enforce when this game has PBP windows (filtered at apply time).
            "require_shot_positive_window": True,
            "drop_unanchored_shot_misses": True,
            "require_steal_to_positive_window": True,
            "cap_shots_to_manual_windows": True,
        },
        "supervised_templates": supervised_templates,
        "learned_event_min_confidence": event_min_confidence,
        "train_snapshot": {
            "games": per_game,
            "shot_anchors": len(shot_anchors),
            "shot_train_rows": len(shot_train),
            "keep_train_rows": len(keep_rows),
            "supervised_templates": len(supervised_templates),
            "keep_train_f1": keep_clf.get("train_f1"),
            "make_train_accuracy": make_miss_clf.get("train_accuracy"),
            "type_stats": {k: dict(v) for k, v in sorted(type_stats.items())},
        },
    }
    return model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--tolerance-ms", type=int, default=10000)
    ap.add_argument("--end-ms", type=int, default=None, help="Optional shared window end (ms)")
    ap.add_argument("--write-model", action="store_true")
    args = ap.parse_args(argv)

    model = build_multi_game_calibrator(
        args.db,
        tolerance_ms=args.tolerance_ms,
        end_ms=args.end_ms,
    )
    snap = model["train_snapshot"]
    print("=" * 60)
    print("Hoopsalytics PBP multi-game teach")
    print("=" * 60)
    for g in snap["games"]:
        print(
            f"  {g['base_key']}: truth={g['truth']} ai={g['ai']} "
            f"exact={g['exact']} miss={g['miss']} extra={g['extra']}"
        )
    print(f"keep_train_rows={snap['keep_train_rows']}  keep_f1={snap['keep_train_f1']}")
    print(f"shot_train_rows={snap['shot_train_rows']}  make_acc={snap['make_train_accuracy']}")
    print(f"templates={snap['supervised_templates']}  anchors={snap['shot_anchors']}")

    if args.write_model:
        HOOPS_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        HOOPS_MODEL_PATH.write_text(json.dumps(model, indent=2), encoding="utf-8")
        # Install as active postprocess calibrator (multi_game scope).
        DEFAULT_MODEL_PATH.write_text(json.dumps(model, indent=2), encoding="utf-8")
        clear_calibrator_cache()
        print(f"\nWrote {HOOPS_MODEL_PATH}")
        print(f"Wrote {DEFAULT_MODEL_PATH} (active)")
    else:
        print("\nDry run only. Pass --write-model to install calibrator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
