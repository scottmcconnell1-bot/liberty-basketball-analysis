#!/usr/bin/env python3
"""
Shot detection v13: Color ball detection + known basket positions
=================================================================
- Ball: HSV color segmentation (orange blob) every frame (~0.001s)
- Basket: from v8 court keypoint analysis (pre-computed basket positions)
- No slow NN models at all
- Estimated runtime: ~1-2 minutes for 2701 frames
"""

import os, sys, time, pickle
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from collections import defaultdict

VIDEO  = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT    = 'pipeline_output'

# Ball color detection params
BALL_H_MIN   = 3
BALL_H_MAX   = 30
BALL_S_MIN   = 30
BALL_AREA_MIN= 30
BALL_AREA_MAX= 5000
BALL_CIRC_MIN= 0.4

# Tracking
MAX_JUMP     = 100   # px between consecutive detections

# Shot detection
BASKET_PROX  = 200   # ball within this px of basket = candidate
MAKE_RADIUS  = 40
TH_PT_THRESH = 120
DEDUP_RANGE  = 20
PEAK_DIST    = 10

os.makedirs(OUT, exist_ok=True)

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)
    with open(f'{OUT}/shot_v13.log', 'a') as f:
        f.write(line + '\n')

def detect_ball_color(hsv):
    mask = cv2.inRange(hsv, np.array([BALL_H_MIN, BALL_S_MIN, 30]),
                       np.array([BALL_H_MAX, 255, 255]))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < BALL_AREA_MIN or area > BALL_AREA_MAX: continue
        (x,y), _ = cv2.minEnclosingCircle(cnt)
        perim = cv2.arcLength(cnt, True)
        if perim == 0: continue
        circ = 4*np.pi*area/(perim*perim)
        if circ < BALL_CIRC_MIN: continue
        if best is None or area > best[2]:
            best = (int(x), int(y), area, circ)
    return best

if __name__ == '__main__':
    START = time.time()

    # Load basket positions from v8
    log("Loading basket positions from v8...")
    try:
        with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
            v8 = pickle.load(f)
        basket_left_x, basket_left_y = v8['basket_left']
        basket_right_x, basket_right_y = v8['basket_right']
        log(f"Basket left:  mean=({np.nanmean(basket_left_x):.0f}, {np.nanmean(basket_left_y):.0f})")
        log(f"Basket right: mean=({np.nanmean(basket_right_x):.0f}, {np.nanmean(basket_right_y):.0f})")
    except Exception as e:
        log(f"Error loading v8 data: {e}")
        log("Using default basket positions")
        # Fallback: typical positions for ceiling camera
        basket_left_x = None; basket_left_y = None
        basket_right_x = None; basket_right_y = None

    # If v8 basket positions unavailable, estimate from keypoint analysis
    if basket_left_x is None:
        log("ERROR: No basket positions available")
        sys.exit(1)

    total_frames = len(basket_left_x)
    log(f"Total frames: {total_frames}")

    # === Phase 1: Color ball detection on every frame ===
    log("Phase 1: Ball detection (color)...")
    cap = cv2.VideoCapture(VIDEO)
    ball_pos = []  # (cx, cy, area) or None
    ball_count = 0
    fn = 0

    while True:
        ret, frame = cap.read()
        if not ret: break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ball = detect_ball_color(hsv)
        if ball is not None:
            ball_pos.append((ball[0], ball[1], ball[2]))
            ball_count += 1
        else:
            ball_pos.append(None)

        fn += 1
        if fn % 500 == 0:
            log(f"  {fn}/{total_frames}, {ball_count} balls found")

    cap.release()
    log(f"Phase 1 done: {ball_count}/{total_frames} frames with ball detected")

    # === Phase 2: Ball tracking filter ===
    log("Phase 2: Ball tracking...")
    ball_clean = []
    last_good, removed = None, 0
    for b in ball_pos:
        if b is None: ball_clean.append(None); continue
        cx, cy, area = b
        if last_good is not None:
            lx, ly, _ = last_good
            if np.sqrt((cx-lx)**2 + (cy-ly)**2) > MAX_JUMP:
                ball_clean.append(None); removed += 1; continue
        ball_clean.append(b); last_good = b
    log(f"Kept {ball_count-removed}, removed {removed}")

    # === Phase 3: Interpolate ball positions ===
    log("Phase 3: Interpolating...")
    bc_x = np.full(total_frames, np.nan)
    bc_y = np.full(total_frames, np.nan)
    bc_a = np.zeros(total_frames)  # area as "confidence"
    for i, b in enumerate(ball_clean):
        if b is not None:
            bc_x[i], bc_y[i], bc_a[i] = b

    nan_m = np.isnan(bc_x)
    if np.any(~nan_m):
        idx = np.arange(total_frames)
        bc_x[nan_m] = np.interp(idx[nan_m], idx[~nan_m], bc_x[~nan_m])
        bc_y[nan_m] = np.interp(idx[nan_m], idx[~nan_m], bc_y[~nan_m])

    # === Phase 4: Compute ball-to-basket distance ===
    log("Phase 4: Ball-to-basket distance...")

    # Distance to nearest basket per frame
    dist_to_basket = np.full(total_frames, np.nan)
    for i in range(total_frames):
        if np.isnan(bc_x[i]): continue
        # Left basket
        if not np.isnan(basket_left_x[i]) and not np.isnan(basket_left_y[i]):
            dl = np.sqrt((bc_x[i]-basket_left_x[i])**2 + (bc_y[i]-basket_left_y[i])**2)
        else:
            dl = np.inf
        # Right basket
        if not np.isnan(basket_right_x[i]) and not np.isnan(basket_right_y[i]):
            dr = np.sqrt((bc_x[i]-basket_right_x[i])**2 + (bc_y[i]-basket_right_y[i])**2)
        else:
            dr = np.inf
        dist_to_basket[i] = min(dl, dr)

    valid = int(np.sum(~np.isnan(dist_to_basket)))
    log(f"Distance computed for {valid}/{total_frames} frames")
    if valid > 0:
        d = dist_to_basket[~np.isnan(dist_to_basket)]
        log(f"Distance stats: min={d.min():.0f} p50={np.percentile(d,50):.0f} max={d.max():.0f}")
        close = int(np.sum(d < BASKET_PROX))
        log(f"Frames with ball within {BASKET_PROX}px of basket: {close}")

    # === Phase 5: Shot detection (triple signal) ===
    log("Phase 5: Shot detection...")

    # Method 1: Proximity (ball within BASKET_PROX of basket)
    prox = [i for i in range(total_frames)
             if not np.isnan(dist_to_basket[i]) and dist_to_basket[i] < BASKET_PROX]
    log(f"  Proximity: {len(prox)} frames")

    # Method 2: Peak-finding (local minima in distance)
    vs = dist_to_basket.copy()
    vs[np.isnan(vs)] = BASKET_PROX * 3
    pk_idx, _ = find_peaks(-vs, distance=PEAK_DIST, height=-BASKET_PROX)
    peaks = [int(p) for p in pk_idx if dist_to_basket[p] < BASKET_PROX]
    log(f"  Peaks: {len(peaks)}")

    # Method 3: Gap shots (ball disappears near basket)
    gaps = []
    for gfn in range(20, total_frames):
        if bc_a[gfn] > 0: continue  # ball was detected at gfn
        # Find last real detection before gap
        lr = None
        for prev in range(gfn-1, max(0, gfn-40), -1):
            if bc_a[prev] > 0: lr = prev; break
        if lr is None: continue
        gap = gfn - lr
        if gap < 3 or gap > 35: continue
        if not np.isnan(dist_to_basket[lr]) and dist_to_basket[lr] < BASKET_PROX:
            gaps.append(lr)
    log(f"  Gaps: {len(gaps)}")

    # === Phase 6: Union + dedup ===
    log("Phase 6: Deduplicating...")
    all_c = sorted(list(set(prox + peaks + gaps)))

    deduped = []
    i = 0
    while i < len(all_c):
        j = i + 1
        while j < len(all_c) and all_c[j] - all_c[j-1] < DEDUP_RANGE:
            j += 1
        group = all_c[i:j]
        best = min(group, key=lambda f: dist_to_basket[f])
        deduped.append(best)
        i = j

    log(f"Deduped: {len(all_c)} -> {len(deduped)} shots")

    # === Phase 7: Classify ===
    shots = []
    for fn in deduped:
        d = dist_to_basket[fn]
        shot_type = '3PT' if d >= TH_PT_THRESH else '2PT'
        # Could also check FT: if ball y is in FT line area
        result = 'MAKE' if d < MAKE_RADIUS else 'MISS'
        shots.append({
            'frame': fn,
            'bx': round(float(bc_x[fn]), 1),
            'by': round(float(bc_y[fn]), 1),
            'dist': round(float(d), 1),
            'type': shot_type,
            'result': result,
            'area': round(float(bc_a[fn]), 1) if bc_a[fn] > 0 else 0
        })

    # === Phase 8: Output ===
    pd.DataFrame(shots).sort_values('frame').to_csv(f'{OUT}/shot_candidates_v13.csv', index=False)
    pickle.dump({'shots': shots, 'ball_x': bc_x, 'ball_y': bc_y,
                 'ball_area': bc_a, 'dist': dist_to_basket,
                 'basket_left': (basket_left_x, basket_left_y),
                 'basket_right': (basket_right_x, basket_right_y)},
                open(f'{OUT}/shot_v13.pkl', 'wb'))

    # === Phase 9: Visualization ===
    log("Phase 9: Visualizations...")
    cap = cv2.VideoCapture(VIDEO)
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s['frame'])
        ret, frame = cap.read()
        if not ret: continue
        bx, by = int(s['bx']), int(s['by'])
        cv2.circle(frame, (bx, by), 15, (0, 165, 255), 3)
        cv2.putText(frame, f"F{s['frame']}: {s['type']} {s['result']} d={s['dist']:.0f}px",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imwrite(f'{OUT}/shot_candidate_v13_{s["frame"]:04d}.jpg', frame)
    cap.release()

    # === Summary ===
    log("=" * 60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')

    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px area={s['area']:.0f}")
    log("DONE")
