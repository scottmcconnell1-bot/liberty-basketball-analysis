import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

# Check all gate timestamps for Game A1
timestamps = [202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836]

g1_h_tens = [1031, 614, 25, 29]
g1_h_ones = [1057, 613, 26, 30]
g1_a_tens = [1197, 613, 26, 30]
g1_a_ones = [1223, 613, 26, 30]

def analyze_box(img, box, name):
    x, y, w, h = box
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        return f"  {name}: EMPTY"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    return f"  {name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) red_pct={(low_red+high_red)/total*100:.1f}%"

for ts in timestamps:
    frame_num = int(round(ts * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ok, frame = cap.read()
    if not ok:
        print(f"Timestamp {ts}s: FAILED TO READ")
        continue
    print(f"\n=== Video frame at {ts}s ===")
    print(analyze_box(frame, g1_h_tens, "home_tens"))
    print(analyze_box(frame, g1_h_ones, "home_ones"))
    print(analyze_box(frame, g1_a_tens, "away_tens"))
    print(analyze_box(frame, g1_a_ones, "away_ones"))

cap.release()