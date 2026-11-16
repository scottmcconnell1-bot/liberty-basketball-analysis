"""Spec 45 Riverstone blind score. Written by Claude Code 2026-11-09 BEFORE the Riverstone finder output
is looked at, BEFORE labels exist, BEFORE the spec-43 FT retrace and BEFORE the spec-45 make/miss run. Frozen.
Same scoring logic as .team/specs/44_gv_score.py (copied unchanged below); adds film_scale from make_miss.json.

Usage: python 45_rs_score.py <45_rs_labels.json> <FT retrace moments.json> <make_miss.json>
labels: {"moments": {"<t_ms>": {"shot": "yes"|"no"|"unclear",
                                "result": "make"|"miss"|"unclear"|null,
                                "ft": "yes"|"no"|"unclear",
                                "shooter_feet": [x, y] or null}}}
Coach load = auto makes the coach must flip (wrong) + coach items + no_track items
             + non-shots called make or coach. Silent errors = real makes called miss (hidden).
"""
import json
import sys

labels = json.load(open(sys.argv[1]))["moments"]
ft_moments = {str(m["t_ms"]): m for m in json.load(open(sys.argv[2]))["moments"]}
mm = {str(r["moment_t_ms"]): r for r in json.load(open(sys.argv[3]))}


def right(box, feet):
    if not box or not feet:
        return None
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return abs(feet[0] - x) <= 0.75 * w and abs(feet[1] - (y + h / 2)) <= 0.3 * h


ft = {"found": [], "missed": [], "false": [], "maybe_real": [], "maybe_not": [], "unclear_flagged": [],
      "shooter_right": 0, "shooter_wrong": [], "reasons_on_missed": {}}
for t, lab in labels.items():
    m = ft_moments.get(t)
    if m is None:
        continue
    reason = m.get("ft_reason")
    is_ft = lab.get("ft") == "yes"
    if reason == "free_throw_line":
        if lab.get("ft") == "unclear":
            ft["unclear_flagged"].append(int(t))
        elif is_ft:
            ft["found"].append(int(t))
            if right(m.get("shooter_box"), lab.get("shooter_feet")):
                ft["shooter_right"] += 1
            else:
                ft["shooter_wrong"].append(int(t))
        else:
            ft["false"].append(int(t))
    elif reason == "maybe_free_throw":
        (ft["maybe_real"] if is_ft else ft["maybe_not"]).append(int(t))
    elif is_ft:
        ft["missed"].append(int(t))
        ft["reasons_on_missed"][reason] = ft["reasons_on_missed"].get(reason, 0) + 1
ft["n_ft"] = sum(1 for v in labels.values() if v.get("ft") == "yes")
ft["coach_orange_added"] = len(ft["maybe_real"]) + len(ft["maybe_not"])
ft["coach_errors"] = len(ft["false"]) + len(ft["shooter_wrong"]) + len(ft["missed"])

mk = {"make_right": [], "make_wrong": [], "miss_right": [], "miss_wrong_silent": [],
      "coach_real_make": [], "coach_real_miss": [], "no_track_real_make": [], "no_track_real_miss": [],
      "nonshot_called_make": [], "nonshot_coach": [], "nonshot_no_track": [], "nonshot_miss_hidden": [],
      "unclear": [], "missing_from_make_miss": []}
for t, lab in labels.items():
    r = mm.get(t)
    if r is None:
        mk["missing_from_make_miss"].append(int(t))
        continue
    call = r["call"]
    if lab.get("shot") == "unclear" or (lab.get("shot") == "yes" and lab.get("result") not in ("make", "miss")):
        mk["unclear"].append(int(t))
        continue
    if lab.get("shot") == "no":
        key = {"make": "nonshot_called_make", "coach": "nonshot_coach",
               "no_track": "nonshot_no_track", "miss": "nonshot_miss_hidden"}[call]
        mk[key].append(int(t))
        continue
    real_make = lab["result"] == "make"
    if call == "make":
        mk["make_right" if real_make else "make_wrong"].append(int(t))
    elif call == "miss":
        mk["miss_wrong_silent" if real_make else "miss_right"].append(int(t))
    elif call == "coach":
        mk["coach_real_make" if real_make else "coach_real_miss"].append(int(t))
    else:
        mk["no_track_real_make" if real_make else "no_track_real_miss"].append(int(t))
n_shots = sum(1 for v in labels.values() if v.get("shot") == "yes" and v.get("result") in ("make", "miss"))
n_makes = sum(1 for v in labels.values() if v.get("shot") == "yes" and v.get("result") == "make")
mk["n_scored_shots"] = n_shots
mk["n_real_makes"] = n_makes
mk["coach_load"] = (len(mk["make_wrong"]) + len(mk["coach_real_make"]) + len(mk["coach_real_miss"])
                    + len(mk["no_track_real_make"]) + len(mk["no_track_real_miss"])
                    + len(mk["nonshot_called_make"]) + len(mk["nonshot_coach"]) + len(mk["nonshot_no_track"]))
mk["silent_errors"] = len(mk["miss_wrong_silent"])
scales = sorted({r.get("film_scale") for r in mm.values()}, key=str)
print(json.dumps({"n_labelled": len(labels), "film_scale": scales, "ft": ft, "make_miss": mk}, indent=1))
