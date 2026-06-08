#!/usr/bin/env python3
"""
Ball detection via color masking in hoop-centered ROI.
- Uses hoop center and radius from hoop_Q1.npy (nearest frame).
- Defines ROI in feet around hoop (configurable).
- Masks orange/brown pixels in HSV.
- Finds contours, filters by size (based on hoop radius), aspect, solidity.
- Selects best contour (closest to expected area) as ball detection.
- Outputs CSV and visualizations.
"""

import cv2
import numpy as np
import os
import csv

HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"
OUT_DIR = "sample_frames_color_roi"
OUT_CSV = "sample_frames_color_roi_detections.csv"
os.makedirs(OUT_DIR, exist_ok=True)

# Hoop constants
HOOP_RADIUS_FT = 0.75   # inner radius
BALL_DIAM_FT = 0.79     # approx 9.5 inches

# ROI in feet (adjust as needed)
HALF_WIDTH_FT = 8.0   # left/right of hoop
HALF_HEIGHT_FT = 10.0 # up/down of hoop

# Color ranges in HSV (OpenCV H 0-180, S 0-255, V 0-255)
# Orange/brown: we'll use a broad hue range 0-20, with saturation and value thresholds to avoid dark shadows and bright whites.
HUE_LOW = 0
HUE_HIGH = 20
SAT_MIN = 100
VAL_MIN = 100
VAL_MAX = 250  # exclude very bright (glare)

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    frame_indices = data['frame_indices']   # 1D array
    centers = data['centers']               # (N,2)
    radii = data['radii']                   # (N,)
    return frame_indices, centers, radii

def get_hoop(frame_idx, frame_indices, centers, radii):
    # nearest frame index
    idx = np.argmin(np.abs(frame_indices - frame_idx))
    return centers[idx], radii[idx], frame_indices[idx]

def detect_ball_in_frame(bgr, hoop_center, hoop_radius_px):
    # Compute scale: ft per pixel from hoop radius
    if hoop_radius_px <= 0:
        ft_per_px = 0.005  # fallback
    else:
        ft_per_px = HOOP_RADIUS_FT / hoop_radius_px
    
    # Expected ball diameter in pixels
    expected_diam_px = BALL_DIAM_FT / ft_per_px
    # Min and max diameter as multiples of hoop radius (to account for depth variation)
    min_diam_px = 0.5 * hoop_radius_px
    max_diam_px = 2.0 * hoop_radius_px
    
    # ROI in pixels
    half_w_px = HALF_WIDTH_FT / ft_per_px
    half_h_px = HALF_HEIGHT_FT / ft_per_px
    
    x1 = int(max(0, hoop_center[0] - half_w_px))
    y1 = int(max(0, hoop_center[1] - half_h_px))
    x2 = int(min(bgr.shape[1]-1, hoop_center[0] + half_w_px))
    y2 = int(min(bgr.shape[0]-1, hoop_center[1] + half_h_px))
    
    roi = bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return None, None
    
    # Convert to HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Mask orange/brown
    mask = cv2.inRange(hsv, 
                       np.array([HUE_LOW, SAT_MIN, VAL_MIN]), 
                       np.array([HUE_HIGH, 255, VAL_MAX]))
    
    # Optional: morphological opening to remove noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_contour = None
    best_score = float('inf')
    expected_area = np.pi * (expected_diam_px/2)**2
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 10:
            continue
        # Approximate circle to get diameter
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        diam_est = 2 * radius
        if diam_est < min_diam_px or diam_est > max_diam_px:
            continue
        # Aspect ratio of bounding rectangle
        rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(cnt)
        if rect_w == 0 or rect_h == 0:
            continue
        aspect = rect_w / rect_h
        if not (0.7 <= aspect <= 1.3):
            continue
        # Solidity (area / convex hull area)
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            continue
        solidity = area / hull_area
        if solidity < 0.5:
            continue
        # Score: closeness to expected area
        score = abs(area - expected_area)
        if score < best_score:
            best_score = score
            best_contour = cnt
    
    if best_contour is None:
        return None, None
    
    # Get bounding box of best contour
    x, y, w, h = cv2.boundingRect(best_contour)
    # Convert to full-frame coordinates
    fx1 = x1 + x
    fy1 = y1 + y
    fx2 = x1 + x + w
    fy2 = y1 + y + h
    
    # Draw on a copy for visualization
    vis = bgr.copy()
    cv2.rectangle(vis, (fx1, fy1), (fx2, fy2), (0,255,0), 2)
    cv2.putText(vis, f"Area:{int(cv2.contourArea(best_contour))}", (fx1, fy1-5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
    # Draw hoop center and radius
    cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (255,0,0), 2)
    cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), 3, (0,0,255), -1)
    # Draw ROI rectangle
    cv2.rectangle(vis, (x1, y1), (x2, y2), (255,255,0), 1)
    
    return (fx1, fy1, fx2, fy2), vis

def main():
    frame_indices, centers, radii = load_hoop()
    print(f"Loaded hoop data for {len(frame_indices)} frames")
    
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])
    all_detections = []
    
    for fname in files:
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            print(f"Failed to load {path}")
            continue
        
        hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, frame_indices, centers, radii)
        det, vis = detect_ball_in_frame(img, hoop_center, hoop_radius_px)
        
        if det is not None:
            x1, y1, x2, y2 = det
            xc = (x1 + x2) / 2.0
            yc = (y1 + y2) / 2.0
            w = x2 - x1
            h = y2 - y1
            all_detections.append({
                'frame': frame_idx,
                'xc': xc,
                'yc': yc,
                'w': w,
                'h': h,
                'conf': 1.0  # placeholder
            })
            if vis is not None:
                out_path = os.path.join(OUT_DIR, f"{fname.split('.')[0]}_det.jpg")
                cv2.imwrite(out_path, vis)
                print(f"Frame {frame_idx}: detection saved -> {out_path}")
        else:
            print(f"Frame {frame_idx}: No detection")
    
    # Write CSV
    with open(OUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['frame','xc','yc','w','h','conf'])
        writer.writeheader()
        for d in all_detections:
            writer.writerow({
                'frame': d['frame'],
                'xc': d['xc'],
                'yc': d['yc'],
                'w': d['w'],
                'h': d['h'],
                'conf': d['conf']
            })
    print(f"Saved {len(all_detections)} detections to {OUT_CSV}")

if __name__ == "__main__":
    main()