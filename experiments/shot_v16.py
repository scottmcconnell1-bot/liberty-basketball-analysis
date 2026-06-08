#!/usr/bin/env python3
"""
Shot detection v16: Sparse NN detections + Optical Flow gap fill + Arc-based shots
==================================================================================
Key insight from v15: HSV alone tracks jerseys/players, not the ball.
v15 found ball on 99% of frames but the "ball" was usually a player's jersey.

v16 approach:
  Phase 1: Use v14's fine-tuned NN detections (unambiguous, but sparse: 488/2711 frames)
  Phase 2: Fill gaps between NN detections using optical flow (Lucas-Kanade PyrLK)
            Between two NN detections 5-40 frames apart, track the ball's motion
            using optical flow to create dense sub-track
  Phase 3: Kalman smooth the full track
  Phase 4: Detect shot arcs — parabolic trajectories with apex + descent through hoop zone
"""

import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

VIDEO  = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT    = 'pipeline_output'

# Parameters
BASKET_PROX    = 200      # frames within this px of basket = "close"
MAKE_RADIUS    = 40       # within this px = make
THREE_PT_THRESH = 120     # >= this px from basket = 3PT
ARC_MIN_FRAMES  = 8       # minimum arc length
ARC_MAX_FRAMES  = 60      # maximum arc length
APEX_JUMP       = 30      # minimum arc height (px)
DEDUP_RANGE     = 25      # merge shots within this many frames
SMOOTH_WINDOW   = 7       # Savitzky-Golay window

os.makedirs(OUT, exist_ok=True)
LOG_FILE = f'{OUT}/shot_v16.log'

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def track_between_frames(cap, frame_a, frame_b, pt_a, pt_b, total):
    """Use optical flow to track ball position between two known frames.

    Given ball position at frame_a and frame_b, interpolate using
    optical flow to estimate ball position at each intermediate frame.

    Returns dict: {frame_num: (x, y)}
    """
    gap = frame_b - frame_a
    if gap <= 1 or gap > 60:
        return {}

    # Read frame_a to get starting points
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_a)
    ret, img_a = cap.read()
    if not ret:
        return {}

    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = None

    # Track forward from frame_a using optical flow
    prev_gray = gray_a.copy()
    prev_pt = np.array([[pt_a]], dtype=np.float32)

    result = {}

    for f in range(frame_a + 1, frame_b):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break

        curr_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # LK optical flow
        next_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            prev_gray, curr_gray, prev_pt, None,
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03)
        )

        if status[0, 0] == 1:
            # Also check backward flow to frame_b for consistency
            x, y = float(next_pt[0, 0]), float(next_pt[0, 1])
            # Check against linear interpolation from pt_a to pt_b
            alpha = (f - frame_a) / gap
            expected_x = pt_a[0] + alpha * (pt_b[0] - pt_a[0])
            expected_y = pt_a[1] + alpha * (pt_b[1] - pt_a[1])
            drift = np.sqrt((x - expected_x)**2 + (y - expected_y)**2)

            if drift < 100:  # OF didn't wander too far from expected
                result[f] = (x, y)
            else:
                # Use linear interpolation instead
                result[f] = (expected_x, expected_y)
            # Update for next iteration
            prev_pt = next_pt
        else:
            # OF lost track — use linear interpolation
            alpha = (f - frame_a) / gap
            ix = pt_a[0] + alpha * (pt_b[0] - pt_a[0])
            iy = pt_a[1] + alpha * (pt_b[1] - pt_a[1])
            result[f] = (ix, iy)
            # Reset point for next OF attempt
            prev_pt = np.array([[(pt_a[0] + (f+1 - frame_a)/gap * (pt_b[0] - pt_a[0])),
                                  (pt_a[1] + (f+1 - frame_a)/gap * (pt_b[1] - pt_a[1]))]], dtype=np.float32)

        prev_gray = curr_gray

    return result


def find_shot_arcs(track_x, track_y, basket_lx, basket_ly, basket_rx, basket_ry, total):
    """Find shot arcs: parabolic trajectories through hoop zone.

    Cluster frames near basket that show:
    1. Ball approaching from distance (arc launch backtrack)
    2. Minimum distance frame (shot apex)
    3. Ball departing (descent/continuation)
    """
    shots = []

    # Compute distance to nearest basket
    dist = np.full(total, np.inf)
    for i in range(total):
        if np.isnan(track_x[i]):
            continue
        dl = np.sqrt((track_x[i] - basket_lx)**2 + (track_y[i] - basket_ly)**2)
        dr = np.sqrt((track_x[i] - basket_rx)**2 + (track_y[i] - basket_ry)**2)
        dist[i] = min(dl, dr)

    # Frames near basket
    close = [i for i in range(total) if dist[i] < BASKET_PROX]

    if not close:
        return shots

    # Cluster into shot attempts
    clusters = []
    cur = [close[0]]
    for i in range(1, len(close)):
        if close[i] - close[i-1] < DEDUP_RANGE:
            cur.append(close[i])
        else:
            clusters.append(cur)
            cur = [close[i]]
    clusters.append(cur)

    for cluster in clusters:
        best_f = min(cluster, key=lambda f: dist[f])
        best_d = dist[best_f]

        # Verify arc: look backward for launch (ball rising)
        arc_start = best_f
        for j in range(best_f - 1, max(0, best_f - ARC_MAX_FRAMES), -1):
            if np.isnan(track_y[j]):
                break
            # Going backward: if Y is increasing, ball was lower (descending toward us = ascending in time)
            if track_y[j] > track_y[arc_start]:
                arc_start = j
            elif track_y[j] < track_y[best_f] - 5:
                break

        arc_h = track_y[arc_start] - track_y[best_f]
        arc_len = best_f - arc_start

        if arc_len < ARC_MIN_FRAMES or arc_h < APEX_JUMP:
            continue  # no arc — probably just passing/play near basket

        # Classify
        stype = '3PT' if best_d >= THREE_PT_THRESH else '2PT'
        sresult = 'MAKE' if best_d < MAKE_RADIUS else 'MISS'

        shots.append({
            'frame': best_f,
            'arc_start': arc_start,
            'arc_end': best_f,
            'arc_frames': arc_len,
            'arc_height': round(float(arc_h), 1),
            'bx': round(float(track_x[best_f]), 1),
            'by': round(float(track_y[best_f]), 1),
            'dist': round(float(best_d), 1),
            'type': stype,
            'result': sresult,
        })

    return shots


# ================================================================
# MAIN
# ================================================================
if __name__ == '__main__':
    START = time.time()

    # Load v14 detections (NN-verified ball positions)
    log("Loading v14 NN detections...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)

    raw_x = v14['ball_x']  # NaN where NN didn't detect
    raw_y = v14['ball_y']
    total = len(raw_x)
    log(f"v14 data: {total} frames, {np.sum(~np.isnan(raw_x))} NN detections")

    # Load basket positions
    log("Loading basket positions...")
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    blx, bly = v8['basket_left']
    brx, bry = v8['basket_right']
    basket_lx = float(np.nanmean(blx))  # 179
    basket_ly = float(np.nanmean(bly))  # 525
    basket_rx = float(np.nanmean(brx))  # 1009
    basket_ry = float(np.nanmean(bry))  # 466
    log(f"Left: ({basket_lx:.0f}, {basket_ly:.0f}), Right: ({basket_rx:.0f}, {basket_ry:.0f})")

    # --- Phase 1: Sparse NN detections ---
    log("Phase 1: Using NN detections as anchor points...")
    nn_frames = [i for i in range(total) if not np.isnan(raw_x[i])]
    log(f"  NN anchors: {len(nn_frames)} frames")

    # --- Phase 2: Optical flow gap fill ---
    log("Phase 2: Optical flow gap filling...")

    # Initialize track with NN detections
    track_x = raw_x.copy()
    track_y = raw_y.copy()

    cap = cv2.VideoCapture(VIDEO)
    filled = 0
    of_windows = []

    # Find gaps between NN detections
    for k in range(len(nn_frames) - 1):
        fa = nn_frames[k]
        fb = nn_frames[k + 1]
        gap = fb - fa

        if gap > 2 and gap <= 60:
            pt_a = (float(raw_x[fa]), float(raw_y[fa]))
            pt_b = (float(raw_x[fb]), float(raw_y[fb]))
            of_windows.append((fa, fb, pt_a, pt_b))
        elif gap > 60:
            # Big gap — split into sub-windows
            n_splits = (gap + 49) // 50  # ~50 frame chunks
            for s in range(n_splits):
                fa2 = fa + s * gap // n_splits
                fb2 = fa + (s + 1) * gap // n_splits
                # Linear interpolation for distant gaps
                if fb2 < total:
                    alpha_a = (fa2 - fa) / gap
                    alpha_b = (fb2 - fa) / gap
                    ix_a = raw_x[fa] + alpha_a * (raw_x[fb] - raw_x[fa])
                    iy_a = raw_y[fa] + alpha_a * (raw_y[fb] - raw_y[fa])
                    ix_b = raw_x[fa] + alpha_b * (raw_x[fb] - raw_x[fa])
                    iy_b = raw_y[fa] + alpha_b * (raw_y[fb] - raw_y[fa])
                    of_windows.append((fa2, fb2, (ix_a, iy_a), (ix_b, iy_b)))

    log(f"  OF windows: {len(of_windows)}")

    # Process optical flow windows
    batch_size = 0
    for fa, fb, pt_a, pt_b in of_windows:
        gap = fb - fa
        if gap <= 1:
            continue

        # Read frame at fa
        cap.set(cv2.CAP_PROP_POS_FRAMES, fa)
        ret, img_a = cap.read()
        if not ret:
            continue

        gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
        prev_gray = gray_a.copy()
        prev_pt = np.array([[pt_a]], dtype=np.float32)

        for f in range(fa + 1, fb):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, img_f = cap.read()
            if not ret:
                break

            curr_gray = cv2.cvtColor(img_f, cv2.COLOR_BGR2GRAY)

            next_pt, status, _ = cv2.calcOpticalFlowPyrLK(
                prev_gray, curr_gray, prev_pt, None,
                winSize=(15, 15), maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
            )

            alpha = (f - fa) / gap
            expected_x = pt_a[0] + alpha * (pt_b[0] - pt_a[0])
            expected_y = pt_a[1] + alpha * (pt_b[1] - pt_a[1])

            if status[0, 0] == 1:
                ox, oy = float(next_pt[0, 0, 0]), float(next_pt[0, 0, 1])
                drift = np.sqrt((ox - expected_x)**2 + (oy - expected_y)**2)
                if drift < 80:
                    track_x[f] = ox
                    track_y[f] = oy
                else:
                    track_x[f] = expected_x
                    track_y[f] = expected_y
            else:
                track_x[f] = expected_x
                track_y[f] = expected_y

            prev_pt = np.array([[[track_x[f], track_y[f]]]], dtype=np.float32)

            filled += 1
            prev_gray = curr_gray

        batch_size += 1
        if batch_size % 50 == 0:
            elapsed = time.time() - START
            log(f"  OF batch {batch_size}/{len(of_windows)}, filled {filled} gaps, {elapsed:.0f}s")

    cap.release()
    log(f"Phase 2 done: filled {filled} gap frames")

    # --- Phase 3: Smooth ---
    log("Phase 3: Smoothing...")

    # Simple moving average on dense segments
    smooth_x = track_x.copy()
    smooth_y = track_y.copy()

    valid = np.where(~np.isnan(track_x))[0]
    log(f"  Total ball frames: {len(valid)} / {total} ({100*len(valid)/total:.0f}%)")

    # Fill remaining NaN with linear interpolation
    nan_mask = np.isnan(smooth_x)
    if np.any(nan_mask) and np.any(~nan_mask):
        smooth_x[nan_mask] = np.interp(np.where(nan_mask)[0], np.where(~nan_mask)[0], smooth_x[~nan_mask])
        smooth_y[nan_mask] = np.interp(np.where(nan_mask)[0], np.where(~nan_mask)[0], smooth_y[~nan_mask])

    # Light smoothing
    from scipy.signal import savgol_filter
    if len(valid) > SMOOTH_WINDOW:
        try:
            sx = savgol_filter(smooth_x, SMOOTH_WINDOW, 2)
            sy = savgol_filter(smooth_y, SMOOTH_WINDOW, 2)
            smooth_x = sx
            smooth_y = sy
        except Exception:
            pass

    # --- Phase 4: Shot arcs ---
    log("Phase 4: Shot arc detection...")
    shots = find_shot_arcs(smooth_x, smooth_y, basket_lx, basket_ly, basket_rx, basket_ry, total)
    log(f"Shots: {len(shots)}")

    # --- Output ---
    if shots:
        shots.sort(key=lambda s: s['frame'])
        for s in shots:
            log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px arc_h={s['arc_height']:.0f}px")

    pd.DataFrame(shots).to_csv(f'{OUT}/shot_candidates_v16.csv', index=False) if shots else \
        pd.DataFrame(columns=['frame','type','result','dist']).to_csv(f'{OUT}/shot_candidates_v16.csv', index=False)

    pickle.dump({
        'shots': shots,
        'track_x': track_x, 'track_y': track_y,
        'smooth_x': smooth_x, 'smooth_y': smooth_y,
    }, open(f'{OUT}/shot_v16.pkl', 'wb'))

    # Summary
    log("=" * 60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result'] == 'MAKE') + sum(3 for s in t3 if s['result'] == 'MAKE')

    det_count = np.sum(~np.isnan(track_x))
    log(f"Ball coverage: {det_count}/{total} ({100*det_count/total:.0f}%)")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    log("DONE")
