"""Spec 49 Riverstone score. Written by Claude Code 2026-11-11 BEFORE the Riverstone game session, BEFORE
labels exist, BEFORE any rules / features / pull run on Riverstone. Frozen (sha256 in drift_log).
Pass bar = spec 49 P1-P3 (P4, P5 information only). Runs ONCE.

Usage: python 49_rs_score.py <labels.json> <session.json> <make_miss.json> <pull.json> <ft_moments.json>
labels: {"moments": {"<t_ms>": {"shot": "yes"|"no"|"unclear", "result": "make"|"miss"|"unclear"|null,
                                "ft": "yes"|"no"|"unclear", ...}}}  (same format as specs/44_gv_labels.json)
pull.json: list of {t_ms, in_session, rules_call, p, pulled}  (hybrid_pull.py pull, T 0.70)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shot_detectors"))
import game_session as gs  # noqa: E402

labels = json.load(open(sys.argv[1]))["moments"]
session = json.load(open(sys.argv[2]))
mm = {int(r["moment_t_ms"]): r["call"] for r in json.load(open(sys.argv[3]))}
pull = {int(r["t_ms"]): r for r in json.load(open(sys.argv[4]))}
ft_flag = {int(m["t_ms"]): m.get("ft_reason") in ("free_throw_line", "maybe_free_throw")
           for m in json.load(open(sys.argv[5]))["moments"]}
mins = lambda ms: f"{ms // 60000}:{(ms // 1000) % 60:02d}"

lab = {int(t): v for t, v in labels.items()}
unclear = sorted(t for t, v in lab.items() if v.get("shot") == "unclear" or (v.get("shot") == "yes" and v.get("result") not in ("make", "miss")))
real = {t: v for t, v in lab.items() if v.get("shot") == "yes" and v.get("result") in ("make", "miss")}
nonshot = {t for t, v in lab.items() if v.get("shot") == "no"}


def ins(t, v=None):
    is_ft = (v or {}).get("ft") == "yes" or ft_flag.get(t, False)
    return gs.in_session(t, session, is_ft=is_ft)


# P1: every labelled real shot in session
p1_out = sorted(t for t, v in real.items() if not ins(t, v))
P1 = not p1_out

# hidden makes = real makes, in session, rules call "miss"
real_in = {t: v for t, v in real.items() if ins(t, v)}
makes = {t for t, v in real_in.items() if v["result"] == "make"}
hidden = {t for t in makes if mm.get(t) == "miss"}


def pulls_at(T):
    return {t for t, r in pull.items() if r.get("in_session") and r.get("rules_call") == "miss" and r.get("p") is not None and r["p"] >= T}


def p2p3(T):
    P = pulls_at(T)
    caught = len(hidden & P)
    real_makes_pulled = len(P & makes)
    return P, caught, real_makes_pulled


P, caught, mk_pulled = p2p3(0.70)
assert {t for t, r in pull.items() if r.get("pulled")} == P, "pull.json 'pulled' differs from T 0.70 rule"
P2 = len(hidden) > 0 and caught * 3 >= len(hidden)
P3 = len(P) > 0 and mk_pulled * 3 >= len(P)

print("== SPEC 49 RIVERSTONE (scored once)")
print(f"labelled moments {len(lab)}; real shots {len(real)}; non-shots {len(nonshot)}; unclear (excluded) {len(unclear)} {[mins(t) for t in unclear]}")
print(f"P1 game time: real shots in session {len(real) - len(p1_out)}/{len(real)} -> {'PASS' if P1 else 'FAIL'}; outside: {[(mins(t), real[t]['result'], 'FT' if real[t].get('ft') == 'yes' else '') for t in p1_out]}")
print(f"P2 hidden makes caught {caught}/{len(hidden)} (need >= 1/3) -> {'PASS' if P2 else 'FAIL'}")
print(f"P3 pulls that are real makes {mk_pulled}/{len(P)} (need >= 1/3) -> {'PASS' if P3 else 'FAIL'}")
print("SPEC 49:", "PASS" if (P1 and P2 and P3) else "FAIL")

# plain numbers for Scott (in-session real shots)
found = {t for t in makes if mm.get(t) == "make"}
coach_mk = {t for t in makes if mm.get(t) == "coach"}
notrack_mk = {t for t in makes if mm.get(t) == "no_track"}
misses = {t for t, v in real_in.items() if v["result"] == "miss"}
ns_in = {t for t in nonshot if ins(t, lab[t])}
coach_items = {t for t, c in mm.items() if c == "coach" and pull.get(t, {}).get("in_session")}
print("\n== PLAIN NUMBERS (real game shots in game time)")
print(f"real makes {len(makes)}: rules found {len(found)}; rules sent to coach {len(coach_mk)}; no track {len(notrack_mk)}; "
      f"called miss {len(hidden)} -> pulled to coach {caught}, still hidden {len(hidden) - caught}")
print(f"real misses {len(misses)}: called make {sum(mm.get(t) == 'make' for t in misses)}; pulled {len(P & misses)}")
print(f"non-shots in game time {len(ns_in)}: called make {sum(mm.get(t) == 'make' for t in ns_in)}; pulled {len(P & ns_in)}")
print(f"coach list = rules coach items {len(coach_items)} + pulls {len(P)} = {len(coach_items | P)}")
print(f"moments dropped as out of game time: {sum(1 for r in pull.values() if not r.get('in_session'))}/{len(pull)}")

# P4 information only
print("\n== P4 (information only, verdict uses T 0.70)")
for T in (0.60, 0.70, 0.80):
    PP, c, m = p2p3(T)
    print(f"T {T:.2f}: pulled {len(PP)}, hidden caught {c}/{len(hidden)}, pulls that are makes {m}/{len(PP)}")

# P5 every out-of-session moment accounted for
print("\n== P5 out-of-session moments by group")
periods = session.get("periods") or []
drops = session.get("dropped_segments") or []
first_tip = min((p["start_ms"] for p in periods), default=None)
last_end = max((p["end_ms"] for p in periods), default=None)
groups = {}
for t, r in sorted(pull.items()):
    if r.get("in_session"):
        continue
    d = next((d for d in drops if d["start_ms"] <= t <= d["end_ms"]), None)
    if d is not None:
        g = f"dropped segment {mins(d['start_ms'])}-{mins(d['end_ms'])} ({d['reason']})"
    elif first_tip is None or t < first_tip:
        g = "before the first tip (no running clock)"
    elif t > last_end:
        g = "after the last period end"
    else:
        g = "gap between a period end and the next segment / no-tip segment"
    groups.setdefault(g, []).append(t)
for g, ts in groups.items():
    rs = [(mins(t), real[t]["result"]) for t in ts if t in real]
    print(f"{g}: {len(ts)} moments; labelled real shots among them: {rs}")
print("warnings:", session.get("warnings"))
