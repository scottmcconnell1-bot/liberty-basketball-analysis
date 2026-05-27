#!/usr/bin/env python3
"""
Shot detection v14: Fine-tuned NN ball + fixed basket + NO stderr suppression
=============================================================================
- Ball: fine-tuned best.pt at conf=0.0002 (Phase 1 from v13 — confirmed working)
- Basket: positions from v8 court keypoint analysis (2701 frames)
- Tracking: court-region filter to reject false positives
- NO DevNull stderr (v13 crashed silently — we need to see errors)
"""

import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

VIDEO       = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT         = 'pipeline_output'
BALL_MODEL  = 'ball_finetune/runs/finetune2/weights/best.pt'

CONF        = 0.0002
IOU         = 0.3
BASKET_PROX = 200
MAKE_RADIUS = 40
TH_PT_THRESH= 120
DEDUP_RANGE = 20
PEAK_DIST   = 10

# Court region constraints (ceiling camera view — excludes scoreboard/top/bottom edges)
COURT_X_MIN = 100
COURT_X_MAX = 1180
COURT_Y_MIN = 100
COURT_Y_MAX = 650

os.makedirs(OUT, exist_ok=True)
LOG_FILE = f'{OUT}/shot_v14.log'

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def is_in_court(cx, cy):
    return COURT_X_MIN <= cx <= COURT_X_MAX and COURT_Y_MIN <= cy <= COURT_Y_MAX

if __name__ == '__main__':
    START = time.time()

    # Load v8 basket positions
    log("Loading v8 basket positions...")
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    blx, bly = v8['basket_left']   # shape (2, 2701)
    brx, bry = v8['basket_right']  # shape (2, 2701)

    log(f"Left basket: ({np.nanmean(blx):.0f}, {np.nanmean(bly):.0f})")
    log(f"Right basket: ({np.nanmean(brx):.0f}, {np.nanmean(bry):.0f})")

    # Phase 1: Detect ball using fine-tuned model on every frame
    log("Phase 1: Ball detection (fine-tuned NN)...")

    from ultralytics import YOLO
    m = YOLO(BALL_MODEL, verbose=False)

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    log(f"Video: {total} frames")

    # v8 arrays are (2, 2701) — exactly match video length
    # Ensure matching slice just in case
    if len(blx) > total:
        blx = blx[:total]
        bly = bly[:total]
        brx = brx[:total]
        bry = bry[:total]
    log(f"Basket arrays: {len(blx)} frames")

    ball_raw = []       # list of (cx, cy, conf) or None, one per frame
    ball_count = 0
    court_filtered = 0
    fn = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        r = m.predict(frame, conf=CONF, iou=IOU, verbose=False)[0]
        best = None
        best_cf = 0

        if r.boxes is not None:
            for box in r.boxes:
                cls = m.names[int(box.cls[0])]
                cf  = float(box.conf[0])
                if cls == 'Ball' and cf > best_cf:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    best_cf = cf
                    best = (cx, cy, cf)

        # Apply court region filter
        if best is not None:
            if is_in_court(best[0], best[1]):
                ball_raw.append(best)
                ball_count += 1
            else:
                ball_raw.append(None)
                court_filtered += 1
        else:
            ball_raw.append(None)

        fn += 1
        if fn % 500 == 0:
            elapsed = time.time() - START
            log(f"  {fn}/{total}, {ball_count} balls, {court_filtered} filtered, {fn/elapsed:.1f} fps")

    cap.release()
    log(f"Phase 1 done: {ball_count} balls in court ({court_filtered} filtered), {len(ball_raw)} total entries")

    # Fix: CAP_PROP_FRAME_COUNT can differ from actual decoded frames
    total = len(ball_raw)  # use actual count, not metadata
    log(f"Using actual frame count: {total} (was {int(cap.get(cv2.CAP_PROP_FRAME_COUNT))})")

    # Trim or pad basket arrays to match actual frames
    if len(blx) > total:
        blx, bly, brx, bry = blx[:total], bly[:total], brx[:total], bry[:total]
    elif len(blx) < total:
        pad = total - len(blx)
        blx = np.concatenate([blx, np.full(pad, blx[-1])])
        bly = np.concatenate([bly, np.full(pad, bly[-1])])
        brx = np.concatenate([brx, np.full(pad, brx[-1])])
        bry = np.concatenate([bry, np.full(pad, bry[-1])])
    log(f"Basket arrays resized to {len(blx)} frames")

    # Phase 2: Distance to nearest basket
    log("Phase 2: Ball-to-basket distance...")
    bc_x = np.full(total, np.nan)
    bc_y = np.full(total, np.nan)
    bc_c = np.zeros(total)
    for i, b in enumerate(ball_raw):
        if b is not None:
            bc_x[i], bc_y[i], bc_c[i] = b

    dist = np.full(total, np.nan)
    for i in range(total):
        if np.isnan(bc_x[i]):
            continue
        dl = np.sqrt((bc_x[i] - blx[i])**2 + (bc_y[i] - bly[i])**2) if not np.isnan(blx[i]) else np.inf
        dr = np.sqrt((bc_x[i] - brx[i])**2 + (bc_y[i] - bry[i])**2) if not np.isnan(brx[i]) else np.inf
        dist[i] = min(dl, dr)

    valid = int(np.sum(~np.isnan(dist)))
    log(f"Distance computed for {valid} frames")
    if valid > 0:
        dd = dist[~np.isnan(dist)]
        close = int(np.sum(dd < BASKET_PROX))
        log(f"Dist stats: min={dd.min():.0f} med={np.median(dd):.0f} max={dd.max():.0f}")
        log(f"Frames within {BASKET_PROX}px of basket: {close}")

    # Phase 3: Shot detection (triple signal)
    log("Phase 3: Shot detection...")

    # Signal 1: Proximity — frames where ball is close to basket
    prox = [i for i in range(total) if not np.isnan(dist[i]) and dist[i] < BASKET_PROX]
    log(f"  Proximity: {len(prox)}")

    # Signal 2: Distance peaks (ball closest to basket = shot moment)
    vs = dist.copy()
    vs[np.isnan(vs)] = BASKET_PROX * 3
    pk_idx, _ = find_peaks(-vs, distance=PEAK_DIST, height=-BASKET_PROX)
    peaks = [int(p) for p in pk_idx if dist[p] < BASKET_PROX]
    log(f"  Peaks: {len(peaks)}")

    # Signal 3: Tracking gaps — ball disappears near basket = shot arc
    gaps = []
    for gfn in range(20, total):
        if bc_c[gfn] > 0:
            continue
        lr = None
        for prev in range(gfn - 1, max(0, gfn - 40), -1):
            if bc_c[prev] > 0:
                lr = prev
                break
        if lr is None:
            continue
        gap = gfn - lr
        if gap < 3 or gap > 35:
            continue
        if not np.isnan(dist[lr]) and dist[lr] < BASKET_PROX:
            gaps.append(lr)
    log(f"  Gaps: {len(gaps)}")

    # Phase 4: Dedup — cluster nearby frames, pick closest-to-basket
    log("Phase 4: Deduplicating...")
    all_c = sorted(list(set(prox + peaks + gaps)))
    log(f"  Total candidates before dedup: {len(all_c)}")

    deduped = []
    i = 0
    while i < len(all_c):
        j = i + 1
        while j < len(all_c) and all_c[j] - all_c[j - 1] < DEDUP_RANGE:
            j += 1
        grp = all_c[i:j]
        best = min(grp, key=lambda f: dist[f])
        deduped.append(best)
        i = j
    log(f"  {len(all_c)} -> {len(deduped)} shots after dedup")

    # Phase 5: Classify each shot
    shots = []
    for fn in deduped:
        d = dist[fn]
        shots.append({
            'frame': fn,
            'bx': round(float(bc_x[fn]), 1),
            'by': round(float(bc_y[fn]), 1),
            'dist': round(float(d), 1),
            'type': '3PT' if d >= TH_PT_THRESH else '2PT',
            'result': 'MAKE' if d < MAKE_RADIUS else 'MISS',
            'conf': round(float(bc_c[fn]), 4)
        })

    # Output CSV + pickle
    pd.DataFrame(shots).sort_values('frame').to_csv(f'{OUT}/shot_candidates_v14.csv', index=False)
    pickle.dump(
        {'shots': shots, 'ball_x': bc_x, 'ball_y': bc_y,
         'dist': dist, 'basket_left': (blx, bly), 'basket_right': (brx, bry)},
        open(f'{OUT}/shot_v14.pkl', 'wb')
    )

    # Visualize — annotate each shot frame
    log("Visualizing...")
    cap = cv2.VideoCapture(VIDEO)
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s['frame'])
        ret, frame = cap.read()
        if not ret:
            continue
        bx_i, by_i = int(s['bx']), int(s['by'])
        cv2.circle(frame, (bx_i, by_i), 15, (0, 165, 255), 3)
        # Draw basket position
        cv2.circle(frame, (int(blx[s['frame']]), int(bly[s['frame']])), 10, (255, 0, 0), 2)
        cv2.putText(frame,
                    f"F{s['frame']}: {s['type']} {s['result']} d={s['dist']:.0f}px",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imwrite(f'{OUT}/shot_candidate_v14_{s["frame"]:04d}.jpg', frame)
    cap.release()

    # Summary
    log("=" * 60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    ft = [s for s in shots if s['type'] == 'FT']  # none, but placeholder
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result'] == 'MAKE') + sum(3 for s in t3 if s['result'] == 'MAKE')

    log(f"RESULTS: {len(shots)} shots detected")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)} makes")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)} makes")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px conf={s['conf']:.4f}")
    log("DONE")
    log(f"Output: {OUT}/shot_candidates_v14.csv")
