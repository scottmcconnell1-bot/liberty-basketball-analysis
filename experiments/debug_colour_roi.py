#!/usr/bin/env python3
"""
Debug colour stats in hoop ROI for frame 1.
"""

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

def main():
    f_ind, cents, rads = load_hoop()
    frame_idx = 1
    path = f"{FRAME_DIR}/frame_{frame_idx:03d}.jpg"
    img = cv2.imread(path)
    hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, f_ind, cents, rads)
    print(f"Hoop center: {hoop_center}, radius_px: {hoop_radius_px}")
    
    HOOP_RADIUS_FT = 0.75
    if hoop_radius_px <= 0:
        ft_per_px = 0.005
    else:
        ft_per_px = HOOP_RADIUS_FT / hoop_radius_px
    print(f"ft_per_px: {ft_per_px}")
    
    HALF_WIDTH_FT = 8.0
    HALF_HEIGHT_FT = 10.0
    half_w_px = HALF_WIDTH_FT / ft_per_px
    half_h_px = HALF_HEIGHT_FT / ft_per_px
    print(f"ROI half-width px: {half_w_px}, half-height px: {half_h_px}")
    
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
    
    # Show histogram of H
    hist_h = cv2.calcHist([h], [0], None, [180], [0,180])
    # Find peaks
    peaks = np.where(hist_h > np.max(hist_h)*0.1)[0]
    print(f"Hue peaks (count>10% max): {peaks[:20]}")
    
    # Try different masks
    masks = []
    masks.append(("H0-20,S>100,V>100", cv2.inRange(hsv, np.array([0,100,100]), np.array([20,255,255]))))
    masks.append(("H0-20,S>50,V>50", cv2.inRange(hsv, np.array([0,50,50]), np.array([20,255,255]))))
    masks.append(("H0-20,S>30,V>30", cv2.inRange(hsv, np.array([0,30,30]), np.array([20,255,255]))))
    masks.append(("H0-20,S>100,V>50", cv2.inRange(hsv, np.array([0,100,50]), np.array([20,255,255]))))
    masks.append(("H0-20,S>50,V>100", cv2.inRange(hsv, np.array([0,50,100]), np.array([20,255,255]))))
    masks.append(("H0-20,S>100,V>150", cv2.inRange(hsv, np.array([0,100,150]), np.array([20,255,255]))))
    masks.append(("H0-20,S>150,V>150", cv2.inRange(hsv, np.array([0,150,150]), np.array([20,255,255]))))
    # Also try brown-ish: low V
    masks.append(("H0-20,S>50,V<100", cv2.inRange(hsv, np.array([0,50,0]), np.array([20,255,100]))))
    masks.append(("H0-20,S>30,V<100", cv2.inRange(hsv, np.array([0,30,0]), np.array([20,255,100]))))
    
    for name, mask in masks:
        cnt = cv2.countNonZero(mask)
        print(f"{name}: {cnt} pixels")
        
        # Also show where these pixels are (maybe draw a few)
        if cnt > 0:
            ys, xs = np.where(mask > 0)
            # take first 5 points
            for i in range(min(5, len(xs))):
                print(f"  point ({xs[i]+x1},{ys[i]+y1}) H={h[ys[i], xs[i]]} S={s[ys[i], xs[i]]} V={v[ys[i], xs[i]]}")

if __name__ == "__main__":
    main()