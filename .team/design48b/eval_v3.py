import json, sys
from pathlib import Path
S = r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad"
REPO = Path(r"C:/Users/scott/Documents/liberty-basketball-analysis")
sys.path.insert(0, S); sys.path.insert(0, str(REPO / ".team/shot_detectors"))
from stopstart48 import states_partial, states_full, fill
from session_v3 import build, resets_full, resets_partial
import game_session as gs, find_shots_measure as fsm
from game_session import parse_clock
mins = lambda ms: f"{ms // 60000}:{(ms // 1000) % 60:02d}"
truth = {"adrian": [(t["t"], t["eventtype"] == "FT") for t in fsm.load_shot_tags(REPO / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json")],
         "notus": [(t["t"], t["eventtype"] == "FT") for t in fsm.load_shot_tags(REPO / "data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json")],
         "idaho": [(1128600, True), (1144240, True)]}
gvl = json.loads((REPO / ".team/specs/44_gv_labels.json").read_text())["moments"]
truth["gv"] = [(int(t), v.get("ft") == "yes") for t, v in gvl.items() if v.get("shot") == "yes"]
RF = Path(r"C:/Users/scott/Documents/Liberty_Shot_Outputs/rim_first")
runs = {"adrian": ["run43_adrian", "run43_adrian_q4"], "notus": ["run43_notus"], "gv": ["run44_gv"], "idaho": ["run43_idaho"]}
for f in ("adrian", "notus", "gv", "idaho"):
    if f == "adrian":
        raw = json.load(open(f"{S}/adrian_raw48.json")); st = fill(states_partial(raw))
        z = [r["fmt"] == "sst" and r["v"] == 0 and r.get("v2") in (0, None) for r in raw]
    else:
        raw = json.load(open(f"{S}/home_raw48_{f}.json"))
        from session_v3 import norm_read, bridge_excursions
        for r in raw:
            r["clock_s"] = parse_clock(norm_read(r["read"])); r["read2"] = norm_read(r.get("read2"))
        cl, br = bridge_excursions([r["clock_s"] for r in raw])
        for r, c in zip(raw, cl): r["clock_s"] = c
        st = fill(states_full(raw), max_gap=130)
        z = [r["clock_s"] == 0 and parse_clock(r.get("read2")) in (0, None) for r in raw]
    t = [r["t_ms"] for r in raw]
    rs = resets_partial(raw) if f == 'adrian' else resets_full([r['clock_s'] for r in raw])
    import session_v3; session_v3.DEBUG.clear()
    s = build(st, z, t, rs, clock=None if f == 'adrian' else [r['clock_s'] for r in raw])
    print("  segments (start, end, stops):", [(mins(a), mins(b), n) for a, b, n, ok in session_v3.DEBUG if ok and b - a > 30000])
    json.dump(s, open(f"{S}/session_v3_{f}.json", "w"), indent=1)
    print(f"\n== {f}: periods {len(s['periods'])}", [(mins(p["start_ms"]), mins(p["end_ms"])) for p in s["periods"]])
    miss = [(mins(x), "FT" if ft else "") for x, ft in truth[f] if not gs.in_session(x, s, is_ft=ft)]
    print(f"  real shots in session {len(truth[f]) - len(miss)}/{len(truth[f])}  missing {miss}")
    ms = []
    for d in runs[f]:
        ms += json.load(open(RF / d / "moments.json"))["moments"]
    kept = [m for m in ms if gs.in_session(int(m["t_ms"]), s, is_ft=m.get("ft_reason") in ("free_throw_line", "maybe_free_throw"))]
    print(f"  finder moments kept {len(kept)}/{len(ms)}")
    if f == "gv":
        no = [int(x) for x, v in gvl.items() if v.get("shot") == "no"]
        print(f"  GV not-a-shot kept {sum(gs.in_session(x, s) for x in no)}/{len(no)}")
        pre = [x for x in no if 57 * 60000 < x < 70 * 60000]
        print(f"  GV not-a-shot between games (57-70 min) kept {sum(gs.in_session(x, s) for x in pre)}/{len(pre)}")
