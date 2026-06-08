#!/usr/bin/env python3
"""
Ball detection using motion (background subtraction) + color + trajectory.
- Uses MOG2 background subtractor to find moving objects.
- Within motion mask, filter by orange/brown color and circular shape.
- Track across frames using Kalman filter / nearest neighbor.
- The ball is the orange-brown moving object with parabolic trajectory.
- Outputs CSV and visualizations.
"""

import cv2
import numpy as np
import os
import csv

FRAME_DIR = "sample_frames"
OUT_DIR = "sample_frames_motion"
OUT_CSV = "sample_frames_motion_detections.csv"
os.makedirs(OUT_DIR, exist_ok=True)

# Color ranges in HSV (OpenCV H 0-180, S 0-255, V 0-255)
HUE_LOW = 0
HUE_HIGH = 25   # slightly wider to catch faded/dirty ball
SAT_MIN = 60    # lowered to catch less vibrant ball
VAL_MIN = 60
VAL_MAX = 255

# Background subtractor
BG_HISTORY = 100
BG_THRESHOLD = 16
DETECT_SHADOWS = False

def fg_mask(bgr, bg_subtractor):
    """Get foreground mask, clean it up."""
    mask = bg_subtractor.apply(bgr)
    # Morphological operations to clean
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    # Dilate slightly to capture full ball
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask

def detect_moving_orange(bgr, fg_mask_img):
    """Within foreground mask, find orange/brown blobs."""
    # Color mask
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    color_mask = cv2.inRange(hsv,
                             np.array([HUE_LOW, SAT_MIN, VAL_MIN]),
                             np.array([HUE_HIGH, 255, VAL_MAX]))
    
    # Combine: must be both moving AND orange/brown
    combined = cv2.bitwise_and(fg_mask_img, color_mask)
    
    # Find contours
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    detections = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 15:
            continue
        # Shape filter
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        diam = 2 * radius
        # Accept diameter 8-150 px (wide range for moving ball)
        if not (8 <= diam <= 150):
            continue
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        if rw == 0 or rh == 0:
            continue
        aspect = rw / rh
        if not (0.5 <= aspect <= 1.5):
            continue
        # Solidity
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            continue
        solidity = area / hull_area
        if solidity < 0.3:  # lower threshold for motion-blurred ball
            continue
        # Circularity: area / (pi * r^2)
        circularity = area / (np.pi * radius * radius) if radius > 0 else 0
        if circularity < 0.2:  # lenient for motion blur
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        detections.append({
            'cx': cx, 'cy': cy,
            'area': area, 'diam': diam,
            'circularity': circularity,
            'solidity': solidity,
            'bbox': (rx, ry, rw, rh),
            'cnt': cnt
        })
    return detections, combined

def track_detections(prev_tracks, curr_dets, max_dist=60):
    """Simple nearest-neighbor tracking."""
    if not prev_tracks:
        new_tracks = []
        for det in curr_dets:
            new_tracks.append({'positions': [(det['cx'], det['cy'])],
                               'det': det, 'age': 1, 'hits': 1})
        return new_tracks
    # Cost matrix
    costs = []
    for pt in prev_tracks:
        px, py = pt['positions'][-1]
        row = []
        for det in curr_dets:
            d = np.sqrt((px - det['cx'])**2 + (py - det['cy'])**2)
            row.append(d)
        costs.append(row)
    costs = np.array(costs) if costs else np.empty((0, len(curr_dets)))
    # Greedy match
    used_det = set()
    matched_tracks = []
    used_tracks = set()
    if costs.size > 0:
        flat = [(costs[i,j], i, j) for i in range(costs.shape[0]) for j in range(costs.shape[1])]
        flat.sort()
        for c, i, j in flat:
            if i in used_tracks or j in used_det:
                continue
            if c > max_dist:
                break
            prev_tracks[i]['positions'].append((curr_dets[j]['cx'], curr_dets[j]['cy']))
            prev_tracks[i]['det'] = curr_dets[j]
            prev_tracks[i]['hits'] += 1
            prev_tracks[i]['age'] += 1
            matched_tracks.append(prev_tracks[i])
            used_tracks.add(i)
            used_det.add(j)
    # Unmatched tracks: keep aging
    for i, pt in enumerate(prev_tracks):
        if i not in used_tracks:
            pt['age'] += 1
            matched_tracks.append(pt)
    # New detections -> new tracks
    for j, det in enumerate(curr_dets):
        if j not in used_det:
            matched_tracks.append({'positions': [(det['cx'], det['cy'])],
                                   'det': det, 'age': 1, 'hits': 1})
    return matched_tracks

def main():
    files = sorted([f for f in os.listdir(FRAME_DIR) 
                    if f.endswith('.jpg') 
                    and 'frame_' in f 
                    and not f.endswith('_det.jpg') 
                    and not f.endswith('_det_orange.jpg') 
                    and not f.endswith('_orange.jpg')])
    # Also pick unique base frames
    seen = set()
    unique_files = []
    for f in files:
        base = f.replace('_det', '').replace('_orange', '').replace('.jpg', '')
        if base not in seen:
            seen.add(base)
            unique_files.append(f)
    files = sorted(unique_files)
    
    print(f"Processing {len(files)} unique frames")
    
    bg = cv2.createBackgroundSubtractorMOG2(history=BG_HISTORY,
                                              varThreshold=BG_THRESHOLD,
                                              detectShadows=DETECT_SHADOWS)
    
    all_detections = []
    tracks = []
    
    for fname in files:
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        
        # For background subtraction, we need multiple frames. 
        # Feed current frame multiple times to stabilize, or just apply.
        fg = fg_mask(img, bg)
        dets, combined = detect_moving_orange(img, fg)
        
        # Track
        tracks = track_detections(tracks, dets, max_dist=60)
        
        # Store detections from tracks that have at least 1 hit this frame
        for t in tracks:
            if t['age'] <= 3 and t['hits'] >= 1:  # recent tracks
                d = t['det']
                all_detections.append({
                    'frame': frame_idx,
                    'xc': d['cx'],
                    'yc': d['cy'],
                    'diam': d['diam'],
                    'area': d['area'],
                    'circularity': d['circularity'],
                    'track_hits': t['hits'],
                    'track_age': t['age'],
                    'conf': d['circularity']
                })
        
        # Visualize
        vis = img.copy()
        # Draw motion mask as overlay
        motion_overlay = np.zeros_like(img)
        motion_overlay[fg > 0] = [255, 255, 255]
        vis = cv2.addWeighted(vis, 1.0, motion_overlay, 0.2, 0)
        
        # Draw detections
        for d in dets:
            cv2.circle(vis, (int(d['cx']), int(d['cy'])), int(d['diam']/2), (0,255,0), 2)
            cv2.putText(vis, f"c:{d['circularity']:.2f}", (int(d['cx'])-20, int(d['cy'])-int(d['diam']/2)-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1)
        
        # Draw track trajectories
        for t in tracks:
            if t['hits'] >= 1:
                pts = t['positions']
                if len(pts) > 1:
                    # Color by age
                    color = (0, 255, 255) if t['hits'] >= 2 else (0, 128, 255)
                    for k in range(1, len(pts)):
                        cv2.line(vis, (int(pts[k-1][0]), int(pts[k-1][1])),
                                 (int(pts[k][0]), int(pts[k][1])), color, 1)
        
        out_path = os.path.join(OUT_DIR, f"frame_{frame_idx:03d}_motion.jpg")
        cv2.imwrite(out_path, vis)
        
        # Save combined mask
        combined_bgr = cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
        mask_path = os.path.join(OUT_DIR, f"frame_{frame_idx:03d}_mask.jpg")
        cv2.imwrite(mask_path, combined_bgr)
        
        print(f"Frame {frame_idx}: {len(dets)} dets, {len([t for t in tracks if t['hits']>=1])} active tracks")
    
    # Write CSV
    if all_detections:
        with open(OUT_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['frame','xc','yc','diam','area','circularity','track_hits','track_age','conf'])
            writer.writeheader()
            for d in all_detections:
                writer.writerow(d)
        print(f"Saved {len(all_detections)} detections to {OUT_CSV}")
    else:
        print("No detections found")
    
    # Print track summary
    print(f"\nTrack summary:")
    for i, t in enumerate(tracks):
        if len(t['positions']) > 0:
            start = t['positions'][0]
            end = t['positions'][-1]
            dist = np.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
            print(f"  Track {i}: {len(t['positions'])} pts, {t['hits']} hits, moved {dist:.1f}px")

if __name__ == "__main__":
    main()
