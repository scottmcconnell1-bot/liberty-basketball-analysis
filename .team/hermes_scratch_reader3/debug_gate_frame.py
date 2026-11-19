import cv2
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from scoreboard_clock import _red_mask
from scoreboard_clock_720p import _read_notus_digit, _read_score

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

# Exact timestamp from ROI: 201900ms
timestamp_ms = 201900
frame_num = int(round(timestamp_ms / 1000.0 * fps))
print(f"Timestamp: {timestamp_ms}ms, frame_num: {frame_num}")

cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
ok, frame = cap.read()
cap.release()

print(f"Frame shape: {frame.shape}")

# Game A1 boxes (original 1280x720 coords)
g1_h_tens = [1031, 614, 25, 29]
g1_h_ones = [1057, 613, 26, 30]
g1_a_tens = [1197, 613, 26, 30]
g1_a_ones = [1223, 613, 26, 30]

def analyze_box(img, box, name):
    x, y, w, h = box
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        print(f"  {name}: EMPTY CROP")
        return
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    print(f"  {name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) red_pct={(low_red+high_red)/total*100:.1f}%")
    
    # Apply actual _red_mask
    mask = _red_mask(crop)
    print(f"    _red_mask pixels: {(mask > 0).sum()} / {total} = {(mask > 0).sum()/total*100:.1f}%")
    
    # Read digit
    digit = _read_notus_digit(mask)
    print(f"    _read_notus_digit: '{digit}'")

print("=== Frame at exact timestamp 201900ms ===")
analyze_box(frame, g1_h_tens, "home_tens")
analyze_box(frame, g1_h_ones, "home_ones")
analyze_box(frame, g1_a_tens, "away_tens")
analyze_box(frame, g1_a_ones, "away_ones")

# Now test _read_score
cells = {
    "home": {"tens": g1_h_tens, "ones": g1_h_ones},
    "away": {"tens": g1_a_tens, "ones": g1_a_ones}
}
home_score = _read_score(frame, cells["home"])
away_score = _read_score(frame, cells["away"])
print(f"\n_read_score: home={home_score}, away={away_score}")