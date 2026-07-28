#!/usr/bin/env python3
"""
Shot detection v29: Trajectory geometry classification
=======================================================
Key insight: NN only detects ball at 3-12ft from basket (approach phase).
Can't use NN distance for 2PT/3PT classification.

Instead, use:
1. Track approach angle (steeper = 3PT, flatter = 2PT)
2. Track total travel distance (longer = 3PT)
3. Dense OF track from v16 to find full trajectory apex
4. Apex height relative to FT line distance
"""
import os, time, pickle, cv2
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


def check_color(hsv, x, y):
    h, w = hsv.shape[:2]
    xi, yi = int(x), int(y)
    return 0 <= xi < w and 0 <= yi < h and 2 <= hsv[yi, xi, 0] <= 32 and hsv[yi, xi, 1] >= 10


def extract_template(img_gray, cx, cy, radius=8):
    h, w = img_gray.shape[:2]
    x1, x2 = max(0, int(cx) - radius), min(w, int(cx) + radius)
    y1, y2 = max(0, int(cy) - radius), min(h, int(cy) + radius)
    patch = img_gray[y1:y2, x1:x2].copy()
    if patch.size < 9:
        return None
    hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-8)
    return {'hist': hist, 'patch': patch.copy()}


def match_template(img_gray, x, y, template, radius=8):
    if template is None:
        return True
    h, w = img_gray.shape[:2]
    x1, x2 = max(0, int(x) - radius), min(w, int(x) + radius + 1)
    y1, y2 = max(0, int(y) - radius), min(h, int(y) + radius + 1)
    patch = img_gray[y1:y2, x1:x2]
    if patch.size < 9:
        return False
    hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-8)
    corr = cv2.compareHist(template['hist'].astype(np.float32),
                           hist.astype(np.float32), cv2.HISTCMP_CORREL)
    ref = template.get('patch')
    if ref is not None and ref.size > 0:
        area_ratio = float(patch.size) / float(ref.size)
    else:
        area_ratio = 1.0
    return corr > 0.5 and 0.3 < area_ratio < 3.0


def track_bidir(cap, fnum, cx, cy, total):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
    ret, img0 = cap.read()
    if not ret:
        return []
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
    if not check_color(hsv0, cx, cy):
        return []

    template = extract_template(gray0, cx, cy, radius=8)

    pts = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []
    for f in range(fnum - 1, max(fnum - BWD_WIN, 0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pts, None,
            winSize=(15,15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                if abs(nx - float(pts[0, 0, 0])) < MAX_JUMP and abs(ny - float(pts[0, 0, 1])) < MAX_JUMP:
                    backward.append((f, nx, ny))
                    pts = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
        gray_prev = gf

    pts = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    forward = []
    for f in range(fnum + 1, min(fnum + FWD_WIN, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pts, None,
            winSize=(15,15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                if abs(nx - float(pts[0, 0, 0])) < MAX_JUMP and abs(ny - float(pts[0, 0, 1])) < MAX_JUMP:
                    forward.append((f, nx, ny))
                    pts = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
        gray_prev = gf

    return backward[::-1] + [(fnum, float(cx), float(cy))] + forward


def classify_geometry(track, anchor_x, anchor_y):
    """Classify shot using trajectory geometry.

    Key features:
    1. Approach angle: angle between launch direction and basket direction
       - 3PT: steep approach (ball comes from high arc, launch far from basket)
       - 2PT: flat approach (ball comes from close, direct line)
    2. Track span: total distance traveled in the track
       - 3PT: longer arc = more travel
       - 2PT: shorter arc = less travel
    3. Direction consistency: how straight the path is
    4. Backward extension: how far back the OF tracker goes before losing the ball
       - 3PT: tracker extends further back (ball visible longer before rim)
    """
    if len(track) < MIN_PTS:
        return None

    fs = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if len(jumps) > 0 and np.max(jumps) > MAX_JUMP:
        return None

    total_travel = np.sqrt((xs[-1] - xs[0])**2 + (ys[-1] - ys[0])**2)
    if total_travel < 30:
        return None

    dists_l = np.sqrt((xs - BLX)**2 + (ys - BLY)**2)
    dists_r = np.sqrt((xs - BRX)**2 + (ys - BRY)**2)
    dists_px = np.minimum(dists_l, dists_r)
    min_dist_px = float(np.min(dists_px))
    best_idx = int(np.argmin(dists_px))

    if min_dist_px > 180:
        return None

    # Nearest basket
    d_l = np.sqrt((anchor_x - BLX)**2 + (anchor_y - BLY)**2)
    d_r = np.sqrt((anchor_x - BRX)**2 + (anchor_y - BRY)**2)
    basket_x = BLX if d_l < d_r else BRX
    basket_y = BLY if d_l < d_r else BRY
    anchor_px = min(d_l, d_r)

    # Feature 1: Approach angle
    # Direction from track start to basket
    start_to_basket = np.array([basket_x - xs[0], basket_y - ys[0]])
    # Direction of motion at start of track (first 5 points)
    if len(xs) >= 5:
        motion_dir = np.array([xs[4] - xs[0], ys[4] - ys[0]])
    else:
        motion_dir = np.array([xs[-1] - xs[0], ys[-1] - ys[0]])

    # Angle between approach and basket direction
    norm_stb = np.linalg.norm(start_to_basket)
    norm_motion = np.linalg.norm(motion_dir)
    if norm_stb > 0 and norm_motion > 0:
        cos_angle = np.dot(start_to_basket, motion_dir) / (norm_stb * norm_motion)
        cos_angle = np.clip(cos_angle, -1, 1)
        approach_angle = np.degrees(np.arccos(cos_angle))
    else:
        approach_angle = 90

    # Feature 2: Track span (pixels)
    span = total_travel

    # Feature 3: Max distance from basket in track
    max_dist_from_basket = float(np.max(dists_px))

    # Feature 4: Track duration (frames)
    track_duration = fs[-1] - fs[0]

    # Feature 5: Vertical range (y max - min)
    y_range = float(np.max(ys) - np.min(ys))

    # Classification rules:
    # 3PT: steep approach (angle > 30°), long span (>200px), high y_range (>150px)
    # 2PT: flat approach, shorter span, lower arc
    # FT: very flat, close to basket (anchor < 100px), short track

    if anchor_px < 80 and track_duration < 20 and approach_angle < 25:
        stype = 'FT'
    elif (approach_angle > 25 and span > 180 and y_range > 100) or max_dist_from_basket > 200:
        stype = '3PT'
    else:
        stype = '2PT'

    # Make/miss
    smooth = float(np.mean(jumps)) if len(jumps) > 0 else 0
    is_make = (min_dist_px < MAKE_R) or (min_dist_px < MAKE_R + 15 and len(track) > 14 and smooth < 30)
    result = 'MAKE' if is_make else 'MISS'

    return {
        'frame': int(fs[best_idx]),
        'type': stype,
        'result': result,
        'closest_px': round(min_dist_px, 1),
        'anchor_px': round(anchor_px, 1),
        'approach_angle': round(approach_angle, 1),
        'span': round(span, 1),
        'y_range': round(y_range, 1),
        'max_dist': round(max_dist_from_basket, 1),
        'track': len(track),
        'smooth': round(smooth, 1),
    }


if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2 + (ry[i]-BLY)**2),
                     np.sqrt((rx[i]-BRX)**2 + (ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(cands):
        track = track_bidir(cap, f, cx, cy, total)
        cls = classify_geometry(track, cx, cy)
        if cls:
            shots.append(cls)
            log(f"  [{ci+1:2d}] F{f}: {cls['type']} {cls['result']} "
                f"anchor={cls['anchor_px']:.0f}px angle={cls['approach_angle']:.0f} "
                f"span={cls['span']:.0f}px yrange={cls['y_range']:.0f}px "
                f"maxdist={cls['max_dist']:.0f}px track={cls['track']}f")
        else:
            log(f"  [{ci+1:2d}] F{f}: REJECTED ({len(track)}f)")
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

    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    ft = [s for s in shots if s['type'] == 'FT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = (sum(2 for s in t2 if s['result'] == 'MAKE') +
           sum(3 for s in t3 if s['result'] == 'MAKE') +
           sum(1 for s in ft if s['result'] == 'MAKE'))

    log(f"\n{'='*60}")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result']=='MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"angle={s['approach_angle']:.0f} span={s['span']:.0f} maxdist={s['max_dist']:.0f}")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v29.csv', index=False)
