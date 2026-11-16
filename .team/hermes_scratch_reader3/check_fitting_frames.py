import cv2
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from scoreboard_clock import _red_mask

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

# Game A1 boxes
g1_h_tens = [1031, 614, 25, 29]
g1_h_ones = [1057, 613, 26, 30]
g1_a_tens = [1197, 613, 26, 30]
g1_a_ones = [1223, 613, 26, 30]

# Check non-gate frames used for fitting (every 8s from 6s, skipping ±60s from gate)
# Gate timestamps: 202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836
# Fitting frames: 6, 14, 22, 30, 38, 46, 54, 62, 70, 78, 86, 94, 102, 110, 118, 126, 134, 142, 150, 158, 166, 174, 182, 190, 198, 206(no, 202±60), 214(no), ..., 266(606-60=546, 606+60=666), etc.

# Let's check frame at 100s (non-gate)
test_times = [6, 14, 22, 30, 38, 46, 54, 62, 70, 78, 86, 94, 102, 110, 118, 126, 134, 142, 150, 158, 166, 174, 182, 190, 198, 200, 210, 220, 230, 240, 250, 260, 270, 280, 290, 300]

def analyze_box(img, box, name):
    x, y, w, h = box
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        return
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    mask = _red_mask(crop)
    print(f"  {name}: V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) _red_mask_pct={(mask>0).sum()/len(v_vals)*100:.1f}%")

print("=== Game A1 non-gate frames (fitting candidates) ===")
for ts in test_times:
    frame_num = int(round(ts * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ok, frame = cap.read()
    if not ok:
        continue
    print(f"\nTimestamp {ts}s:")
    analyze_box(frame, g1_h_tens, "home_tens")
    analyze_box(frame, g1_h_ones, "home_ones")
    analyze_box(frame, g1_a_tens, "away_tens")
    analyze_box(frame, g1_a_ones, "away_ones")

cap.release()