"""Label sheets from hoop-tracked clips (same crops the model sees) + wide context frames.
Row per moment: wide -1.0 s | 14 tracked crops (clip frames 6..32 step 2 = -0.40..+1.68 s... clipped to 31) | wide +2 s / +4 s.
Usage: python contact_sheet.py <moments.json> <video> <out_dir> [start_idx end_idx]"""
import sys, json
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, r"C:/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip")
import extract_clips as E

mj, vid, out = sys.argv[1], sys.argv[2], Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
d = json.load(open(mj)); ms = d["moments"]; fps = d["fps"]
a = int(sys.argv[4]) if len(sys.argv) > 4 else 0
b = int(sys.argv[5]) if len(sys.argv) > 5 else len(ms)
cap = cv2.VideoCapture(vid)
def grab(f):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(f)))); ok, im = cap.read()
    return im if ok else np.zeros((720, 1280, 3), np.uint8)
idx = list(range(a, b))
clips = E.extract([ms[i] for i in idx], vid)
rows = []
for j, i in enumerate(idx):
    m = ms[i]; f0 = m["frame"]
    w1 = cv2.resize(grab(f0 - 1.0 * fps), (300, 170)); cv2.putText(w1, "-1.0", (4, 18), 0, 0.6, (0, 255, 255), 2)
    crops = []
    for k in range(7, 32, 2):
        c = cv2.resize(clips[j][k], (120, 140)); t = E.T0 + k * E.STEP
        cv2.putText(c, f"{t:+.2f}", (2, 12), 0, 0.4, (0, 255, 255), 1); crops.append(c)
    strip = np.hstack(crops)
    strip = np.vstack([strip, np.zeros((30, strip.shape[1], 3), np.uint8)])
    g2 = grab(f0 - 2.0 * fps); g8 = grab(f0 + 8.0 * fps); H_ = g2.shape[0]; sc = lambda im: cv2.resize(im[int(H_*0.885):int(H_*0.94), int(im.shape[1]*0.05):int(im.shape[1]*0.85)], (300, 30)); w2 = cv2.resize(grab(f0 + 2.0 * fps), (150, 85)); w4 = cv2.resize(grab(f0 + 4.0 * fps), (150, 85))
    right = np.vstack([w2, w4])
    w1s = cv2.resize(w1, (300, 110))
    s2, s8 = sc(g2), sc(g8)
    cv2.putText(s2, "-2s", (2, 12), 0, 0.4, (0, 255, 255), 1); cv2.putText(s8, "+8s", (2, 12), 0, 0.4, (0, 255, 255), 1)
    w1p = np.vstack([w1s, s2, s8])
    row = np.hstack([w1p, strip, right])
    cv2.putText(row, f"#{i} t={m['t_ms']}", (4, 104), 0, 0.6, (255, 255, 255), 2)
    rows.append(row)
for p in range(0, len(rows), 5):
    rr = rows[p:p + 5]
    while len(rr) < 5: rr.append(np.zeros_like(rows[0]))
    cv2.imwrite(str(out / f"t{idx[p]:03d}.jpg"), np.vstack(rr), [cv2.IMWRITE_JPEG_QUALITY, 82])
print(len(rows))
