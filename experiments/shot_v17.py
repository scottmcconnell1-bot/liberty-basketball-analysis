#!/usr/bin/env python3
"""
Shot detection v17: NN detections as direct shot signal
======================================================
Key insight: The fine-tuned NN fires on visually distinct balls — which
primarily happens during shots (ball in air, isolated, clear silhouette).
During ground play the ball is occluded by players → NN misses it.
So the 488 NN detections are already enriched for shot frames.

Approach: Count NN detection clusters near each basket as shot attempts.
Make/miss by ball speed: fast-moving ball through hoop = make, slow/deflected = miss.
No optical flow, no arc fitting, no gap analysis — just count what the NN sees.
"""

import os, sys, time, pickle
import numpy as np
import pandas as pd

VIDEO = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = 'pipeline_output'

BASKET_LX = 179.0
BASKET_LY = 525.0
BASKET_RX = 1009.0
BASKET_RY = 466.0

PROX_THRESHOLD = 150    # NN detection within this px = shot attempt
MAKE_RADIUS    = 40     # within this px = make
THREE_PT      = 120     # beyond this from basket = 3PT
FT_MAX_DIST   = 80      # FT is close and slow (free throw line ~midcourt)
DEDUP_RANGE   = 25      # merge nearby frames into one shot

os.makedirs(OUT, exist_ok=True)

def log(msg):
    print(msg, flush=True)

if __name__ == '__main__':
    # Load v14 NN detections
    log("Loading v14 NN detections...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)

    raw_x = v14['ball_x']
    raw_y = v14['ball_y']
    total = len(raw_x)

    # Get all NN detections near either basket
    shot_frames = []
    for i in range(total):
        if np.isnan(raw_x[i]):
            continue
        dl = np.sqrt((raw_x[i] - BASKET_LX)**2 + (raw_y[i] - BASKET_LY)**2)
        dr = np.sqrt((raw_x[i] - BASKET_RX)**2 + (raw_y[i] - BASKET_RY)**2)
        d = min(dl, dr)
        if d < PROX_THRESHOLD:
            # Which basket?
            basket = 'L' if dl < dr else 'R'
            shot_frames.append((i, d, basket, raw_x[i], raw_y[i]))

    log(f"NN detections near basket: {len(shot_frames)}")

    # Sort by frame
    shot_frames.sort()

    # Cluster into shot attempts (consecutive or near frames = same shot)
    clusters = []
    if shot_frames:
        cur = [shot_frames[0]]
        for i in range(1, len(shot_frames)):
            if shot_frames[i][0] - shot_frames[i-1][0] < DEDUP_RANGE:
                cur.append(shot_frames[i])
            else:
                clusters.append(cur)
                cur = [shot_frames[i]]
        clusters.append(cur)

    log(f"Shot clusters: {len(clusters)}")

    # Classify each cluster as a shot
    shots = []
    for ci, cl in enumerate(clusters):
        # Best frame = closest to basket in this cluster
        best = min(cl, key=lambda t: t[1])
        f, d, basket, bx, by = best

        # Shot type by distance
        if d < FT_MAX_DIST and abs(bx - 640) < 100:
            stype = 'FT'
        elif d >= THREE_PT:
            stype = '3PT'
        else:
            stype = '2PT'

        # Make/miss by distance
        result = 'MAKE' if d < MAKE_RADIUS else 'MISS'

        shots.append({
            'frame': f,
            'cluster_size': len(cl),
            'cluster_start': cl[0][0],
            'cluster_end': cl[-1][0],
            'bx': round(bx, 1),
            'by': round(by, 1),
            'basket': basket,
            'dist': round(float(d), 1),
            'type': stype,
            'result': result,
        })

    # Output
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px "
            f"({s['cluster_size']}f cluster, {s['basket']}-basket)")

    pd.DataFrame(shots).to_csv(f'{OUT}/shot_candidates_v17.csv', index=False)

    # Summary
    log("\n" + "=" * 60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    ft = [s for s in shots if s['type'] == 'FT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = (sum(2 for s in t2 if s['result']=='MAKE') +
           sum(3 for s in t3 if s['result']=='MAKE') +
           sum(1 for s in ft if s['result']=='MAKE'))

    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result']=='MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    log(f"Per-basket: L={sum(1 for s in shots if s['basket']=='L')}, "
        f"R={sum(1 for s in shots if s['basket']=='R')}")
    log("DONE")
