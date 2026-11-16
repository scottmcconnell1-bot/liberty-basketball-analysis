"""Calibration-only FT-line rule v0 on the 6 spec-40 Q7 FTs. Read-only on repo."""
import sys, math, pickle, json
from pathlib import Path
import numpy as np, cv2
ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
sys.path.insert(0, str(ROOT / ".team" / "shot_detectors")); sys.path.insert(0, str(ROOT))
import ft_half_circle as F
cfg = F.stage1b_config(); det = cfg["detection"]
NEAR, ANG_MIN, SUPPORT_MIN, BAND_FRONT, BAND_BACK, END_PAD = 0.25, 60.0, 0.6, 0.15, 1.2, 0.5
D = Path(sys.argv[1]); OUT = Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\rim_first")
hoops = {}
for film in ("adrian", "notus"):
    for m in json.load(open(OUT / f"run37_{film}" / "moments.json"))["moments"]:
        hoops[f"{film}_{m['t_ms']}"] = m["hoop"]
def feet(p): return p["x"], p["y"] + p["h"] / 2
for pk in sorted(D.glob("*.pkl")):
    tag = pk.stem; gym = "adrian" if tag.startswith("adrian") else "liberty"
    fr = cv2.imread(str(D / f"{tag}.png")); W = fr.shape[1]; sc = W / 1280.0
    d = pickle.load(open(pk, "rb")); hp = hoops[tag]; hx, hy = hp["x"], hp["y"]
    mask = F.build_paint_mask(fr, gym, cfg)
    for p in d["players"]:
        x, y, w, h = p["x"], p["y"], p["w"], p["h"]
        cv2.rectangle(mask, (int(x-w/2-3), int(y-h/2-3)), (int(x+w/2+3), int(y+h/2+3)), 0, -1)
    L = cv2.HoughLinesP(mask, 1, np.pi/180, threshold=int(det["hough_threshold"]),
                        minLineLength=max(12, int(round(det["hough_min_line_length_px_at_1280"]*sc))),
                        maxLineGap=max(4, int(round(det["hough_max_line_gap_px_at_1280"]*sc))))
    L = [] if L is None else L.reshape(-1, 4).astype(float)
    boxm = np.zeros(mask.shape, np.uint8)
    for p in d["players"]:
        x, y, w, h = p["x"], p["y"], p["w"], p["h"]
        cv2.rectangle(boxm, (int(x-w/2-3), int(y-h/2-3)), (int(x+w/2+3), int(y+h/2+3)), 255, -1)
    fat = cv2.dilate(mask, np.ones((7, 7), np.uint8))
    def coverage(mx, my, ux, uy, t_mid, h, reach):
        hit = valid = 0
        for t in np.arange(t_mid - reach*h, t_mid + reach*h, 2.0):
            x, y = int(round(mx + ux*t)), int(round(my + uy*t))
            if not (0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]) or boxm[y, x]: continue
            valid += 1; hit += fat[y, x] > 0
        return (hit / valid if valid else 0.0), valid
    gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(float)
    def contrast(x1, y1, x2, y2):
        ln = math.hypot(x2-x1, y2-y1); nx, ny = -(y2-y1)/ln, (x2-x1)/ln; off = 8*sc; on = side = 0.0; n = 0
        for t in np.linspace(0, 1, 20):
            x, y = x1 + (x2-x1)*t, y1 + (y2-y1)*t
            pts = [(x, y), (x+nx*off, y+ny*off), (x-nx*off, y-ny*off)]
            if not all(0 <= int(a) < gray.shape[1] and 0 <= int(b) < gray.shape[0] for a, b in pts): continue
            on += gray[int(y), int(x)]; side += min(gray[int(pts[1][1]), int(pts[1][0])], gray[int(pts[2][1]), int(pts[2][0])]); n += 1
        return (on - side) / n if n else 0.0
    vis = fr.copy(); res = []
    for c in d["cands"]:
        fx, fy = feet(c); h = c["h"]
        hd = math.degrees(math.atan2(hy - fy, hx - fx)) % 180
        kept = []
        for x1, y1, x2, y2 in L:
            dx, dy = x2-x1, y2-y1; ln = math.hypot(dx, dy)
            if ln < 1: continue
            dist = abs(dy*(fx-x1) - dx*(fy-y1)) / ln
            t = ((fx-x1)*dx + (fy-y1)*dy) / ln
            a = math.degrees(math.atan2(dy, dx)) % 180; off = abs(a - hd); off = min(off, 180 - off)
            if dist <= NEAR*h and -END_PAD*h <= t <= ln + END_PAD*h and off >= ANG_MIN and (gym != 'adrian' or contrast(x1, y1, x2, y2) <= -10):
                kept.append((x1, y1, x2, y2, a, off))
        if not kept: res.append((int(fx), int(fy), "no line")); continue
        # dominant direction, then union extent along it through the feet
        a0 = float(np.median([k[4] for k in kept])); ux, uy = math.cos(math.radians(a0)), math.sin(math.radians(a0))
        grp = [k for k in kept if min(abs(k[4]-a0), 180-abs(k[4]-a0)) <= 5]
        ts = [((px-fx)*ux + (py-fy)*uy) for k in grp for px, py in ((k[0], k[1]), (k[2], k[3]))]
        tmin, tmax = min(ts), max(ts); support = (tmax - tmin) / h
        # line through mean of group points
        mx = np.mean([v for k in grp for v in (k[0], k[2])]); my = np.mean([v for k in grp for v in (k[1], k[3])])
        nx, ny = -uy, ux
        if (hx-mx)*nx + (hy-my)*ny > 0: nx, ny = -nx, -ny   # normal points AWAY from hoop
        inside = []
        for p in d["players"]:
            px, py = feet(p); s = (px-mx)*nx + (py-my)*ny; t = (px-mx)*ux + (py-my)*uy
            t0 = ((fx-mx)*ux + (fy-my)*uy) + tmin; t1 = t0 + (tmax - tmin)
            if -BAND_FRONT*p["h"] <= s <= BAND_BACK*p["h"] and t0 - END_PAD*h <= t <= t1 + END_PAD*h:
                inside.append((int(px), int(py)))
        tf = (fx-mx)*ux + (fy-my)*uy
        cov, nval = coverage(mx, my, ux, uy, tf, h, 1.0)
        res.append((int(fx), int(fy), f"cov {cov:.2f} (n {nval}) angle_off {np.median([k[5] for k in grp]):.0f} support {support:.2f}h inside {inside}"))
        for k in grp: cv2.line(vis, (int(k[0]), int(k[1])), (int(k[2]), int(k[3])), (255, 0, 255), 3)
        cv2.circle(vis, (int(fx), int(fy)), 8, (0, 255, 255), -1)
    print(tag); [print("  ", r) for r in res]
    cv2.imwrite(str(D / f"{tag}_rule.png"), vis)
