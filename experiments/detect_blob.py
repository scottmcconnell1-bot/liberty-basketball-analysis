#!/usr/bin/env python3
"""
Blob-based ball detection using colour masking and hoop ROI.
- For each frame, get hoop centre and radius from hoop_Q1.npy (interpolated if needed).
- Define ROI around hoop (±4 ft horizontally, ±6 ft vertically).
- Convert to HSV, mask orange/brown.
- Find contours, filter by area, aspect ratio, solidity.
- Optionally apply size filter based on hoop radius.
- Output detections as CSV: frame, x_center, y_center, width, height, confidence (proxy).
"""

import cv2
import numpy as np
import os
import csv

HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"  # change to full video frames later
OUTPUT_CSV = "sample_frames_blob_detections.csv"
VIS_DIR = "sample_frames_blob_vis"
os.makedirs(VIS_DIR, exist_ok=True)

# Colour ranges in HSV (OpenCV H 0-180)
ORANGE_LOW = np.array([10, 150, 150])
ORANGE_HIGH = np.array([30, 255, 255])
BROWN_LOW = np.array([0, 80, 80])
BROWN_HIGH = np.array([20, 150, 150])

# ROI in feet
HALF_WIDTH_FT = 4.0   # left/right of hoop
HALF_HEIGHT_FT = 6.0  # up/down of hoop

# Known hoop inner radius (ft)
HOOP_RADIUS_FT = 0.75
# Basketball diameter ft
BALL_DIAM_FT = 0.79   # ~9.5 inches

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

def process_frame(frame_idx, bgr, hoop_center, hoop_radius_px):
    # Compute ft per px from hoop radius
    if hoop_radius_px <= 0:
        ft_per_px = 0.005  # fallback
    else:
        ft_per_px = HOOP_RADIUS_FT / hoop_radius_px
    
    # ROI in pixels
    half_w_px = HALF_WIDTH_FT / ft_per_px
    half_h_px = HALF_HEIGHT_FT / ft_per_px
    
    x1 = int(max(0, hoop_center[0] - half_w_px))
    y1 = int(max(0, hoop_center[1] - half_h_px))
    x2 = int(min(bgr.shape[1]-1, hoop_center[0] + half_w_px))
    y2 = int(min(bgr.shape[0]-1, hoop_center[1] + half_h_px))
    
    roi = bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return []
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask_orange = cv2.inRange(hsv, ORANGE_LOW, ORANGE_HIGH)
    mask_brown = cv2.inRange(hsv, BROWN_LOW, BROWN_HIGH)
    mask = cv2.bitwise_or(mask_orange, mask_brown)
    
    # Optional: morphological opening to remove noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 10:  # too small
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        # aspect ratio
        if w == 0 or h == 0:
            continue
        aspect = w / h
        if not (0.7 <= aspect <= 1.3):
            continue
        # size filter: expected ball diameter in px
        expected_diam_px = hoop_radius_px * (BALL_DIAM_FT / HOOP_RADIUS_FT) * 2.0  # radius to diameter? Actually hoop_radius_px is radius, so diameter_px = 2 * hoop_radius_px * (BALL_DIAM_FT/HOOP_RADIUS_FT)
        # Simpler: scale ft/px to get ball diameter px
        diam_px = BALL_DIAM_FT / ft_per_px
        if not (0.5 * diam_px <= w <= 1.5 * diam_px and 0.5 * diam_px <= h <= 1.5 * diam_px):
            continue
        # solidity (area / convex hull area) to avoid elongated noise
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            continue
        solidity = area / hull_area
        if solidity < 0.5:
            continue
        
        # Convert to full-frame coordinates
        fx1 = x1 + x
        fy1 = y1 + y
        fx2 = x1 + x + w
        fy2 = y1 + y + h
        
        detections.append({
            'frame': frame_idx,
            'x': fx1, 'y': fy1, 'w': w, 'h': h,
            'xc': fx1 + w/2, 'yc': fy1 + h/2,
            'area': area,
            'conf': 1.0  # placeholder
        })
        
        # Draw on vis image
        cv2.rectangle(bgr, (fx1, fy1), (fx2, fy2), (0,255,0), 2)
        cv2.putText(bgr, f"{area:.0f}", (fx1, fy1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
    
    # Draw hoop centre and radius
    cv2.circle(bgr, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (255,0,0), 2)
    cv2.circle(bgr, (int(hoop_center[0]), int(hoop_center[1])), 3, (0,0,255), -1)
    # Draw ROI rectangle
    cv2.rectangle(bgr, (x1, y1), (x2, y2), (255,255,0), 1)
    
    return detections, bgr

def main():
    frame_indices, centers, radii = load_hoop()
    print(f"Loaded hoop data for {len(frame_indices)} frames")
    
    # For sample frames, we just process the files in FRAME_DIR
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])
    all_detections = []
    
    for fname in files:
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        bgr = cv2.imread(path)
        if bgr is None:
            print(f"Failed to load {path}")
            continue
        
        hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, frame_indices, centers, radii)
        detections, vis = process_frame(frame_idx, bgr.copy(), hoop_center, hoop_radius_px)
        
        for det in detections:
            all_detections.append(det)
        
        out_path = os.path.join(VIS_DIR, f"{fname.split('.')[0]}_blob.jpg")
        cv2.imwrite(out_path, vis)
        print(f"Frame {frame_idx}: {len(detections)} detections -> saved {out_path}")
    
    # Write CSV
    with open(OUTPUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['frame','xc','yc','w','h','area','conf'])
        writer.writeheader()
        for d in all_detections:
            writer.writerow({
                'frame': d['frame'],
                'xc': d['xc'],
                'yc': d['yc'],
                'w': d['w'],
                'h': d['h'],
                'area': d['area'],
                'conf': d['conf']
            })
    print(f"Saved {len(all_detections)} detections to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()