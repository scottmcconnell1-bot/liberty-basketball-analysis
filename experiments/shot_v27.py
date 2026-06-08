#!/usr/bin/env python3
"""
Shot detection v27: Court-scale classification using semantic keypoints
=======================================================================
Semantic keypoint mapping (verified from spatial analysis across frames):

  KP15 (612,219) — paired with KP14 → Top of 3PT arc (far from baskets)
  KP14 (604,229) — paired with KP15 → Same landmark as KP15
  KP13 (611,307) — right side → Right lane elbow
  KP16 (582,331) — center → FT line center / top of key
  KP12 (270,427) — left side → Left lane elbow
  KP17 (583,460) — center → Left FT corner / top of key

Strategy:
  - Use KP12 (left) and KP13 (right) as "elbow" markers near each basket
  - Use KP16 (center-top-of-key) and KP17 (center-bottom) for FT line scale
  - Use KP15 (far top) for 3PT arc reference
  - Estimate px/ft scale per frame from keypoint distances
  - Convert shot anchor distance to feet for classification
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


# ---- Semantic Keypoint Definitions ----
# Court landmarks in real-world coordinates (feet from left baseline)
# Half-court: 47ft long x 50ft wide
# Left basket at (4, 25), Right basket at (43, 25)
# FT line at x=19 (left) and x=28 (right)
# 3PT line at ~22ft from basket

# Key semantic keypoints and their typical court positions:
SEMANTIC_KPS = {
    # Left side (near left basket)
    12: {'court': (19, 8), 'desc': 'left_elbow'},      # Left lane edge/elbow
    17: {'court': (15, 17), 'desc': 'left_ft_corner'},  # Left FT lane corner
    # Center
    16: {'court': (19, 25), 'desc': 'ft_line_center'}, # FT line center
    # Right side (near right basket)
    13: {'court': (28, 42), 'desc': 'right_elbow'},     # Right lane edge/elbow
    # Far (3PT arc area)
    15: {'court': (44, 25), 'desc': 'three_pt_arc'},    # 3PT arc center (far end)
    14: {'court': (40, 35), 'desc': 'three_pt_right'},   # 3PT arc right
}


# ---- Tracking (same as v23/v26) ----

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


# ---- Court-space helpers ----

# NCAA half-court (feet from left baseline origin)
COURT_47 = 47.0   # half court length
COURT_W = 50.0    # court width
FT_X_LEFT = 19.0  # FT line x (from left baseline)
FT_X_RIGHT = 28.0 # FT line x from left baseline (= 47-19)
BASKET_LEFT = (4.0, 25.0)
BASKET_RIGHT = (43.0, 25.0)
THREE_PT_FT = 22.0  # 3PT line from basket


def get_scale_from_kps(kp_frame):
    """Get pixels-per-foot scale from semantic keypoints.

    Uses known court distances between landmarks to compute scale.
    Returns (scale_ft_per_px, confidence).
    """
    if kp_frame is None:
        return None, 0

    # Get reliable keypoints (12-17)
    reliable = {}
    for i in range(12, 18):
        if not (np.isnan(kp_frame[i, 0]) or np.isnan(kp_frame[i, 1])):
            reliable[i] = kp_frame[i].copy()

    if len(reliable) < 3:
        return None, 0

    # Use known distances between landmarks to estimate scale:
    # KP16 (ft_line_center) to KP12 (left_elbow): ~17ft (diagonal across key)
    # KP16 to KP17 (left_ft_corner): ~8ft
    # KP15 (3pt_arc) to KP16: ~25ft (3PT to FT line)
    scales = []

    # KP16 to KP17: should be ~8ft (half the key width)
    if 16 in reliable and 17 in reliable:
        d = np.sqrt((reliable[16][0] - reliable[17][0]) ** 2 +
                    (reliable[16][1] - reliable[17][1]) ** 2)
        if d > 10:
            scales.append(8.0 / d)

    # KP16 to KP12: should be ~17ft (FT line center to left elbow)
    if 16 in reliable and 12 in reliable:
        d = np.sqrt((reliable[16][0] - reliable[12][0]) ** 2 +
                    (reliable[16][1] - reliable[12][1]) ** 2)
        if d > 10:
            scales.append(17.0 / d)

    # KP15 (3PT) to KP16 (FT): should be ~25ft (3PT line to FT line: 22+19=41ft... no)
    # Actually KP15 is at 3PT arc center, KP16 is at FT line center
    # Distance should be ~25ft (44-19=25)
    if 15 in reliable and 16 in reliable:
        d = np.sqrt((reliable[15][0] - reliable[16][0]) ** 2 +
                    (reliable[15][1] - reliable[16][1]) ** 2)
        if d > 10:
            scales.append(25.0 / d)

    # KP13 (right_elbow) to KP16 (ft_line_center): ~sqrt((28-19)^2 + (42-25)^2) ≈ 20ft
    if 13 in reliable and 16 in reliable:
        d = np.sqrt((reliable[13][0] - reliable[16][0]) ** 2 +
                    (reliable[13][1] - reliable[16][1]) ** 2)
        if d > 10:
            scales.append(20.0 / d)

    if scales:
        # Use median for robustness
        scale = float(np.median(scales))
        # Sanity check: scale should be 5-30 px/ft
        if 3.0 < scale < 50.0:
            return scale, len(scales)

    return None, 0


def classify_with_scale(track, anchor_x, anchor_y, kp_frame):
    """Classify shot using court-scale distance."""
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

    # Closest approach
    dists_l = np.sqrt((xs - BLX) ** 2 + (ys - BLY) ** 2)
    dists_r = np.sqrt((xs - BRX) ** 2 + (ys - BRY) ** 2)
    dists_px = np.minimum(dists_l, dists_r)
    min_dist_px = float(np.min(dists_px))
    best_idx = int(np.argmin(dists_px))

    if min_dist_px > 180:
        return None

    # Nearest basket
    d_l = np.sqrt((anchor_x - BLX) ** 2 + (anchor_y - BLY) ** 2)
    d_r = np.sqrt((anchor_x - BRX) ** 2 + (anchor_y - BRY) ** 2)

    # Get court scale
    scale, n_scale = get_scale_from_kps(kp_frame)

    if scale is not None and n_scale >= 2:
        # Use court-scale classification
        anchor_dist_ft = min(d_l, d_r) * scale

        if anchor_dist_ft >= THREE_PT_FT - 2:
            stype = '3PT'
        elif 12 <= anchor_dist_ft <= THREE_PT_FT - 2:
            # Between FT and 3PT — use track properties
            if len(track) < 18 and total_travel < 100:
                stype = 'FT'
            else:
                stype = '2PT'
        else:
            stype = '2PT'
    else:
        # Fallback: calibrated pixel thresholds (less reliable)
        anchor_px = min(d_l, d_r)
        if anchor_px >= 150:
            stype = '3PT'
        elif anchor_px < 60:
            stype = '2PT'
        else:
            stype = '2PT'

    # Make/miss
    smooth = float(np.mean(jumps)) if len(jumps) > 0 else 0
    is_make = (min_dist_px < MAKE_R) or (min_dist_px < MAKE_R + 15 and len(track) > 14 and smooth < 30)
    result = 'MAKE' if is_make else 'MISS'

    anchor_dist_ft = min(d_l, d_r) * scale if scale else None

    return {
        'frame': int(fs[best_idx]),
        'type': stype,
        'result': result,
        'closest_px': round(min_dist_px, 1),
        'anchor_dist_px': round(min(d_l, d_r), 1),
        'anchor_dist_ft': round(anchor_dist_ft, 1) if anchor_dist_ft else None,
        'scale': round(scale, 2) if scale else None,
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

    for ci, (f, cx, cy) in enumerate(cands):
        kp_frame = kp_all[f] if f < kp_all.shape[0] else None
        track = track_bidir(cap, f, cx, cy, total)
        cls = classify_with_scale(track, cx, cy, kp_frame)
        if cls:
            shots.append(cls)
            extra = f"scale={cls['scale']} ft/px anchor_ft={cls['anchor_dist_ft']}" if cls['scale'] else "NO_SCALE"
            log(f"  [{ci+1:2d}] F{f}: {cls['type']} {cls['result']} "
                f"anchor_px={cls['anchor_dist_px']:.0f} closest={cls['closest_px']:.0f} "
                f"track={cls['track']}f {extra}")
        else:
            log(f"  [{ci+1:2d}] F{f}: REJECTED ({len(track)}f)")
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
        extra = f"anchor_ft={s['anchor_dist_ft']:.1f}" if s['anchor_dist_ft'] else ""
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"anchor_px={s['anchor_dist_px']:.0f} closest={s['closest_px']:.0f} {extra}")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track'],
            'anchor_dist_ft': s.get('anchor_dist_ft'),
            'scale': s.get('scale')} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v27.csv', index=False)
