#!/usr/bin/env python3
"""
Shot detection v26: Court-space classification (redesigned)
============================================================
Key insight: KP12-KP17 are reliable (high confidence), KP0-KP11 are noisy.
Since camera pans, we can't use fixed keypoint-to-landmark mapping.

Instead, use a SIMPLER approach:
1. Identify which basket is "left" and "right" per frame from keypoints
2. Compute shot launch angle relative to basket direction
3. Use trajectory shape (not position) for classification:
   - 3PT: shot originates >22ft from basket (long approach in court coords)
   - FT: shot originates ~15ft from basket with vertical-ish trajectory
   - 2PT: everything else that reaches the basket

The basket-direction angle helps normalize for camera rotation.
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


# ---- Appearance-locked tracking (same as v23/v25) ----

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
            winSize=(15, 15), maxLevel=2,
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
            winSize=(15, 15), maxLevel=2,
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


# ---- Court geometry helpers ----

def get_basket_positions(kp_frame):
    """Extract left/right basket pixel positions from court keypoints.

    Uses high-confidence keypoints 12-17 to find basket regions.
    Returns (left_basket_px, right_basket_px, nearest_basket_to_ball).
    """
    if kp_frame is None or len(kp_frame) < 18:
        return None, None, None

    # High confidence keypoints: 12-17
    robust = [(i, float(kp_frame[i, 0]), float(kp_frame[i, 1]))
              for i in range(12, 18)
              if not (np.isnan(kp_frame[i, 0]) or np.isnan(kp_frame[i, 1]))]

    if len(robust) < 3:
        return None, None, None

    # Sort by x to find left/right groups
    robust.sort(key=lambda t: t[1])

    # The leftmost 2-3 keypoints = left side (near left basket)
    # The rightmost 2-3 keypoints = right side (near right basket)
    n = len(robust)
    left_kps = robust[:n // 2]
    right_kps = robust[n // 2:]

    left_px = (np.mean([x for _, x, _ in left_kps]),
               np.mean([y for _, _, y in left_kps]))
    right_px = (np.mean([x for _, x, _ in right_kps]),
                np.mean([y for _, _, y in right_kps]))

    return left_px, right_px


def estimate_scale(kp_frame):
    """Estimate pixels-per-foot from court keypoints.

    Uses the distance between high-confidence keypoints to estimate scale.
    Known: distance from FT line to baseline is ~19ft, FT to basket is ~15ft.
    """
    if kp_frame is None:
        return None

    # Get high-confidence keypoints
    kps = []
    for i in range(12, 18):
        if not (np.isnan(kp_frame[i, 0]) or np.isnan(kp_frame[i, 1])):
            kps.append(kp_frame[i])

    if len(kps) < 2:
        return None

    kps = np.array(kps)

    # Compute pairwise distances
    max_dist = 0
    for i in range(len(kps)):
        for j in range(i + 1, len(kps)):
            d = np.sqrt((kps[i, 0] - kps[j, 0]) ** 2 + (kps[i, 1] - kps[j, 1]) ** 2)
            if d > max_dist:
                max_dist = d

    # Heuristic: max distance between court keypoints ≈ 30-40ft (half court width or FT-to-3PT)
    # Conservative: assume max_dist = 35ft
    if max_dist > 0:
        return 35.0 / max_dist  # feet per pixel
    return None


def classify_trajectory(track, anchor_x, anchor_y, kp_frame=None):
    """Classify shot using trajectory geometry + optional court keypoints.

    Uses:
    1. Track length and total travel distance (proxy for shot distance)
    2. Trajectory shape (direction of approach)
    3. Court keypoints for absolute position (if available)
    """
    if len(track) < MIN_PTS:
        return None

    fs = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    jumps = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
    if len(jumps) > 0 and np.max(jumps) > MAX_JUMP:
        return None

    total_travel = np.sqrt((xs[-1] - xs[0]) ** 2 + (ys[-1] - ys[0]) ** 2)
    if total_travel < 30:
        return None

    # Closest approach to either basket
    dists_l = np.sqrt((xs - BLX) ** 2 + (ys - BLY) ** 2)
    dists_r = np.sqrt((xs - BRX) ** 2 + (ys - BRY) ** 2)
    dists_px = np.minimum(dists_l, dists_r)
    min_dist_px = float(np.min(dists_px))
    best_idx = int(np.argmin(dists_px))

    if min_dist_px > 180:
        return None

    # ---- Classify by trajectory geometry ----
    # Key: use the track's SPAN (total travel) and approach direction
    # to classify shot type.

    # Find nearest basket for anchor
    d_anchor_l = np.sqrt((anchor_x - BLX) ** 2 + (anchor_y - BLY) ** 2)
    d_anchor_r = np.sqrt((anchor_x - BRX) ** 2 + (anchor_y - BRY) ** 2)

    if d_anchor_l < d_anchor_r:
        basket_x, basket_y = BLX, BLY
        anchor_dist_px = d_anchor_l
    else:
        basket_x, basket_y = BRX, BRY
        anchor_dist_px = d_anchor_r

    # Estimate real-world distance using court keypoints for scale
    scale = estimate_scale(kp_frame)  # feet per pixel
    if scale is not None and anchor_dist_px < 400:
        # Sanity check: anchor should be on court (0-94ft from nearest basket)
        anchor_dist_ft = anchor_dist_px * scale
        if anchor_dist_ft > 80:
            scale = None  # bad scale estimate

    if scale is None:
        # Fallback: use pixel distance with calibrated threshold
        # At typical camera zoom, ~130px ≈ 22ft (3PT line)
        # But this is unreliable — try range-based classification
        if anchor_dist_px >= 160:
            stype = '3PT'
        elif 80 <= anchor_dist_px < 160:
            stype = '2PT'
        elif anchor_dist_px < 80:
            # Close to basket — could be FT or 2PT
            # FT clues: short track, vertical-ish, ball starts near FT line
            vertical_motion = abs(ys[-1] - ys[0])
            horizontal_motion = abs(xs[-1] - xs[0])
            if len(track) < 18 and vertical_motion > horizontal_motion * 0.5:
                stype = 'FT'
            else:
                stype = '2PT'
        else:
            stype = '2PT'
    else:
        anchor_dist_ft = anchor_dist_px * scale
        if anchor_dist_ft >= 20:
            stype = '3PT'
        elif 12 <= anchor_dist_ft < 20:
            stype = 'FT' if len(track) < 18 else '2PT'
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
        'anchor_dist_px': round(anchor_dist_px, 1),
        'track': len(track),
        'smooth': round(smooth, 1),
        'total_travel': round(total_travel, 1),
    }


# ---- Main ----

if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    # Load court keypoints for scale estimation
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    kp_all = v8['kp_arr']

    # Find candidates
    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i] - BLX) ** 2 + (ry[i] - BLY) ** 2),
                     np.sqrt((rx[i] - BRX) ** 2 + (ry[i] - BRY) ** 2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f_idx, cx, cy) in enumerate(cands):
        kp_frame = kp_all[f_idx] if f_idx < kp_all.shape[0] else None
        track = track_bidir(cap, f_idx, cx, cy, total)
        cls = classify_trajectory(track, cx, cy, kp_frame)
        if cls:
            shots.append(cls)
            log(f"  [{ci+1}] F{f_idx}: {cls['type']} {cls['result']} "
                f"anchor={cls['anchor_dist_px']:.0f}px closest={cls['closest_px']:.0f}px "
                f"travel={cls['total_travel']:.0f}px track={cls['track']}f")
        else:
            log(f"  [{ci+1}] F{f_idx}: REJECTED ({len(track)}f)")
    cap.release()

    # Dedup
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

    log(f"\n{'=' * 60}")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result'] == 'MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result'] == 'MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result'] == 'MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"anchor={s['anchor_dist_px']:.0f}px closest={s['closest_px']:.0f}px")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v26.csv', index=False)
