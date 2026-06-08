#!/usr/bin/env python3
"""
Detect ball as a circle in an annulus around the hoop using Hough circles.
- Load hoop centre and radius from hoop_Q1.npy (nearest frame).
- Define annulus: inner radius = hoop_radius * 1.2, outer radius = hoop_radius * 3.0
- Convert to HSV, mask orange/brown (but exclude very bright whites?).
- Apply Canny edge detection and HoughCircles with appropriate param.
- Draw detected circles.
"""

import cv2
import numpy as np
import os

HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"
OUT_DIR = "sample_frames_hough"
os.makedirs(OUT_DIR, exist_ok=True)

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    return data['frame_indices'], data['centers'], data['radii']

def get_hoop(frame_idx, f_ind, cents, rads):
    idx = np.argmin(np.abs(f_ind - frame_idx))
    return cents[idx], rads[idx], f_ind[idx]

def main():
    f_ind, cents, rads = load_hoop()
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])
    for fname in files:
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, f_ind, cents, rads)
        # Create mask for orange/brown
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # Orange
        mask_orange = cv2.inRange(hsv, np.array([10, 150, 150]), np.array([30, 255, 255]))
        # Brown/dark orange
        mask_brown = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([20, 200, 200]))
        mask = cv2.bitwise_or(mask_orange, mask_brown)
        # Exclude the hoop itself: create a mask of the hoop region (circle) and subtract
        hoop_mask = np.zeros_like(mask)
        cv2.circle(hoop_mask, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), 255, -1)
        mask_no_hoop = cv2.subtract(mask, hoop_mask)
        # Optional: dilate/erode to clean
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
        mask_no_hoop = cv2.morphologyEx(mask_no_hoop, cv2.MORPH_OPEN, kernel, iterations=1)
        mask_no_hoop = cv2.morphologyEx(mask_no_hoop, cv2.MORPH_CLOSE, kernel, iterations=1)
        # Edge detection
        edges = cv2.Canny(mask_no_hoop, 50, 150)
        # Hough circles
        # dp = 1, minDist = hoop_radius_px/2, param1=100, param2=30, minRadius, maxRadius
        min_radius = int(hoop_radius_px * 0.3)  # ball smaller than hoop
        max_radius = int(hoop_radius_px * 1.5)
        circles = cv2.HoughCircles(edges, cv2.HOUGH_GRADIENT, dp=1, minDist=hoop_radius_px/2,
                                   param1=100, param2=30, minRadius=min_radius, maxRadius=max_radius)
        vis = img.copy()
        # Draw hoop
        cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (255,0,0), 2)
        cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), 2, (0,0,255), 3)
        # Draw annulus
        cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px*1.2), (0,255,255), 1)
        cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px*3.0), (0,255,255), 1)
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for i in range(circles.shape[1]):
                cx, cy, r = circles[0,i]
                cv2.circle(vis, (cx, cy), r, (0,255,0), 2)
                cv2.circle(vis, (cx, cy), 2, (0,255,255), 3)
                cv2.putText(vis, f"r={r}", (cx+10, cy-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
            print(f"Frame {frame_idx}: {circles.shape[1]} circles detected")
        else:
            print(f"Frame {frame_idx}: No circles detected")
        out_path = os.path.join(OUT_DIR, f"{fname.split('.')[0]}_hough.jpg")
        cv2.imwrite(out_path, vis)
        print(f"Saved {out_path}")

if __name__ == "__main__":
    main()