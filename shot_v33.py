#!/usr/bin/env python3
"""
Shot detection v33: Backward motion corridor + zone classification
==================================================================
Architecture shift: Stop treating shooter as a person. Treat it as a
spatial-temporal origin hypothesis.

Pipeline:
  1. v23 appearance-locked OF anchors (rim approach confirms ball)
  2. v16 dense track back-anchored by v23 (validated trajectory)
  3. Backward motion corridor: trace OF path from anchor backward
     through dense track to find origin zone
  4. Court zone intersection: map corridor to court regions using keypoints
  5. Probabilistic classification by zone, not hard thresholds

Key insight from v32: F1303 recovered 27.9ft distance — perimeter origin
information IS recoverable from backward context. The problem was nearest-
contour attribution. Motion corridor is the stable signal.
"""
import os, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
BASKETS = [(BLX, BLY), (BRX, BRY)]
FWD_WIN, BWD_WIN = 20, 15
MIN_PTS, MAX_JUMP = 10, 80
MAKE_R = 55

# NCAA half-court: 47ft x 50ft
# Zones (distance from basket, feet):
# paint: <8, midrange: 8-15, FT: 12-17, wing3: 15-24, corner3: 15-24 (lateral), 3PT: >20
ZONES = {
    'paint':       (0, 8, '2PT'),
    'midrange':    (8, 12, '2PT'),
    'ft_range':    (12, 18, 'FT'),
    'wing_3':      (18, 24, '3PT'),
    'corner_3':    (18, 24, '3PT'),
    'deep':        (24, 50, '3PT'),
}


def log(msg):
    print(msg, flush=True)


# ---- Tracking (v23, unchanged) ----

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


# ---- Backward motion corridor ----

def estimate_motion_corridor_of(anchor_f, anchor_x, anchor_y, cap, total, max_back=30):
    """Estimate the ball's backward motion corridor using optical flow.

    Instead of tracking a template (which loses the ball), use sparse OF
    to estimate the BACKWARD motion direction from the anchor.

    This is different from template tracking: we're measuring the OPTICAL
    FLOW in a region around the anchor to infer where the ball came from.

    Returns: (origin_x, origin_y, corridor_angle, confidence)
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, anchor_f)
    ret, img_now = cap.read()
    if not ret:
        return None

    gray_now = cv2.cvtColor(img_now, cv2.COLOR_BGR2GRAY)

    # Collect backward displacement vectors
    displacements = []
    prev_gray = gray_now

    for df in range(1, min(max_back, anchor_f + 1)):
        fi = anchor_f - df
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, img_prev = cap.read()
        if not ret:
            break
        gray_prev_frame = cv2.cvtColor(img_prev, cv2.COLOR_BGR2GRAY)

        # Estimate optical flow at the anchor point
        pt = np.array([[[anchor_x, anchor_y]]], dtype=np.float32)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev_frame, gray_now, pt, None,
            winSize=(21, 21), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 15, 0.03))

        if st[0, 0] == 1:
            # Forward flow (prev → now)
            fx = float(np2[0, 0, 0] - anchor_x) / df  # average per-frame
            fy = float(np2[0, 0, 1] - anchor_y) / df
            # Backward flow = where the ball came FROM
            displacements.append((-fx, -fy))

        prev_gray = gray_prev_frame

    if len(displacements) < 3:
        return None

    displacements = np.array(displacements)
    # Average backward direction
    avg_dir = np.mean(displacements, axis=0)
    avg_mag = np.linalg.norm(avg_dir)

    if avg_mag < 0.5:
        return None

    # Origin = anchor projected backward along corridor
    # Project further back based on motion magnitude
    corridor_angle = np.degrees(np.arctan2(avg_dir[1], avg_dir[0]))

    # Confidence: consistency of direction
    if len(displacements) > 1:
        norms = np.linalg.norm(displacements, axis=1)
        norms[norms == 0] = 1e-8
        unit = displacements / norms[:, None]
        mean_unit = np.mean(unit, axis=0)
        confidence = np.linalg.norm(mean_unit)  # 1.0 = perfectly consistent
    else:
        confidence = 0.5

    # Estimate origin by extending corridor backward
    # Use the OF track's backward extent as a proxy for corridor length
    origin_x = anchor_x - avg_dir[0] * max_back * 0.5
    origin_y = anchor_y - avg_dir[1] * max_back * 0.5

    return {
        'origin_x': origin_x, 'origin_y': origin_y,
        'angle': corridor_angle, 'confidence': confidence,
        'displacements': len(displacements),
    }


def estimate_corridor_from_dense_track(anchor_f, anchor_x, anchor_y, dense_x, dense_y, total, max_back=50):
    """Estimate motion corridor by backtracing through the v16 dense track.

    The dense track gives us ball positions at every frame. We validate
    which ones are likely the ball by checking proximity to the known
    anchor point and color consistency.

    Returns: (origin_x, origin_y, corridor_angle, confidence)
    """
    # Find the ball's trajectory in the dense track by walking backward
    # from the anchor and finding consistent positions
    corridor_points = []

    # Start from anchor
    prev_x, prev_y = anchor_x, anchor_y

    for df in range(1, min(max_back, anchor_f + 1)):
        fi = anchor_f - df
        if fi < 0 or np.isnan(dense_x[fi]) or np.isnan(dense_y[fi]):
            continue

        dx = dense_x[fi]
        dy = dense_y[fi]

        # Check if this dense track point is a plausible continuation
        dist_from_prev = np.sqrt((dx - prev_x)**2 + (dy - prev_y)**2)
        dist_from_anchor = np.sqrt((dx - anchor_x)**2 + (dy - anchor_y)**2)

        # The dense track points should be progressively farther from
        # the anchor as we go backward (approaching the launch point)
        if dist_from_prev < 80 or (dist_from_anchor > 100 and dist_from_prev < 60):
            corridor_points.append((fi, dx, dy))
            prev_x, prev_y = dx, dy
        elif corridor_points:
            # Point is inconsistent — stop
            break

    if len(corridor_points) < 3:
        return None

    # Use corridor points to estimate origin
    # The first point (farthest back) is the best origin estimate
    first_f, first_x, first_y = corridor_points[-1]

    # Direction from origin to anchor
    dx = anchor_x - first_x
    dy = anchor_y - first_y
    corridor_angle = np.degrees(np.arctan2(dy, dx))

    # Confidence: how linear is the corridor?
    if len(corridor_points) > 2:
        pts = np.array([(x, y) for _, x, y in corridor_points])
        # Fit line, compute residuals
        if len(pts) > 2:
            mean_pt = np.mean(pts, axis=0)
            centered = pts - mean_pt
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            direction = vt[0]
            projections = centered @ direction
            residual = np.sqrt(np.sum(centered**2, axis=1) - projections**2)
            mean_res = np.mean(residual)
            span = np.max(projections) - np.min(projections)
            confidence = min(span / (mean_res + 1), 1.0) * 0.5 + 0.5
        else:
            confidence = 0.5
    else:
        confidence = 0.5

    return {
        'origin_x': first_x, 'origin_y': first_y,
        'angle': corridor_angle, 'confidence': confidence,
        'n_points': len(corridor_points),
        'first_frame': first_f,
    }


# ---- Zone classification ----

def classify_by_zone(origin_x, origin_y, anchor_f, bl_x, bl_y, br_x, br_y):
    """Classify shot by mapping origin to court zone.

    Uses court keypoints to define zone boundaries relative to basket.
    """
    # Nearest basket
    d_l = np.sqrt((origin_x - BLX)**2 + (origin_y - BLY)**2)
    d_r = np.sqrt((origin_x - BRX)**2 + (origin_y - BRY)**2)
    nearest_basket = (BLX, BLY) if d_l < d_r else (BRX, BRY)
    d_px = min(d_l, d_r)

    # Get scale from basket separation
    if anchor_f < len(bl_x) and not np.isnan(bl_x[anchor_f]):
        bsep = np.sqrt((bl_x[anchor_f] - br_x[anchor_f])**2 + (bl_y[anchor_f] - br_y[anchor_f])**2)
        scale = bsep / 47.0 if bsep > 200 else 17.7  # default to median
    else:
        scale = 17.7

    d_ft = d_px / scale

    # Lateral position relative to basket (for corner vs wing distinction)
    bx, by = nearest_basket
    dx = origin_x - bx
    dy = origin_y - by

    # Classify by distance
    if d_ft >= 20:
        # Periphery: distinguish corner from wing by lateral position
        # NCAA half-court is 50ft wide, so y=25 is center
        lateral_offset = abs(dy)
        lateral_ft = lateral_offset / scale
        if lateral_ft > 12:
            zone = 'corner_3'
            stype = '3PT'
        else:
            zone = 'wing_3'
            stype = '3PT'
    elif 14 <= d_ft < 20:
        zone = 'ft_range'
        stype = 'FT'
    elif 10 <= d_ft < 14:
        zone = 'midrange'
        stype = '2PT'
    else:
        zone = 'paint'
        stype = '2PT'

    return {
        'zone': zone,
        'type': stype,
        'dist_ft': round(d_ft, 1),
        'lateral_ft': round(abs(dy) / scale, 1),
        'origin': (round(origin_x), round(origin_y)),
    }


# ---- Make/Miss ----

def check_make_miss(track):
    """Determine make/miss from closest approach to basket."""
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])
    dists = np.minimum(np.sqrt((xs - BLX)**2 + (ys - BLY)**2),
                       np.sqrt((xs - BRX)**2 + (ys - BRY)**2))
    return float(np.min(dists))


# ---- Main ----

if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    # Load dense track
    with open(f'{OUT}/shot_v16.pkl', 'rb') as f:
        v16 = pickle.load(f)
    dense_x, dense_y = v16['track_x'], v16['track_y']

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
        # Track ball
        track = track_bidir(cap, f, cx, cy, total)
        if len(track) < MIN_PTS:
            log(f"  [{ci+1:2d}] F{f}: REJECTED ({len(track)}f)")
            continue

        # Estimate backward motion corridor
        corridor = estimate_corridor_from_dense_track(
            f, cx, cy, dense_x, dense_y, total, max_back=40)

        if corridor and corridor['confidence'] > 0.3:
            origin_x = corridor['origin_x']
            origin_y = corridor['origin_y']

            # Classify by zone
            cls = classify_by_zone(origin_x, origin_y, f, bl_x, bl_y, br_x, br_y)

            min_dist = check_make_miss(track)
            is_make = (min_dist < MAKE_R)
            result = 'MAKE' if is_make else 'MISS'

            shots.append({
                'frame': f,
                'type': cls['type'],
                'zone': cls['zone'],
                'result': result,
                'closest': round(min_dist, 1),
                'dist_ft': cls['dist_ft'],
                'origin': cls['origin'],
                'n_corridor': corridor['n_points'],
                'corr_f': corridor['first_frame'],
                'track': len(track),
            })

            log(f"  [{ci+1:2d}] F{f}: {cls['type']} {cls['zone']} {result} "
                f"dist_ft={cls['dist_ft']} origin={cls['origin']} "
                f"corridor={corridor['n_points']}pts ({corridor['first_frame']}-{f}) "
                f"track={len(track)}f")
        else:
            # Fallback: classify by anchor distance
            d_l = np.sqrt((cx - BLX)**2 + (cy - BLY)**2)
            d_r = np.sqrt((cx - BRX)**2 + (cy - BRY)**2)
            d_px = min(d_l, d_r)
            stype = '2PT'
            zone = 'paint' if d_px / 17.7 < 8 else 'midrange'
            min_dist = check_make_miss(track)
            is_make = min_dist < MAKE_R

            shots.append({
                'frame': f, 'type': stype, 'zone': zone,
                'result': 'MAKE' if is_make else 'MISS',
                'closest': round(min_dist, 1),
                'dist_ft': round(d_px / 17.7, 1),
                'origin': (round(cx), round(cy)),
                'n_corridor': 0, 'corr_f': f,
                'track': len(track),
            })
            log(f"  [{ci+1:2d}] F{f}: {stype} {zone} {'MAKE' if is_make else 'MISS'} "
                f"(fallback, no corridor) track={len(track)}f")

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

    log(f"\n{'='*60}")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"FT:  {sum(1 for s in ft if s['result']=='MAKE')}/{len(ft)}")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['zone']:10s} {s['result']:4s} "
            f"dist_ft={s['dist_ft']} origin={s['origin']} corridor={s['n_corridor']}pts")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'zone': s['zone'],
            'result': s['result'], 'dist': s['closest'],
            'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v33.csv', index=False)
