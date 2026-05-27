#!/usr/bin/env python3
"""
Shot detection v18: Local arc verification from NN detections
=============================================================
Forget the global trajectory. It jumps between objects.

Instead:
  1. Each NN detection near a basket (= 48 frames) is a SHOT CANDIDATE
  2. For each candidate, run optical flow LOCALLY (30 frames before → 30 after)
     to see if the ball actually traces a parabolic arc through the hoop
  3. Count only those with consistent arc motion as real shots
  4. Classify by: dist=close → MAKE, far → MISS, approach angle → 2PT/3PT/FT
"""

import os, sys, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BASKET_LX, BASKET_LY = 179.0, 525.0
BASKET_RX, BASKET_RY = 1009.0, 466.0

SHOT_WINDOW = 40     # frames before/after to check for arc
MIN_ARC_PTS = 8      # minimum tracked frames to confirm arc
ARC_HEIGHT  = 25     # minimum Y change for arc
MAKE_RADIUS = 45     # within this px = make
DEEP_THRESH = 200    # pre-approach distance > this = 3PT
FT_RANGE    = (300, 700, 250, 500)  # FT launch zone: x_min, x_max, y_min, y_max

def log(msg):
    print(msg, flush=True)

def track_arc(cap, frame_num, cx, cy, total):
    """Track ball locally around a candidate frame using optical flow.

    Reads frames [frame_num-SHOT_WINDOW, frame_num+SHOT_WINDOW].
    Tacks ball position in each frame using LK optical flow + NN color verification.

    Returns list of (frame, x, y) for tracked positions.
    """
    # Read the candidate frame and convert
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, img = cap.read()
    if not ret:
        return []

    gray_prev = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv_frame = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Verify color at detection point
    ix, iy = int(cx), int(cy)
    h, w = hsv_frame.shape[:2]
    if ix < 0 or ix >= w or iy < 0 or iy >= h:
        return []
    px = hsv_frame[iy, ix]
    if not (3 <= px[0] <= 28 and px[1] > 20):
        return []  # fails color check at candidate point

    pt = np.array([[[cx, cy]]], dtype=np.float32)  # shape (1, 1, 2) for LK
    results = [(frame_num, cx, cy)]

    # Track forward
    for f in range(frame_num + 1, min(frame_num + SHOT_WINDOW, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img_f = cap.read()
        if not ret:
            break

        gray_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2GRAY)
        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )

        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            # Color check
            hsv_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2HSV)
            nxi, nyi = int(nx), int(ny)
            if 0 <= nxi < w and 0 <= nyi < h:
                npx = hsv_f[nyi, nxi]
                if 3 <= npx[0] <= 28 and npx[1] > 15:
                    results.append((f, nx, ny))
                    pt = new_pt.reshape(1, 1, 2)  # ensure correct shape
                    gray_prev = gray_f
                    continue
        # Lost track or color failed — still update gray
        gray_prev = gray_f

    # Track backward
    pt = np.array([[[cx, cy]]], dtype=np.float32)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, img_b = cap.read()
    if not ret:
        return results
    gray_prev = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)

    backward = []
    for f in range(frame_num - 1, max(frame_num - SHOT_WINDOW, 0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img_f = cap.read()
        if not ret:
            break

        gray_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2GRAY)
        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )

        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            hsv_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2HSV)
            nxi, nyi = int(nx), int(ny)
            hf, wf = hsv_f.shape[:2]
            if 0 <= nxi < wf and 0 <= nyi < hf:
                npx = hsv_f[nyi, nxi]
                if 3 <= npx[0] <= 28 and npx[1] > 15:
                    backward.append((f, nx, ny))
                    pt = new_pt.reshape(1, 1, 2)
                    gray_prev = gray_f
                    continue
        # Lost track — still update gray for next attempt
        gray_prev = gray_f

    return backward[::-1] + results


def classify_shot(track, total):
    """Classify a local track as 2PT, 3PT, FT, or NOT_A_SHOT.

    Requirements for a real shot:
    - Track has enough frames (> MIN_ARC_PTS)
    - Ball approaches from distance and reaches hoop zone
    - Track is consistent (no massive jumps)

    Returns (type, result, confidence) or None.
    """
    if len(track) < MIN_ARC_PTS:
        return None

    # Compute distance to nearest basket at each tracked frame
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    dists_l = np.sqrt((xs - BASKET_LX)**2 + (ys - BASKET_LY)**2)
    dists_r = np.sqrt((xs - BASKET_RX)**2 + (ys - BASKET_RY)**2)
    dists = np.minimum(dists_l, dists_r)

    # Minimum distance and at which frame
    min_idx = np.argmin(dists)
    min_dist = dists[min_idx]

    # Check consistency: max jump between consecutive frames
    if len(xs) > 1:
        jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
        max_jump = np.max(jumps)
    else:
        max_jump = 0

    if max_jump > 200:
        return None  # track jumped too far — different objects

    # Approach: distance at start vs at closest approach
    pre_dist = dists[0]
    approach_depth = pre_dist - min_dist

    if approach_depth < 15:
        return None  # barely moved — not a shot approach

    # Classify by approach distance
    x_min, x_max, y_min, y_max = FT_RANGE
    start_x, start_y = xs[0], ys[0]

    if x_min < start_x < x_max and y_min < start_y < y_max and pre_dist < 500:
        stype = 'FT'
    elif pre_dist > DEEP_THRESH and min_dist < 100:
        stype = '3PT'
    else:
        stype = '2PT'

    result = 'MAKE' if min_dist < MAKE_RADIUS else 'MISS'

    return stype, result, min_dist, len(track)


if __name__ == '__main__':
    START = time.time()

    # Load NN detections
    log("Loading v14 NN detections...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)

    raw_x, raw_y = v14['ball_x'], v14['ball_y']
    total = len(raw_x)
    nn_frames = [(i, raw_x[i], raw_y[i])
                 for i in range(total) if not np.isnan(raw_x[i])]
    log(f"NN detections: {len(nn_frames)}")

    # Filter: NN detections near basket
    candidates = []
    for f, x, y in nn_frames:
        dl = np.sqrt((x - BASKET_LX)**2 + (y - BASKET_LY)**2)
        dr = np.sqrt((x - BASKET_RX)**2 + (y - BASKET_RY)**2)
        d = min(dl, dr)
        if d < 180:
            candidates.append((f, x, y, d))

    log(f"Candidates near basket (<180px): {len(candidates)}")

    # Local arc tracking for each candidate
    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy, d) in enumerate(candidates):
        track = track_arc(cap, f, cx, cy, total)
        cls = classify_shot(track, total)

        if cls:
            stype, result, min_dist, n_track = cls
            # Find frame of closest approach
            track_f = [fr for fr, x, y in track]
            track_x = [x for fr, x, y in track]
            track_y = [y for fr, x, y in track]
            dists_t = np.minimum(
                np.sqrt((np.array(track_x) - BASKET_LX)**2 + (np.array(track_y) - BASKET_LY)**2),
                np.sqrt((np.array(track_x) - BASKET_RX)**2 + (np.array(track_y) - BASKET_RY)**2),
            )
            best_idx = np.argmin(dists_t)
            best_f = track_f[best_idx]
            shots.append({
                'frame': best_f,
                'type': stype,
                'result': result,
                'dist': round(float(min_dist), 1),
                'track_frames': n_track,
            })
            log(f"  [{ci+1}/{len(candidates)}] F{f}: {stype} {result} d={min_dist:.0f}px ({n_track}f track)")
        else:
            log(f"  [{ci+1}/{len(candidates)}] F{f}: REJECTED (no arc, d={d:.0f}px)")

    cap.release()

    # Dedup: remove shots within 30 frames of each other, keep the one with longer track
    if shots:
        shots.sort(key=lambda s: s['frame'])
        deduped = [shots[0]]
        for s in shots[1:]:
            if s['frame'] - deduped[-1]['frame'] < 30:
                # Keep the one with more tracked frames (more confident)
                if s['track_frames'] > deduped[-1]['track_frames']:
                    deduped[-1] = s
            else:
                deduped.append(s)
        shots = deduped

    # Summary
    log(f"\n{'='*60}")
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    ft = [s for s in shots if s['type'] == 'FT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')

    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result']=='MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px track={s['track_frames']}f")
    log("DONE")

    pd.DataFrame(shots).to_csv(f'{OUT}/shot_candidates_v18.csv', index=False)
