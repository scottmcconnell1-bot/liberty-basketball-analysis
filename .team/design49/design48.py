"""Spec 48 design on SEEN games only (frozen spec-47 labels/features). Out-of-game scores with the 4
stable features (F4 crossing x offset, F5 depth, F6 in-column count, F12 net motion / film median).
Hybrid: rules call kept; rules-"miss" moments with high score -> pulled to coach. Shows pull settings."""
import json, statistics as st
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

M = "C:/Users/scott/Documents/Liberty_Shot_Outputs/mm_learned/"
RULES = {"adrian": M + "rules_adrian/vote/make_miss.json", "notus": M + "rules_notus/vote/make_miss.json",
         "gv": "C:/Users/scott/Documents/Liberty_Shot_Outputs/rim_first/mm46_gv/vote/make_miss.json"}
IDX = [3, 4, 5, 11]
data = {}
for f in RULES:
    feats = {r["moment_t_ms"]: r["features"] for r in json.load(open(M + f"frozen/features_{f}.json"))["rows"]}
    med12 = st.median(v[11] for v in feats.values()) or 1.0
    rules = {r["moment_t_ms"]: r["call"] for r in json.load(open(RULES[f]))}
    rows = [r for r in json.load(open(M + f"frozen/labels_{f}.json"))["rows"] if r["label"] in (0, 1)]
    X = np.array([[feats[r["moment_t_ms"]][i] / (med12 if i == 11 else 1) for i in IDX] for r in rows])
    data[f] = dict(X=X, y=np.array([r["label"] for r in rows]), rule=[rules[r["moment_t_ms"]] for r in rows])
for f in data:
    tr = [g for g in data if g != f]
    pipe = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000))
    pipe.fit(np.vstack([data[g]["X"] for g in tr]), np.concatenate([data[g]["y"] for g in tr]))
    data[f]["p"] = pipe.predict_proba(data[f]["X"])[:, 1]
from sklearn.metrics import roc_auc_score
for f, d in data.items():
    print(f, "AUC 4-feature out-of-game %.2f" % roc_auc_score(d["y"], d["p"]))
print("\nrules-'miss' moments only: pull if p >= T")
for T in (0.5, 0.6, 0.7, 0.8, 0.9):
    line = []
    for f, d in data.items():
        miss = [(p, y) for p, y, c in zip(d["p"], d["y"], d["rule"]) if c == "miss"]
        hidden = sum(y for _, y in miss)
        pulled = [(p, y) for p, y in miss if p >= T]
        caught = sum(y for _, y in pulled)
        line.append(f"{f}: hidden {hidden}, pulled {len(pulled)}, caught {caught}")
    print(f"T={T}: " + " | ".join(line))

# GV: what are the high-score rules-miss non-makes?
lab = json.load(open("C:/Users/scott/Documents/liberty-basketball-analysis/.team/specs/44_gv_labels.json"))["moments"]
rows = [r for r in json.load(open(M + "frozen/labels_gv.json"))["rows"] if r["label"] in (0, 1)]
d = data["gv"]
import collections
for T in (0.7, 0.9):
    c = collections.Counter()
    for r, p, y, call in zip(rows, d["p"], d["y"], d["rule"]):
        if call == "miss" and p >= T and y == 0:
            L = lab[str(r["moment_t_ms"])]
            c[("real miss" if L["shot"] == "yes" else "not a shot") + ("" if L["shot"] == "yes" else f" result={L.get('result')}")] += 1
    print("GV pulled non-makes T=%.1f" % T, dict(c))
# split by game-shot-only (what if finder removed non-shots perfectly)
for T in (0.5, 0.6, 0.7):
    out = []
    for f in data:
        rr = [r for r in json.load(open(M + f"frozen/labels_{f}.json"))["rows"] if r["label"] in (0, 1)]
        dd = data[f]
        shot = [(p, y) for r, p, y, c in zip(rr, dd["p"], dd["y"], dd["rule"]) if c == "miss" and r.get("matched_tag_t_ms") is not None]
        pulled = [(p, y) for p, y in shot if p >= T]
        out.append(f"{f}: pulled {len(pulled)}, caught {sum(y for _, y in pulled)}, hidden {sum(y for _, y in shot)}")
    print(f"real shots only T={T}: " + " | ".join(out))

# cap: pull top-K rules-miss moments by p (and p >= T) per game
for T in (0.6, 0.7):
    for K in (10, 15, 20):
        out = []
        for f, d in data.items():
            miss = sorted([(p, y) for p, y, c in zip(d["p"], d["y"], d["rule"]) if c == "miss" and p >= T], reverse=True)[:K]
            out.append(f"{f}: pulled {len(miss)}, caught {sum(y for _, y in miss)}")
        print(f"T={T} cap {K}: " + " | ".join(out))

top = sorted([(p, r["moment_t_ms"]) for r, p, y, c in zip(rows, d["p"], d["y"], d["rule"]) if c == "miss" and y == 0 and lab[str(r["moment_t_ms"])]["shot"] == "no"], reverse=True)[:8]
print("GV top non-shot pulls:", [(t, round(p, 3)) for p, t in top])
json.dump([t for _, t in top], open("C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad/gv_top_nonshot.json", "w"))
