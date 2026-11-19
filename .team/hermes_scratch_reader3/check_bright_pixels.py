import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

g1_h_ones = [1057, 613, 26, 30]

# Check frame at 6s (home_ones has good _red_mask response)
frame_num = int(round(6 * fps))
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
ok, frame = cap.read()
cap.release()

x, y, w, h = g1_h_ones
crop = frame[y:y+h, x:x+w]
hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

# Find pixels with V > 200 (very bright)
bright = hsv[:,:,2] > 200
if bright.any():
    h_bright = hsv[:,:,0][bright]
    s_bright = hsv[:,:,1][bright]
    v_bright = hsv[:,:,2][bright]
    print(f"Bright pixels (V>200): count={len(h_bright)}")
    print(f"  H: {h_bright.min()}-{h_bright.max()}, mean={h_bright.mean():.1f}")
    print(f"  S: {s_bright.min()}-{s_bright.max()}, mean={s_bright.mean():.1f}")
    print(f"  V: {v_bright.min()}-{v_bright.max()}, mean={v_bright.mean():.1f}")

# Find pixels with V > 120 (red mask threshold)
bright120 = hsv[:,:,2] > 120
if bright120.any():
    h_bright = hsv[:,:,0][bright120]
    s_bright = hsv[:,:,1][bright120]
    v_bright = hsv[:,:,2][bright120]
    print(f"\nBright pixels (V>120): count={len(h_bright)}")
    print(f"  H: {h_bright.min()}-{h_bright.max()}, mean={h_bright.mean():.1f}")
    print(f"  S: {s_bright.min()}-{s_bright.max()}, mean={s_bright.mean():.1f}")
    print(f"  V: {v_bright.min()}-{v_bright.max()}, mean={v_bright.mean():.1f}")

# Find pixels with V > 50
bright50 = hsv[:,:,2] > 50
if bright50.any():
    h_bright = hsv[:,:,0][bright50]
    s_bright = hsv[:,:,1][bright50]
    v_bright = hsv[:,:,2][bright50]
    print(f"\nBright pixels (V>50): count={len(h_bright)}")
    print(f"  H: {h_bright.min()}-{h_bright.max()}, mean={h_bright.mean():.1f}")
    print(f"  S: {s_bright.min()}-{s_bright.max()}, mean={s_bright.mean():.1f}")
    print(f"  V: {v_bright.min()}-{v_bright.max()}, mean={v_bright.mean():.1f}")

# Check dark pixels (V < 50)
dark = hsv[:,:,2] < 50
if dark.any():
    h_dark = hsv[:,:,0][dark]
    s_dark = hsv[:,:,1][dark]
    v_dark = hsv[:,:,2][dark]
    print(f"\nDark pixels (V<50): count={len(h_dark)}")
    print(f"  H: {h_dark.min()}-{h_dark.max()}, mean={h_dark.mean():.1f}")
    print(f"  S: {s_dark.min()}-{s_dark.max()}, mean={s_dark.mean():.1f}")
    print(f"  V: {v_dark.min()}-{v_dark.max()}, mean={v_dark.mean():.1f}")