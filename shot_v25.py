#!/usr/bin/env python3
"""
Shot detection v25: Court-space classification with smoothed per-frame homography
=================================================================================
v23 had better tracking (appearance lock) but regressed on classification.
v24 was the first homography attempt but had bugs.

v25 combines:
  - v23's appearance-locked bidirectional OF tracking
  - Per-frame homography from court keypoints (using v8 cached keypoints)
  - Smoothed homography interpolation for missing frames
  - Court-space classification (3PT / 2PT / FT) using real geometry
  - FT-specific detection via NN detection pattern at FT line
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

# NCAA court dimensions (feet)
COURT_WIDTH = 50.0
COURT_HALF_LENGTH = 47.0
BASKET_DIST_BASELINE = 4.0
FT_DIST_FROM_BASELINE = 19.0
FT_DIST_FROM_BASKET = FT_DIST_FROM_BASELINE - BASKET_DIST_BASELINE  # 15ft
THREE_PT_DIST = 22.0

# Derived
LEFT_BASKET_COURT = np.array([BASKET_DIST_BASELINE, COURT_WIDTH / 2])   # (4, 25)
RIGHT_BASKET_COURT = np.array([COURT_HALF_LENGTH - BASKET_DIST_BASELINE, COURT_WIDTH / 2])  # (43, 25)
FT_LINE_COURT_X_LEFT = FT_DIST_FROM_BASELINE   # 19ft from left baseline
FT_LINE_COURT_X_RIGHT = COURT_HALF_LENGTH - FT_DIST_FROM_BASELINE  # 28ft from left baseline

# Court landmarks for homography destination (feet from left baseline origin)
COURT_LANDMARKS_DST = np.array([
    [BASKET_DIST_BASELINE, COURT_WIDTH / 2],                     # 0: Left basket
    [COURT_HALF_LENGTH - BASKET_DIST_BASELINE, COURT_WIDTH / 2], # 1: Right basket
    [FT_DIST_FROM_BASELINE, 0],                                   # 2: FT line left
    [FT_DIST_FROM_BASELINE, COURT_WIDTH],                         # 3: FT line right
    [0, 0],                                                       # 4: BL corner
    [0, COURT_WIDTH],                                             # 5: BR corner
], dtype=np.float32)


def log(msg):
    print(msg, flush=True)


# ================================================================
# Court Homography
# ================================================================

def compute_homography_robust(kp_frame):
    """Compute per-frame homography using RANSAC from 18 court keypoints.

    Strategy: sort keypoints by x, take leftmost 4 and rightmost 4 as
    reliable anchors (basket + baseline areas). Map to known court positions.
    """
    if kp_frame is None or len(kp_frame) < 18:
        return None, 0

    valid_pts = []
    for i in range(18):
        x, y = kp_frame[i]
        if not (np.isnan(x) or np.isnan(y)):
            valid_pts.append((i, float(x), float(y)))

    if len(valid_pts) < 6:
        return None, 0

    # Sort by x-coordinate
    valid_pts.sort(key=lambda t: t[1])

    n = len(valid_pts)
    k = min(4, n // 3)  # take k from each side

    left_kps = valid_pts[:k]
    right_kps = valid_pts[-k:]

    # Build pixel source points
    pixel_src = np.array([(x, y) for _, x, y in left_kps] +
                         [(x, y) for _, x, y in right_kps], dtype=np.float32)

    # Map to court destinations:
    # Left kps → [basket, FT-line-left, FT-line-right, baseline-center]
    # Right kps → [basket, FT-line-right, FT-line-left, baseline-center]
    left_dst = np.array([
        [BASKET_DIST_BASELINE, COURT_WIDTH / 2],
        [FT_DIST_FROM_BASELINE, 0],
        [FT_DIST_FROM_BASELINE, COURT_WIDTH],
        [0, COURT_WIDTH / 2],
    ][:k], dtype=np.float32)

    right_dst = np.array([
        [COURT_HALF_LENGTH - BASKET_DIST_BASELINE, COURT_WIDTH / 2],
        [COURT_HALF_LENGTH - FT_DIST_FROM_BASELINE, COURT_WIDTH],
        [COURT_HALF_LENGTH - FT_DIST_FROM_BASELINE, 0],
        [COURT_HALF_LENGTH, COURT_WIDTH / 2],
    ][:k], dtype=np.float32)

    court_dst = np.vstack([left_dst, right_dst])

    if len(pixel_src) < 4:
        return None, 0

    try:
        M, mask = cv2.findHomography(pixel_src, court_dst, cv2.RANSAC, 10.0)
        inliers = int(np.sum(mask)) if mask is not None else 0
        return M, inliers
    except Exception:
        return None, 0


def smooth_homographies(raw_dict, total_frames):
    """Interpolate homographies for frames without reliable detection."""
    valid = sorted(raw_dict.keys())
    if not valid:
        return {}

    result = {}
    for f in range(total_frames):
        # Find bracketing frames
        before = None
        after = None
        for vf in valid:
            if vf <= f:
                before = vf
            if vf >= f and after is None:
                after = vf
                break

        if before is not None and after is not None and before != after:
            alpha = (f - before) / (after - before)
            result[f] = raw_dict[before] * (1 - alpha) + raw_dict[after] * alpha
        elif before is not None:
            result[f] = raw_dict[before]
        elif after is not None:
            result[f] = raw_dict[after]

    return result


def pixel_to_court(x, y, M):
    """Transform pixel (x,y) to court coordinates (feet)."""
    if M is None:
        return None, None
    try:
        pts = np.array([[[float(x), float(y)]]], dtype=np.float32)
        t = cv2.perspectiveTransform(pts, M)
        return float(t[0, 0, 0]), float(t[0, 0, 1])
    except Exception:
        return None, None


# ================================================================
# Appearance-locked tracking
# ================================================================

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


# ================================================================
# Court-space shot classification
# ================================================================

def classify_court_space(track, anchor_x, anchor_y, M):
    """Classify shot using court coordinates from homography."""
    if len(track) < MIN_PTS:
        return None

    fs = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    jumps = np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2)
    if len(jumps) > 0 and np.max(jumps) > MAX_JUMP:
        return None

    total_travel = np.sqrt((xs[-1] - xs[0]) ** 2 + (ys[-1] - ys[0]) ** 2)
    if len(track) >= 3 and total_travel < 30:
        return None

    # Transform anchor to court coords
    acx, acy = pixel_to_court(anchor_x, anchor_y, M)
    if acx is None:
        return None

    # Distance from nearest basket in court feet
    d_left = np.sqrt((acx - LEFT_BASKET_COURT[0]) ** 2 + (acy - LEFT_BASKET_COURT[1]) ** 2)
    d_right = np.sqrt((acx - RIGHT_BASKET_COURT[0]) ** 2 + (acy - RIGHT_BASKET_COURT[1]) ** 2)
    basket_dist = float(min(d_left, d_right))

    # Classify by court geometry
    if basket_dist >= THREE_PT_DIST - 2:
        stype = '3PT'
    elif FT_DIST_FROM_BASKET - 3 <= basket_dist <= FT_DIST_FROM_BASKET + 6:
        # Check if near FT line x-position (±3ft)
        near_left_ft = abs(acx - FT_LINE_COURT_X_LEFT) < 4
        near_right_ft = abs(acx - FT_LINE_COURT_X_RIGHT) < 4
        if near_left_ft or near_right_ft:
            stype = 'FT'
        else:
            stype = '2PT'
    else:
        stype = '2PT'

    # Closest approach (pixel space for make/miss)
    dists_px = np.minimum(np.sqrt((xs - BLX) ** 2 + (ys - BLY) ** 2),
                          np.sqrt((xs - BRX) ** 2 + (ys - BRY) ** 2))
    min_dist_px = float(np.min(dists_px))
    best_idx = int(np.argmin(dists_px))

    if min_dist_px > 180:
        return None

    smooth = float(np.mean(jumps)) if len(jumps) > 0 else 0
    is_make = (min_dist_px < MAKE_R) or (min_dist_px < MAKE_R + 15 and len(track) > 14 and smooth < 30)
    result = 'MAKE' if is_make else 'MISS'

    return {
        'frame': int(fs[best_idx]),
        'type': stype,
        'result': result,
        'closest_px': round(min_dist_px, 1),
        'basket_dist_ft': round(basket_dist, 1),
        'court_x': round(acx, 1),
        'court_y': round(acy, 1),
        'track': len(track),
        'smooth': round(smooth, 1),
    }


# ================================================================
# FT-specific detection
# ================================================================

def detect_ft_candidates(rx, ry, total):
    """Detect potential free throw events using NN detection pattern.

    FT signature in overhead footage:
    - Ball detected near FT line (x=19 or x=28 in court coords)
    - Short trajectory toward basket
    - Detected for only a few frames (isolated from play)

    Since NN rarely fires at FT line, we look for detections that ARE near
    FT line positions and check if they fit FT geometry.
    """
    ft_shots = []

    # Use court homographies to transform all NN detections
    # Check which ones are near FT line
    for i in range(total):
        if np.isnan(rx[i]):
            continue
        d_left = np.sqrt((rx[i] - BLX) ** 2 + (ry[i] - BLY) ** 2)
        d_right = np.sqrt((rx[i] - BRX) ** 2 + (ry[i] - BRY) ** 2)
        # FT line is roughly at these pixel positions (from v8 analysis):
        # Left FT: around (580, 350-410) — mid court area
        # Right FT: around (620, 350-410)
        # These overlap with regular play, so FT detection needs homography

    return ft_shots


# ================================================================
# MAIN
# ================================================================

if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    # ---- Precompute court homographies from v8 keypoints ----
    log("Precomputing court homographies from v8 keypoints...")
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    kp_all = v8['kp_arr']  # (2701, 18, 2)

    raw_h = {}
    for f_idx in range(0, min(total, kp_all.shape[0])):
        M, inliers = compute_homography_robust(kp_all[f_idx])
        if M is not None and inliers >= 4:
            raw_h[f_idx] = M

    log(f"Raw homographies: {len(raw_h)} / {total} frames ({100 * len(raw_h) / total:.0f}%)")
    homographies = smooth_homographies(raw_h, total)
    log(f"Smoothed homographies: {len(homographies)} / {total} frames")

    # ---- Find candidates ----
    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i] - BLX) ** 2 + (ry[i] - BLY) ** 2),
                     np.sqrt((rx[i] - BRX) ** 2 + (ry[i] - BRY) ** 2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f_idx, cx, cy) in enumerate(cands):
        M = homographies.get(f_idx)
        if M is None:
            for delta in range(1, 20):
                M = homographies.get(f_idx - delta) or homographies.get(f_idx + delta)
                if M is not None:
                    break

        track = track_bidir(cap, f_idx, cx, cy, total)
        try:
            cls = classify_court_space(track, cx, cy, M) if M is not None else None
        except Exception:
            cls = None
        if cls:
            shots.append(cls)
            log(f"  [{ci + 1}] F{f_idx}: {cls['type']} {cls['result']} "
                f"basket={cls['basket_dist_ft']:5.1f}ft court=({cls['court_x']:5.1f},{cls['court_y']:5.1f}) "
                f"closest={cls['closest_px']:.0f}px track={cls['track']}f")
        else:
            reason = "NO_H" if not M else f"REJ ({len(track)}f)"
            log(f"  [{ci + 1}] F{f_idx}: {reason}")
    cap.release()

    # ---- Dedup ----
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

    # ---- Summary ----
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
            f"basket={s['basket_dist_ft']:5.1f}ft court=({s['court_x']:5.1f},{s['court_y']:5.1f})")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track'],
            'basket_dist_ft': s['basket_dist_ft'],
            'court_x': s['court_x'], 'court_y': s['court_y']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v25.csv', index=False)
