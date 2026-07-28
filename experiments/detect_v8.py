#!/usr/bin/env python3
"""
Shot detection v8: Backboard detection approach.
The backboard is a white rectangle that's much easier to detect than the rim.
Strategy:
1. Detect the white backboard rectangle in each frame
2. The rim is at the bottom-center of the backboard
3. Track ball activity near the rim
4. Detect shots as ball passing through rim region
"""

import cv2
import numpy as np
import csv
import os

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
OUT_CSV = "shots_v8.csv"
OUT_DIR = "v8_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2
MAX_FRAMES = None

def detect_backboard(frame):
    """
    Detect the basketball backboard as a white/bright rectangle.
    Returns (x, y, w, h) of backboard or None.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = frame.shape[:2]
    
    # The backboard is white/bright and rectangular
    # Threshold for bright regions
    _, bright = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    
    # Morphological operations to clean up
    kernel = np.ones((5,5), np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel, iterations=3)
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, kernel, iterations=2)
    
    # Find contours
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_bb = None
    best_score = 0
    
    for c in contours:
        area = cv2.contourArea(c)
        if area < 500 or area > w * h * 0.1:  # backboard is medium-sized
            continue
        
        x, y, bw, bh = cv2.boundingRect(c)
        
        # Backboard aspect ratio: width > height (roughly 1.5:1 to 3:1)
        aspect = bw / bh if bh > 0 else 0
        if aspect < 1.2 or aspect > 5.0:
            continue
        
        # Solidity: backboard is solid (not fragmented)
        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        solidity = area / hull_area if hull_area > 0 else 0
        if solidity < 0.6:
            continue
        
        # Position: backboard is typically in the upper portion of one half of the court
        center_x = x + bw / 2
        center_y = y + bh / 2
        
        # Prefer boards in the top 60% of frame
        if center_y > h * 0.7:
            continue
        
        # Score: prefer larger, more central, better aspect ratio
        size_score = area / (w * h)
        aspect_score = 1.0 - abs(aspect - 2.0) / 2.0  # prefer ~2:1
        pos_score = 1.0 - center_y / h  # prefer higher in frame
        
        score = 0.3 * size_score * 10 + 0.3 * aspect_score + 0.2 * pos_score + 0.2 * solidity
        
        if score > best_score:
            best_score = score
            best_bb = (x, y, bw, bh, score)
    
    return best_bb

def detect_ball_near_backboard(frame, bb):
    """
    Detect basketball near the backboard.
    The rim is at the bottom-center of the backboard.
    """
    if bb is None:
        return None
    
    bx, by, bw, bh, _ = bb
    h, w = frame.shape[:2]
    
    # Rim region: bottom-center of backboard, extended downward
    rim_x = bx + bw // 2
    rim_y = by + bh
    rim_r = int(bw * 0.3)  # rim radius ~30% of backboard width
    
    # ROI: around the rim
    margin = int(rim_r * 1.5)
    x1 = max(0, rim_x - margin)
    y1 = max(0, rim_y - margin // 2)
    x2 = min(w, rim_x + margin)
    y2 = min(h, rim_y + margin)
    
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    
    # Detect orange ball
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([8, 80, 80]), np.array([30, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best = None
    best_score = -1
    
    for c in contours:
        a = cv2.contourArea(c)
        if a < 8 or a > 1000:
            continue
        (cx, cy), r = cv2.minEnclosingCircle(c)
        d = 2 * r
        if not (5 <= d <= 40):
            continue
        
        # Full frame coords
        full_cx = cx + x1
        full_cy = cy + y1
        
        # Distance from rim center
        dist = np.sqrt((full_cx - rim_x)**2 + (full_cy - rim_y)**2)
        
        # Score
        dist_score = max(0, 1.0 - dist / rim_r)
        circ = a / (np.pi * r * r) if r > 0 else 0
        
        score = 0.5 * dist_score + 0.3 * circ + 0.2 * min(1, a / 50)
        
        if score > best_score:
            best_score = score
            best = {
                'cx': full_cx, 'cy': full_cy, 'diam': d,
                'dist_from_rim': dist, 'score': score,
                'in_rim': dist < rim_r,
                'rim_x': rim_x, 'rim_y': rim_y, 'rim_r': rim_r
            }
    
    return best

def detect_net_motion(frame_prev, frame_curr, bb):
    """
    Detect motion in the net region (below the rim, slightly inside backboard width).
    """
    if bb is None or frame_prev is None or frame_curr is None:
        return 0.0
    
    bx, by, bw, bh, _ = bb
    h, w = frame_curr.shape[:2]
    
    rim_x = bx + bw // 2
    rim_y = by + bh
    rim_r = int(bw * 0.3)
    
    # Net ROI: below the rim, narrow horizontally
    net_x1 = max(0, rim_x - int(rim_r * 0.6))
    net_x2 = min(w, rim_x + int(rim_r * 0.6))
    net_y1 = max(0, rim_y)
    net_y2 = min(h, rim_y + int(rim_r * 1.5))
    
    if net_y2 <= net_y1 or net_x2 <= net_x1:
        return 0.0
    
    prev_net = cv2.cvtColor(frame_prev[net_y1:net_y2, net_x1:net_x2], cv2.COLOR_BGR2GRAY)
    curr_net = cv2.cvtColor(frame_curr[net_y1:net_y2, net_x1:net_x2], cv2.COLOR_BGR2GRAY)
    
    if prev_net.shape != curr_net.shape or prev_net.size == 0:
        return 0.0
    
    diff = cv2.absdiff(prev_net, curr_net)
    _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
    
    # Exclude top portion (where ball might be)
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
    
    bb_detections = []
    ball_detections = []
    net_motion_events = []
    shot_candidates = []
    
    vis_saved = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        if MAX_FRAMES and frame_idx >= MAX_FRAMES: break
        if frame_idx % STRIDE != 0:
            frame_idx += 1; continue
        
        # Detect backboard
        bb = detect_backboard(frame)
        
        if bb:
            bb_detections.append((frame_idx, bb))
            
            ball = None
            if bb:
                ball = detect_ball_near_backboard(frame, bb)
            
            if ball is not None:
                ball_detections.append({
                    'frame': frame_idx,
                    'cx': ball['cx'], 'cy': ball['cy'], 'diam': ball['diam'],
                    'dist_from_rim': ball['dist_from_rim'], 'score': ball['score'],
                    'in_rim': ball['in_rim'],
                    'rim_x': ball['rim_x'], 'rim_y': ball['rim_y'], 'rim_r': ball['rim_r'],
                    'bb_x': bb[0], 'bb_y': bb[1], 'bb_w': bb[2], 'bb_h': bb[3]
                })
            
            # Detect net motion
            net_mot = detect_net_motion(prev_frame, frame, bb)
            
            if net_mot > 0.03:
                net_motion_events.append({'frame': frame_idx, 'motion': round(net_mot, 4), 'ball': ball})
            
            # Shot candidate: ball near rim AND net motion
            if ball is not None and ball['score'] > 0.2 and net_mot > 0.02:
                shot_candidates.append({
                    'frame': frame_idx,
                    'ball_score': ball['score'],
                    'net_motion': round(net_mot, 4),
                    'in_rim': ball['in_rim'],
                    'dist_from_rim': round(ball['dist_from_rim'], 1),
                    'diam': ball['diam'],
                    'rim_x': ball['rim_x'], 'rim_y': ball['rim_y'], 'rim_r': ball['rim_r']
                })
        
        # Save vis
        if vis_saved < 25 and frame_idx % (STRIDE * 200) == 0:
            vis = frame.copy()
            if bb:
                cv2.rectangle(vis, (bb[0], bb[1]), (bb[0]+bb[2], bb[1]+bb[3]), (255,0,0), 2)
                rim_x = bb[0] + bb[2]//2
                rim_y = bb[1] + bb[3]
                cv2.circle(vis, (rim_x, rim_y), int(bb[2]*0.3), (0,255,255), 1)
            if ball:
                cv2.circle(vis, (int(ball['cx']), int(ball['cy'])), int(ball['diam']/2), (0,255,0), 2)
            cv2.putText(vis, f"F:{frame_idx} BB={len(bb_detections)} net={len(net_motion_events)} shots={len(shot_candidates)}",
                        (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
            cv2.imwrite(f"{OUT_DIR}/f{frame_idx:05d}.jpg", vis)
            vis_saved += 1
        
        prev_frame = frame.copy()
        
        if frame_idx % (STRIDE * 300) == 0:
            print(f"F{frame_idx}: BB={len(bb_detections)} ball={len(ball_detections)} net={len(net_motion_events)} candidates={len(shot_candidates)}")
        
        frame_idx += 1
    
    cap.release()
    
    print(f"\n=== Results ===")
    print(f"Backboard detections: {len(bb_detections)}")
    print(f"Ball detections near rim: {len(ball_detections)}")
    print(f"Net motion events: {len(net_motion_events)}")
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
            best = max(group, key=lambda s: s['ball_score'] + s['net_motion'])
            merged.append(best)
            i = j
        
        print(f"\nMerged shots: {len(merged)}")
        for s in merged:
            print(f"  F{s['frame']:4d}: ball_score={s['ball_score']:.2f} net_motion={s['net_motion']:.3f} "
                  f"in_rim={'Y' if s['in_rim'] else 'N'} dist={s['dist_from_rim']:.0f}px diam={s['diam']:.0f}px")
        
        with open(OUT_CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['frame','ball_score','net_motion','in_rim','dist_from_rim','diam','rim_x','rim_y','rim_r'])
            w.writeheader()
            for s in merged:
                w.writerow(s)
        print(f"\nSaved to {OUT_CSV}")

if __name__ == "__main__":
    main()
