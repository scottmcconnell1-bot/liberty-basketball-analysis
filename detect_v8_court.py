#!/usr/bin/env python3
"""
Hoop detection via court line detection.
1. Detect court lines (white lines on brown court)
2. Find the baseline (long horizontal line near the basket)
3. Compute rim position from court geometry
4. Track ball through rim region for shot detection

Court geometry (NBA/NCAA):
- Court: 94ft x 50ft
- Baseline to backboard: 4ft
- Backboard to rim center: ~1.5ft (rim extends 1.5ft from backboard)
- Rim height: 10ft
- Free throw line: 15ft from backboard (19ft from baseline)
- 3PT line: 22ft from basket center (corner)
"""

import cv2
import numpy as np
import csv
import os

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
OUT_CSV = "hoop_from_court.csv"
SHOT_CSV = "shots_v8.csv"
OUT_DIR = "v8_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2

# Court physical dimensions (ft)
COURT_W = 50.0
COURT_H = 94.0
BASELINE_TO_BACKBOARD = 4.0
BACKBOARD_TO_RIM = 1.5  # rim extends 1.5ft from backboard face
RIM_HEIGHT = 10.0
FT_LINE_FROM_BASELINE = 19.0
THREE_PT_CORNER_DIST = 22.0  # from basket center

def detect_court_lines(frame):
    """
    Detect white court lines on the brown court.
    Returns list of line segments [(x1,y1,x2,y2), ...]
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = frame.shape[:2]
    
    # Court lines are bright white on brown
    # Use adaptive thresholding since lighting varies
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Detect bright lines
    _, bright = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Edge detection
    edges = cv2.Canny(blurred, 50, 150)
    
    # Combine: edges that are also bright
    line_mask = cv2.bitwise_and(edges, bright)
    
    # Morphological: connect broken line segments
    kernel_h = np.ones((1, 15), np.uint8)  # horizontal connector
    kernel_v = np.ones((15, 1), np.uint8)  # vertical connector
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_CLOSE, kernel_h, iterations=2)
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_CLOSE, kernel_v, iterations=1)
    
    # Hough line detection
    lines = cv2.HoughLinesP(line_mask, rho=1, theta=np.pi/180, 
                             threshold=50, minLineLength=w//8, maxLineGap=20)
    
    if lines is None:
        return []
    
    result = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
        angle = np.degrees(np.arctan2(y2-y1, x2-x1)) % 180
        
        # Filter: court lines are either horizontal (baseline, FT line) or vertical (sidelines)
        is_horizontal = abs(angle) < 15 or abs(angle - 180) < 15
        is_vertical = abs(angle - 90) < 15
        
        if length > w // 10 and (is_horizontal or is_vertical):
            result.append((x1, y1, x2, y2, angle, length))
    
    return result

def find_baseline_and_hoop(lines, frame_shape):
    """
    From detected court lines, find the baseline and compute hoop position.
    The baseline is the long horizontal line closest to the basket area.
    """
    h, w = frame_shape[:2]
    
    if not lines:
        return None
    
    # Separate horizontal and vertical lines
    h_lines = [(x1,y1,x2,y2,length) for x1,y1,x2,y2,angle,length in lines 
               if abs(angle) < 15 or abs(angle-180) < 15]
    v_lines = [(x1,y1,x2,y2,length) for x1,y1,x2,y2,angle,length in lines 
               if abs(angle-90) < 15]
    
    if not h_lines:
        return None
    
    # The baseline is typically the longest horizontal line in the lower portion
    # But with ceiling camera, it could be anywhere
    # Sort by length
    h_lines.sort(key=lambda x: -x[4])
    
    # Take the top 3 longest horizontal lines
    candidates = h_lines[:3]
    
    # The baseline is the one closest to the bottom of the frame (in most camera angles)
    # But with ceiling mount, we need to be smarter
    # Use the longest horizontal line as baseline
    bl = candidates[0]
    bx1, by1, bx2, by2, blength = bl
    
    # Baseline center
    baseline_cx = (bx1 + bx2) / 2
    baseline_cy = (by1 + by2) / 2
    
    # Determine which side of the court this baseline is on
    # The hoop is INWARD from the baseline (toward center court)
    # If baseline is in the lower half of frame, hoop is above it
    # If baseline is in the upper half, hoop is below it
    
    if baseline_cy > h * 0.5:
        # Baseline in lower half → hoop is above (toward top of frame)
        hoop_direction = -1
    else:
        # Baseline in upper half → hoop is below
        hoop_direction = 1
    
    # Find the sideline (vertical line) closest to the baseline center
    # This tells us which basket (left or right side)
    nearest_v = None
    nearest_v_dist = float('inf')
    for vx1, vy1, vx2, vy2, vlength in v_lines:
        v_cx = (vx1 + vx2) / 2
        dist = abs(v_cx - baseline_cx)
        if dist < nearest_v_dist:
            nearest_v_dist = dist
            nearest_v = (vx1, vy1, vx2, vy2)
    
    # Estimate hoop position
    # From baseline, the hoop is ~5.5ft inward (4ft to backboard + 1.5ft to rim)
    # In pixel terms, we need to estimate the scale
    # Court width is 50ft, which spans roughly the frame width
    ft_per_px = COURT_W / w
    
    hoop_offset_px = (BASELINE_TO_BACKBOARD + BACKBOARD_TO_RIM) / ft_per_px
    
    hoop_x = baseline_cx
    hoop_y = baseline_cy + hoop_direction * hoop_offset_px
    
    # If we have a sideline, the hoop is between the sideline and center
    if nearest_v:
        v_cx = (nearest_v[0] + nearest_v[2]) / 2
        # The basket is roughly 1/4 court width from the sideline
        court_quarter = w / 4
        if abs(baseline_cx - v_cx) < court_quarter:
            # This baseline is near a sideline → hoop is toward center from baseline
            if baseline_cx < v_cx:
                hoop_x = baseline_cx + court_quarter
            else:
                hoop_x = baseline_cx - court_quarter
    
    # Estimate rim radius in pixels
    # Rim diameter = 18 inches = 1.5ft
    rim_radius_px = (1.5 / 2) / ft_per_px
    
    return {
        'baseline': (bx1, by1, bx2, by2),
        'hoop_x': int(hoop_x),
        'hoop_y': int(hoop_y),
        'rim_radius': int(rim_radius_px),
        'ft_per_px': ft_per_px,
        'sideline': nearest_v,
        'h_lines': h_lines[:5],
        'v_lines': v_lines[:5]
    }

def detect_ball_near_hoop(frame, hoop_info):
    """Detect basketball near the computed hoop position."""
    hx, hy = hoop_info['hoop_x'], hoop_info['hoop_y']
    hr = hoop_info['rim_radius']
    h, w = frame.shape[:2]
    
    # ROI around hoop
    margin = int(hr * 3)
    x1 = max(0, hx - margin)
    y1 = max(0, hy - margin)
    x2 = min(w, hx + margin)
    y2 = min(h, hy + margin)
    
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([8, 80, 80]), np.array([30, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best = None
    best_score = -1
    
    for c in contours:
        a = cv2.contourArea(c)
        if a < 8 or a > 1000: continue
        (bx, by), br = cv2.minEnclosingCircle(c)
        bd = 2 * br
        if not (5 <= bd <= 40): continue
        
        full_bx = bx + x1
        full_by = by + y1
        dist = np.sqrt((full_bx - hx)**2 + (full_by - hy)**2)
        
        dist_score = max(0, 1.0 - dist / (hr * 2))
        circ = a / (np.pi * br * br) if br > 0 else 0
        score = 0.5 * dist_score + 0.3 * circ + 0.2 * min(1, a / 50)
        
        if score > best_score:
            best_score = score
            best = {'cx': full_bx, 'cy': full_by, 'diam': bd,
                    'dist_from_hoop': dist, 'score': score,
                    'in_hoop': dist < hr}
    
    return best

def detect_net_motion(frame_prev, frame_curr, hoop_info):
    """Detect motion in net region below the rim."""
    if frame_prev is None or frame_curr is None:
        return 0.0
    
    hx, hy = hoop_info['hoop_x'], hoop_info['hoop_y']
    hr = hoop_info['rim_radius']
    h, w = frame_curr.shape[:2]
    
    # Net ROI: below rim
    net_x1 = max(0, hx - int(hr * 0.8))
    net_x2 = min(w, hx + int(hr * 0.8))
    net_y1 = max(0, hy + int(hr * 0.3))
    net_y2 = min(h, hy + int(hr * 2.0))
    
    if net_y2 <= net_y1 or net_x2 <= net_x1:
        return 0.0
    
    prev_net = cv2.cvtColor(frame_prev[net_y1:net_y2, net_x1:net_x2], cv2.COLOR_BGR2GRAY)
    curr_net = cv2.cvtColor(frame_curr[net_y1:net_y2, net_x1:net_x2], cv2.COLOR_BGR2GRAY)
    
    if prev_net.shape != curr_net.shape or prev_net.size == 0:
        return 0.0
    
    diff = cv2.absdiff(prev_net, curr_net)
    _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
    lower = thresh[int(thresh.shape[0]*0.3):, :]
    if lower.size == 0:
        return 0.0
    
    return np.count_nonzero(lower) / lower.size

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {total} frames")
    
    frame_idx = 0
    prev_frame = None
    
    hoop_positions = []
    ball_detections = []
    shot_candidates = []
    vis_saved = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        if frame_idx % STRIDE != 0:
            frame_idx += 1; continue
        
        # Detect court lines
        lines = detect_court_lines(frame)
        
        # Find baseline and compute hoop position
        hoop = find_baseline_and_hoop(lines, frame.shape[:2])
        
        if hoop:
            hoop_positions.append({
                'frame': frame_idx,
                'hoop_x': hoop['hoop_x'], 'hoop_y': hoop['hoop_y'],
                'rim_radius': hoop['rim_radius'], 'ft_per_px': hoop['ft_per_px'],
                'n_lines': len(lines)
            })
            
            # Detect ball near hoop
            ball = detect_ball_near_hoop(frame, hoop)
            
            if ball:
                ball_detections.append({'frame': frame_idx, **ball})
            
            # Detect net motion
            net_mot = detect_net_motion(prev_frame, frame, hoop)
            
            # Shot candidate
            if ball and ball['score'] > 0.15 and net_mot > 0.02:
                shot_candidates.append({
                    'frame': frame_idx,
                    'ball_score': ball['score'],
                    'net_motion': round(net_mot, 4),
                    'in_hoop': ball['in_hoop'],
                    'dist_from_hoop': round(ball['dist_from_hoop'], 1),
                    'diam': ball['diam'],
                    'hoop_x': hoop['hoop_x'], 'hoop_y': hoop['hoop_y']
                })
        
        # Save vis
        if vis_saved < 30 and frame_idx % (STRIDE * 150) == 0:
            vis = frame.copy()
            if hoop:
                # Draw baseline
                bl = hoop['baseline']
                cv2.line(vis, (int(bl[0]), int(bl[1])), (int(bl[2]), int(bl[3])), (255,0,0), 2)
                # Draw hoop
                cv2.circle(vis, (hoop['hoop_x'], hoop['hoop_y']), hoop['rim_radius'], (0,255,255), 2)
                cv2.circle(vis, (hoop['hoop_x'], hoop['hoop_y']), 3, (0,0,255), -1)
                # Draw all detected lines
                for x1,y1,x2,y2,angle,length in lines[:10]:
                    cv2.line(vis, (x1,y1), (x2,y2), (0,255,0), 1)
            if ball:
                cv2.circle(vis, (int(ball['cx']), int(ball['cy'])), int(ball['diam']/2), (0,255,0), 2)
            cv2.putText(vis, f"F:{frame_idx} lines={len(lines)} hoop={'Y' if hoop else 'N'} shots={len(shot_candidates)}",
                        (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
            cv2.imwrite(f"{OUT_DIR}/f{frame_idx:05d}.jpg", vis)
            vis_saved += 1
        
        prev_frame = frame.copy()
        
        if frame_idx % (STRIDE * 300) == 0:
            print(f"F{frame_idx}: lines={len(lines)} hoops={len(hoop_positions)} balls={len(ball_detections)} shots={len(shot_candidates)}")
        
        frame_idx += 1
    
    cap.release()
    
    print(f"\n=== Results ===")
    print(f"Hoop positions computed: {len(hoop_positions)}")
    print(f"Ball detections near hoop: {len(ball_detections)}")
    print(f"Shot candidates: {len(shot_candidates)}")
    
    if shot_candidates:
        # Merge within 20 frames
        shot_candidates.sort(key=lambda x: x['frame'])
        merged = []
        i = 0
        while i < len(shot_candidates):
            group = [shot_candidates[i]]
            j = i + 1
            while j < len(shot_candidates) and shot_candidates[j]['frame'] - group[-1]['frame'] < 20:
                group.append(shot_candidates[j]); j += 1
            best = max(group, key=lambda s: s['ball_score'] + s['net_motion'] * 10)
            merged.append(best)
            i = j
        
        print(f"\nMerged shots: {len(merged)}")
        for s in merged:
            print(f"  F{s['frame']:4d}: ball={s['ball_score']:.2f} net={s['net_motion']:.3f} "
                  f"in_hoop={'Y' if s['in_hoop'] else 'N'} dist={s['dist_from_hoop']:.0f}px")
        
        with open(SHOT_CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['frame','ball_score','net_motion','in_hoop','dist_from_hoop','diam','hoop_x','hoop_y'])
            w.writeheader()
            for s in merged:
                w.writerow(s)
    
    if hoop_positions:
        with open(OUT_CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['frame','hoop_x','hoop_y','rim_radius','ft_per_px','n_lines'])
            w.writeheader()
            for h in hoop_positions:
                w.writerow(h)
        print(f"\nHoop positions saved to {OUT_CSV}")

if __name__ == "__main__":
    main()
