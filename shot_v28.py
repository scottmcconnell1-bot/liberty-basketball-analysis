#!/usr/bin/env python3
"""
Shot detection v28: Per-frame court-scale classification
=========================================================
Uses basket-to-basket distance from v8 keypoints to compute px/ft scale
per frame. Then classifies shots using real court geometry:

  FT:  anchor 220-290px from basket (≈15ft at typical scale)
  3PT: anchor >330px from basket (≈22ft at typical scale)
  2PT: everything else approaching basket

Scale varies 14.7-18.9 px/ft (camera zooms), so we compute it per-frame.
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

# Court distances in feet
FT_DIST = 15.0    # FT line from basket
THREE_PT_DIST = 22.0  # 3PT line from basket
HALF_COURT = 47.0  # basket to basket


def log(msg):
    print(msg, flush=True)


# ---- Tracking (v23/v26/v27) ----

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


# ---- Court-scale classification ----

def get_scale_for_frame(f, bl_x, bl_y, br_x, br_y):
    """Get px/ft scale from basket-to-basket distance at frame f."""
    if f >= len(bl_x) or np.isnan(bl_x[f]) or np.isnan(br_x[f]):
        return None
    d = np.sqrt((bl_x[f] - br_x[f])**2 + (bl_y[f] - br_y[f])**2)
    if d < 200:
        return None
    return d / HALF_COURT  # px/ft


def get_scale_near_frame(f, bl_x, bl_y, br_x, br_y, search=30):
    """Get scale from nearest valid frame within search radius."""
    s = get_scale_for_frame(f, bl_x, bl_y, br_x, br_y)
    if s is not None:
        return s
    for delta in range(1, search):
        s = get_scale_for_frame(f - delta, bl_x, bl_y, br_x, br_y)
        if s is not None:
            return s
        s = get_scale_for_frame(f + delta, bl_x, bl_y, br_x, br_y)
        if s is not None:
            return s
    return None


def classify_v28(track, anchor_x, anchor_y, scale):
    """Classify shot using per-frame court scale."""
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

    # Nearest basket
    d_l = np.sqrt((anchor_x - BLX)**2 + (anchor_y - BLY)**2)
    d_r = np.sqrt((anchor_x - BRX)**2 + (anchor_y - BRY)**2)
    anchor_px = min(d_l, d_r)

    # Closest approach
    dists_l = np.sqrt((xs - BLX)**2 + (ys - BLY)**2)
    dists_r = np.sqrt((xs - BRX)**2 + (ys - BRY)**2)
    dists_px = np.minimum(dists_l, dists_r)
    min_dist_px = float(np.min(dists_px))
    best_idx = int(np.argmin(dists_px))

    if min_dist_px > 180:
        return None

    # Convert to feet using per-frame scale
    if scale is not None:
        anchor_ft = anchor_px * scale  # BUG: scale is px/ft, should divide
        # Actually: anchor_ft = anchor_px / scale
        anchor_ft = anchor_px / scale
    else:
        anchor_ft = None

    # Classify
    if anchor_ft is not None:
        if anchor_ft >= THREE_PT_DIST - 2:
            stype = '3PT'
        elif FT_DIST - 3 <= anchor_ft <= FT_DIST + 6:
            stype = 'FT'
        else:
            stype = '2PT'
    else:
        # Fallback
        if anchor_px >= 350:
            stype = '3PT'
        elif anchor_px >= 220:
            stype = 'FT'
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
        'anchor_ft': round(anchor_ft, 1) if anchor_ft is not None else None,
        'scale': round(scale, 1) if scale else None,
        'track': len(track),
    }


# ---- Main ----

if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    # Load basket positions for scale
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    bl_x, bl_y = v8['basket_left']
    br_x, br_y = v8['basket_right']

    # Find candidates
    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2 + (ry[i]-BLY)**2),
                     np.sqrt((rx[i]-BRX)**2 + (ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(cands):
        scale = get_scale_near_frame(f, bl_x, bl_y, br_x, br_y)
        track = track_bidir(cap, f, cx, cy, total)
        cls = classify_v28(track, cx, cy, scale)
        if cls:
            shots.append(cls)
            extra = f"anchor_ft={cls['anchor_ft']:.1f}ft scale={cls['scale']:.1f}px/ft" if cls['scale'] else "NO_SCALE"
            log(f"  [{ci+1:2d}] F{f}: {cls['type']} {cls['result']} "
                f"anchor_px={cls['anchor_px']:.0f} closest={cls['closest_px']:.0f} "
                f"track={cls['track']}f {extra}")
        else:
            log(f"  [{ci+1:2d}] F{f}: REJECTED ({len(track)}f)")
    cap.release()

    # Dedup: remove F237 (close to F236) — check tracks
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

    # Summary
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
        extra = f"anchor_ft={s['anchor_ft']:.1f}" if s['anchor_ft'] else ""
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} anchor_px={s['anchor_px']:.0f} {extra}")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track'],
            'anchor_ft': s.get('anchor_ft'), 'scale': s.get('scale')} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v28.csv', index=False)
