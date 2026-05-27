#!/usr/bin/env python3
"""
Shot detection v17b: Dense track + velocity-based shot detection
=============================================================
Using v16's 97% dense OF track, detect shots by:
  1. Ball moving TOWARD basket (velocity vector points at basket)
  2. Passing within MAKE_RADIUS of basket center
  3. Then moving AWAY (descending through hoop)
  → This is "shot entering hoop" motion.

For misses:
  1. Ball at basket proximity but moving horizontally (pass/rebound)
  2. Ball approaching basket but deflected away (>150px closest approach)
"""

import os, sys, time, pickle
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

OUT = 'pipeline_output'

BASKET_LX = 179.0
BASKET_LY = 525.0
BASKET_RX = 1009.0
BASKET_RY = 466.0

SHOT_ENTER_RADIUS = 55     # ball within this = entering hoop
SHOT_EXIT_RADIUS  = 120    # ball past this = descending
APPROACH_RADIUS   = 250    # start tracking approach from here
MIN_APPROACH_VEL  = 3      # minimum px/frame moving toward basket
DEDUP_FRAMES      = 40     # min frames between separate shots
THREE_PT_THRESH   = 130    # distance threshold
MAKE_RADIUS       = 50     # within this = make

def log(msg):
    print(msg, flush=True)

if __name__ == '__main__':
    # Load dense track from v16
    log("Loading v16 dense track...")
    with open(f'{OUT}/shot_v16.pkl', 'rb') as f:
        v16 = pickle.load(f)
    
    sx = np.array(v16['smooth_x'])
    sy = np.array(v16['smooth_y'])
    total = len(sx)
    
    nnz = np.sum(~np.isnan(sx))
    log(f"Track: {total} frames, {nnz} non-NaN ({100*nnz/total:.0f}%)")
    
    # Fill NaN
    nan_mask = np.isnan(sx)
    if np.any(nan_mask):
        sx[nan_mask] = np.interp(np.where(nan_mask)[0], 
                                   np.where(~nan_mask)[0], sx[~nan_mask])
        sy[nan_mask] = np.interp(np.where(nan_mask)[0],
                                   np.where(~nan_mask)[0], sy[~nan_mask])
    
    # Smooth
    try:
        sx = savgol_filter(sx, 7, 2)
        sy = savgol_filter(sy, 7, 2)
    except:
        pass
    
    # Compute velocity
    vx = np.gradient(sx)
    vy = np.gradient(sy)
    speed = np.sqrt(vx**2 + vy**2)
    
    # Distance to nearest basket per frame
    dist_L = np.sqrt((sx - BASKET_LX)**2 + (sy - BASKET_LY)**2)
    dist_R = np.sqrt((sx - BASKET_RX)**2 + (sy - BASKET_RY)**2)
    dist = np.minimum(dist_L, dist_R)
    nearest_basket = np.where(dist_L < dist_R, 'L', 'R')
    
    # Radial velocity: is ball moving toward or away from nearest basket?
    # + = approaching, - = receding
    bx = np.where(nearest_basket == 'L', BASKET_LX, BASKET_RX)
    by = np.where(nearest_basket == 'L', BASKET_LY, BASKET_RY)
    
    dx = bx - sx  # vector from ball to basket
    dy = by - sy
    dnorm = np.sqrt(dx**2 + dy**2)
    dnorm[dnorm == 0] = 1
    
    # Radial velocity = component of velocity toward basket
    radial_v = (vx * dx + vy * dy) / dnorm
    
    log(f"Speed: median={np.median(speed):.1f} max={np.max(speed):.1f}")
    log(f"Radial v: median={np.median(radial_v):.1f} max={np.max(radial_v):.1f}")
    
    # Find shot events: ball approaching basket then passing through
    shots = []
    i = 0
    while i < total - 5:
        # Fast forward to where ball is in approach zone
        if dist[i] > APPROACH_RADIUS or radial_v[i] < MIN_APPROACH_VEL:
            i += 1
            continue
        
        # Found an approach — track it through the basket zone
        approach_start = i
        min_dist = dist[i]
        min_dist_frame = i
        
        while i < total and dist[i] < APPROACH_RADIUS:
            if dist[i] < min_dist:
                min_dist = dist[i]
                min_dist_frame = i
            i += 1
        
        # Ball left approach zone — was it a shot?
        arc_frames = i - approach_start
        
        # Shot criteria:
        # 1. Ball got reasonably close (< 200px)
        # 2. Arc has reasonable duration (>5 frames, <40 frames)
        # 3. Ball was in SHOT_ENTER_RADIUS at some point (shot/make)
        # OR ball approached within 120px but bounced away (miss)
        
        if arc_frames < 3 or arc_frames > 60:
            continue
        
        # Classify by minimum distance
        if min_dist < MAKE_RADIUS:
            result = 'MAKE'
        elif min_dist < SHOT_EXIT_RADIUS:
            result = 'MISS'
        else:
            continue  # just passing by
        
        stype = '3PT' if min_dist >= THREE_PT_THRESH else '2PT'
        
        shots.append({
            'frame': min_dist_frame,
            'approach_start': approach_start,
            'dist': round(float(min_dist), 1),
            'type': stype,
            'result': result,
        })
        
        i += DEDUP_FRAMES  # skip ahead to avoid double-counting
    
    # Dedup by proximity
    if shots:
        deduped = [shots[0]]
        for s in shots[1:]:
            if s['frame'] - deduped[-1]['frame'] < DEDUP_FRAMES:
                # Keep the closer one
                if s['dist'] < deduped[-1]['dist']:
                    deduped[-1] = s
            else:
                deduped.append(s)
        shots = deduped
    
    log(f"\nShots detected: {len(shots)}")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px")
    
    # Summary
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')
    
    log(f"\n2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    
    pd.DataFrame(shots).to_csv(f'{OUT}/shot_candidates_v17b.csv', index=False)
    log("DONE")
