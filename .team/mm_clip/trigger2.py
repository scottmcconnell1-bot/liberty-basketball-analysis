"""Finder trigger v2 (offline, on a finder base run's frames.json). Camera-pan safe: every ball point is
compared with the hoop detected in the SAME frame (nearest hoop within +-3 frames), not a fixed x-bucket.

Ball points: v6 series points (all series) plus BODD 'b' box centres as fallback where v6 has none.
Trigger frame: ball within R_TRIG hoop widths of that frame's hoop centre, AND within the previous
LOOKBACK_S seconds a ball point was above the rim (y < hy - ABOVE_HW*hw) and within ABOVE_X_HW widths
in x of the hoop at that time. Triggers closer than MERGE_S to the previous one belong to the same moment.
Moment = first trigger frame of a group; hoop = that frame's hoop.

Usage: python trigger2.py <frames.json> <fps> <out_moments.json> [R_TRIG]
"""
import bisect
import json
import math
import sys

R_TRIG = 1.0
ABOVE_HW = 0.3
ABOVE_X_HW = 3.0
LOOKBACK_S = 1.2
MERGE_S = 1.5
HOOP_NEAR_FRAMES = 3
MIN_HOOP_W = 20
HOOP_MAX_Y_FRAC = 0.55


def build(frames_json, fps, r_trig=R_TRIG):
    d = json.load(open(frames_json))
    frames = d["frames"]
    # plausible hoops only (as the old finder's K8 filter): width 0.5-1.5 x the film's median hoop width,
    # centre in the upper HOOP_MAX_Y_FRAC of the frame (drops the scoreboard overlay and floor logos)
    allw = sorted(h[2] for fr in frames for h in fr["h"] if h[2] >= MIN_HOOP_W)
    med = allw[len(allw) // 2] if allw else 0
    maxy = max((h[1] for fr in frames for h in fr["h"]), default=0)
    frame_h = d.get("height") or (720 if maxy <= 720 else 1080)
    hoops = {}
    for fr in frames:
        hs = [h for h in fr["h"] if h[2] >= MIN_HOOP_W and 0.5 * med <= h[2] <= 1.5 * med and h[1] <= HOOP_MAX_Y_FRAC * frame_h]
        if hs:
            hoops[fr["f"]] = hs
    hoop_frames = sorted(hoops)
    ball = {}
    for s in d.get("series", []):
        for p in s["points"]:
            ball.setdefault(int(p[0]), []).append((float(p[1]), float(p[2])))
    for fr in frames:
        if fr["f"] not in ball and fr["b"]:
            ball[fr["f"]] = [(b[0], b[1]) for b in fr["b"]]
    ball_frames = sorted(ball)

    def hoops_near(f):
        i = bisect.bisect_left(hoop_frames, f)
        best = None
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(hoop_frames) and abs(hoop_frames[j] - f) <= HOOP_NEAR_FRAMES:
                if best is None or abs(hoop_frames[j] - f) < abs(best - f):
                    best = hoop_frames[j]
        return hoops.get(best, []) if best is not None else []

    look = int(round(LOOKBACK_S * fps))
    trig = []
    for f in ball_frames:
        hs = hoops_near(f)
        if not hs:
            continue
        for (x, y) in ball[f]:
            h = min(hs, key=lambda h: math.hypot(x - h[0], y - h[1]))
            hx, hy, hw = h[0], h[1], h[2]
            if math.hypot(x - hx, y - hy) / hw > r_trig:
                continue
            # came from above, near this hoop, in the last LOOKBACK_S
            i0 = bisect.bisect_left(ball_frames, f - look)
            above = False
            for fb in ball_frames[i0:bisect.bisect_left(ball_frames, f)]:
                hb = hoops_near(fb)
                if not hb:
                    continue
                for (xb, yb) in ball[fb]:
                    hh = min(hb, key=lambda h2: math.hypot(xb - h2[0], yb - h2[1]))
                    if abs(hh[0] - hx) > 3 * hw:  # a different hoop (other end)
                        continue
                    if yb < hh[1] - ABOVE_HW * hh[2] and abs(xb - hh[0]) <= ABOVE_X_HW * hh[2]:
                        above = True
                        break
                if above:
                    break
            if above:
                trig.append((f, h))
                break
    moments = []
    merge = int(round(MERGE_S * fps))
    for f, h in trig:
        if moments and f - moments[-1]["_last"] <= merge:
            moments[-1]["_last"] = f
            continue
        moments.append({"frame": f, "t_ms": int(round(f / fps * 1000)), "hoop": {"x": h[0], "y": h[1], "w": h[2], "h": h[3]},
                        "_last": f})
    for m in moments:
        del m["_last"]
    return moments


if __name__ == "__main__":
    fj, fps, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    r = float(sys.argv[4]) if len(sys.argv) > 4 else R_TRIG
    ms = build(fj, fps, r)
    json.dump({"fps": fps, "moments": ms, "trigger": "trigger2", "r_trig": r}, open(out, "w"))
    print(len(ms), "moments ->", out)
