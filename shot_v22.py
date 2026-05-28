#!/usr/bin/env python3
"""Shot detection v22: Bidirectional color-verified OF arc tracking."""
import os, time, pickle, cv2, sys
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
FWD_WIN, BWD_WIN = 20, 15
MIN_PTS, MAX_JUMP = 10, 80
MAKE_R = 55

def log(msg):
    print(msg, flush=True)

def nn_nearest_to(f, rx, ry, total):
    best_d, best_x, best_y = 9999, None, None
    for df in range(0, 21):
        for s in [0, 1, -1]:
            fi = f + s * df
            if 0 <= fi < total and not np.isnan(rx[fi]):
                d = min(np.sqrt((rx[fi]-BLX)**2+(ry[fi]-BLY)**2), np.sqrt((rx[fi]-BRX)**2+(ry[fi]-BRY)**2))
                if d < best_d:
                    best_d, best_x, best_y = d, rx[fi], ry[fi]
    return best_x, best_y, best_d

def check_color(hsv, x, y):
    h, w = hsv.shape[:2]
    xi, yi = int(x), int(y)
    return 0 <= xi < w and 0 <= yi < h and 2 <= hsv[yi, xi, 0] <= 32 and hsv[yi, xi, 1] >= 10

def track_bidir(cap, fnum, cx, cy, total):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
    ret, img0 = cap.read()
    if not ret: return []
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
    if not check_color(hsv0, cx, cy): return []

    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []
    for f in range(fnum-1, max(fnum-BWD_WIN,0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret: break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pt, None, winSize=(15,15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0,0] == 1:
            nx, ny = float(np2[0,0,0]), float(np2[0,0,1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny):
                jx, jy = abs(nx-float(pt[0,0,0])), abs(ny-float(pt[0,0,1]))
                if jx < MAX_JUMP and jy < MAX_JUMP:
                    backward.append((f, nx, ny))
                    pt = np2.reshape(1,1,2); gray_prev = gf; continue
        gray_prev = gf

    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    forward = []
    for f in range(fnum+1, min(fnum+FWD_WIN, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret: break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pt, None, winSize=(15,15), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0,0] == 1:
            nx, ny = float(np2[0,0,0]), float(np2[0,0,1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny):
                jx, jy = abs(nx-float(pt[0,0,0])), abs(ny-float(pt[0,0,1]))
                if jx < MAX_JUMP and jy < MAX_JUMP:
                    forward.append((f, nx, ny))
                    pt = np2.reshape(1,1,2); gray_prev = gf; continue
        gray_prev = gf

    return backward[::-1] + [(fnum, float(cx), float(cy))] + forward


def classify(track, rx, ry, total, anchor_x, anchor_y, debug=False):
    if debug: print(f'[DBG] anchor=({anchor_x:.0f},{anchor_y:.0f})', file=sys.stderr)

    if len(track) < MIN_PTS:
        if debug: print(f'[DBG] REJ len={len(track)}<{MIN_PTS}', file=sys.stderr)
        return None

    fs = np.array([f for f,x,y in track])
    xs = np.array([x for f,x,y in track])
    ys = np.array([y for f,x,y in track])

    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if np.max(jumps) > MAX_JUMP:
        if debug: print(f'[DBG] REJ max_jump={np.max(jumps):.1f}>{MAX_JUMP}', file=sys.stderr)
        return None

    dists = np.minimum(np.sqrt((xs-BLX)**2+(ys-BLY)**2), np.sqrt((xs-BRX)**2+(ys-BRY)**2))
    min_idx = int(np.argmin(dists))
    min_dist = float(dists[min_idx])
    best_f = int(fs[min_idx])

    nn_x, nn_y, nn_d = nn_nearest_to(best_f, rx, ry, total)
    anchor_d = min(np.sqrt((anchor_x-BLX)**2+(anchor_y-BLY)**2), np.sqrt((anchor_x-BRX)**2+(anchor_y-BRY)**2))

    if debug: print(f'[DBG] min_dist={min_dist:.0f} nn_d={nn_d:.0f} anchor_d={anchor_d:.0f}', file=sys.stderr)

    if nn_d > 180 and anchor_d > 180:
        if debug: print(f'[DBG] REJ nn&anchor both>180', file=sys.stderr)
        return None

    cls_x = anchor_x if anchor_d <= nn_d else nn_x
    cls_y = anchor_y if anchor_d <= nn_d else nn_y
    cls_d = min(anchor_d, nn_d)

    total_travel = np.sqrt((xs[-1]-xs[0])**2 + (ys[-1]-ys[0])**2)
    if total_travel < 30:
        if debug: print(f'[DBG] REJ travel={total_travel:.0f}<30', file=sys.stderr)
        return None

    if min_dist > 180:
        if debug: print(f'[DBG] REJ min_dist={min_dist:.0f}>180', file=sys.stderr)
        return None

    # Classify type by anchor NN detection (most reliable)
    if cls_d >= 130:
        stype = '3PT'
    elif 350 < cls_x < 800 and 250 < cls_y < 520 and cls_d < 400:
        stype = 'FT'
    else:
        stype = '2PT'

    smooth = np.mean(jumps)
    is_make = (min_dist < MAKE_R) or (min_dist < MAKE_R + 15 and len(track) > 14 and smooth < 30)
    result = 'MAKE' if is_make else 'MISS'

    return {'frame': best_f, 'type': stype, 'result': result,
            'closest': round(min_dist, 1), 'nn_dist': round(cls_d, 1),
            'track': len(track), 'smooth': round(smooth, 1)}


if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f: v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2+(ry[i]-BLY)**2), np.sqrt((rx[i]-BRX)**2+(ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []
    for ci, (f, cx, cy) in enumerate(cands):
        track = track_bidir(cap, f, cx, cy, total)
        debug = int(f) in (1609, 2051, 236, 237, 1290, 1614, 120)
        if debug:
            print(f'[SETUP] F{f}: anchor=({cx:.0f},{cy:.0f}) track={len(track)}', file=sys.stderr)
        cls = classify(track, rx, ry, total, cx, cy, debug=debug)
        if cls:
            shots.append(cls)
            log(f"  [{ci+1}] F{f}: {cls['type']} {cls['result']} closest={cls['closest']:.0f}px nn={cls['nn_dist']:.0f}px track={cls['track']}f")
        else:
            log(f"  [{ci+1}] F{f}: REJECTED ({len(track)}f)")
    cap.release()

    if shots:
        shots.sort(key=lambda s: s['frame'])
        deduped = [shots[0]]
        for s in shots[1:]:
            if s['frame'] - deduped[-1]['frame'] < 30:
                if s['track'] > deduped[-1]['track']: deduped[-1] = s
            else: deduped.append(s)
        shots = deduped

    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    ft = [s for s in shots if s['type'] == 'FT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE') + sum(1 for s in ft if s['result']=='MAKE')

    log(f"\n{'='*60}")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result']=='MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} closest={s['closest']:.0f}px nn={s['nn_dist']:.0f}px")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v22.csv', index=False)
