"""Ensemble make/miss prediction for one film + locked post-processing + coach-review list (spec 52).

Ensemble = mean softmax (with flip TTA) of every model in --models. Post-processing and review band from
postproc52.json (R7). Writes <out>/preds.npz, <out>/shots.json.

Honest review scoring (R8): non-flagged auto calls stand; tags matched by non-flagged autos marked used
(4 s); flagged items match only unused tags within 2 s using the candidate's own label; flagged non-shots
removed; never insert truth at unflagged times.

E2E scoring (R6): against a full real-shot list (coach tags or labels json); no candidate = not found.
Silent-reject diagnostic (R6): labelled misses with ensemble P(shot) < floor and all seeds P(shot) < 0.5.

Usage:
  python ensemble_predict.py <clips.npz> <out_dir> --models a.pt b.pt ...
      [--labels labels.json] [--tags tags.json] [--truth-labels labels.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shot_detectors"))
import find_shots_measure as fsm  # noqa: E402
import game_session as gs  # noqa: E402

CFG_PATH = HERE / "postproc52.json"
CFG = json.load(open(CFG_PATH))
THR = CFG["shot_thr"]
DEDUP = CFG["dedup_ms"]
SESSION_FILTER = bool(CFG.get("session_filter", False))
LO = CFG["review"]["flag_below_thr_candidates_with_shot_prob_at_least"]  # floor 0.2
WEAK = CFG["review"]["flag_auto_shots_with_shot_prob_below"]
MM = CFG["review"]["flag_auto_shots_with_abs_pmake_minus_half_below"]
FLAG_SEED = CFG["review"].get("flag_seed_disagreement", True)
FLOOR = LO

# Spec 52a Item 2: per-film session.json (rimrock / no board -> None = no filter).
_OUTPUTS = Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs")
SESSION_PATHS = {
    "adrian": _OUTPUTS / "game_session_48b" / "adrian" / "session.json",
    "notus": _OUTPUTS / "game_session_48b" / "notus" / "session.json",
    "gvg": _OUTPUTS / "game_session_48b" / "gv" / "session.json",
    "hsb": _OUTPUTS / "hybrid49" / "hsb" / "session" / "session.json",
    "rimrock": None,
}


# Spec 52b/52c: when true, below-thr extras flagged only if seed_disagreement(PM, i).
# Absent / false in postproc52 / postproc52a keeps the flat band.
EXTRAS_REQUIRE_SEED = bool(CFG["review"].get("extras_require_seed_disagreement", False))


def load_postproc(path=None):
    """Load postproc cfg into module globals (R7 postproc52; 52a; 52b)."""
    global CFG_PATH, CFG, THR, DEDUP, SESSION_FILTER, LO, WEAK, MM, FLAG_SEED, FLOOR
    global EXTRAS_REQUIRE_SEED
    CFG_PATH = Path(path) if path is not None else HERE / "postproc52.json"
    CFG = json.load(open(CFG_PATH))
    THR = CFG["shot_thr"]
    DEDUP = CFG["dedup_ms"]
    SESSION_FILTER = bool(CFG.get("session_filter", False))
    LO = CFG["review"]["flag_below_thr_candidates_with_shot_prob_at_least"]
    WEAK = CFG["review"]["flag_auto_shots_with_shot_prob_below"]
    MM = CFG["review"]["flag_auto_shots_with_abs_pmake_minus_half_below"]
    FLAG_SEED = CFG["review"].get("flag_seed_disagreement", True)
    EXTRAS_REQUIRE_SEED = bool(CFG["review"].get("extras_require_seed_disagreement", False))
    FLOOR = LO
    return CFG


def session_path_for_film(film):
    """Return session.json Path for film, or None (no filter / no readable board)."""
    if film in SESSION_PATHS:
        return SESSION_PATHS[film]
    return None


def load_session_for_film(film):
    """Load session dict for film, or None when no session path (rimrock / unknown)."""
    p = session_path_for_film(film)
    if p is None:
        return None
    return json.load(open(p))


def seed_disagreement(PM, i, thr=None):
    """R7: True if >=1 model P(shot)>=thr and >=1 model <thr, or among shot-callers a make/miss split."""
    if thr is None:
        thr = THR
    ps = PM[:, i, 1] + PM[:, i, 2]
    is_shot = ps >= thr
    if is_shot.any() and (~is_shot).any():
        return True
    if int(is_shot.sum()) >= 2:
        makes = PM[is_shot, i, 2] > PM[is_shot, i, 1]
        if makes.any() and (~makes).any():
            return True
    return False


def shot_list(
    P,
    T,
    PM=None,
    thr=None,
    dedup_ms=None,
    lo=None,
    weak=None,
    mm=None,
    flag_seed=None,
    session=None,
    session_filter=None,
    extras_require_seed_disagreement=None,
):
    """Build auto shots + below-thr extra checks; set check flags (R7 / 52b).

    Spec 52a: when session_filter is on and session is provided, out-of-session
    candidates are OMITTED from the shot list (and from extras). A filtered real
    shot is simply missing -> auto recall miss. Default session_filter follows
    postproc52.json (false) so logo52 numbers stay unchanged. Pinned definition:
    game_session.in_session(t, session, is_ft=True). No session (rimrock) = no filter.

    Spec 52b/52c: when extras_require_seed_disagreement is true (postproc52b),
    below-thr band extras are flagged only if seed_disagreement(PM, i). When the
    key is absent/false (postproc52 / postproc52a), the flat band is kept.
    Auto check flags are unchanged.
    """
    thr = THR if thr is None else thr
    dedup_ms = DEDUP if dedup_ms is None else dedup_ms
    lo = LO if lo is None else lo
    weak = WEAK if weak is None else weak
    mm = MM if mm is None else mm
    flag_seed = FLAG_SEED if flag_seed is None else flag_seed
    use_filter = SESSION_FILTER if session_filter is None else bool(session_filter)
    extras_req = (
        EXTRAS_REQUIRE_SEED
        if extras_require_seed_disagreement is None
        else bool(extras_require_seed_disagreement)
    )
    ps = P[:, 1] + P[:, 2]
    pm = P[:, 2] / np.maximum(ps, 1e-6)

    def _keep(i):
        if not use_filter or session is None:
            return True
        return gs.in_session(int(T[i]), session, is_ft=True)

    idx = sorted((i for i in np.where(ps >= thr)[0] if _keep(i)), key=lambda i: T[i])
    groups = []
    for i in idx:
        if groups and T[i] - T[groups[-1][-1]] <= dedup_ms:
            groups[-1].append(i)
        else:
            groups.append([i])
    auto = [max(g, key=lambda i: ps[i]) for g in groups]
    shots = []
    for i in auto:
        check = bool(ps[i] < weak or abs(pm[i] - 0.5) < mm)
        if flag_seed and PM is not None and seed_disagreement(PM, i, thr=thr):
            check = True
        shots.append({
            "t_ms": int(T[i]),
            "call": "make" if P[i, 2] > P[i, 1] else "miss",
            "p_shot": round(float(ps[i]), 3),
            "p_make": round(float(pm[i]), 3),
            "check": check,
            "_i": int(i),
        })
    extra = []
    auto_set = set(auto)
    for i in range(len(T)):
        if i in auto_set:
            continue
        if not _keep(i):
            continue
        if lo <= ps[i] < thr:
            if extras_req:
                if PM is None or not seed_disagreement(PM, i, thr=thr):
                    continue
            extra.append({"t_ms": int(T[i]), "p_shot": round(float(ps[i]), 3), "_i": int(i)})
    return shots, extra


def load_truth_tags(path):
    """Full real-shot list from coach tags json (load_shot_tags) -> [(t_ms, call 1|2), ...]."""
    tags = fsm.load_shot_tags(Path(path))
    out = []
    for t in tags:
        res = str(t.get("result") or t.get("eventresult") or "").lower()
        if res.startswith("make"):
            out.append((int(t["t"]), 2))
        elif res.startswith("miss"):
            out.append((int(t["t"]), 1))
    return out


def load_truth_labels(path):
    """Full real-shot list from gvfmt-style labels json moments -> [(t_ms, call 1|2), ...]."""
    lab = json.load(open(path))["moments"]
    out = []
    for t, v in lab.items():
        if v.get("shot") == "yes" and v.get("result") in ("make", "miss"):
            out.append((int(t), 2 if v["result"] == "make" else 1))
    return sorted(out)


def load_candidate_labels(path):
    """Candidate labels keyed by t_ms (gvfmt moments) for honest-review coach answers."""
    lab = json.load(open(path))["moments"]
    out = {}
    for t, v in lab.items():
        if v.get("shot") == "no":
            out[int(t)] = 0
        elif v.get("shot") == "yes" and v.get("result") == "miss":
            out[int(t)] = 1
        elif v.get("shot") == "yes" and v.get("result") == "make":
            out[int(t)] = 2
        else:
            out[int(t)] = -1
    return out


def candidate_labels_from_Y(T, Y):
    return {int(t): int(y) for t, y in zip(T, Y)}


def _match_score(pred_list, truth):
    """pred_list: [(t_ms, call)]; truth: [(t_ms, call)]. Returns (right, n_truth, false_shots)."""
    tt = [t for t, _ in truth]
    r = fsm.match_shot_indices(tt, [t for t, _ in pred_list], 4000)
    right = sum(1 for ti, fi, _ in r["matches"] if pred_list[fi][1] == truth[ti][1])
    return right, len(truth), len(r["unmatched_finder"])


def auto_score(shots, truth):
    """E2E auto: predicted auto shots vs ALL real shots; unmatched truth = not found (R6)."""
    pred = [(s["t_ms"], 2 if s["call"] == "make" else 1) for s in shots]
    return _match_score(pred, truth)


def honest_review_score(shots, extra, truth, cand_labels):
    """R8 honest coach-review score.

    - Non-flagged auto calls stand.
    - Tags matched (4 s, one-to-one) by non-flagged autos are marked used first.
    - Each flagged item answered once by simulated coach = its own candidate label.
    - Flagged real shot (label 1|2) -> match nearest unused tag within 2 s; add with true call.
    - Flagged non-shot (label 0) -> removed.
    - Never insert truth at unflagged times.
    """
    final = [(s["t_ms"], 2 if s["call"] == "make" else 1) for s in shots if not s["check"]]
    tt = [t for t, _ in truth]
    used = set()
    if final and tt:
        r = fsm.match_shot_indices(tt, [t for t, _ in final], 4000)
        for ti, _fi, _ in r["matches"]:
            used.add(ti)
    flagged = sorted(
        [{"t_ms": s["t_ms"], "kind": "shot"} for s in shots if s["check"]]
        + [{"t_ms": e["t_ms"], "kind": "extra"} for e in extra],
        key=lambda x: x["t_ms"],
    )
    for item in flagged:
        lab = cand_labels.get(int(item["t_ms"]), -1)
        if lab <= 0:
            # non-shot (0) removed; unknown (-1) not inserted
            continue
        cand = [k for k in range(len(tt)) if k not in used and abs(tt[k] - item["t_ms"]) <= 2000]
        if not cand:
            continue
        k = min(cand, key=lambda k: abs(tt[k] - item["t_ms"]))
        used.add(k)
        final.append((tt[k], truth[k][1]))
    final = sorted(final)
    right, n, false = _match_score(final, truth)
    nck = sum(1 for s in shots if s["check"]) + len(extra)
    return right, n, false, nck


def silent_reject_count(P, PM, Y, floor=None):
    """R6: labelled misses with ensemble mean P(shot) < floor AND all M seeds P(shot) < 0.5."""
    floor = FLOOR if floor is None else floor
    Y = np.asarray(Y)
    miss = Y == 1
    if not miss.any():
        return 0
    ps_ens = P[:, 1] + P[:, 2]
    ps_seeds = PM[:, :, 1] + PM[:, :, 2]  # (M, N)
    silent = miss & (ps_ens < floor) & (ps_seeds < 0.5).all(axis=0)
    return int(silent.sum())


def predict_all(X, models, seq=None):
    """Ensemble softmax over models. Spec 52d: R4 512-head, no seq; FORCE predict bs=8.

    seq is accepted for call-site compatibility but ignored (52d single-input head).
    """
    import torch
    import train_clip as tc
    del seq  # 52d: no seq
    Ps = []
    for p in models:
        m = tc.make_model()
        m.load_state_dict(torch.load(p))
        m.cuda()
        Ps.append(tc.predict(m, X, bs=tc.PREDICT_BS, seq=None))
        del m
        torch.cuda.empty_cache()
    return np.stack(Ps)  # (M, N, 3)


def score_report(shots, extra, truth, cand_labels, P=None, PM=None, Y=None, name=""):
    a_right, a_n, a_false = auto_score(shots, truth)
    b_right, b_n, b_false, nck = honest_review_score(shots, extra, truth, cand_labels)
    prefix = f"{name} " if name else ""
    print(
        f"{prefix}real shots {a_n}: AUTO {a_right}/{a_n} = {100 * a_right / max(a_n, 1):.1f}% "
        f"(false {a_false}) | WITH HONEST REVIEW {b_right}/{b_n} = {100 * b_right / max(b_n, 1):.1f}% "
        f"(false {b_false}, checks {nck})",
        flush=True,
    )
    out = {
        "n_truth": a_n,
        "auto_right": a_right,
        "auto_pct": 100.0 * a_right / max(a_n, 1),
        "auto_false": a_false,
        "review_right": b_right,
        "review_pct": 100.0 * b_right / max(b_n, 1),
        "review_false": b_false,
        "checks": nck,
    }
    if P is not None and PM is not None and Y is not None:
        sr = silent_reject_count(P, PM, Y)
        out["silent_reject"] = sr
        print(f"{prefix}silent_reject {sr}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--labels", help="candidate labels json (gvfmt) for honest-review coach answers")
    ap.add_argument("--tags", help="coach tags json = full real-shot list for e2e (R6)")
    ap.add_argument("--truth-labels", help="gvfmt labels json = full real-shot list for e2e (R6)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = np.load(a.clips)
    X, T = d["clips"], d["t_ms"]
    Y = d["y"] if "y" in d.files else None
    # Spec 52d: single pooled clip, no seq; predict bs forced inside predict_all
    PM = predict_all(X, a.models, seq=None)
    P = PM.mean(0)
    np.savez(out / "preds.npz", P=P, PM=PM, T=T, models=np.array(a.models))
    shots, extra = shot_list(P, T, PM=PM)
    nck = sum(s["check"] for s in shots) + len(extra)
    json.dump(
        {
            "models": a.models,
            "postproc": CFG,
            "shots": [{k: v for k, v in s.items() if k != "_i"} for s in shots],
            "extra_checks": [{k: v for k, v in e.items() if k != "_i"} for e in extra],
            "flags_count": nck,
        },
        open(out / "shots.json", "w"),
        indent=1,
    )
    print(
        f"{len(shots)} shots ({sum(s['call'] == 'make' for s in shots)} make), "
        f"coach checks {nck}",
        flush=True,
    )

    truth = None
    if a.tags:
        truth = load_truth_tags(a.tags)
    elif a.truth_labels:
        truth = load_truth_labels(a.truth_labels)
    elif a.labels:
        # labels alone: use yes-shot rows as truth (legacy path)
        truth = load_truth_labels(a.labels)

    if truth is not None:
        if a.labels:
            cand = load_candidate_labels(a.labels)
        elif Y is not None:
            cand = candidate_labels_from_Y(T, Y)
        else:
            cand = {}
        for k, p in enumerate(a.models):
            s1, e1 = shot_list(PM[k], T, PM=PM[k:k + 1])
            print(f"  single model {Path(p).name}: ", end="")
            score_report(s1, e1, truth, cand, name="")
        print("  ENSEMBLE: ", end="")
        score_report(shots, extra, truth, cand, P=P, PM=PM, Y=Y if Y is not None else np.full(len(T), -1))


if __name__ == "__main__":
    main()
