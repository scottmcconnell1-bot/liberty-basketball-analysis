#!/usr/bin/env python3
"""
Shot detection v34: Local backward emergence → soft zone probabilities
========================================================================
No hard classification yet. For each v23 anchor, backtrack locally
(10-20 frames) with strict appearance lock to estimate:

  - origin_distance_ft: how far back the ball emerged from
  - emergence_angle: direction the ball came from
  - lateral_offset_ft: left/right position relative to basket-attack line
  - corridor_stability: how consistent the backward motion is
  - origin_sector: soft zone (paint/elbow/wing/perimeter/deep/ft)
  - zone_confidence: probability of sector assignment
  - anchor_confidence: how reliable this shot event is

Output is FEATURES, not labels. The next step (v35+) will calibrate
these features against ground truth to learn sector→label mapping.
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
        if not ret: break
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
        if not ret: break
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


def estimate_local_backward_emergence(anchor_f, anchor_x, anchor_y, cap, total, max_back=15):
    """Estimate local backward emergence using template-locked OF.

    Instead of global dense track, we:
    1. Start from the v23 anchor (known ball position)
    2. Backtrack with appearance-locked OF ONLY (no global track)
    3. Collect backward points until appearance lock is lost
    4. Use the last valid backward point as origin estimate

    This is LOCAL and SHORT-HORIZON — immune to global drift.
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, anchor_f)
    ret, img0 = cap.read()
    if not ret:
        return None
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    template = extract_template(gray0, anchor_x, anchor_y, radius=8)
    if template is None:
        return None

    backward_pts = []
    pts = np.array([[[float(anchor_x), float(anchor_y)]]], dtype=np.float32)
    gray_prev = gray0

    for df in range(1, min(max_back, anchor_f + 1)):
        fi = anchor_f - df
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
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

            # Strict appearance lock
            color_ok = check_color(hf, nx, ny)
            template_ok = match_template(gf, nx, ny, template, radius=8)
            jump_ok = abs(nx - float(pts[0, 0, 0])) < MAX_JUMP and abs(ny - float(pts[0, 0, 1])) < MAX_JUMP

            if color_ok and template_ok and jump_ok:
                backward_pts.append((fi, nx, ny))
                pts = np2.reshape(1, 1, 2)
                gray_prev = gf
                continue
            elif len(backward_pts) > 3:
                # Lost lock after having enough points — that's fine
                break
            # Lost lock early — discard
            break
        else:
            break

    if len(backward_pts) < 3:
        return None

    # Origin = first backward point (farthest from anchor)
    origin_f, origin_x, origin_y = backward_pts[-1]

    # Emergence vector: from origin to anchor
    dx = anchor_x - origin_x
    dy = anchor_y - origin_y
    emergence_dist = np.sqrt(dx**2 + dy**2)
    emergence_angle = np.degrees(np.arctan2(dy, dx))

    # Corridor stability: variance in displacement direction
    if len(backward_pts) >= 3:
        displacements = []
        for i in range(1, len(backward_pts)):
            ddx = backward_pts[i][1] - backward_pts[i-1][1]
            ddy = backward_pts[i][2] - backward_pts[i-1][2]
            displacements.append((ddx, ddy))
        displacements = np.array(displacements)
        norms = np.linalg.norm(displacements, axis=1)
        norms[norms < 1e-8] = 1e-8
        unit_vecs = displacements / norms[:, None]
        mean_dir = np.mean(unit_vecs, axis=0)
        stability = np.linalg.norm(mean_dir)  # 0=random, 1=perfectly straight
    else:
        stability = 0.5

    return {
        'origin_x': origin_x, 'origin_y': origin_y, 'origin_f': origin_f,
        'emergence_dist': emergence_dist, 'emergence_angle': emergence_angle,
        'n_points': len(backward_pts), 'stability': stability,
    }


def compute_origin_features(anchor_x, anchor_y, anchor_f, emergence, bl_x, bl_y, br_x, br_y):
    """Compute origin features relative to nearest basket and court."""
    if emergence is None:
        return None

    ox, oy = emergence['origin_x'], emergence['origin_y']
    o_f = emergence['origin_f']

    # Nearest basket
    d_l = np.sqrt((ox - BLX)**2 + (oy - BLY)**2)
    d_r = np.sqrt((ox - BRX)**2 + (oy - BRY)**2)
    nearest = 'left' if d_l < d_r else 'right'
    basket_x, basket_y = (BLX, BLY) if nearest == 'left' else (BRX, BRY)
    dist_px = min(d_l, d_r)

    # Scale from basket separation
    sf = anchor_f if anchor_f < len(bl_x) and not np.isnan(bl_x[anchor_f]) else o_f
    if sf < len(bl_x) and not np.isnan(bl_x[sf]):
        bsep = np.sqrt((bl_x[sf] - br_x[sf])**2 + (bl_y[sf] - br_y[sf])**2)
        scale = bsep / 47.0 if bsep > 200 else 17.7
    else:
        scale = 17.7

    dist_ft = dist_px / scale

    # Lateral offset from center-attack line (basket to halfcourt center)
    # Center-attack line: from basket to (640, 360) approx center of frame
    center_x, center_y = 640, 360
    attack_dx = center_x - basket_x
    attack_dy = center_y - basket_y
    attack_len = np.sqrt(attack_dx**2 + attack_dy**2)
    if attack_len > 0:
        # Project origin-to-basket vector onto attack line
        to_origin_x = ox - basket_x
        to_origin_y = oy - basket_y
        # Lateral offset = distance from attack line
        cross = abs(to_origin_x * attack_dy - to_origin_y * attack_dx) / attack_len
        lateral_ft = cross / scale
    else:
        lateral_ft = 0

    # Emergence cone angle (direction ball came from)
    angle = emergence['emergence_angle']

    # Soft zone assignment based on distance + lateral + angle
    # Sectors: paint, ft_range, midrange, wing, corner, deep
    if dist_ft < 7:
        zone = 'paint'
    elif dist_ft < 12:
        zone = 'midrange'
    elif dist_ft < 16:
        zone = 'ft_range'
    elif dist_ft < 20:
        zone = 'elbow_wing'
    elif dist_ft >= 20 and lateral_ft > 11:
        zone = 'corner'
    elif dist_ft >= 20:
        zone = 'wing'
    else:
        zone = 'deep'

    # Zone confidence from emergence quality
    conf = min(emergence['stability'] * min(emergence['n_points'] / 8, 1.0), 1.0)

    return {
        'origin_distance_ft': round(dist_ft, 1),
        'origin_lateral_ft': round(lateral_ft, 1),
        'emergence_angle': round(angle, 1),
        'emergence_dist_px': round(emergence['emergence_dist'], 1),
        'emergence_n_points': emergence['n_points'],
        'corridor_stability': round(emergence['stability'], 2),
        'anchor_confidence': round(conf, 2),
        'origin_sector': zone,
        'nearest_basket': nearest,
        'origin': (round(ox), round(oy)),
        'scale': round(scale, 1),
    }


if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    bl_x, bl_y = v8['basket_left']
    br_x, br_y = v8['basket_right']

    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2 + (ry[i]-BLY)**2),
                     np.sqrt((rx[i]-BRX)**2 + (ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    results = []

    for ci, (f, cx, cy) in enumerate(cands):
        # v23 tracking
        track = track_bidir(cap, f, cx, cy, total)
        if len(track) < MIN_PTS:
            log(f"  [{ci+1:2d}] F{f}: TRACK_FAIL ({len(track)}f)")
            continue

        # Local backward emergence
        emergence = estimate_local_backward_emergence(f, cx, cy, cap, total, max_back=15)

        # Make/miss (from forward track)
        xs = np.array([x for _, x, y in track])
        ys = np.array([y for _, x, y in track])
        dists = np.minimum(np.sqrt((xs-BLX)**2 + (ys-BLY)**2),
                           np.sqrt((xs-BRX)**2 + (ys-BRY)**2))
        min_dist = float(np.min(dists))
        is_make = min_dist < MAKE_R

        if emergence:
            features = compute_origin_features(cx, cy, f, emergence, bl_x, bl_y, br_x, br_y)
            if features:
                result = {
                    'frame': f,
                    'make_miss': 'MAKE' if is_make else 'MISS',
                    'closest_px': round(min_dist, 1),
                    'anchor_px': round(min(np.sqrt((cx-BLX)**2+(cy-BLY)**2),
                                            np.sqrt((cx-BRX)**2+(cy-BRY)**2)), 1),
                    **features,
                }
                results.append(result)
                log(f"  [{ci+1:2d}] F{f}: {'MAKE' if is_make else 'MISS'} "
                    f"sector={features['origin_sector']} dist_ft={features['origin_distance_ft']} "
                    f"lateral_ft={features['origin_lateral_ft']} angle={features['emergence_angle']} "
                    f"conf={features['anchor_confidence']} "
                    f"stab={features['corridor_stability']} pts={features['emergence_n_points']} "
                    f"origin={features['origin']} scale={features['scale']}")
                continue

        # No emergence — output anchor-only features
        d_l = np.sqrt((cx-BLX)**2 + (cy-BLY)**2)
        d_r = np.sqrt((cx-BRX)**2 + (cy-BRY)**2)
        anchor_px = min(d_l, d_r)
        results.append({
            'frame': f, 'make_miss': 'MAKE' if is_make else 'MISS',
            'closest_px': round(min_dist, 1), 'anchor_px': round(anchor_px, 1),
            'origin_distance_ft': None, 'origin_lateral_ft': None,
            'emergence_angle': None, 'emergence_dist_px': None,
            'emergence_n_points': 0, 'corridor_stability': 0,
            'anchor_confidence': 0, 'origin_sector': 'unknown',
            'nearest_basket': 'left' if d_l < d_r else 'right',
            'origin': (round(cx), round(cy)), 'scale': 17.7,
        })
        log(f"  [{ci+1:2d}] F{f}: {'MAKE' if is_make else 'MISS'} "
            f"NO_EMERGENCE anchor_px={anchor_px:.0f} track={len(track)}f")

    cap.release()

    # Dedup
    results.sort(key=lambda r: r['frame'])
    deduped = []
    for r in results:
        if deduped and r['frame'] - deduped[-1]['frame'] < 30:
            if r.get('anchor_confidence', 0) > deduped[-1].get('anchor_confidence', 0):
                deduped[-1] = r
        else:
            deduped.append(r)
    results = deduped

    log(f"\n{'='*70}")
    log(f"RESULTS: {len(results)} shot events")
    log(f"{'Frame':>6} {'Make/Miss':>9} {'Sector':>12} {'Dist_ft':>8} {'Lat_ft':>7} "
        f"{'Angle':>6} {'Conf':>5} {'Stab':>5} {'Pts':>4} {'Origin':>12}")
    log(f"{'-'*70}")
    for r in results:
        ox = r.get('origin')
        origin_str = f"({ox[0]},{ox[1]})" if isinstance(ox, (tuple, list)) else str(ox)
        log(f"  F{r['frame']:4d} {r['make_miss']:>9} {r.get('origin_sector','?'):>12} "
            f"{str(r.get('origin_distance_ft','')):>8} {str(r.get('origin_lateral_ft','')):>7} "
            f"{str(r.get('emergence_angle','')):>6} {r.get('anchor_confidence',0):>5} "
            f"{r.get('corridor_stability',0):>5} {r.get('emergence_n_points',0):>4} "
            f"{origin_str:>12}")

    log("\n=== Sector Distribution ===")
    sectors = {}
    for r in results:
        s = r.get('origin_sector', 'unknown')
        sectors[s] = sectors.get(s, 0) + 1
    for s, n in sorted(sectors.items()):
        log(f"  {s}: {n}")

    pd.DataFrame(results).to_csv(f'{OUT}/shot_features_v34.csv', index=False)
    log("DONE")
