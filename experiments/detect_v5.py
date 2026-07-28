#!/usr/bin/env python3
"""
Ball detector v5: Single best ball per frame + shot detection from Y-temporal pattern.
For each frame, pick ONE detection most likely to be the ball (small, round, upper-half).
Then find shots by looking at temporal pattern of ballY over time.
Also saves visualization frames for human verification.
"""

import csv, numpy as np, cv2, os

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
OUT_CSV = "ball_v5_per_frame.csv"
SHOT_CSV = "shots_v5.csv"
OUT_DIR = "v5_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2
HUE_LOW=0; HUE_HIGH=25; SAT_MIN=60; VAL_MIN=60; VAL_MAX=255
BALL_MIN_DIAM=7; BALL_MAX_DIAM=35
BALL_MIN_CIRC=0.2; BALL_MIN_SOL=0.3

def fg_mask(frame, bg_sub, kernel):
    mask = bg_sub.apply(frame)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask

def best_ball_in_frame(frame, fg):
    """Find the single most ball-like detection in a frame."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cmask = cv2.inRange(hsv, np.array([HUE_LOW, SAT_MIN, VAL_MIN]),
                        np.array([HUE_HIGH, 255, VAL_MAX]))
    combined = cv2.bitwise_and(fg, cmask)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best = None
    best_score = -999
    
    for c in contours:
        a = cv2.contourArea(c)
        if a < 10 or a > 2000: continue
        (x,y), r = cv2.minEnclosingCircle(c)
        d = 2*r
        if not (BALL_MIN_DIAM <= d <= BALL_MAX_DIAM): continue
        rx,ry,rw,rh = cv2.boundingRect(c)
        if rw==0 or rh==0: continue
        asp = rw/rh
        if not (0.4 <= asp <= 1.6): continue
        hull = cv2.convexHull(c)
        ha = cv2.contourArea(hull)
        if ha==0: continue
        sol = a/ha
        if sol < BALL_MIN_SOL: continue
        circ = a/(np.pi*r*r) if r>0 else 0
        if circ < BALL_MIN_CIRC: continue
        
        M = cv2.moments(c)
        if M["m00"]==0: continue
        cx = M["m10"]/M["m00"]
        cy = M["m01"]/M["m00"]
        
        # Score: prefer upper half, small, circular, centered horizontally
        y_score = (720 - cy) / 720  # higher = better (prefer upper frame)
        circ_score = circ
        size_score = 1.0 - abs(d - 15) / 15  # prefer ~15px diameter
        center_x_score = 1.0 - abs(cx - 640) / 640  # prefer near center-X
        
        score = 0.3*y_score + 0.25*circ_score + 0.2*size_score + 0.25*center_x_score
        
        if score > best_score:
            best_score = score
            best = {'cx': cx, 'cy': cy, 'diam': d, 'circ': circ, 'sol': sol, 'area': a, 'score': score}
    
    return best, combined

def find_shots(ball_sequence):
    """
    ball_sequence: list of (frame, cy) where cy is ball Y position (or None).
    A shot: ball Y dips (ball moves down in frame = toward hoop in center),
    then rises again. The dip = ball approaching and passing through hoop region.
    """
    # Fill gaps with interpolation
    frames = [b[0] for b in ball_sequence]
    cys = [b[1] for b in ball_sequence]
    
    # Smooth the Y signal
    cys_smooth = np.array(cys, dtype=float)
    for i in range(2, len(cys_smooth)-2):
        if cys_smooth[i] > 0:
            window = [cys_smooth[j] for j in range(max(0,i-2), min(len(cys_smooth),i+3)) if cys_smooth[j] > 0]
            if window:
                cys_smooth[i] = np.median(window)
    
    # Find local minima in cy (ball closest to hoop = lowest Y in frame context)
    # But with auto-tracking, the ball stays near center, so we look for
    # patterns where cy DECREASES then INCREASES
    shots = []
    i = 2
    while i < len(cys_smooth) - 2:
        if cys_smooth[i] <= 0:
            i += 1; continue
        
        # Check if this is a local minimum (±3 frame window)
        window = [cys_smooth[j] for j in range(max(0,i-3), min(len(cys_smooth),i+4)) if cys_smooth[j] > 0]
        if len(window) < 3:
            i += 1; continue
        
        local_min = min(window)
        if cys_smooth[i] == local_min and cys_smooth[i] < 400:  # below middle of frame
            # Found a dip - this could be a shot peak
            # Expand to find start and end of the dip
            start = i
            while start > 0 and cys_smooth[start] > 0 and cys_smooth[start-1] >= cys_smooth[start]:
                start -= 1
            end = i
            while end < len(cys_smooth)-1 and cys_smooth[end] > 0 and cys_smooth[end+1] >= cys_smooth[end]:
                end += 1
            
            depth = 0
            if start < i:
                depth = max(depth, cys_smooth[start] - cys_smooth[i])
            if end > i:
                depth = max(depth, cys_smooth[end] - cys_smooth[i])
            
            if depth > 30 and end - start >= 3:  # meaningful dip
                shots.append({
                    'peak_frame': int(frames[i]),
                    'peak_cy': round(float(cys_smooth[i]), 1),
                    'start_frame': int(frames[start]),
                    'end_frame': int(frames[end]),
                    'depth': round(depth, 0),
                    'span': end - start
                })
                i = end + 1
                continue
        i += 1
    
    return shots

def main():
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    bg_sub = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=20, detectShadows=False)
    
    cap = cv2.VideoCapture(VIDEO_PATH)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {total} frames")
    
    # Warmup
    for _ in range(100):
        ret, f = cap.read()
        if not ret: break
        bg_sub.apply(f)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    
    ball_seq = []  # (frame, cx, cy, diam)
    frame_count = 0
    det_count = 0
    vis_saved = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        if frame_count % STRIDE != 0:
            frame_count += 1; continue
        
        fg = fg_mask(frame, bg_sub, kernel)
        best, _ = best_ball_in_frame(frame, fg)
        
        if best:
            ball_seq.append((frame_count, best['cx'], best['cy'], best['diam']))
            det_count += 1
        
        # Save vis every 100 frames
        if vis_saved < 50 and frame_count % (STRIDE*100) == 0 and frame_count > 0:
            vis = frame.copy()
            if best:
                cv2.circle(vis, (int(best['cx']), int(best['cy'])), int(best['diam']/2), (0,255,0), 2)
                cv2.putText(vis, f"d={best['diam']:.0f} c={best['circ']:.2f}", (int(best['cx'])-30, int(best['cy'])-15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1)
            cv2.putText(vis, f"F:{frame_count} seq={len(ball_seq)}", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
            cv2.imwrite(f"{OUT_DIR}/f{frame_count:05d}.jpg", vis)
            vis_saved += 1
        
        if frame_count % (STRIDE*200) == 0:
            print(f"Frame {frame_count}: {det_count} ball dets so far")
        
        frame_count += 1
    
    cap.release()
    print(f"\nDone: {len(ball_seq)} frames with ball detection out of ~{frame_count//STRIDE}")
    
    # Save per-frame ball positions
    with open(OUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['frame','cx','cy','diam'])
        w.writeheader()
        for fi, cx, cy, diam in ball_seq:
            w.writerow({'frame': fi, 'cx': round(cx,1), 'cy': round(cy,1), 'diam': round(diam,1)})
    print(f"Saved to {OUT_CSV}")
    
    # Find shots from Y-temporal pattern
    cy_data = [(fi, cy) for fi, cx, cy, d in ball_seq if cy > 0]
    shots = find_shots(cy_data)
    
    # Merge shots within 30 frames
    shots.sort(key=lambda x: x['peak_frame'])
    merged = []
    i = 0
    while i < len(shots):
        group = [shots[i]]
        j = i+1
        while j < len(shots) and shots[j]['peak_frame'] - group[0]['peak_frame'] < 30:
            group.append(shots[j]); j += 1
        # Keep deepest dip
        group.sort(key=lambda s: -s['depth'])
        merged.append(group[0])
        i = j
    
    print(f"\nShots detected: {len(merged)}")
    for s in merged:
        print(f"  Frame {s['peak_frame']:4d}: cy={s['peak_cy']:.0f}px, depth={s['depth']:.0f}px, span={s['span']}f")
    
    # Classify 2PT vs 3PT by peak_cy
    # Closer to frame center (higher cy in pixel coords) = closer to hoop = 2PT
    if merged:
        cys = [s['peak_cy'] for s in merged]
        cy_cutoff = np.percentile(cys, 50)
        for s in merged:
            s['shot_type'] = '2PT' if s['peak_cy'] > cy_cutoff else '3PT'
            s['make'] = False  # need separate logic
    
    m2 = sum(1 for s in merged if s.get('shot_type')=='2PT')
    m3 = sum(1 for s in merged if s.get('shot_type')=='3PT')
    print(f"\n  2PT attempts: {m2}, 3PT attempts: {m3}")
    print(f"  (Target: ~7 2PT + ~2 3PT + ~3 FT = ~12 attempts)")
    
    with open(SHOT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['peak_frame','peak_cy','start_frame','end_frame','depth','span','shot_type','make'])
        w.writeheader()
        for s in merged:
            w.writerow(s)

if __name__ == "__main__":
    main()
