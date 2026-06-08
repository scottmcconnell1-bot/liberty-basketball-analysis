#!/usr/bin/env python3
"""
Shot detection v31: Hybrid v16+v23 approach
============================================
Uses v16 dense OF track (97% coverage) to find the ball's position
throughout the game, then uses v23 appearance-locked anchors near
the basket to identify which dense track segments are actual shots.

Key insight: even though v16 tracks the wrong things sometimes,
the APPEARANCE-LOCKED anchors from v23 tell us:
"these specific dense-track positions are definitely the ball"

So:
1. v16 gives us a dense trajectory for every frame
2. v23 anchors identify which frames are "ball near basket"
3. From those anchor frames, trace backward through v16 to find
   the ball's apex (highest point of arc before descent)
4. Apex position + approach geometry = shot classification
"""
import os, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
FWD_WIN, BWD_WIN = 25, 20
MIN_PTS, MAX_JUMP = 10, 80
MAKE_R = 55


def log(msg):
    print(msg, flush=True)


# ---- Appearance-locked tracking (from v23) ----

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


def find_apex_in_dense_track(anchor_frame, anchor_x, anchor_y, dense_x, dense_y, total, max_lookback=50):
    """Find the apex (highest point) of the shot arc by looking backward
    through the dense track from the anchor point.

    The apex is the point where:
    1. The ball is farthest from the basket (top of arc)
    2. The y-coordinate is at an extreme (high point)
    3. The direction changes from upward to downward

    Returns (apex_frame, apex_x, apex_y, apex_dist_from_basket).
    """
    # Find the dense track position at the anchor frame
    if np.isnan(dense_x[anchor_frame]):
        # Find nearest non-NaN position
        for delta in range(1, 10):
            if anchor_frame - delta >= 0 and not np.isnan(dense_x[anchor_frame - delta]):
                anchor_frame -= delta
                break
            if anchor_frame + delta < total and not np.isnan(dense_x[anchor_frame + delta]):
                anchor_frame += delta
                break

    # Look backward through dense track for the apex
    best_apex_frame = anchor_frame
    best_apex_dist = 0

    for f in range(anchor_frame, max(anchor_frame - max_lookback, 0), -1):
        if np.isnan(dense_x[f]):
            continue
        d = min(np.sqrt((dense_x[f] - BLX)**2 + (dense_y[f] - BLY)**2),
                np.sqrt((dense_x[f] - BRX)**2 + (dense_y[f] - BRY)**2))
        if d > best_apex_dist:
            best_apex_dist = d
            best_apex_frame = f

    return best_apex_frame, dense_x[best_apex_frame], dense_y[best_apex_frame], best_apex_dist


def classify_v31(track, anchor_x, anchor_y, apex_x, apex_y, apex_dist, basket_dist_ft, scale):
    """Classify shot using anchor + apex geometry."""
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

    # Apex-based classification:
    # 3PT: apex far from basket (>22ft), high arc
    # 2PT: apex close to basket, lower arc
    # FT: apex == anchor (vertical shot), near FT line

    anchor_ft = basket_dist_ft

    if apex_ft is not None:
        # Classify by apex distance (the true launch point)
        if apex_ft >= 20 and anchor_ft > 12:
            stype = '3PT'
        elif 10 <= apex_ft < 20 and (track[-1][0] - track[0][0]) < 25:
            stype = 'FT'
        else:
            stype = '2PT'
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
        'anchor_ft': round(anchor_ft, 1) if anchor_ft else None,
        'apex_ft': round(apex_ft, 1) if apex_ft else None,
        'track': len(track),
    }


if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    # Load dense track from v16
    with open(f'{OUT}/shot_v16.pkl', 'rb') as f:
        v16 = pickle.load(f)
    dense_x, dense_y = v16['ball_x'], v16['ball_y']

    # Load court data
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    bl_x, bl_y = v8['basket_left']
    br_x, br_y = v8['basket_right']

    # Find candidates (NN near basket)
    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2 + (ry[i]-BLY)**2),
                     np.sqrt((rx[i]-BRX)**2 + (ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(cands):
        # Get scale
        if f < len(bl_x) and not np.isnan(bl_x[f]):
            bsep = np.sqrt((bl_x[f]-br_x[f])**2 + (bl_y[f]-br_y[f])**2)
            scale = bsep / 47.0 if bsep > 200 else None
        else:
            scale = None

        anchor_dist_ft = None
        if scale:
            d_l = np.sqrt((cx - BLX)**2 + (cy - BLY)**2)
            d_r = np.sqrt((cx - BRX)**2 + (cy - BRY)**2)
            anchor_dist_ft = min(d_l, d_r) / scale

        # Find apex in dense track
        apex_f, apex_x, apex_y, apex_dist = find_apex_in_dense_track(
            f, cx, cy, dense_x, dense_y, total, max_lookback=50)

        apex_ft = None
        if scale and not np.isnan(apex_x):
            apex_ft = apex_dist / scale

        # Track from anchor
        track = track_bidir(cap, f, cx, cy, total)

        cls = classify_v31(track, cx, cy, apex_x, apex_y, apex_dist, anchor_dist_ft, scale)
        if cls:
            shots.append(cls)
            log(f"  [{ci+1:2d}] F{f}: {cls['type']} {cls['result']} "
                f"anchor_ft={cls['anchor_ft']} apex_ft={cls['apex_ft']} "
                f"track={cls['track']}f")
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
            f"anchor_ft={s['anchor_ft']} apex_ft={s['apex_ft']}")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v31.csv', index=False)
