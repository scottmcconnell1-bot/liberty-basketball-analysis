#!/usr/bin/env python3
"""
Shot detection v7: Rim-based approach.
Key insight from successful basketball analysis systems:
1. Detect the rim/backboard region (large, white, static relative to court)
2. Track balls passing through the rim region
3. Make/miss: dual validation - trajectory through rim center + net motion after

This is how commercial systems like Second Spectrum, Noah, etc. work.
They detect the RIM, not the ball.
"""

import cv2
import numpy as np
import csv
import os

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
HOOP_PATH = "hoop_Q1.npy"
OUT_CSV = "shots_v7.csv"
OUT_DIR = "v7_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2

# Physical constants (feet)
HOOP_HEIGHT_FT = 10.0
HOOP_INNER_RADIUS_FT = 0.75  # 9 inch radius
BACKBOARD_WIDTH_FT = 6.0
BACKBOARD_HEIGHT_FT = 4.0
BASKET_X_FROM_FT_LINE = 4.0  # basket center is 4ft from baseline

# Court dimensions
COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0
THREE_PT_RADIUS_FT = 22.0  # corner 3PT distance
THREE_PT_ARC_RADIUS_FT = 23.75  # NBA 3PT arc radius
FT_LINE_FT = 19.0  # free throw line distance from baseline
FT_CIRCLE_RADIUS_FT = 6.0

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    frame_data = {}
    for i, f in enumerate(data['frame_indices']):
        r = data['radii'][i]
        if r > 0:
            frame_data[f] = {
                'center': data['centers'][i],
                'radius_px': r,
                'ft_per_px': HOOP_INNER_RADIUS_FT / r
            }
    return frame_data

def get_hoop(frame_idx, hoop_data):
    if frame_idx in hoop_data:
        return hoop_data[frame_idx]
    # nearest
    available = sorted(hoop_data.keys())
    nearest = min(available, key=lambda f: abs(f - frame_idx))
    return hoop_data[nearest]

def detect_rim_region(frame, hoop_info):
    """
    Detect the rim/backboard region more precisely.
    The hoop detection from HoughCircles gives us an approximate region.
    Now refine it by looking for the white rim specifically.
    Returns: (rim_center_px, rim_radius_px, backboard_bbox) or None
    """
    cx, cy = hoop_info['center']
    r = hoop_info['radius_px']
    h, w = frame.shape[:2]
    
    # ROI around detected hoop
    margin = int(r * 0.8)
    x1 = max(0, int(cx) - int(r) - margin)
    y1 = max(0, int(cy) - int(r) - margin)
    x2 = min(w, int(cx) + int(r) + margin)
    y2 = min(h, int(cy) + int(r) + margin)
    
    if x2 <= x1 or y2 <= y1:
        return None
    
    roi = frame[y1:y2, x1:x2]
    
    # Detect white rim using color
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # White detection: low saturation, high value
    white_mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([180, 30, 255]))
    
    # Also detect orange rim (some rims are orange)
    orange_mask = cv2.inRange(hsv, np.array([10, 100, 100]), np.array([30, 255, 255]))
    
    combined = cv2.bitwise_or(white_mask, orange_mask)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, np.ones((5,5), np.uint8))
    
    # Find circles in the rim region
    circles = cv2.HoughCircles(combined, cv2.HOUGH_GRADIENT, dp=1, minDist=int(r*0.5),
                                param1=50, param2=20,
                                minRadius=int(r*0.5), maxRadius=int(r*1.5))
    
    if circles is not None:
        # Take the circle closest to the expected hoop center
        best_c = None
        best_dist = float('inf')
        for c in circles[0]:
            ccx, ccy = c[0] + x1, c[1] + y1
            dist = np.sqrt((ccx - cx)**2 + (ccy - cy)**2)
            if dist < best_dist:
                best_dist = dist
                best_c = (ccx, ccy, c[2])
        if best_c:
            return {'rim_center': (best_c[0], best_c[1]), 'rim_radius': best_c[2],
                    'roi': (x1, y1, x2, y2)}
    
    # Fallback to the HoughCircle detection
    return {'rim_center': (cx, cy), 'rim_radius': r, 'roi': (x1, y1, x2, y2)}

def detect_ball_near_rim(frame, rim_info, hoop_info):
    """
    Detect the basketball in the vicinity of the rim.
    Uses color, size, and shape filtering within the rim ROI.
    Returns ball position and size, or None.
    """
    x1, y1, x2, y2 = rim_info['roi']
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Orange/brown ball
    mask = cv2.inRange(hsv, np.array([8, 80, 80]), np.array([30, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    rim_cx, rim_cy = rim_info['rim_center']
    rim_r = rim_info['rim_radius']
    
    best_ball = None
    best_score = -999
    
    for c in contours:
        a = cv2.contourArea(c)
        if a < 8 or a > 1000:
            continue
        (bx, by), br = cv2.minEnclosingCircle(c)
        bd = 2 * br
        if not (5 <= bd <= 40):
            continue
        
        # Position relative to rim (full frame coords)
        full_bx = bx + x1
        full_by = by + y1
        
        # Distance from rim center
        dist_from_rim = np.sqrt((full_bx - rim_cx)**2 + (full_by - rim_cy)**2)
        
        # Score: prefer balls near the rim center, ball-sized, circular
        dist_score = max(0, 1.0 - dist_from_rim / (rim_r * 2))
        circ_score = a / (np.pi * br * br) if br > 0 else 0
        size_score = 1.0 - abs(bd - 12) / 12  # prefer ~12px diameter
        
        score = 0.4 * dist_score + 0.3 * circ_score + 0.3 * size_score
        
        if score > best_score:
            best_score = score
            best_ball = {
                'cx': full_bx, 'cy': full_by, 'diam': bd,
                'dist_from_rim': dist_from_rim, 'score': score,
                'in_rim': dist_from_rim < rim_r
            }
    
    return best_ball

def detect_net_motion(frame_prev, frame_curr, rim_info):
    """
    Detect pixel-level motion inside the net region.
    This is the key signal for make/miss classification.
    A made shot = ball passes through rim = net moves (swings).
    """
    if frame_prev is None or frame_curr is None:
        return 0.0
    
    x1, y1, x2, y2 = rim_info['roi']
    h, w = frame_curr.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
    
    # Net region is BELOW the rim
    rim_cy = rim_info['rim_center'][1]
    rim_r = rim_info['rim_radius']
    
    net_y1 = int(rim_cy + rim_r * 0.3)
    net_y2 = int(rim_cy + rim_r * 2.0)
    net_x1 = int(rim_info['rim_center'][0] - rim_r * 0.8)
    net_x2 = int(rim_info['rim_center'][0] + rim_r * 0.8)
    
    net_y1 = max(0, net_y1)
    net_y2 = min(h, net_y2)
    net_x1 = max(0, net_x1)
    net_x2 = min(w, net_x2)
    
    if net_y2 <= net_y1 or net_x2 <= net_x1:
        return 0.0
    
    prev_net = cv2.cvtColor(frame_prev[net_y1:net_y2, net_x1:net_x2], cv2.COLOR_BGR2GRAY)
    curr_net = cv2.cvtColor(frame_curr[net_y1:net_y2, net_x1:net_x2], cv2.COLOR_BGR2GRAY)
    
    if prev_net.shape != curr_net.shape:
        return 0.0
    
    # Frame difference
    diff = cv2.absdiff(prev_net, curr_net)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    
    # Exclude the ball region (top of net area where ball might be)
    # Only count motion in the LOWER part of the net (ball had passed through)
    lower_start = int(thresh.shape[0] * 0.4)
    lower_thresh = thresh[lower_start:, :]
    
    motion = np.count_nonzero(lower_thresh) / lower_thresh.size
    
    return motion

def main():
    hoop_data = load_hoop()
    print(f"Hoop data: {len(hoop_data)} frames")
    
    cap = cv2.VideoCapture(VIDEO_PATH)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    frame_idx = 0
    prev_frame = None
    
    # Detection log
    rim_detections = []  # frames where rim detected
    ball_near_rim = []   # frames where ball detected near rim
    net_motion_scores = []  # net motion per frame
    shot_candidates = []  # potential shot events
    
    vis_saved = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        if frame_idx % STRIDE != 0:
            frame_idx += 1; continue
        
        hp = get_hoop(frame_idx, hoop_data)
        h, w = frame.shape[:2]
        
        # Detect rim region
        rim = detect_rim_region(frame, hp)
        
        if rim:
            rim_detections.append(frame_idx)
            
            # Detect ball near rim
            ball = detect_ball_near_rim(frame, rim, hp)
            
            if ball and ball['score'] > 0.3:
                ball_near_rim.append({
                    'frame': frame_idx,
                    'cx': ball['cx'], 'cy': ball['cy'],
                    'diam': ball['diam'],
                    'dist_from_rim': ball['dist_from_rim'],
                    'score': ball['score'],
                    'in_rim': ball['in_rim'],
                    'rim_cx': rim['rim_center'][0],
                    'rim_cy': rim['rim_center'][1],
                    'rim_r': rim['rim_radius']
                })
            
            # Detect net motion
            net_motion = detect_net_motion(prev_frame, frame, rim)
            net_motion_scores.append({'frame': frame_idx, 'motion': round(net_motion, 4)})
            
            # Shot candidate: ball in rim region + net motion
            if net_motion > 0.05:
                shot_candidates.append({
                    'frame': frame_idx,
                    'net_motion': round(net_motion, 4),
                    'ball': ball,
                    'rim_cx': rim['rim_center'][0],
                    'rim_cy': rim['rim_center'][1]
                })
        
        # Save vis
        if vis_saved < 30 and frame_idx % (STRIDE * 150) == 0 and rim:
            vis = frame.copy()
            rcx, rcy = int(rim['rim_center'][0]), int(rim['rim_center'][1])
            rr = int(rim['rim_radius'])
            cv2.circle(vis, (rcx, rcy), rr, (255, 0, 0), 2)
            if ball:
                cv2.circle(vis, (int(ball['cx']), int(ball['cy'])), int(ball['diam']/2), (0, 255, 0), 2)
            cv2.putText(vis, f"F:{frame_idx} rim={len(rim_detections)} ball={len(ball_near_rim)} shots={len(shot_candidates)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imwrite(f"{OUT_DIR}/f{frame_idx:05d}.jpg", vis)
            vis_saved += 1
        
        prev_frame = frame.copy()
        
        if frame_idx % (STRIDE * 300) == 0:
            print(f"F{frame_idx}: rim={len(rim_detections)} ball_near={len(ball_near_rim)} candidates={len(shot_candidates)}")
        
        frame_idx += 1
    
    cap.release()
    
    print(f"\n=== Results ===")
    print(f"Rim detections: {len(rim_detections)}")
    print(f"Ball near rim: {len(ball_near_rim)}")
    print(f"Shot candidates (net motion): {len(shot_candidates)}")
    
    # Print shot candidates
    if shot_candidates:
        print(f"\nShot candidates:")
        # Merge candidates within 20 frames
        merged = []
        i = 0
        while i < len(shot_candidates):
            group = [shot_candidates[i]]
            j = i + 1
            while j < len(shot_candidates) and shot_candidates[j]['frame'] - group[-1]['frame'] < 20:
                group.append(shot_candidates[j]); j += 1
            best = max(group, key=lambda s: s['net_motion'])
            merged.append(best)
            i = j
        
        print(f"Merged: {len(merged)} shots")
        for s in merged[:30]:
            ball_str = f"ball=({s['ball']['cx']:.0f},{s['ball']['cy']:.0f})" if s['ball'] else "no_ball"
            print(f"  F{s['frame']:4d}: net_motion={s['net_motion']:.3f} rim=({s['rim_cx']:.0f},{s['rim_cy']:.0f}) {ball_str}")
    
    # Save ball near rim data
    if ball_near_rim:
        with open(OUT_CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['frame','cx','cy','diam','dist_from_rim','score','in_rim','rim_cx','rim_cy','rim_r'])
            w.writeheader()
            for b in ball_near_rim:
                w.writerow(b)
        print(f"\nSaved ball-near-rim data to {OUT_CSV}")

if __name__ == "__main__":
    main()
