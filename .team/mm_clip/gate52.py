"""Spec 52 R6 gate over LOGO predictions (logo_preds.npz with PM).

Per held-out game prints: 3-seed ensemble auto %, per-seed auto % and spread, honest review %,
checks count, silent-reject count, and PASS/FAIL per R6 condition and overall.

R6 PASS per game:
  - ensemble auto >= 90%
  - seed spread (best - worst auto %) <= 5 pts
  - honest review >= 90%
  - checks <= 20 (hard, no truncation)
  - silent-reject == 0

Usage:
  python gate52.py <logo_preds.npz> film=<tags.json|labels.json>[=kind] ...
  kind = tags (default for coach tag files) or labels (gvfmt moments). Example:
    python gate52.py runs/logo/logo_preds.npz adrian=data/tags/adrian.json=tags \\
        gvg=.team/specs/50_gv_labels.json=labels
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shot_detectors"))

import ensemble_predict as ep  # noqa: E402

AUTO_MIN = 90.0
REVIEW_MIN = 90.0
SPREAD_MAX = 5.0
CHECKS_MAX = 20
SILENT_MAX = 0


def parse_truth_arg(arg):
    """film=path or film=path=tags|labels -> (film, path, kind)."""
    parts = arg.split("=", 2)
    if len(parts) == 2:
        film, path = parts
        kind = "tags"
    else:
        film, path, kind = parts
    if kind not in ("tags", "labels"):
        raise SystemExit(f"bad kind {kind!r} for {arg}; use tags or labels")
    return film, path, kind


def load_truth(path, kind):
    if kind == "tags":
        return ep.load_truth_tags(path)
    return ep.load_truth_labels(path)


def score_film(P, PM, T, Y, truth, session=None, session_filter=None):
    """Score one held-out game. P (N,3), PM (M,N,3).

    Spec 52a: pass session + session_filter through to shot_list. Default filter
    OFF (postproc52); logo52a uses postproc52a (session_filter true) with the
    per-film SESSION_PATHS mapping. Filtered candidates are omitted; a filtered
    real shot counts as an unmatched truth (recall miss).
    """
    cand = ep.candidate_labels_from_Y(T, Y)
    shots, extra = ep.shot_list(
        P, T, PM=PM, session=session, session_filter=session_filter
    )
    a_right, a_n, a_false = ep.auto_score(shots, truth)
    b_right, b_n, b_false, nck = ep.honest_review_score(shots, extra, truth, cand)
    auto_pct = 100.0 * a_right / max(a_n, 1)
    review_pct = 100.0 * b_right / max(b_n, 1)
    seed_pcts = []
    for s in range(PM.shape[0]):
        s_shots, _ = ep.shot_list(
            PM[s], T, PM=PM[s:s + 1], session=session, session_filter=session_filter
        )
        sr, sn, _ = ep.auto_score(s_shots, truth)
        seed_pcts.append(100.0 * sr / max(sn, 1))
    spread = (max(seed_pcts) - min(seed_pcts)) if seed_pcts else 0.0
    silent = ep.silent_reject_count(P, PM, Y)
    conds = {
        "auto_ge_90": auto_pct >= AUTO_MIN,
        "spread_le_5": spread <= SPREAD_MAX,
        "review_ge_90": review_pct >= REVIEW_MIN,
        "checks_le_20": nck <= CHECKS_MAX,
        "silent_eq_0": silent <= SILENT_MAX,
    }
    overall = all(conds.values())
    return {
        "n_truth": a_n,
        "auto_right": a_right,
        "auto_pct": round(auto_pct, 1),
        "auto_false": a_false,
        "seed_auto_pct": [round(x, 1) for x in seed_pcts],
        "seed_spread": round(spread, 1),
        "review_right": b_right,
        "review_pct": round(review_pct, 1),
        "review_false": b_false,
        "checks": nck,
        "silent_reject": silent,
        "conditions": conds,
        "PASS": overall,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logo_preds")
    ap.add_argument("truth", nargs="+", help="film=path[=tags|labels]")
    ap.add_argument(
        "--postproc",
        default=None,
        help="postproc json (default postproc52.json; logo52a: postproc52a.json)",
    )
    a = ap.parse_args()
    if a.postproc:
        ep.load_postproc(a.postproc)
    session_filter = bool(ep.CFG.get("session_filter", False))
    d = np.load(a.logo_preds, allow_pickle=True)
    if "PM" not in d.files:
        raise SystemExit("logo_preds.npz must contain PM (n_seeds, N, 3)")
    P, PM, Y, T, F = d["P"], d["PM"], d["Y"], d["T"], d["F"]
    films = {}
    for arg in a.truth:
        film, path, kind = parse_truth_arg(arg)
        films[film] = load_truth(path, kind)

    results = {}
    all_pass = True
    for film, truth in films.items():
        m = F == film
        if not m.any():
            print(f"{film}: NO ROWS in preds", flush=True)
            all_pass = False
            results[film] = {"PASS": False, "error": "no rows"}
            continue
        session = ep.load_session_for_film(film) if session_filter else None
        r = score_film(
            P[m],
            PM[:, m],
            T[m],
            Y[m],
            truth,
            session=session,
            session_filter=session_filter,
        )
        results[film] = r
        status = "PASS" if r["PASS"] else "FAIL"
        print(
            f"{film}: ensemble auto {r['auto_pct']}% ({r['auto_right']}/{r['n_truth']}) | "
            f"seeds {r['seed_auto_pct']} spread {r['seed_spread']} | "
            f"honest review {r['review_pct']}% | checks {r['checks']} | "
            f"silent_reject {r['silent_reject']} | {status}",
            flush=True,
        )
        for k, ok in r["conditions"].items():
            print(f"  {k}: {'PASS' if ok else 'FAIL'}", flush=True)
        if not r["PASS"]:
            all_pass = False

    results["OVERALL"] = "PASS" if all_pass else "FAIL"
    print(f"OVERALL: {results['OVERALL']}", flush=True)
    out = Path(a.logo_preds).resolve().parent / "gate52_report.json"
    json.dump(results, open(out, "w"), indent=1)
    print(f"wrote {out}", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
