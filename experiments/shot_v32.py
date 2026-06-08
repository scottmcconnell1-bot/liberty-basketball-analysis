#!/usr/bin/env python3
"""
Shot detection v32: Pre-shot context recovery
==============================================
For each NN ball anchor (rim approach), rewind to find the
possession context: who was near the ball before it became visible?

The ball appears isolated near the basket (NN fires).
30-40 frames earlier, someone had the ball.
Find that person → infer shooter location → classify shot.

This is INDIRECT inference:
  ball anchor (certain) → rewind → find nearest player contour → shooter zone

No YOLO player model needed — just contour proximity in the
frames preceding each shot anchor.
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


# ---- Appearance-locked tracking (v23) ----

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


# ---- Player contour detection (lightweight, no NN) ----

def detect_player_contours(frame, min_area=150, max_area=6000):
    """Detect player-sized contour blobs.

    Players appear as non-court-colored blobs moving through the court.
    Uses HSV color filtering to exclude court floor and ball.
    Returns list of (cx, cy, area) sorted by area (largest first).
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Court floor: brown/tan (H 10-35, S 40-180, V 80-220)
    court = cv2.inRange(hsv, np.array([10, 40, 80]), np.array([35, 180, 220]))

    # Ball: orange (H 2-32, S > 10)
    ball = cv2.inRange(hsv, np.array([2, 10, 50]), np.array([32, 255, 255]))

    # Bright regions (lights, scoreboard)
    bright = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))

    # Players = NOT (court OR ball OR bright)
    not_player = cv2.bitwise_or(court, ball)
    not_player = cv2.bitwise_or(not_player, bright)
    player_mask = cv2.bitwise_not(not_player)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    player_mask = cv2.morphologyEx(player_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    player_mask = cv2.morphologyEx(player_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(player_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blobs = []
    for c in contours:
        area = cv2.contourArea(c)
        if min_area < area < max_area:
            M = cv2.moments(c)
            if M['m00'] > 0:
                cx = int(M['m10'] / M['m00'])
                cy = int(M['m01'] / M['m00'])
                blobs.append((cx, cy, area))

    blobs.sort(key=lambda b: b[2], reverse=True)
    return blobs


# ---- Pre-shot context recovery ----

def find_shooter_context(anchor_f, anchor_x, anchor_y, rx, ry, total, cap, lookback=40):
    """Rewind from the ball anchor to find the shooter.

    For each frame from anchor_f-lookback to anchor_f:
    - Detect player contours
    - Find the contour nearest to where the ball was at that frame
    - Also check NN ball detections near that frame

    Returns: (shooter_x, shooter_y, shooter_frame, confidence)
    where confidence is based on proximity and consistency.
    """
    best_shooter = None
    best_confidence = 0

    # Collect ball positions in the lookback window from NN detections
    ball_positions = {}
    for df in range(0, lookback + 1):
        fi = anchor_f - df
        if fi >= 0 and not np.isnan(rx[fi]):
            ball_positions[fi] = (rx[fi], ry[fi])

    if not ball_positions:
        return None, 0

    # For frames where we have both ball and player data, find nearest player
    shooter_votes = {}  # (px, py) → count

    for fi, (bx, by) in ball_positions.items():
        if fi < 0 or fi >= total:
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret:
            continue

        blobs = detect_player_contours(frame)

        # Find nearest player to ball
        for cx, cy, area in blobs:
            d = np.sqrt((bx - cx)**2 + (by - cy)**2)
            if d < 80:  # ball within 80px of player
                key = (round(cx / 30) * 30, round(cy / 30) * 30)  # quantize
                shooter_votes[key] = shooter_votes.get(key, 0) + 1

                # Weight by proximity and area
                confidence = (80 - d) / 80.0 * min(area / 500, 2.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_shooter = (cx, cy, fi)

    if best_shooter and best_confidence > 0.1:
        return best_shooter, best_confidence
    return None, 0


# ---- Classification ----

def shooter_zone_to_shot_type(sx, sy, kp_frame, scale):
    """Map shooter position to court zone and infer shot type."""
    # Estimate shooter distance from baskets
    d_l = np.sqrt((sx - BLX)**2 + (sy - BLY)**2)
    d_r = np.sqrt((sx - BRX)**2 + (sy - BRY)**2)
    d_px = min(d_l, d_r)

    if scale and scale > 3:
        d_ft = d_px / scale
    else:
        return '2PT', None

    # Classify by distance
    if d_ft >= 20:
        return '3PT', d_ft
    elif 12 <= d_ft < 20:
        return 'FT', d_ft
    else:
        return '2PT', d_ft


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

    # Phase 1: Find ball anchors (v23 approach)
    log("Phase 1: Finding ball anchors...")
    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i]-BLX)**2 + (ry[i]-BLY)**2),
                     np.sqrt((rx[i]-BRX)**2 + (ry[i]-BRY)**2)) < 180]
    log(f"Anchors: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []

    for ci, (f, cx, cy) in enumerate(cands):
        # Get scale for this frame
        if f < len(bl_x) and not np.isnan(bl_x[f]):
            bsep = np.sqrt((bl_x[f]-br_x[f])**2 + (bl_y[f]-br_y[f])**2)
            scale = bsep / 47.0 if bsep > 200 else None
        else:
            scale = None

        # Track ball (v23)
        track = track_bidir(cap, f, cx, cy, total)

        if len(track) < MIN_PTS:
            log(f"  [{ci+1:2d}] F{f}: REJECTED ({len(track)}f)")
            continue

        # Phase 2: Find shooter context
        log(f"  [{ci+1:2d}] F{f}: finding shooter context...")
        shooter, conf = find_shooter_context(f, cx, cy, rx, ry, total, cap)

        if shooter and conf > 0.1:
            sx, sy, sf = shooter
            stype, d_ft = shooter_zone_to_shot_type(sx, sy, None, scale)

            # Make/miss
            xs = np.array([x for _, x, y in track])
            ys = np.array([y for _, x, y in track])
            dists = np.minimum(np.sqrt((xs-BLX)**2 + (ys-BLY)**2),
                               np.sqrt((xs-BRX)**2 + (ys-BRY)**2))
            min_dist = float(np.min(dists))
            is_make = min_dist < MAKE_R

            shots.append({
                'frame': f,
                'type': stype,
                'result': 'MAKE' if is_make else 'MISS',
                'closest': round(min_dist, 1),
                'shooter': (round(sx), round(sy)),
                'shooter_frame': sf,
                'dist_ft': round(d_ft, 1) if d_ft else None,
                'confidence': round(conf, 2),
                'track': len(track),
            })

            log(f"    → {stype} {'MAKE' if is_make else 'MISS'} "
                f"shooter=({sx:.0f},{sy:.0f}) dist_ft={d_ft:.1f} conf={conf:.2f}")
        else:
            # Fallback: classify by anchor distance
            if scale:
                d_l = np.sqrt((cx-BLX)**2 + (cy-BLY)**2)
                d_r = np.sqrt((cx-BRX)**2 + (cy-BRY)**2)
                d_ft = min(d_l, d_r) / scale
            else:
                d_ft = None

            min_dist_px = min(np.sqrt((cx-BLX)**2 + (cy-BLY)**2),
                              np.sqrt((cx-BRX)**2 + (cy-BRY)**2))

            if d_ft and d_ft >= 20:
                stype = '3PT'
            elif d_ft and 12 <= d_ft < 20:
                stype = 'FT'
            else:
                stype = '2PT'

            is_make = min_dist_px < MAKE_R
            shots.append({
                'frame': f,
                'type': stype,
                'result': 'MAKE' if is_make else 'MISS',
                'closest': round(min_dist_px, 1),
                'shooter': None,
                'dist_ft': round(d_ft, 1) if d_ft else None,
                'confidence': 0,
                'track': len(track),
            })
            log(f"    → {stype} {'MAKE' if is_make else 'MISS'} (fallback, no shooter found)")

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
        src = f"shooter={s['shooter']} conf={s['confidence']}" if s['shooter'] else "NO_SHOOTER"
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist_ft={s.get('dist_ft')} {src}")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v32.csv', index=False)
