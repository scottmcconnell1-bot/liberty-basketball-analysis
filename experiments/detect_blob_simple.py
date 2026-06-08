#!/usr/bin/env python3
"""
Detect orange-brown blobs in the whole frame, filter by size/shape, link across frames via simple nearest-neighbor.
"""

import cv2
import numpy as np
import os
import csv

FRAME_DIR = "sample_frames"
OUT_DIR = "sample_frames_blob"
OUT_CSV = "sample_frames_blob_detections.csv"
os.makedirs(OUT_DIR, exist_ok=True)

# Color ranges in HSV (OpenCV H 0-180, S 0-255, V 0-255)
HUE_LOW = 0
HUE_HIGH = 20
SAT_MIN = 80
VAL_MIN = 80
VAL_MAX = 255

def detect_blobs_in_frame(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, 
                       np.array([HUE_LOW, SAT_MIN, VAL_MIN]), 
                       np.array([HUE_HIGH, 255, VAL_MAX]))
    # Morphological opening
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 20:  # min area
            continue
        # Approximate circle
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        diam = 2 * radius
        # size filter: diameter between 10 and 100 pixels? adjust
        if not (10 <= diam <= 100):
            continue
        # aspect ratio of bounding rect
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        if rw == 0 or rh == 0:
            continue
        aspect = rw / rh
        if not (0.6 <= aspect <= 1.4):
            continue
        # solidity
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            continue
        solidity = area / hull_area
        if solidity < 0.5:
            continue
        # compute centroid
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        detections.append({
            'contour': cnt,
            'area': area,
            'centroid': (cx, cy),
            'bbox': (rx, ry, rw, rh),
            'diam': diam
        })
    return detections

def link_detections(prev_dets, curr_dets, max_dist=50):
    """Link detections from previous frame to current using nearest centroid distance."""
    if not prev_dets:
        return [(None, det) for det in curr_dets]  # all new
    if not curr_dets:
        return [(det, None) for det in prev_dets]  # all lost
    # Compute distance matrix
    prev_cent = np.array([d['centroid'] for d in prev_dets])
    curr_cent = np.array([d['centroid'] for d in curr_dets])
    dist = np.linalg.norm(prev_cent[:, np.newaxis, :] - curr_cent[np.newaxis, :, :], axis=2)
    # Simple greedy matching
    matched_prev = set()
    matched_curr = set()
    pairs = []
    # Flatten and sort by distance
    flat = [(dist[i,j], i, j) for i in range(len(prev_dets)) for j in range(len(curr_dets))]
    flat.sort(key=lambda x: x[0])
    for d, i, j in flat:
        if i in matched_prev or j in matched_curr:
            continue
        if d > max_dist:
            break
        pairs.append((prev_dets[i], curr_dets[j]))
        matched_prev.add(i)
        matched_curr.add(j)
    # Add unmatched
    for i, det in enumerate(prev_dets):
        if i not in matched_prev:
            pairs.append((det, None))
    for j, det in enumerate(curr_dets):
        if j not in matched_curr:
            pairs.append((None, det))
    return pairs

def main():
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])
    print(f"Found {len(files)} frames")
    all_detections = []  # list of dict per detection with frame
    tracks = {}  # track_id -> list of detections
    next_track_id = 0
    prev_dets = []
    for fname in files:
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        dets = detect_blobs_in_frame(img)
        print(f"Frame {frame_idx}: {len(dets)} raw blobs")
        # Link
        pairs = link_detections(prev_dets, dets, max_dist=40)
        # Update tracks
        # For simplicity, we'll just assign new track IDs for each detection in this frame
        # and not maintain tracks across frames for now.
        # We'll just save detections per frame.
        for det in dets:
            all_detections.append({
                'frame': frame_idx,
                'xc': det['centroid'][0],
                'yc': det['centroid'][1],
                'w': det['bbox'][2],
                'h': det['bbox'][3],
                'conf': 1.0
            })
        # Visualize
        vis = img.copy()
        for det in dets:
            cx, cy = det['centroid']
            cv2.circle(vis, (cx, cy), int(det['diam']/2), (0,255,0), 2)
            cv2.putText(vis, f"{int(det['area'])}", (cx-10, cy-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
        out_path = os.path.join(OUT_DIR, f"{fname.split('.')[0]}_blob.jpg")
        cv2.imwrite(out_path, vis)
        prev_dets = dets
    # Write CSV
    with open(OUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['frame','xc','yc','w','h','conf'])
        writer.writeheader()
        for d in all_detections:
            writer.writerow(d)
    print(f"Saved {len(all_detections)} detections to {OUT_CSV}")

if __name__ == "__main__":
    main()