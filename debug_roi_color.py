#!/usr/bin/env python3
import cv2
import numpy as np
HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"
def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    return data['frame_indices'], data['centers'], data['radii']
def get_hoop(frame_idx, f_ind, cents, rads):
    idx = np.argmin(np.abs(f_ind - frame_idx))
    return cents[idx], rads[idx], f_ind[idx]
f_ind, cents, rads = load_hoop()
frame_idx = 1
img = cv2.imread(f"{FRAME_DIR}/frame_{frame_idx:03d}.jpg")
hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, f_ind, cents, rads)
print(f"Hoop center: {hoop_center}, radius_px: {hoop_radius_px}")
HOOP_RADIUS_FT = 0.75
ft_per_px = HOOP_RADIUS_FT / hoop_radius_px if hoop_radius_px>0 else 0.005
print(f"ft_per_px: {ft_per_px}")
HALF_WIDTH_FT = 1.5
HALF_HEIGHT_FT = 2.5
half_w_px = HALF_WIDTH_FT / ft_per_px
half_h_px = HALF_HEIGHT_FT / ft_per_px
print(f"half_w_px: {half_w_px}, half_h_px: {half_h_px}")
x1 = int(max(0, hoop_center[0] - half_w_px))
y1 = int(max(0, hoop_center[1] - half_h_px))
x2 = int(min(img.shape[1]-1, hoop_center[0] + half_w_px))
y2 = int(min(img.shape[0]-1, hoop_center[1] + half_h_px))
print(f"ROI: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
roi = img[y1:y2, x1:x2]
print(f"ROI shape: {roi.shape}")
hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
h, s, v = cv2.split(hsv)
print(f"H: min={h.min()}, max={h.max()}, mean={h.mean():.1f}")
print(f"S: min={s.min()}, max={s.max()}, mean={s.mean():.1f}")
print(f"V: min={v.min()}, max={v.max()}, mean={v.mean():.1f}")
# Try different thresholds
for sat_min in [0,30,60,100]:
    for val_min in [0,30,60,100]:
        mask = cv2.inRange(hsv, np.array([0, sat_min, val_min]), np.array([20,255,255]))
        cnt = cv2.countNonZero(mask)
        print(f"sat_min={sat_min}, val_min={val_min}: {cnt} pixels")
        if cnt > 0:
            # show some pixel values
            ys, xs = np.where(mask > 0)
            if len(ys) > 0:
                for i in range(min(3, len(ys))):
                    y, x = ys[i], xs[i]
                    print(f"  ({x},{y}) H={h[y,x]} S={s[y,x]} V={v[y,x]}")