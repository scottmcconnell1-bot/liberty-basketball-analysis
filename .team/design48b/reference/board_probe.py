"""Probe: find the scoreboard as a static dark rectangle (seen films only)."""
import sys
import cv2
import numpy as np

S = r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad"
films = {"adrian": "uploads/nfhs_gam0a66d85e12.mp4", "notus": "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
         "gv": "uploads/LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4", "idaho": "uploads/LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4"}
out = []
for name, path in films.items():
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for i in range(30):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / 30))
        ok, f = cap.read()
        if ok:
            frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32))
    st = np.stack(frames)
    h, w = st.shape[1:]
    dark = (st < 45).mean(axis=0)          # fraction of samples where pixel is dark
    mask = (dark > 0.85).astype(np.uint8)
    mask[: int(h * 0.5), :] = 0             # bottom half only
    mask[:, : int(w * 0.5)] = 0             # right half only
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    num, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    best = max(range(1, num), key=lambda k: stats[k, cv2.CC_STAT_AREA]) if num > 1 else None
    if best is None:
        print(name, "no board"); continue
    x, y, bw, bh, area = stats[best]
    print(name, "board box", x, y, bw, bh, "area", area, "frame", w, h)
    cap.set(cv2.CAP_PROP_POS_FRAMES, n // 2)
    ok, f = cap.read()
    crop = f[max(0, y - 10): y + bh + 10, max(0, x - 10): x + bw + 10]
    out.append(cv2.resize(crop, (360, int(360 * crop.shape[0] / max(1, crop.shape[1])))))
H = max(o.shape[0] for o in out)
cv2.imwrite(S + "/board_probe.jpg", cv2.hconcat([cv2.copyMakeBorder(o, 0, H - o.shape[0], 0, 0, cv2.BORDER_CONSTANT) for o in out]))
