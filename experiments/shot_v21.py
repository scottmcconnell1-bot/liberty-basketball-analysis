#!/usr/bin/env python3
"""
Shot detection v21: Bidirectional color-verified OF (v18++).
Same as v18 but:
  - Relaxed color check: H 2-32, S>10 (handles motion blur / lighting shifts)
  - Track window: 15 back, 20 forward (v18 was 40/40 — too wide = wandering)
  - Classify make by closest approach in track (not NN detection point)
  - Reject launches outside court bounds (scoreboard false positives)
"""
import os, sys, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

FWD_WIN  = 20
BWD_WIN  = 15
MIN_PTS  = 10
MAX_JUMP = 100
MAKE_R   = 50

# Relaxed color for tracking (ball in motion may shift)
TRACK_H_LO, TRACK_H_HI = 2, 32
TRACK_S_MIN = 10

# Strict color for anchor verification
ANCHOR_H_LO, ANCHOR_H_HI = 3, 28
ANCHOR_S_MIN = 15

def log(msg):
    print(msg, flush=True)

def check_color(hsv, x, y, strict=False):
    """Check if pixel at (x,y) matches basketball color."""
    h, w = hsv.shape[:2]
    xi, yi = int(x), int(y)
    if not (0 <= xi < w and 0 <= yi < h):
        return False
    if strict:
        return ANCHOR_H_LO <= hsv[yi, xi, 0] <= ANCHOR_H_HI and hsv[yi, xi, 1] >= ANCHOR_S_MIN
    return TRACK_H_LO <= hsv[yi, xi, 0] <= TRACK_H_HI and hsv[yi, xi, 1] >= TRACK_S_MIN


def track_bidir(cap, fnum, cx, cy, total):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
    ret, img0 = cap.read()
    if not ret:
        return []

    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)

    # Strict color check at anchor
    if not check_color(hsv0, cx, cy, strict=True):
        return []

    # Track backward
    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []

    for f in range(fnum - 1, max(fnum - BWD_WIN, 0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gray_f = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            hsv_f = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            jx = abs(nx - float(pt[0, 0, 0]))
            jy = abs(ny - float(pt[0, 0, 1]))
            if check_color(hsv_f, nx, ny) and jx < MAX_JUMP and jy < MAX_JUMP:
                backward.append((f, nx, ny))
                pt = new_pt.reshape(1, 1, 2)
                gray_prev = gray_f
                continue
        gray_prev = gray_f

    # Track forward
    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    forward = []

    for f in range(fnum + 1, min(fnum + FWD_WIN, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gray_f = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            hsv_f = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            jx = abs(nx - float(pt[0, 0, 0]))
            jy = abs(ny - float(pt[0, 0, 1]))
            if check_color(hsv_f, nx, ny) and jx < MAX_JUMP and jy < MAX_JUMP:
                forward.append((f, nx, ny))
                pt = new_pt.reshape(1, 1, 2)
                gray_prev = gray_f
                continue
        gray_prev = gray_f

    return backward[::-1] + [(fnum, float(cx), float(cy))] + forward


def classify(track, nn_f, nn_x, nn_y):
    if len(track) < MIN_PTS:
        return None

    fs = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    # Consistency
    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if np.max(jumps) > MAX_JUMP:
        return None

    # Closest approach to basket
    dists = np.minimum(
        np.sqrt((xs - BLX)**2 + (ys - BLY)**2),
        np.sqrt((xs - BRX)**2 + (ys - BRY)**2),
    )
    min_idx = int(np.argmin(dists))
    min_dist = float(dists[min_idx])
    best_f = int(fs[min_idx])

    # Reject if no meaningful movement
    if min_dist > 160:
        return None

    # Launch position (first tracked point)
    launch_x, launch_y = xs[0], ys[0]

    # Reject out-of-bounds launches
    if launch_x < 20 or launch_x > 1260 or launch_y < 20 or launch_y > 700:
        return None

    # Classify: launch in FT zone = FT, nn_dist >= 130 = 3PT, else 2PT
    nn_dist = float(np.minimum(
        np.sqrt((nn_x - BLX)**2 + (nn_y - BLY)**2),
        np.sqrt((nn_x - BRX)**2 + (nn_y - BRY)**2),
    ))

    in_ft_zone = (350 < launch_x < 800 and 250 < launch_y < 520)
    if in_ft_zone and nn_dist < 400 and min_dist < 150:
        stype = 'FT'
    elif nn_dist >= 130 and min_dist < 200:
        stype = '3PT'
    else:
        stype = '2PT'

    is_make = min_dist < MAKE_R and np.mean(jumps) < 40
    result = 'MAKE' if is_make else 'MISS'

    return {
        'frame': best_f, 'type': stype, 'result': result,
        'closest': round(min_dist, 1), 'nn_dist': round(nn_dist, 1),
        'track': len(track),
        'launch': (round(launch_x, 0), round(launch_y, 0)),
    }


if __name__ == '__main__':
    log("Loading NN detections...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2+(ry[i]-BLY)**2), np.sqrt((rx[i]-BRX)**2+(ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(cands):
        track = track_bidir(cap, f, cx, cy, total)
        cls = classify(track, f, cx, cy)
        if cls:
            shots.append(cls)
            log(f"  [{ci+1}/{len(cands)}] F{f}: {cls['type']} {cls['result']} "
                f"closest={cls['closest']:.0f}px nn={cls['nn_dist']:.0f}px track={cls['track']}f")
        else:
            log(f"  [{ci+1}/{len(cands)}] F{f}: REJECTED (track={len(track)}f)")

    cap.release()

    if shots:
        shots.sort(key=lambda s: s['frame'])
        deduped = [shots[0]]
        for s in shots[1:]:
            if s['frame'] - deduped[-1]['frame'] < 30:
                if s['track'] > deduped[-1]['track']:
                    deduped[-1] = s
            else:
                deduped.append(s)
        shots = deduped

    log(f"\n{'='*60}")
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
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"closest={s['closest']:.0f}px nn={s['nn_dist']:.0f}px track={s['track']}f")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v21.csv', index=False)
