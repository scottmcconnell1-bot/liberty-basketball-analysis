#!/usr/bin/env python3
"""
Shot detection v35: Derived second-order features + diagnostic table
====================================================================
Builds on v34's local backward emergence and adds:

DERIVED FEATURES:
  - distance_growth_rate: how fast the ball moves away from basket in backward track
    (short compact = layup, long gradual = 3PT)
  - angle_variance: consistency of backward motion direction
    (clean = set shot, noisy = traffic/contested)
  - corridor_width: max lateral deviation from straight line to anchor
    (narrow = set shot, wide = off-balance)
  - origin_to_anchor_ratio: how far back we got vs total visible flight
    (low = early NN detection, high = late detection = long shot)
  - mean_backward_speed: average px/frame in backward track
    (fast = live ball, slow = set shot)
  - lateral_velocity: lateral displacement per frame
    (fast = wing shot, slow = center)
  - corridor_curvature: total angular change in backward path
  - appearance_decay_rate: how quickly template correlation drops backward

Also outputs a proper diagnostic CSV with all features for each shot event,
sorted by ground truth labels (once provided) for distribution analysis.
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


def estimate_local_backward_emergence(anchor_f, anchor_x, anchor_y, cap, total, max_back=20):
    """Local backward emergence with strict appearance lock.

    Returns emergence data + per-frame backward measurements
    for derived feature computation.
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
    backward_corrs = []
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

            color_ok = check_color(hf, nx, ny)

            # Compute template correlation
            h_patch = gf.shape[0]
            w_patch = gf.shape[1]
            x1p = max(0, int(nx) - 8)
            x2p = min(w_patch, int(nx) + 8)
            y1p = max(0, int(ny) - 8)
            y2p = min(h_patch, int(ny) + 8)
            patch = gf[y1p:y2p, x1p:x2p]
            if patch.size >= 9:
                hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
                hist = hist / (hist.sum() + 1e-8)
                corr = cv2.compareHist(template['hist'].astype(np.float32),
                                       hist.astype(np.float32), cv2.HISTCMP_CORREL)
            else:
                corr = 0

            jump = np.sqrt((nx - float(pts[0, 0, 0]))**2 + (ny - float(pts[0, 0, 1]))**2)
            jump_ok = jump < MAX_JUMP

            if color_ok and corr > 0.5 and jump_ok:
                backward_pts.append((fi, nx, ny))
                backward_corrs.append(corr)
                pts = np2.reshape(1, 1, 2)
                gray_prev = gf
                continue
            elif len(backward_pts) > 3:
                break
            break
        else:
            break

    if len(backward_pts) < 3:
        return None

    origin_f, origin_x, origin_y = backward_pts[-1]
    anchor_dist = np.sqrt((anchor_x - origin_x)**2 + (anchor_y - origin_y)**2)
    emergence_angle = np.degrees(np.arctan2(anchor_y - origin_y, anchor_x - origin_x))

    return {
        'origin_x': origin_x, 'origin_y': origin_y, 'origin_f': origin_f,
        'anchor_dist': anchor_dist, 'emergence_angle': emergence_angle,
        'n_points': len(backward_pts),
        'forward_pts': backward_pts,
        'forward_corrs': backward_corrs,
    }


def compute_derived_features(emergence, anchor_x, anchor_y, anchor_f, bl_x, bl_y, br_x, br_y):
    """Compute second-order derived features from emergence data."""
    if emergence is None or emergence['n_points'] < 3:
        return None

    pts = emergence['forward_pts']  # (frame, x, y) sorted backward from anchor
    n = len(pts)

    # --- Basic geometry ---
    ox, oy = emergence['origin_x'], emergence['origin_y']
    dist_px = emergence['anchor_dist']

    # Nearest basket
    d_l = np.sqrt((ox - BLX)**2 + (oy - BLY)**2)
    d_r = np.sqrt((ox - BRX)**2 + (oy - BRY)**2)
    nearest = 'left' if d_l < d_r else 'right'
    basket_x, basket_y = (BLX, BLY) if nearest == 'left' else (BRX, BRY)

    # Scale
    sf = anchor_f if anchor_f < len(bl_x) and not np.isnan(bl_x[anchor_f]) else pts[-1][0]
    if sf < len(bl_x) and not np.isnan(bl_x[sf]):
        bsep = np.sqrt((bl_x[sf] - br_x[sf])**2 + (bl_y[sf] - br_y[sf])**2)
        scale = bsep / 47.0 if bsep > 200 else 17.7
    else:
        scale = 17.7

    dist_ft = dist_px / scale

    # --- Lateral offset from center-attack line ---
    center_x, center_y = 640, 360
    attack_dx = center_x - basket_x
    attack_dy = center_y - basket_y
    attack_len = np.sqrt(attack_dx**2 + attack_dy**2)
    if attack_len > 0:
        to_origin_x = ox - basket_x
        to_origin_y = oy - basket_y
        cross = abs(to_origin_x * attack_dy - to_origin_y * attack_dx) / attack_len
        lateral_ft = cross / scale
    else:
        lateral_ft = 0

    # --- distance_growth_rate: how fast distance increases backward ---
    # Compute distance from basket at each backward point
    dists = [np.sqrt((x - basket_x)**2 + (y - basket_y)**2) for _, x, y in pts]
    if len(dists) >= 3:
        # Rate of distance increase (px per frame moving backward)
        total_growth = dists[-1] - dists[0]
        total_frames = pts[0][0] - pts[-1][0] if pts[0][0] != pts[-1][0] else 1
        dist_growth_rate = total_growth / total_frames  # px/frame
        dist_growth_rate_ft = dist_growth_rate / scale  # ft/frame
    else:
        dist_growth_rate = 0
        dist_growth_rate_ft = 0

    # --- angle_variance: how much the backward direction changes ---
    if len(pts) >= 3:
        angles = []
        for i in range(1, len(pts)):
            dx = pts[i][1] - pts[i-1][1]
            dy = pts[i][2] - pts[i-1][2]
            if abs(dx) > 0.1 or abs(dy) > 0.1:
                angles.append(np.degrees(np.arctan2(dy, dx)))
        if len(angles) >= 2:
            angle_var = float(np.std(angles))
        else:
            angle_var = 0
    else:
        angle_var = 0

    # --- corridor_width: max deviation from straight line origin→anchor ---
    if len(pts) >= 3:
        # Line from origin to anchor
        line_dx = anchor_x - ox
        line_dy = anchor_y - oy
        line_len = np.sqrt(line_dx**2 + line_dy**2)
        if line_len > 0:
            max_dev = 0
            for _, px, py in pts:
                # Distance from point to line
                dev = abs((px - ox) * line_dy - (py - oy) * line_dx) / line_len
                max_dev = max(max_dev, dev)
            corridor_width_px = max_dev
            corridor_width_ft = max_dev / scale
        else:
            corridor_width_px = 0
            corridor_width_ft = 0
    else:
        corridor_width_px = 0
        corridor_width_ft = 0

    # --- origin_to_anchor_ratio: how far back we got vs visible flight ---
    # Forward track extent (from bidir) would be ideal, but we use NN proximity
    # as a proxy: closer to basket = earlier NN detection = shorter visible flight
    nn_prox = min(np.sqrt((anchor_x - BLX)**2 + (anchor_y - BLY)**2),
                  np.sqrt((anchor_x - BRX)**2 + (anchor_y - BRY)**2))
    if nn_prox > 0:
        oa_ratio = dist_px / nn_prox
    else:
        oa_ratio = 0

    # --- mean_backward_speed ---
    if len(pts) >= 2:
        speeds = []
        for i in range(1, len(pts)):
            dx = pts[i][1] - pts[i-1][1]
            dy = pts[i][2] - pts[i-1][2]
            dt = abs(pts[i][0] - pts[i-1][0])
            if dt > 0:
                speeds.append(np.sqrt(dx**2 + dy**2) / dt)
        mean_backward_speed = float(np.mean(speeds)) if speeds else 0
    else:
        mean_backward_speed = 0

    # --- lateral_velocity: lateral displacement per frame ---
    if len(pts) >= 2:
        lateral_displacements = []
        for i in range(1, len(pts)):
            # Project displacement onto lateral axis (perpendicular to center-attack line)
            if attack_len > 0:
                lat_dx = -attack_dy / attack_len
                lat_dy = attack_dx / attack_len
                ddx = pts[i][1] - pts[i-1][1]
                ddy = pts[i][2] - pts[i-1][2]
                lat_disp = ddx * lat_dx + ddy * lat_dy
                dt = abs(pts[i][0] - pts[i-1][0])
                if dt > 0:
                    lateral_displacements.append(lat_disp / dt)
        lateral_velocity = float(np.mean(lateral_displacements)) / scale if lateral_displacements else 0
    else:
        lateral_velocity = 0

    # --- corridor_curvature: total angular change in path ---
    if len(pts) >= 3:
        total_turn = 0
        prev_angle = None
        for i in range(1, len(pts)):
            dx = pts[i][1] - pts[i-1][1]
            dy = pts[i][2] - pts[i-1][2]
            if abs(dx) > 0.1 or abs(dy) > 0.1:
                angle = np.arctan2(dy, dx)
                if prev_angle is not None:
                    turn = abs(angle - prev_angle)
                    if turn > np.pi:
                        turn = 2 * np.pi - turn
                    total_turn += turn
                prev_angle = angle
        corridor_curvature = total_turn
    else:
        corridor_curvature = 0

    # --- appearance_decay_rate: how fast template correlation drops ---
    corrs = emergence.get('forward_corrs', [])
    if len(corrs) >= 3:
        # Linear fit to correlation vs frame index
        x = np.arange(len(corrs))
        if len(x) > 1:
            slope = np.polyfit(x, corrs, 1)[0]
            appearance_decay_rate = slope
        else:
            appearance_decay_rate = 0
    else:
        appearance_decay_rate = 0

    # --- corridor_stability (from v34) ---
    if len(pts) >= 3:
        unit_vecs = []
        for i in range(1, len(pts)):
            dx = pts[i][1] - pts[i-1][1]
            dy = pts[i][2] - pts[i-1][2]
            norm = np.sqrt(dx**2 + dy**2)
            if norm > 1e-8:
                unit_vecs.append((dx/norm, dy/norm))
        if unit_vecs:
            mean_dir = np.mean(unit_vecs, axis=0)
            stability = float(np.linalg.norm(mean_dir))
        else:
            stability = 0.5
    else:
        stability = 0.5

    return {
        # First-order (v34)
        'origin_distance_ft': round(dist_ft, 1),
        'origin_lateral_ft': round(lateral_ft, 1),
        'emergence_angle': round(emergence['emergence_angle'], 1),
        'emergence_n_points': emergence['n_points'],
        'corridor_stability': round(stability, 2),
        'nearest_basket': nearest,

        # Derived second-order
        'distance_growth_rate_ft': round(dist_growth_rate_ft, 2),
        'angle_variance': round(angle_var, 1),
        'corridor_width_ft': round(corridor_width_ft, 1),
        'origin_to_anchor_ratio': round(oa_ratio, 2),
        'mean_backward_speed': round(mean_backward_speed, 1),
        'lateral_velocity_fps': round(lateral_velocity, 2),
        'corridor_curvature': round(corridor_curvature, 2),
        'appearance_decay_rate': round(appearance_decay_rate, 3),

        # Meta
        'scale': round(scale, 1),
        'origin': (round(ox), round(oy)),
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
    bl_x, bl_y = v8['basket_left']
    br_x, br_y = v8['basket_right']

    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2 + (ry[i]-BLY)**2),
                     np.sqrt((rx[i]-BRX)**2 + (ry[i]-BRY)**2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    results = []

    for ci, (f, cx, cy) in enumerate(cands):
        track = track_bidir(cap, f, cx, cy, total)
        if len(track) < MIN_PTS:
            continue

        # Make/miss
        xs = np.array([x for _, x, y in track])
        ys = np.array([y for _, x, y in track])
        dists = np.minimum(np.sqrt((xs-BLX)**2 + (ys-BLY)**2),
                           np.sqrt((xs-BRX)**2 + (ys-BRY)**2))
        min_dist = float(np.min(dists))
        is_make = min_dist < MAKE_R

        # Local backward emergence
        emergence = estimate_local_backward_emergence(f, cx, cy, cap, total, max_back=20)

        if emergence and emergence['n_points'] >= 3:
            features = compute_derived_features(
                emergence, cx, cy, f, bl_x, bl_y, br_x, br_y)

            if features:
                result = {
                    'anchor_frame': f,
                    'make_miss': 'MAKE' if is_make else 'MISS',
                    'closest_px': round(min_dist, 1),
                    **features,
                }
                results.append(result)

                log(f"  [{ci+1:2d}] F{f:4d} {'MAKE' if is_make else 'MISS'} "
                    f"d={features['origin_distance_ft']:5.1f}ft "
                    f"lat={features['origin_lateral_ft']:5.1f}ft "
                    f"growth={features['distance_growth_rate_ft']:5.2f} "
                    f"w={features['corridor_width_ft']:4.1f}ft "
                    f"stab={features['corridor_stability']:.2f} "
                    f"turn={features['corridor_curvature']:.2f} "
                    f"dec={features['appearance_decay_rate']:+.3f} "
                    f"pts={features['emergence_n_points']}")
                continue

        log(f"  [{ci+1:2d}] F{f:4d} {'MAKE' if is_make else 'MISS'} NO_EMERGENCE")

    cap.release()

    # Dedup
    results.sort(key=lambda r: r['anchor_frame'])
    deduped = []
    for r in results:
        if deduped and r['anchor_frame'] - deduped[-1]['anchor_frame'] < 30:
            if r['emergence_n_points'] > deduped[-1]['emergence_n_points']:
                deduped[-1] = r
        else:
            deduped.append(r)
    results = deduped

    # --- Output diagnostic table ---
    log(f"\n{'='*100}")
    log(f"FEATURE DIAGNOSTIC TABLE — {len(results)} shot events")
    hdr = (f"{'Frame':>6} {'MM':>4} {'Dist':>6} {'Lat':>6} {'Growth':>7} "
           f"{'Width':>6} {'Stab':>5} {'Turn':>5} {'Decay':>6} {'AngVar':>6} "
           f"{'LatVel':>6} {'Ratio':>6} {'OAR':>4} {'Basket':>6}")
    log(hdr)
    log("-" * len(hdr))
    for r in results:
        log(f"  F{r['anchor_frame']:4d} {r['make_miss']:>4} "
            f"{r.get('origin_distance_ft',0):>6} {r.get('origin_lateral_ft',0):>6} "
            f"{r.get('distance_growth_rate_ft',0):>7} {r.get('corridor_width_ft',0):>6} "
            f"{r.get('corridor_stability',0):>5} {r.get('corridor_curvature',0):>5} "
            f"{r.get('appearance_decay_rate',0):>+6} {r.get('angle_variance',0):>6} "
            f"{r.get('lateral_velocity_fps',0):>6} {r.get('origin_to_anchor_ratio',0):>6} "
            f"{r.get('emergence_n_points',0):>4} {r.get('nearest_basket','?'):>6}")

    # --- Feature distributions ---
    log("\n=== Feature Distributions ===")
    for feat in ['origin_distance_ft', 'origin_lateral_ft', 'distance_growth_rate_ft',
                 'corridor_width_ft', 'corridor_stability', 'corridor_curvature',
                 'appearance_decay_rate', 'angle_variance', 'lateral_velocity_fps',
                 'origin_to_anchor_ratio']:
        vals = [r[feat] for r in results if feat in r and r[feat] is not None]
        if vals:
            log(f"  {feat:30s}: mean={np.mean(vals):.2f} std={np.std(vals):.2f} "
                f"min={np.min(vals):.2f} max={np.max(vals):.2f} n={len(vals)}")

    # --- Make vs Miss comparison ---
    log("\n=== Make vs Miss ===")
    makes = [r for r in results if r['make_miss'] == 'MAKE']
    misses = [r for r in results if r['make_miss'] == 'MISS']
    log(f"  MAKES ({len(makes)}):")
    for feat in ['origin_distance_ft', 'corridor_stability', 'corridor_width_ft']:
        vals = [r[feat] for r in makes if feat in r and r[feat] is not None]
        if vals:
            log(f"    {feat:30s}: mean={np.mean(vals):.2f}")
    log(f"  MISSES ({len(misses)}):")
    for feat in ['origin_distance_ft', 'corridor_stability', 'corridor_width_ft']:
        vals = [r[feat] for r in misses if feat in r and r[feat] is not None]
        if vals:
            log(f"    {feat:30s}: mean={np.mean(vals):.2f}")

    pd.DataFrame(results).to_csv(f'{OUT}/shot_features_v35.csv', index=False)
    log("DONE")
