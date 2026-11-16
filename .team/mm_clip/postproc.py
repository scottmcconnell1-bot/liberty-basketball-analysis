"""Post-processing of clip-model predictions into a shot list, and its end-to-end score.

Steps (each optional): (1) game-time filter (spec 48b session.json; FT window kept), (2) shot threshold on
P(miss)+P(make), (3) de-duplicate: predicted shots closer than DEDUP_MS keep only the one with the highest
shot probability (a make in the group wins if any member's P(make) > P(miss)).

Usage: python postproc.py <preds.npz> film=<tags.json>=<session.json or ->  ...
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".team/shot_detectors"))
import find_shots_measure as fsm  # noqa: E402
import game_session as gs  # noqa: E402


def shot_list(P, T, session=None, thr=0.5, dedup_ms=2500):
    ps = P[:, 1] + P[:, 2]
    keep = ps >= thr
    if session is not None:
        keep &= np.array([gs.in_session(int(t), session, is_ft=True) for t in T])
    idx = sorted(np.where(keep)[0], key=lambda i: T[i])
    groups = []
    for i in idx:
        if groups and T[i] - T[groups[-1][-1]] <= dedup_ms:
            groups[-1].append(i)
        else:
            groups.append([i])
    out = []
    for g in groups:
        best = max(g, key=lambda i: ps[i])
        made = any(P[i, 2] > P[i, 1] for i in g)
        out.append((int(T[best]), 2 if made else 1))
    return out


def score(shots, tags):
    r = fsm.match_shot_indices([t["t"] for t in tags], [s[0] for s in shots], 4000)
    right = sum(1 for ti, fi, _ in r["matches"]
                if shots[fi][1] == (2 if str(tags[ti]["result"]).lower().startswith("make") else 1))
    return right, len(tags), len(r["unmatched_finder"]), len(r["matches"]) - right


def main():
    d = np.load(sys.argv[1], allow_pickle=True)
    P, T, F = d["P"], d["T"], d["F"]
    films = []
    for a in sys.argv[2:]:
        f, tp, sp = a.split("=", 2)
        films.append((f, fsm.load_shot_tags(Path(tp)), json.load(open(sp)) if sp != "-" else None))
    print("session dedup thr | right/tags pct | false shots | wrong calls   (per film ...)")
    for use_s in (False, True):
        for dd in (0, 1500, 2500, 4000):
            for thr in (0.5, 0.6, 0.7, 0.8):
                tot = [0, 0, 0, 0]; per = []
                for f, tags, sess in films:
                    m = F == f
                    s = shot_list(P[m], T[m], sess if use_s else None, thr, dd)
                    r = score(s, tags)
                    tot = [a + b for a, b in zip(tot, r)]
                    per.append(f"{f} {r[0]}/{r[1]} fs{r[2]}")
                print(f"{int(use_s)} {dd:5d} {thr:.1f} | {tot[0]}/{tot[1]} {100 * tot[0] / tot[1]:.1f}% | {tot[2]:3d} | {tot[3]}   ({'; '.join(per)})")


if __name__ == "__main__":
    main()
