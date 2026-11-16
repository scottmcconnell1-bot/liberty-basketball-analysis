"""Spec 43 V3/V4 Idaho City blind score. Written by Claude Code 2026-11-08 BEFORE the spec-43 retrace on Idaho.

Usage: python 43_idaho_score.py <labels.json> <run43_idaho/moments.json>
labels.json: {"moments": {"<t_ms>": {"label": "FT"|"no"|"unclear", "shooter_feet": [x, y] or null}}}
A flagged shooter is right when the labelled feet lie inside the flagged box widened by 25% each side
and within 0.3 box heights of the box bottom.
"""
import json, sys
labels = json.load(open(sys.argv[1]))["moments"]
moments = {str(m["t_ms"]): m for m in json.load(open(sys.argv[2]))["moments"]}
def right(box, feet):
    if not box or not feet: return None
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return abs(feet[0] - x) <= 0.75 * w and abs(feet[1] - (y + h / 2)) <= 0.3 * h
out = {"found": [], "missed": [], "false": [], "maybe_real": [], "maybe_not": [], "unclear_flagged": [], "shooter_right": 0, "shooter_wrong": [], "reasons_on_missed": {}}
for t, lab in labels.items():
    m = moments.get(t)
    if m is None: continue
    reason = m.get("ft_reason"); is_ft = lab["label"] == "FT"
    if reason == "free_throw_line":
        if lab["label"] == "unclear": out["unclear_flagged"].append(int(t))
        elif is_ft:
            out["found"].append(int(t)); ok = right(m.get("shooter_box"), lab.get("shooter_feet"))
            if ok: out["shooter_right"] += 1
            else: out["shooter_wrong"].append(int(t))
        else: out["false"].append(int(t))
    elif reason == "maybe_free_throw":
        (out["maybe_real"] if is_ft else out["maybe_not"]).append(int(t))
    elif is_ft:
        out["missed"].append(int(t)); out["reasons_on_missed"][reason] = out["reasons_on_missed"].get(reason, 0) + 1
n_ft = sum(1 for v in labels.values() if v["label"] == "FT")
out["n_labelled"] = len(labels); out["n_ft"] = n_ft
out["coach_orange_added"] = len(out["maybe_real"]) + len(out["maybe_not"])
out["coach_errors"] = len(out["false"]) + len(out["shooter_wrong"]) + len(out["missed"])
print(json.dumps(out, indent=1))
