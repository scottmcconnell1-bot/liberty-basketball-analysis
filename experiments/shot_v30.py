#!/usr/bin/env python3
"""
Shot detection v30: Release-based shot detection
==================================================
New architecture: detect the RELEASE, not the landing.

Pipeline:
  1. Player blob detection (contour-based, no NN needed)
  2. Ball possession: ball near player blob
  3. Release event: ball separates from player, moves upward
  4. Track ball from release to basket (OF)
  5. Classify by release location (court coords from keypoints)

Key insight: FTs have unique signatures:
  - Stationary player at FT line
  - Vertical release
  - Isolated possession (no nearby players)
  - Ball rises then falls toward basket
"""
import os, time, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
FWD_WIN, BWD_WIN = 25, 20  # wider windows for full trajectory
MIN_PTS, MAX_JUMP = 10, 80
MAKE_R = 55


def log(msg):
    print(msg, flush=True)


# ---- Player blob detection ----

def detect_player_blobs(frame, min_area=200, max_area=5000):
    """Detect player blobs using contour detection on the court area.

    Players are typically the largest moving blobs on the court.
    Uses background subtraction + contour detection.
    Returns list of (cx, cy, area, bbox) tuples.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Detect skin-colored regions (players' faces/arms/hands)
    # HSV skin range
    skin_mask = cv2.inRange(hsv, np.array([0, 20, 70]), np.array([30, 180, 255]))
    skin_mask2 = cv2.inRange(hsv, np.array([150, 20, 70]), np.array([180, 180, 255]))
    skin_mask = cv2.bitwise_or(skin_mask, skin_mask2)

    # Also detect non-court colors (players wear colored jerseys)
    # Court is typically brown/tan — exclude it
    court_mask = cv2.inRange(hsv, np.array([10, 40, 80]), np.array([35, 180, 220]))
    non_court = cv2.bitwise_not(court_mask)

    # Combine: skin OR non-court (but not too bright — exclude scoreboard)
    bright_mask = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 30, 255]))
    combined = cv2.bitwise_or(skin_mask, non_court)
    combined = cv2.bitwise_and(combined, cv2.bitwise_not(bright_mask))

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blobs = []
    for c in contours:
        area = cv2.contourArea(c)
        if min_area < area < max_area:
            M = cv2.moments(c)
            if M['m00'] > 0:
                cx = int(M['m10'] / M['m00'])
                cy = int(M['m01'] / M['m00'])
                x, y, w, h = cv2.boundingRect(c)
                blobs.append((cx, cy, area, (x, y, w, h)))

    # Sort by area (largest first)
    blobs.sort(key=lambda b: b[2], reverse=True)
    return blobs[:10]  # top 10 blobs


def find_nearest_player(ball_x, ball_y, blobs, max_dist=60):
    """Find the nearest player blob to the ball position."""
    best = None
    best_dist = max_dist
    for cx, cy, area, bbox in blobs:
        d = np.sqrt((ball_x - cx)**2 + (ball_y - cy)**2)
        if d < best_dist:
            best_dist = d
            best = (cx, cy, area, bbox)
    return best, best_dist


# ---- Ball tracking (appearance-locked OF) ----

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
    """Bidirectional OF tracking with appearance lock."""
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


# ---- Release detection ----

def detect_release_events(rx, ry, total, cap):
    """Detect shot release events by analyzing ball-player interactions.

    A release event is:
    1. Ball is near a player (possession)
    2. Ball suddenly separates and moves upward
    3. Ball then approaches a basket

    Returns list of (release_frame, release_x, release_y, player_x, player_y) tuples.
    """
    releases = []

    # For each NN ball detection, look backward to find possession
    nn_frames = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])]

    for i, (f, bx, by) in enumerate(nn_frames):
        # Look backward up to 30 frames for possession
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            continue

        blobs = detect_player_blobs(img)
        nearest, dist = find_nearest_player(bx, by, blobs)

        if nearest is not None:
            # Ball is near a player — check if this is a release
            # Look at previous frames: was the ball stationary (in hands)?
            # Look at next frames: does the ball move upward then toward basket?

            # Check backward: ball position in previous NN detections
            prev_ball = None
            for j in range(i - 1, max(i - 10, 0), -1):
                pf, px, py = nn_frames[j]
                if abs(pf - f) <= 15:
                    prev_ball = (px, py)
                    break

            # Check forward: ball position in next NN detections
            next_ball = None
            for j in range(i + 1, min(i + 10, len(nn_frames))):
                nf, nx, ny = nn_frames[j]
                if abs(nf - f) <= 15:
                    next_ball = (nx, ny)
                    break

            if prev_ball and next_ball:
                # Was ball stationary before? (possession)
                prev_dist = np.sqrt((bx - prev_ball[0])**2 + (by - prev_ball[1])**2)
                # Is ball moving toward basket after?
                d_l_prev = np.sqrt((prev_ball[0] - BLX)**2 + (prev_ball[1] - BLY)**2)
                d_l_next = np.sqrt((next_ball[0] - BLX)**2 + (next_ball[1] - BLY)**2)
                d_r_prev = np.sqrt((prev_ball[0] - BRX)**2 + (prev_ball[1] - BRY)**2)
                d_r_next = np.sqrt((next_ball[0] - BRX)**2 + (next_ball[1] - BRY)**2)

                approaching = min(d_l_next, d_r_next) < min(d_l_prev, d_r_prev)

                # Release signature: ball was close to player, now approaching basket
                if dist < 50 and approaching and prev_dist < 40:
                    releases.append((f, bx, by, nearest[0], nearest[1]))

    return releases


# ---- Classification ----

def classify_release(release_x, release_y, player_x, player_y, kp_frame, bl_x, bl_y, br_x, br_y, f):
    """Classify shot by release location."""
    # Distance from release to nearest basket
    d_l = np.sqrt((release_x - BLX)**2 + (release_y - BLY)**2)
    d_r = np.sqrt((release_x - BRX)**2 + (release_y - BRY)**2)
    basket_dist_px = min(d_l, d_r)

    # Get scale
    if f < len(bl_x) and not np.isnan(bl_x[f]):
        basket_sep = np.sqrt((bl_x[f] - br_x[f])**2 + (bl_y[f] - br_y[f])**2)
        if basket_sep > 200:
            scale = basket_sep / 47.0  # px/ft
            basket_dist_ft = basket_dist_px / scale
        else:
            basket_dist_ft = None
    else:
        basket_dist_ft = None

    # Player movement (FT = stationary)
    player_stationary = True  # TODO: track player across frames

    # Classify
    if basket_dist_ft is not None:
        if basket_dist_ft >= 20:
            stype = '3PT'
        elif 12 <= basket_dist_ft < 20 and player_stationary:
            stype = 'FT'
        else:
            stype = '2PT'
    else:
        if basket_dist_px >= 350:
            stype = '3PT'
        elif basket_dist_px >= 220:
            stype = 'FT'
        else:
            stype = '2PT'

    return {
        'type': stype,
        'basket_dist_px': round(basket_dist_px, 1),
        'basket_dist_ft': round(basket_dist_ft, 1) if basket_dist_ft else None,
        'release': (round(release_x, 1), round(release_y, 1)),
        'player': (round(player_x, 1), round(player_y, 1)),
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

    # Phase 1: Detect release events
    log("Phase 1: Detecting release events...")
    cap = cv2.VideoCapture(VIDEO)
    releases = detect_release_events(rx, ry, total, cap)
    log(f"Found {len(releases)} release events")

    for r in releases:
        log(f"  Release at F{r[0]}: ball=({r[1]:.0f},{r[2]:.0f}) player=({r[3]:.0f},{r[4]:.0f})")

    # Phase 2: For each release, track ball to basket and classify
    log("\nPhase 2: Tracking and classifying...")
    shots = []

    for rel_f, rel_x, rel_y, player_x, player_y in releases:
        kp_frame = v8['kp_arr'][rel_f] if rel_f < v8['kp_arr'].shape[0] else None

        # Track from release
        track = track_bidir(cap, rel_f, rel_x, rel_y, total)

        if len(track) >= MIN_PTS:
            # Classify
            cls = classify_release(rel_x, rel_y, player_x, player_y,
                                   kp_frame, bl_x, bl_y, br_x, br_y, rel_f)

            # Make/miss
            xs = np.array([x for f, x, y in track])
            ys = np.array([y for f, x, y in track])
            dists = np.minimum(np.sqrt((xs - BLX)**2 + (ys - BLY)**2),
                               np.sqrt((xs - BRX)**2 + (ys - BRY)**2))
            min_dist = float(np.min(dists))
            is_make = min_dist < MAKE_R

            shots.append({
                'frame': rel_f,
                'type': cls['type'],
                'result': 'MAKE' if is_make else 'MISS',
                'closest_px': round(min_dist, 1),
                'basket_dist_ft': cls['basket_dist_ft'],
                'track': len(track),
            })

            log(f"  F{rel_f}: {cls['type']} {'MAKE' if is_make else 'MISS'} "
                f"dist_ft={cls['basket_dist_ft']} track={len(track)}f")

    cap.release()

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
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"dist_ft={s['basket_dist_ft']} track={s['track']}f")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest_px'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v30.csv', index=False)
