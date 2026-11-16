import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)
print(f"FPS: {fps}")

# Timestamp 202s = frame 202 * fps
timestamp = 202.0
frame_num = int(round(timestamp * fps))
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

print("=== Video frame at 202s (notus_A1_00) ===")
analyze_box(frame, g1_h_tens, "home_tens")
analyze_box(frame, g1_h_ones, "home_ones")
analyze_box(frame, g1_a_tens, "away_tens")
analyze_box(frame, g1_a_ones, "away_ones")

# Also check the crop PNG
crop_png = cv2.imread(str(ROOT / 'data/roi/notus_crops/notus_A1_00_202s.png'))
print("\n=== Crop PNG notus_A1_00_202s.png ===")
# Scale boxes for 1120x640
scale_x = 1120 / 1280
scale_y = 640 / 720
g1_h_tens_s = [int(1031*scale_x), int(614*scale_y), int(25*scale_x), int(29*scale_y)]
g1_h_ones_s = [int(1057*scale_x), int(613*scale_y), int(26*scale_x), int(30*scale_y)]
g1_a_tens_s = [int(1197*scale_x), int(613*scale_y), int(26*scale_x), int(30*scale_y)]
g1_a_ones_s = [int(1223*scale_x), int(613*scale_y), int(26*scale_x), int(30*scale_y)]
analyze_box(crop_png, g1_h_tens_s, "home_tens")
analyze_box(crop_png, g1_h_ones_s, "home_ones")
analyze_box(crop_png, g1_a_tens_s, "away_tens")
analyze_box(crop_png, g1_a_ones_s, "away_ones")