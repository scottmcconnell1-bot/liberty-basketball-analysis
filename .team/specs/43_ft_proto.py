"""Spec 43 prototype (Claude Code 2026-11-08): spec 42 + try next candidate on a failed check + release check. Tuned on Adrian Q1-Q4 + Notus Q1 (all seen). Blind test = Idaho City."""
import sys, json, pickle, math
from pathlib import Path
ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
sys.path.insert(0, str(ROOT / ".team" / "shot_detectors")); sys.path.insert(0, str(ROOT))
import numpy as np, cv2
import ft_half_circle as F
S = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent  # folder with c42_<film>/<t>.pkl+.jpg caches
R = Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\rim_first")
B0, B1 = 0.0, 0.35
LANE_ANG = 30.0   # min angle between lane seg and FT line
LANE_GAP = 1.0    # nearest lane endpoint within this many cand heights of the line
LANE_REACH = 2.5  # crossing within this many cand heights of feet along line
LANE_MINOFF = 0.2
LANE_LEN = 0.0
HOOP_DIST_MAX = 3.8
RELEASE_DX_MAX = 0.8
def lane_info(line, feet, h, hoop, segs, gray, gym, W):
    mx, my = line["point"]; ux, uy = line["direction"]; nx, ny = F._line_normal(line, hoop)
    tf = (feet[0]-mx)*ux + (feet[1]-my)*uy
    left, right = [], []
    for x1, y1, x2, y2 in segs:
        L = math.hypot(x2-x1, y2-y1)
        if L < 1: continue
        ang = math.degrees(math.atan2(y2-y1, x2-x1))
        off = F._undirected_angle_off(ang, math.degrees(math.atan2(uy, ux)))
        if off < LANE_ANG: continue
        s1 = (x1-mx)*nx + (y1-my)*ny; s2 = (x2-mx)*nx + (y2-my)*ny
        if max(s1, s2) > 0.15*h: continue          # must sit on hoop side
        if min(abs(s1), abs(s2)) > LANE_GAP*h: continue
        if L < LANE_LEN*h: continue
        if gym == "adrian" and not F._adrian_darker_than_both_sides(gray, x1, y1, x2, y2, W): continue
        # crossing with FT line
        dx, dy = (x2-x1)/L, (y2-y1)/L
        den = dx*nx + dy*ny
        if abs(den) < 1e-6: continue
        k = -s1/den; cx, cy = x1+k*dx, y1+k*dy
        ti = (cx-mx)*ux + (cy-my)*uy - tf
        r = ti / h
        if -LANE_REACH <= r <= -LANE_MINOFF: left.append(round(r, 2))
        if LANE_MINOFF <= r <= LANE_REACH: right.append(round(r, 2))
    return left, right
def decide(d, gray):
    players, found, hoop = d["players"], d["found"], d["hoop"]
    if hoop is None: return "no_hoop", None, None
    ck = {F._box_key(b) for b in found}; any_line = False; info = []; fails = []
    for c in found:
        fx, fy = F._feet(c); h = c["h"]
        kept = F.keep_segments(d["segs"], (fx, fy), h, hoop, gray, d["gym"], d["W"])
        line = F.ft_line(kept) if kept else None
        if line is None: continue
        any_line = True
        mx, my = line["point"]; ux, uy = line["direction"]; nx, ny = F._line_normal(line, hoop); tmin, tmax = line["extent"]
        band = []
        for p in players:
            px, py = F._feet(p); s = (px-mx)*nx+(py-my)*ny; t = (px-mx)*ux+(py-my)*uy
            if B0*p["h"] <= s <= B1*p["h"] and tmin-F.END_PAD*h <= t <= tmax+F.END_PAD*h: band.append(p)
        if len(band) == 1 and F._box_key(band[0]) in ck:
            b = band[0]; l, r = lane_info(line, F._feet(b), b["h"], hoop, d["segs"], gray, d["gym"], d["W"])
            info.append((l, r))
            pick = [round(F._feet(b)[0]), round(F._feet(b)[1])]
            fx, fy = F._feet(b)
            if math.hypot(hoop[0] - fx, hoop[1] - fy) / b["h"] > HOOP_DIST_MAX: fails.append("too_far_from_hoop"); continue
            if not (l and r): fails.append("no_lane_lines"); continue
            rf = d.get("release_frame"); balls = d.get("balls") or []
            if rf is not None and balls:
                fr, bx, by = min(balls, key=lambda q: (abs(q[0] - rf), q[0]))
                if abs(bx - b["x"]) / b["h"] > RELEASE_DX_MAX: fails.append("release_not_shooter"); continue
            return "free_throw_line", pick, (l, r)
    if fails: return fails[0], None, None
    return ("line_not_one" if any_line else "ft_line_not_found"), None, None
STILL_MOVE_MAX = 0.15
MAYBE_STILL_MAX = 0.25
def decide_full(d, gray, still):
    """N3 / V1: still <= 0.15 -> decide; (0.15, 0.25] -> decide, free_throw_line becomes maybe_free_throw; else not_still."""
    if still is None or still > MAYBE_STILL_MAX:
        return "not_still", None, None
    r, pick, lr = decide(d, gray)
    if still > STILL_MOVE_MAX:
        return ("maybe_free_throw", pick, lr) if r == "free_throw_line" else ("not_still", None, None)
    return r, pick, lr
for film in ("adrian", "notus"):
    res = json.load(open(R / f"measure41_{film}" / "results.json"))
    ev = {m["moment_t_ms"]: m["eventtype"] for m in res["matches"]}
    for p in sorted((S / f"c42_{film}").glob("*.pkl"), key=lambda q: int(q.stem)):
        d = pickle.load(open(p, "rb"))
        gray = cv2.cvtColor(cv2.imread(str(p.with_suffix(".jpg"))), cv2.COLOR_BGR2GRAY).astype(float)
        r, pick, lr = decide(d, gray)
        tag = ev.get(d["t"])
        mark = ""
        if tag == "FT" and r != "free_throw_line": mark = "MISS"
        if tag != "FT" and r == "free_throw_line": mark = "FALSE"
        print(film, d["t"], tag, r, pick, mark)
