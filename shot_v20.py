#!/usr/bin/env python3
"""
Shot detection v20: Bidirectional local OF arc tracking
========================================================
Anchor at NN detection. Track backward ~15f to find shot launch.
Track forward ~15f to find post-shot motion.
Use full track to determine closest approach + arc quality.
"""
import os, sys, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

FWD_WIN   = 20   # forward track window
BWD_WIN   = 15   # backward track window
MIN_PTS   = 12   # minimum total tracked points
MAX_JUMP  = 120  # max px jump between consecutive frames
MAKE_DIST = 50   # within this = make
FT_ZONE   = (350, 800, 280, 500)  # x_lo, x_hi, y_lo, y_hi

def log(msg):
    print(msg, flush=True)

def track_bidirectional(cap, fnum, cx, cy, total):
    """Track backward then forward from anchor point."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
    ret, img0 = cap.read()
    if not ret:
        return []
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    h, w = gray0.shape[:2]

    ix, iy = int(cx), int(cy)
    if 0 <= ix < w and 0 <= iy < h:
        # Use grayscale brightness as rough check for ball vs dark jersey
        brightness = gray0[iy, ix]
        if brightness < 40:  # too dark — probably not ball
            return []
    else:
        return []

    anchor = (float(fnum), float(cx), float(cy))

    # Track backward
    backward = []
    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0

    for f in range(fnum - 1, max(fnum - BWD_WIN, 0), -1):
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
            # Bounding box check
            if 50 < nx < w - 50 and 50 < ny < h - 50:
                jump = np.sqrt((nx - float(pt[0, 0, 0]))**2 + (ny - float(pt[0, 0, 1]))**2)
                if jump < MAX_JUMP:
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
            if 50 < nx < w - 50 and 50 < ny < h - 50:
                jump = np.sqrt((nx - float(pt[0, 0, 0]))**2 + (ny - float(pt[0, 0, 1]))**2)
                if jump < MAX_JUMP:
                    forward.append((f, nx, ny))
                    pt = new_pt.reshape(1, 1, 2)
                    gray_prev = gray_f
                    continue
        gray_prev = gray_f

    track = backward[::-1] + [anchor] + forward
    return track


def classify(track, nn_dist):
    """Classify shot from bidirectional track."""
    if len(track) < MIN_PTS:
        return None

    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])
    fs = np.array([f for f, x, y in track])

    # Consistency
    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if np.max(jumps) > MAX_JUMP:
        return None

    # Distance to nearest basket
    dists = np.minimum(
        np.sqrt((xs - BLX)**2 + (ys - BLY)**2),
        np.sqrt((xs - BRX)**2 + (ys - BRY)**2),
    )

    min_idx = np.argmin(dists)
    min_dist = float(dists[min_idx])
    best_f = int(fs[min_idx])

    # Launch and landing
    launch_x, launch_y = xs[0], ys[0]
    land_x, land_y = xs[-1], ys[-1]
    land_dist = float(np.minimum(
        np.sqrt((land_x - BLX)**2 + (land_y - BLY)**2),
        np.sqrt((land_x - BRX)**2 + (land_y - BRY)**2),
    ))

    # Ball should travel toward basket then away
    total_travel = abs(nn_dist - min_dist)
    if total_travel < 20:
        return None  # barely moved — not a shot

    # Classify type
    ft_xl, ft_xh, ft_yl, ft_yh = FT_ZONE
    launch_in_ft = (ft_xl < launch_x < ft_xh and ft_yl < launch_y < ft_yh)
    dist_from_basket = float(nn_dist)

    if launch_in_ft and dist_from_basket < 400:
        stype = 'FT'
    elif dist_from_basket >= 130 and min_dist < 200:
        stype = '3PT'
    else:
        stype = '2PT'

    # Make: closest approach < 50px + smooth track
    is_make = min_dist < MAKE_DIST and np.mean(jumps) < 40
    result = 'MAKE' if is_make else 'MISS'

    return {
        'frame': best_f,
        'type': stype,
        'result': result,
        'dist': round(min_dist, 1),
        'track_frames': len(track),
        'nn_dist': round(float(nn_dist), 1),
        'launch': (round(launch_x, 0), round(launch_y, 0)),
    }


if __name__ == '__main__':
    START = time.time()
    log("Loading v14 NN detections...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)

    raw_x, raw_y = v14['ball_x'], v14['ball_y']
    total = len(raw_x)

    candidates = []
    for i in range(total):
        if np.isnan(raw_x[i]):
            continue
        dl = np.sqrt((raw_x[i] - BLX)**2 + (raw_y[i] - BLY)**2)
        dr = np.sqrt((raw_x[i] - BRX)**2 + (raw_y[i] - BRY)**2)
        d = min(dl, dr)
        if d < 180:
            candidates.append((i, raw_x[i], raw_y[i], d))

    log(f"Candidates: {len(candidates)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy, d) in enumerate(candidates):
        track = track_bidirectional(cap, f, cx, cy, total)
        cls = classify(track, d)
        if cls:
            shots.append(cls)
            log(f"  [{ci+1}/{len(candidates)}] F{f}: {cls['type']} {cls['result']} "
                f"d={cls['dist']:.0f}px (nn={cls['nn_dist']:.0f}px) track={cls['track_frames']}f")
        else:
            log(f"  [{ci+1}/{len(candidates)}] F{f}: REJECTED (track={len(track)}f)")

    cap.release()

    # Dedup
    if shots:
        shots.sort(key=lambda s: s['frame'])
        deduped = [shots[0]]
        for s in shots[1:]:
            if s['frame'] - deduped[-1]['frame'] < 30:
                if s['track_frames'] > deduped[-1]['track_frames']:
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
            f"closest={s['dist']:.0f}px (nn={s['nn_dist']:.0f}px) track={s['track_frames']}f "
            f"launch={s['launch']}")
    log("DONE")

    # Create output with the fields we want
    out = []
    for s in shots:
        out.append({
            'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['dist'], 'track_frames': s['track_frames'],
        })
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v20.csv', index=False)
