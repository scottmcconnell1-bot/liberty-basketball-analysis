#!/usr/bin/env python3
"""
Shot detection v24: Court-space classification with per-frame homography
=========================================================================
Camera pans/zooms, so pixel-space thresholds (130px for 3PT) don't work.
v24 computes homography per-frame from court keypoints, then classifies
shot launch position in real court coordinates (feet from basket).

v23 architecture + court coordinate normalization:
  1. Per-frame court keypoint detection → homography
  2. Transform shot launch position to court space
  3. Classify by court coordinates: 3PT = beyond arc, FT = FT line region
"""
import os, sys, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
FWD_WIN, BWD_WIN = 20, 15
MIN_PTS, MAX_JUMP = 10, 80
MAKE_R = 55

# Standard NCAA half-court dimensions (feet from left basket origin)
# Court: 50ft wide x 47ft long (half)
# Basket at (0, 25) [center of width]
# Left baseline: x=0, Right baseline: x=47
# FT line: x=19, 3PT line (NCAA): x=22 from basket = 22ft from our origin = 22
# Wait, if left basket is at x=0 (our court origin), then:
# FT line = 15ft from backboard (NCAA: 19ft from baseline, but basket is 4ft from baseline → 15ft from basket)
# Actually NCAA FT line is 15ft from backboard = 19ft from baseline, basket at 4ft from baseline
# So FT line = 15ft from basket

# For simplicity, use distances from nearest basket in court feet:
# 3PT line is ~22ft from basket (NCAA: 22ft 1.75in from center of basket)
# FT line is ~15ft from basket (15ft from backboard)

COURT_3PT_DISTANCE = 22.0  # feet from basket to 3PT line
COURT_FT_DISTANCE = 15.0  # feet from basket to FT line


def log(msg):
    print(msg, flush=True)


def compute_homography(kp_frame):
    """Compute homography from court keypoints to real court coordinates.

    Uses the known keypoint layout:
    - 4 left-basket-area keypoints → left side of court
    - 4 right-basket-area keypoints → right side of court
    - remaining keypoints → court features

    Maps pixel coords to court coords (feet from left basket).
    """
    if kp_frame is None:
        return None

    # Get valid keypoints
    valid = []
    for i in range(18):
        if i < len(kp_frame) and not np.isnan(kp_frame[i, 0]):
            valid.append(i)

    if len(valid) < 4:
        return None

    # Sort by x-coordinate to identify left/right areas
    kp_sorted = sorted([(i, kp_frame[i, 0], kp_frame[i, 1]) for i in valid], key=lambda x: x[1])
    left_ids = set(k[0] for k in kp_sorted[:4])
    right_ids = set(k[0] for k in kp_sorted[-4:])

    # Build point correspondences
    # Left basket pixel (mean of left 4 keypoints) → court (0, 25)
    # Right basket pixel (mean of right 4 keypoints) → court (47, 25)
    # Need to identify other landmarks from the 10 mid keypoints

    # Compute basket pixel positions
    left_pts = kp_frame[list(left_ids)]
    right_pts = kp_frame[list(right_ids)]

    basket_l_px = (np.mean(left_pts[:, 0]), np.mean(left_pts[:, 1]))
    basket_r_px = (np.mean(right_pts[:, 0]), np.mean(right_pts[:, 1]))

    # Compute center of court from remaining keypoints
    mid_ids = [i for i in valid if i not in left_ids and i not in right_ids]
    if mid_ids:
        mid_pts = kp_frame[mid_ids]
        center_px = (np.mean(mid_pts[:, 0]), np.mean(mid_pts[:, 1]))
    else:
        center_px = ((basket_l_px[0] + basket_r_px[0]) / 2, (basket_l_px[1] + basket_r_px[1]) / 2)

    # Build correspondences:
    # Left basket  → (0, 25)   [our origin, center of court width]
    # Right basket → (47, 25)  [47ft from left basket, center width]
    # Center       → (23.5, 25) [midpoint]
    # Need 4+ points for homography

    src_pts = np.array([basket_l_px, basket_r_px, center_px], dtype=np.float32)
    dst_pts = np.array([[0, 25], [47, 25], [23.5, 25]], dtype=np.float32)

    # With only 3 points, we can't compute full homography
    # Need at least 4. Let me use additional heuristics:
    # If y range of mid keypoints is small, they're on the far FT line
    # If y range is large, they span midcourt

    # Add 4th/5th points based on geometry:
    # The basket-to-basket direction gives us the court length axis
    # The perpendicular direction gives us the court width

    # Court width direction (perpendicular to basket-basket line)
    dx = basket_r_px[0] - basket_l_px[0]
    dy = basket_r_px[1] - basket_l_px[1]
    length = np.sqrt(dx**2 + dy**2)
    if length > 0:
        nx, ny = -dy / length, dx / length  # perpendicular unit vector

        # Left side of court at basket level → (0, 0) and (0, 50)
        side_l_px = (basket_l_px[0] + nx * 50, basket_l_px[1] + ny * 50)
        side_r_px = (basket_l_px[0] - nx * 50, basket_l_px[1] - ny * 50)

        src_pts = np.array([basket_l_px, basket_r_px, side_l_px, side_r_px], dtype=np.float32)
        dst_pts = np.array([[0, 25], [47, 25], [0, 0], [0, 50]], dtype=np.float32)

        try:
            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            return M
        except Exception:
            return None

    return None


def pixel_to_court(x, y, M):
    """Transform pixel coordinates to court coordinates using homography."""
    if M is None:
        return None, None
    pts = np.array([[[x, y]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pts, M)
    return float(transformed[0, 0, 0]), float(transformed[0, 0, 1])


def nn_nearest_to(f, rx, ry, total):
    best_d, best_x, best_y = 9999, None, None
    for df in range(0, 21):
        for s in [0, 1, -1]:
            fi = f + s * df
            if 0 <= fi < total and not np.isnan(rx[fi]):
                d = min(np.sqrt((rx[fi] - BLX) ** 2 + (ry[fi] - BLY) ** 2),
                        np.sqrt((rx[fi] - BRX) ** 2 + (ry[fi] - BRY) ** 2))
                if d < best_d:
                    best_d, best_x, best_y = d, rx[fi], ry[fi]
    return best_x, best_y, best_d


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
    roi = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    circularity = 0
    area = 0
    if contours:
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        perimeter = cv2.arcLength(c, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
    return {'hist': hist, 'area': area, 'circularity': circularity, 'patch': patch}


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
    area_ratio = patch.size / (template['patch'].size + 1e-8) if template['patch'].size > 0 else 1
    return corr > 0.5 and 0.3 < area_ratio < 3.0


def track_bidir(cap, fnum, cx, cy, total, img0=None):
    if img0 is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
        ret, img0 = cap.read()
        if not ret:
            return []
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
    if not check_color(hsv0, cx, cy):
        return []

    template = extract_template(gray0, cx, cy, radius=8)

    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []
    for f in range(fnum - 1, max(fnum - BWD_WIN, 0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                jx, jy = abs(nx - float(pt[0, 0, 0])), abs(ny - float(pt[0, 0, 1]))
                if jx < MAX_JUMP and jy < MAX_JUMP:
                    backward.append((f, nx, ny))
                    pt = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
        gray_prev = gf

    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    forward = []
    for f in range(fnum + 1, min(fnum + FWD_WIN, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                jx, jy = abs(nx - float(pt[0, 0, 0])), abs(ny - float(pt[0, 0, 1]))
                if jx < MAX_JUMP and jy < MAX_JUMP:
                    forward.append((f, nx, ny))
                    pt = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
        gray_prev = gf

    return backward[::-1] + [(fnum, float(cx), float(cy))] + forward


def classify(track, anchor_x, anchor_y, basket_dist_feet=None):
    if len(track) < MIN_PTS:
        return None

    fs = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if np.max(jumps) > MAX_JUMP:
        return None

    dists = np.minimum(np.sqrt((xs - BLX)**2 + (ys - BLY)**2),
                       np.sqrt((xs - BRX)**2 + (ys - BRY)**2))
    min_idx = int(np.argmin(dists))
    min_dist = float(dists[min_idx])
    best_f = int(fs[min_idx])

    total_travel = np.sqrt((xs[-1] - xs[0])**2 + (ys[-1] - ys[0])**2)
    if total_travel < 30:
        return None

    if min_dist > 180:
        return None

    # Classify using COURT COORDINATES if available, else fallback to pixel distance
    if basket_dist_feet is not None and not np.isnan(basket_dist_feet):
        # Classify by court distance from basket
        if basket_dist_feet >= COURT_3PT_DISTANCE - 2:  # within 2ft of arc
            stype = '3PT'
        elif basket_dist_feet >= COURT_FT_DISTANCE - 3 and basket_dist_feet < COURT_FT_DISTANCE + 3:
            stype = 'FT'
        elif basket_dist_feet < COURT_3PT_DISTANCE - 2:
            stype = '2PT'
        else:
            stype = '2PT'  # between FT and 3PT arc
    else:
        # Fallback to pixel distance
        anchor_d = min(np.sqrt((anchor_x - BLX)**2 + (anchor_y - BLY)**2),
                       np.sqrt((anchor_x - BRX)**2 + (anchor_y - BRY)**2))
        if anchor_d >= 130:
            stype = '3PT'
        else:
            stype = '2PT'

    smooth = np.mean(jumps)
    is_make = (min_dist < MAKE_R) or (min_dist < MAKE_R + 15 and len(track) > 14 and smooth < 30)
    result = 'MAKE' if is_make else 'MISS'

    return {'frame': best_f, 'type': stype, 'result': result,
            'closest': round(min_dist, 1), 'track': len(track),
            'smooth': round(smooth, 1), 'basket_dist_feet': basket_dist_feet}


if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    # Load court homographies (precomputed per-frame from v8 kp_arr)
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    kp_all = v8['kp_arr']  # (2701, 18, 2)

    # Precompute homographies for key frames
    log("Precomputing court homographies...")
    homographies = {}  # frame_idx -> homography matrix
    homography_distances = {}  # frame_idx -> distance from ball to basket in feet

    for f in range(0, total, 10):  # every 10 frames
        kp_frame = kp_all[f] if f < len(kp_all) else None
        M = compute_homography(kp_frame)
        if M is not None:
            homographies[f] = M

    log(f"Computed {len(homographies)} homographies")

    # For each shot candidate, find nearest homography frame
    def get_homography_for_frame(f):
        # Find nearest precomputed homography
        best_f = None
        best_dist = 999
        for hf in homographies:
            d = abs(hf - f)
            if d < best_dist:
                best_dist = d
                best_f = hf
        if best_f is not None and best_dist <= 10:
            return homographies[best_f]
        return None

    def get_basket_dist_feet(x, y, f):
        M = get_homography_for_frame(f)
        if M is None:
            return None
        cx, cy = pixel_to_court(x, y, M)
        if cx is None:
            return None
        # Distance from nearest basket in court feet
        d_left = np.sqrt((cx - 0)**2 + (cy - 25)**2)
        d_right = np.sqrt((cx - 47)**2 + (cy - 25)**2)
        return min(d_left, d_right)

    # Find candidates
    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i] - BLX)**2 + (ry[i] - BLY)**2),
                     np.sqrt((rx[i] - BRX)**2 + (ry[i] - BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(cands):
        track = track_bidir(cap, f, cx, cy, total)
        basket_dist = get_basket_dist_feet(cx, cy, f)
        cls = classify(track, cx, cy, basket_dist)
        if cls:
            shots.append(cls)
            log(f"  [{ci + 1}] F{f}: {cls['type']} {cls['result']} "
                f"closest={cls['closest']:.0f}px track={cls['track']}f "
                f"basket_dist={cls['basket_dist_feet']:.1f}ft" if cls['basket_dist_feet'] else "")
        else:
            log(f"  [{ci + 1}] F{f}: REJECTED ({len(track)}f)")
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

    log(f"\n{'=' * 60}")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result'] == 'MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result'] == 'MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result'] == 'MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        feet = f" dist={s['basket_dist_feet']:.1f}ft" if s['basket_dist_feet'] else ""
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} closest={s['closest']:.0f}px{feet}")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v24.csv', index=False)
