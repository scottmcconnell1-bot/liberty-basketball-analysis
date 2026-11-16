"""Static-object filter for candidates: a real ball near the hoop MOVES. Drops candidates where every 'ball'
point within NEAR_HW hoop widths of the candidate's hoop, in the +-WIN_S window, stays inside a box smaller
than MIN_SPAN_HW hoop widths (e.g. a red shot clock beside the rim read as a ball).
Hoop position follows the camera: per frame, the detected hoop nearest the candidate hoop (else the candidate's).

Usage: python moving_ball.py <cands.json> <frames.json>[,<frames2>] <out.json>
"""
import json
import math
import sys

WIN_S = 0.6
NEAR_HW = 2.5
MIN_SPAN_HW = 0.6


def load_points(paths):
    ball, hoops = {}, {}
    for p in paths.split(","):
        d = json.load(open(p))
        for s in d.get("series", []):
            for q in s["points"]:
                ball.setdefault(int(q[0]), []).append((float(q[1]), float(q[2])))
        for fr in d["frames"]:
            if fr["b"]:
                ball.setdefault(fr["f"], []).extend((b[0], b[1]) for b in fr["b"])
            if fr["h"]:
                hoops[fr["f"]] = fr["h"]
    return ball, hoops


CELL_HW = 0.25
STATIC_FRAC = 0.02


def static_cells(ball, hoops):
    """Cells (relative to the nearest hoop, CELL_HW hoop widths) holding a 'ball' in more than STATIC_FRAC of
    all frames that have a hoop: a fixed object beside the rim (shot clock, logo), not a ball."""
    from collections import Counter
    cnt = Counter()
    n = 0
    for f, hs in hoops.items():
        n += 1
        seen = set()
        for (x, y) in ball.get(f, []):
            h = min(hs, key=lambda h: math.hypot(h[0] - x, h[1] - y))
            if h[2] <= 0 or math.hypot(x - h[0], y - h[1]) > 3 * h[2]:
                continue
            seen.add((int(math.floor((x - h[0]) / h[2] / CELL_HW)), int(math.floor((y - h[1]) / h[2] / CELL_HW))))
        cnt.update(seen)
    return {c for c, k in cnt.items() if n and k / n > STATIC_FRAC}


def moving(m, fps, ball, hoops, static=frozenset()):
    f0 = int(m["frame"]); h0 = m["hoop"]; hw = float(h0["w"])
    w = int(round(WIN_S * fps))
    px, py = float(h0["x"]), float(h0["y"])
    xs, ys = [], []
    had_static = False
    for f in range(f0 - w, f0 + w + 1):
        hs = hoops.get(f)
        if hs:
            h = min(hs, key=lambda h: math.hypot(h[0] - px, h[1] - py))
            if math.hypot(h[0] - px, h[1] - py) < 1.5 * hw:
                px, py = h[0], h[1]
        for (x, y) in ball.get(f, []):
            if math.hypot(x - px, y - py) <= NEAR_HW * hw:
                cell = (int(math.floor((x - px) / hw / CELL_HW)), int(math.floor((y - py) / hw / CELL_HW)))
                if cell in static:
                    had_static = True
                    continue
                xs.append(x - px); ys.append(y - py)
    if not xs:
        return not had_static  # only clutter near the hoop -> drop; nothing at all -> cannot judge, keep
    span = max(max(xs) - min(xs), max(ys) - min(ys)) / hw
    return span >= MIN_SPAN_HW


def main():
    cj, fj, out = sys.argv[1:4]
    c = json.load(open(cj))
    ball, hoops = load_points(fj)
    static = static_cells(ball, hoops)
    print("static cells (dx,dy in 0.25 hoop widths):", sorted(static))
    keep = [m for m in c["moments"] if moving(m, c["fps"], ball, hoops, static)]
    json.dump({"fps": c["fps"], "moments": keep}, open(out, "w"))
    print(f"{len(c['moments'])} -> {len(keep)} moving-ball candidates -> {out}")


if __name__ == "__main__":
    main()
