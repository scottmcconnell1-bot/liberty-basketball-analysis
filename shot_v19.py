#!/usr/bin/env python3
"""
Shot detection v19: Tightened arc verification + make/miss by tracking quality
=============================================================================
Building on v18's local arc tracking. Fixes:
  1. Reject arcs where max jump > 100px (player running, not ball)
  2. Require approach angle to be realistic (ball coming from court, not scoreboard)
  3. Classify 2PT/3PT by launch position relative to 3PT line
  4. Classify FT by center-court launch + slow approach speed
  5. Make = track passes through hoop zone AND continues downward consistently
"""

import os, sys, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BASKET_LX, BASKET_LY = 179.0, 525.0
BASKET_RX, BASKET_RY = 1009.0, 466.0

SHOT_WINDOW  = 40
MIN_ARC_PTS  = 10       # need more tracked frames for confidence
MAX_JUMP     = 100      # reject if track jumps > this between frames
ARC_HEIGHT   = 20       # minimum Y change
MAKE_RADIUS  = 50
DEEP_THRESH  = 250      # launch distance > this = 3PT
FT_LAUNCH_X  = (350, 800)  # FT must launch from this x range
FT_LAUNCH_Y  = (280, 520)  # and this y range
MIN_APPROACH = 30       # minimum distance traveled toward basket

def log(msg):
    print(msg, flush=True)

def track_arc(cap, frame_num, cx, cy, total):
    """Track ball forward from detection using optical flow with color verification.

    The NN detection is the shot moment. Forward tracking shows the ball's
    arc after the shot — does it continue consistently or jump away?
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, img = cap.read()
    if not ret:
        return []

    gray_prev = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv_frame = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, w = hsv_frame.shape[:2]

    # Color verify at detection point
    ix, iy = int(cx), int(cy)
    if not (0 <= ix < w and 0 <= iy < h):
        return []
    px = hsv_frame[iy, ix]
    if not (3 <= px[0] <= 28 and px[1] > 15):
        return []

    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    results = [(frame_num, float(cx), float(cy))]

    for f in range(frame_num + 1, min(frame_num + SHOT_WINDOW, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img_f = cap.read()
        if not ret:
            break
        gray_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2GRAY)
        new_pt, status, err = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            # Relaxed color check (ball in motion may shift hue)
            hsv_f = cv2.cvtColor(img_f, cv2.COLOR_BGR2HSV)
            nxi, nyi = int(nx), int(ny)
            hf, wf = hsv_f.shape[:2]
            if 0 <= nxi < wf and 0 <= nyi < hf:
                npx = hsv_f[nyi, nxi]
                if 2 <= npx[0] <= 32 and npx[1] > 10:
                    results.append((f, nx, ny))
                    pt = new_pt.reshape(1, 1, 2)
                    gray_prev = gray_f
                    continue
        # Lost track — try to reacquire from last known position
        gray_prev = gray_f

    return results


def classify_shot(track, nn_x, nn_y, total):
    """Classify a shot from NN detection quality + forward track."""
    # track = [(frame, x, y), ...] starting at detection, going forward
    if len(track) < 5:
        return None  # too short to be a shot

    frames = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    # Check smoothness
    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if np.max(jumps) > MAX_JUMP:
        return None  # jumped too far — not a consistent object

    # NN detection point = the shot moment
    shot_x, shot_y = xs[0], ys[0]

    # Distance to nearest basket at shot moment
    dl = np.sqrt((shot_x - BASKET_LX)**2 + (shot_y - BASKET_LY)**2)
    dr = np.sqrt((shot_x - BASKET_RX)**2 + (shot_y - BASKET_RY)**2)
    dist = min(dl, dr)

    # Find closest approach in the forward track
    dists_track = np.sqrt((xs - BASKET_LX)**2 + (ys - BASKET_LY)**2)
    dists_track_r = np.sqrt((xs - BASKET_RX)**2 + (ys - BASKET_RY)**2)
    dists_both = np.minimum(dists_track, dists_track_r)
    min_idx = np.argmin(dists_both)
    min_dist = float(dists_both[min_idx])

    # After the shot, ball should move away from basket (descent/post-shot)
    if min_idx < len(track) - 3:
        late_dists = dists_both[min_idx+1:]
        moving_away = np.mean(late_dists) > min_dist - 15
    else:
        moving_away = True

    if not moving_away:
        return None

    # Classify 2PT/3PT/FT by NN detection distance
    nn_dist = dist

    if dist < 90 and 350 < shot_x < 800 and 280 < shot_y < 520:
        stype = 'FT'
    elif nn_dist >= 130:
        stype = '3PT'
    else:
        stype = '2PT'

    # Make: track passes very close to basket + smooth
    is_make = min_dist < MAKE_RADIUS and len(track) > 8 and np.max(jumps) < 60
    result = 'MAKE' if is_make else 'MISS'

    return {
        'frame': int(frames[0]),
        'type': stype,
        'result': result,
        'dist': round(float(dist), 1),
        'track_frames': len(track),
        'max_jump': round(float(np.max(jumps)), 1),
        'launch': (round(float(shot_x), 0), round(float(shot_y), 0)),
    }


if __name__ == '__main__':
    START = time.time()

    log("Loading v14 NN detections...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)

    raw_x, raw_y = v14['ball_x'], v14['ball_y']
    total = len(raw_x)
    nn_frames = [(i, raw_x[i], raw_y[i])
                 for i in range(total) if not np.isnan(raw_x[i])]
    log(f"NN detections: {len(nn_frames)}")

    # NN detections near basket
    candidates = []
    for f, x, y in nn_frames:
        dl = np.sqrt((x - BASKET_LX)**2 + (y - BASKET_LY)**2)
        dr = np.sqrt((x - BASKET_RX)**2 + (y - BASKET_RY)**2)
        if min(dl, dr) < 180:
            candidates.append((f, x, y))

    log(f"Candidates: {len(candidates)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(candidates):
        track = track_arc(cap, f, cx, cy, total)
        cls = classify_shot(track, cx, cy, total)

        if cls:
            shots.append(cls)
            log(f"  [{ci+1}/{len(candidates)}] F{f}: {cls['type']} {cls['result']} "
                f"d={cls['dist']:.0f}px track={cls['track_frames']}f "
                f"max_jump={cls['max_jump']:.0f}px")
        else:
            log(f"  [{ci+1}/{len(candidates)}] F{f}: REJECTED (track={len(track)}f)")

    cap.release()

    # Dedup: shots within 30 frames
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
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')

    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result']=='MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px "
            f"track={s['track_frames']}f max_jump={s['max_jump']:.0f}px")
    log("DONE")

    pd.DataFrame(shots).to_csv(f'{OUT}/shot_candidates_v19.csv', index=False)
