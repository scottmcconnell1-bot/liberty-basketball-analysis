#!/usr/bin/env python3
"""Accuracy benchmark: score the event generator against coach-tagged ground truth.

No GPU, OpenCV/YOLO or LFS needed, so it runs in CI on every PR. Each fixture under
benchmarks/accuracy/<name>/ holds frozen detections from a real analyzer run
(detections.csv.gz, made by scripts/bench/build_accuracy_fixture.py) and the
coach's Film Tool tags for the same film (truth.json). This script loads the
detections into a throwaway DB, runs the current event generator, and matches its
events to the tags by type and time (±10 s, the same matcher as
tag-exports/manual_vs_ai_q1_compare.py).

  python scripts/accuracy_benchmark.py              # print metrics, fail on regression
  python scripts/accuracy_benchmark.py --update-baseline   # accept the new numbers

A regression means precision, recall or F1 fell below
benchmarks/accuracy/baseline.json. Raise the baseline in the same PR that improves it.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmarks" / "accuracy"
BASELINE_PATH = BENCH_DIR / "baseline.json"
METRICS = ("precision_exact", "recall_exact", "f1_exact")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tag-exports"))


def fixtures() -> list[Path]:
    return sorted(p for p in BENCH_DIR.iterdir() if (p / "truth.json").is_file()
                  and (p / "detections.csv.gz").is_file()) if BENCH_DIR.is_dir() else []


def _load_detections(db_path: Path, fixture: Path, key: str) -> int:
    conn = sqlite3.connect(db_path)
    with gzip.open(fixture / "detections.csv.gz", "rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [
            (key, int(r["frame_number"]), int(float(r["timestamp_ms"])), r["object_class"],
             float(r["confidence"]), int(float(r["x_center"])), int(float(r["y_center"])),
             int(float(r["width"])), int(float(r["height"])),
             int(r["tracker_id"]) if r.get("tracker_id") not in (None, "") else None)
            for r in reader
        ]
    conn.executemany(
        """INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence,
                                   x_center, y_center, width, height, tracker_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


TYPED_SHOTS = {
    "made_two": ("2PT", "Make"), "missed_two": ("2PT", "Miss"),
    "made_three": ("3PT", "Make"), "missed_three": ("3PT", "Miss"),
    "made_free_throw": ("FT", "Make"), "missed_free_throw": ("FT", "Miss"),
}
OTHER_TYPES = {
    "assist": "Assist", "steal": "Steal", "turnover": "Turnover", "block": "Block", "foul": "Foul",
    "rebound_offensive": "OffRebound", "offensive_rebound": "OffRebound",
    "rebound_defensive": "DefRebound", "defensive_rebound": "DefRebound",
}


def ai_stat_rows(events: list[dict]) -> list[dict]:
    """Current event names -> the coach's tag types (2PT/3PT/FT make/miss, rebounds, ...).

    manual_vs_ai_q1_compare.convert_ai_events_to_stat_rows predates the precision
    generator: it dropped rebound_offensive/defensive and read every shot from the
    generic `shot` row (defaulting to 2PT), so 3s and FTs scored as 2s. Each precision
    shot is a generic `shot` row plus a typed twin; count the typed row, and fall back
    to the generic row only for games that have no typed shots at all.
    """
    import json as _json

    has_typed = any(str(e.get("event_type") or "").lower() in TYPED_SHOTS for e in events)
    rows = []
    for e in events:
        et = str(e.get("event_type") or "").lower()
        ts = int(e.get("timestamp_ms") or 0)
        if et in TYPED_SHOTS:
            kind, result = TYPED_SHOTS[et]
        elif et == "shot" and not has_typed:
            try:
                details = _json.loads(e.get("details_json") or "{}")
            except ValueError:
                details = {}
            shot = str(details.get("shot_type") or "2pt").lower()
            kind = "3PT" if "3" in shot else ("FT" if "ft" in shot or "free" in shot else "2PT")
            result = "Make" if str(e.get("shot_result") or "").lower() in ("make", "made") else "Miss"
        elif et == "rebound":
            try:
                details = _json.loads(e.get("details_json") or "{}")
            except ValueError:
                details = {}
            kind, result = ("OffRebound" if "off" in str(details.get("rebound_type") or "").lower()
                            else "DefRebound"), "NA"
        elif et in OTHER_TYPES:
            kind, result = OTHER_TYPES[et], "NA"
        else:
            continue
        rows.append({"eventtype": kind, "result": result, "start": str(ts / 1000),
                     "timestamp_ms": ts, "source_event_id": e.get("id")})
    return rows


def score_fixture(fixture: Path) -> dict:
    """Run the event generator on one fixture and score it against the coach's tags."""
    from manual_vs_ai_q1_compare import (
        STAT_EVENTTYPES, event_level_match, filter_manual_q1_rows, match_key, pr_summary,
    )

    truth = json.loads((fixture / "truth.json").read_text(encoding="utf-8"))
    window_ms = int(truth.get("window_sec", 871)) * 1000
    key = f"accuracy_{fixture.name}"
    with tempfile.TemporaryDirectory(prefix="accuracy_bench_") as tmp:
        db_path = Path(tmp) / "bench.db"
        os.environ["LIBERTY_DATABASE"] = str(db_path)
        os.environ.setdefault("LIBERTY_UPLOAD_FOLDER", str(Path(tmp) / "uploads"))
        import app as app_module
        import event_generator

        app_module.app.config["DATABASE"] = str(db_path)
        with app_module.app.app_context():
            app_module.init_db()
        n_det = _load_detections(db_path, fixture, key)
        event_generator.main(key, str(db_path))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        events = [dict(r) for r in conn.execute(
            "SELECT * FROM events WHERE game_id=? AND COALESCE(source_type,'ai')='ai' "
            "ORDER BY timestamp_ms, id", (key,))]
        conn.close()

    manual = [r for r in filter_manual_q1_rows(truth["rows"]) if r.get("eventtype") in STAT_EVENTTYPES]
    ai_rows = ai_stat_rows([e for e in events if 0 <= int(e.get("timestamp_ms") or 0) <= window_ms])
    matches, extras, misses, disagreements = event_level_match(manual, ai_rows)
    summary = pr_summary(matches, extras, misses, disagreements)

    by_type = {}
    truth_counts = Counter(match_key(r) for r in manual)
    hit_counts = Counter(match_key(m["manual"]) for m in matches)
    ai_counts = Counter(match_key(r) for r in ai_rows)
    for k in sorted(set(truth_counts) | set(ai_counts)):
        by_type[k] = {"truth": truth_counts.get(k, 0), "ai": ai_counts.get(k, 0), "matched": hit_counts.get(k, 0)}
    return {
        "fixture": fixture.name,
        "detections": n_det,
        "truth_events": len(manual),
        "ai_events": len(ai_rows),
        **{m: summary[m] for m in METRICS},
        "true_positives": summary["true_positives"],
        "ai_extras": summary["false_positives_ai_extras"],
        "missed": summary["false_negatives_ai_misses"],
        "wrong_label": summary["disagreements_near_but_wrong_label"],
        "by_type": by_type,
    }


def regressions(result: dict, baseline: dict) -> list[str]:
    base = baseline.get(result["fixture"])
    if not base:
        return [f"{result['fixture']}: no baseline (run with --update-baseline)"]
    return [
        f"{result['fixture']}: {m} {result[m]:.4f} < baseline {base[m]:.4f}"
        for m in METRICS if result[m] + 1e-9 < float(base[m])
    ]


def markdown(results: list[dict], baseline: dict) -> str:
    lines = ["### Accuracy benchmark", "",
             "| Fixture | Precision | Recall | F1 | Matched / truth | AI events | Baseline P / R |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for r in results:
        b = baseline.get(r["fixture"], {})
        lines.append(
            f"| {r['fixture']} | {r['precision_exact']:.1%} | {r['recall_exact']:.1%} | {r['f1_exact']:.1%} | "
            f"{r['true_positives']} / {r['truth_events']} | {r['ai_events']} | "
            f"{b.get('precision_exact', 0):.1%} / {b.get('recall_exact', 0):.1%} |")
    for r in results:
        lines += ["", f"<details><summary>{r['fixture']} by event type</summary>", "",
                  "| Type | Truth | AI | Matched |", "|---|---:|---:|---:|"]
        lines += [f"| {k} | {v['truth']} | {v['ai']} | {v['matched']} |" for k, v in r["by_type"].items()]
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--json", type=Path, help="also write results as JSON here")
    args = ap.parse_args(argv)

    found = fixtures()
    if not found:
        print("No accuracy fixtures under benchmarks/accuracy/.")
        return 1
    results = [score_fixture(f) for f in found]
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.is_file() else {}
    report = markdown(results, baseline)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(report)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    if args.update_baseline:
        new = {r["fixture"]: {m: r[m] for m in METRICS} for r in results}
        BASELINE_PATH.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written to {BASELINE_PATH.relative_to(ROOT)}")
        return 0
    failed = [msg for r in results for msg in regressions(r, baseline)]
    for msg in failed:
        print("REGRESSION:", msg)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
