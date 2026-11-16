import cv2
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from scoreboard_clock import _red_mask

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

# Game A boxes (original 1280x720 coords)
g2_h_tens = [1032, 615, 22, 28]
g2_h_ones = [1058, 614, 23, 29]
g2_a_tens = [1199, 615, 22, 28]
g2_a_ones = [1225, 614, 23, 29]

# Check a few gate timestamps
timestamps_ms = [187300, 561900, 936500, 1311100, 1685700, 2060300, 2434900, 2809500, 3184100, 3558700]

def analyze_box(img, box, name):
    x, y, w, h = box
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        return
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    mask = _red_mask(crop)
    print(f"  {name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) _red_mask_pct={(mask>0).sum()/total*100:.1f}%")

print("=== Game A video frames ===")
for ts in timestamps_ms:
    frame_num = int(round(ts / 1000.0 * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ok, frame = cap.read()
    if not ok:
        continue
    print(f"\nTimestamp {ts/1000:.0f}s:")
    analyze_box(frame, g2_h_tens, "home_tens")
    analyze_box(frame, g2_h_ones, "home_ones")
    analyze_box(frame, g2_a_tens, "away_tens")
    analyze_box(frame, g2_a_ones, "away_ones")

cap.release()