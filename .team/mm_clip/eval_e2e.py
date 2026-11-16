"""End-to-end score on films with complete coach tags: of ALL tagged shots, how many were found AND called
right (make/miss), and how many extra 'shots' the system reports.

Predicted shots = candidates whose argmax class is miss (1) or make (2). They are matched to tags greedily
(find_shots_measure.match_shot_indices, 4 s). A tag is right if matched and the predicted class equals the
tag result. Unmatched predicted shots = false shots.

Usage: python eval_e2e.py <preds.npz> film=<tags.json> [film=<tags.json> ...] [--thr-shot X]
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".team/shot_detectors"))
import find_shots_measure as fsm  # noqa: E402


def score(P, T, tags, thr_shot=None):
    if thr_shot is None:
        cls = P.argmax(1)
    else:  # shot if P(miss)+P(make) >= thr, then make vs miss by the larger
        shot = (P[:, 1] + P[:, 2]) >= thr_shot
        cls = np.where(shot, np.where(P[:, 2] >= P[:, 1], 2, 1), 0)
    idx = np.where(cls > 0)[0]
    tt = [t["t"] for t in tags]
    r = fsm.match_shot_indices(tt, [int(T[i]) for i in idx], 4000)
    right = 0
    wrong_call = 0
    for ti, fi, _ in r["matches"]:
        res = 2 if str(tags[ti]["result"]).lower().startswith("make") else 1
        if cls[idx[fi]] == res:
            right += 1
        else:
            wrong_call += 1
    n = len(tags)
    return {"tags": n, "found_and_right": right, "pct": round(100 * right / n, 1), "found_wrong_call": wrong_call,
            "not_found": len(r["unmatched_tags"]), "false_shots": len(r["unmatched_finder"]),
            "makes_tagged": sum(str(t["result"]).lower().startswith("make") for t in tags)}


def main():
    d = np.load(sys.argv[1], allow_pickle=True)
    P, T, F = d["P"], d["T"], d["F"]
    thr = None
    args = sys.argv[2:]
    if "--thr-shot" in args:
        thr = float(args[args.index("--thr-shot") + 1])
        args = [a for a in args if a not in ("--thr-shot", str(thr), args[args.index("--thr-shot") + 1])]
    tot = {"tags": 0, "found_and_right": 0, "false_shots": 0}
    for a in args:
        film, tp = a.split("=", 1)
        m = F == film
        tags = fsm.load_shot_tags(Path(tp))
        s = score(P[m], T[m], tags, thr)
        print(film, s)
        for k in tot:
            tot[k] += s[k]
    print("TOTAL found_and_right", tot["found_and_right"], "/", tot["tags"], f"= {100 * tot['found_and_right'] / max(1, tot['tags']):.1f}%",
          "false shots", tot["false_shots"])


if __name__ == "__main__":
    main()
