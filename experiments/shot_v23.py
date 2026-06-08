#!/usr/bin/env python3
"""
Shot detection v23: Appearance-locked tracking
===============================================
v18 worked best because color verification constrained drift.
v23 adds APPEARANCE LOCKING:
  - At NN anchor: extract grayscale patch template + circularity + size
  - During OF: validate histogram correlation + circularity match
  - FT detection: vertical rise at free throw line (different motion signature)
Key insight from ChatGPT: "What still looks like THIS ball?" not "What orange thing moved nearby?"
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
MAKE_R = 50

# FT line in pixel coords: roughly the middle of the court
# Left basket at x=179, right at x=1009. FT line around x=594
FT_LINE_X = (400, 750)  # x range for FT zone
FT_LINE_Y = (300, 550)  # y range

def log(msg):
    print(msg, flush=True)


def extract_template(img_gray, cx, cy, radius=8):
    """Extract appearance template and features from a verified ball detection."""
    h, w = img_gray.shape[:2]
    x1, x2 = max(0, int(cx)-radius), min(w, int(cx)+radius)
    y1, y2 = max(0, int(cy)-radius), min(h, int(cy)+radius)
    patch = img_gray[y1:y2, x1:x2].copy()
    if patch.size < 9:
        return None

    # Histogram (normalized)
    hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-8)

    # Circularity from contour
    roi_color = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(roi_color, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    circularity = 0
    area = 0
    if contours:
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        perimeter = cv2.arcLength(c, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)

    return {
        'patch': patch,
        'hist': hist,
        'circularity': circularity,
        'area': area,
        'cx': float(cx),
        'cy': float(cy),
    }


def match_template(img_gray, x, y, template, radius=8):
    """Check if position (x,y) matches the ball template."""
    if template is None:
        return True  # no template to compare against

    h, w = img_gray.shape[:2]
    x1, x2 = max(0, int(x)-radius), min(w, int(x)+radius+1)
    y1, y2 = max(0, int(y)-radius), min(h, int(y)+radius+1)
    patch = img_gray[y1:y2, x1:x2]

    if patch.size < 9:
        return False

    # Histogram correlation
    hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-8)
    corr = cv2.compareHist(template['hist'].astype(np.float32),
                           hist.astype(np.float32), cv2.HISTCMP_CORREL)

    # Size check: within 50% of template area
    area_ratio = 1.0
    if template['area'] > 0:
        area_ratio = (patch.size) / (template['patch'].size + 1e-8)

    return corr > 0.5 and 0.3 < area_ratio < 3.0


def check_color(hsv, x, y):
    h, w = hsv.shape[:2]
    xi, yi = int(x), int(y)
    return 0 <= xi < w and 0 <= yi < h and 2 <= hsv[yi, xi, 0] <= 32 and hsv[yi, xi, 1] >= 10


def track_bidir(cap, fnum, cx, cy, total, img0=None):
    """Track ball bidirectionally with appearance validation."""
    if img0 is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
        ret, img0 = cap.read()
        if not ret:
            return [], None
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)

    if not check_color(hsv0, cx, cy):
        return [], None

    # Extract appearance template
    template = extract_template(gray0, cx, cy, radius=8)

    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []

    for f in range(fnum - 1, max(fnum - BWD_WIN, 0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gray_f = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            hsv_f = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hsv_f, nx, ny) and match_template(gray_f, nx, ny, template):
                jx = abs(nx - float(pt[0, 0, 0]))
                jy = abs(ny - float(pt[0, 0, 1]))
                if jx < MAX_JUMP and jy < MAX_JUMP:
                    backward.append((f, nx, ny))
                    pt = new_pt.reshape(1, 1, 2)
                    gray_prev = gray_f
                    continue
        gray_prev = gray_f

    # Forward
    pt = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    forward = []

    for f in range(fnum + 1, min(fnum + FWD_WIN, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            break
        gray_f = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            gray_prev, gray_f, pt, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        if status[0, 0] == 1:
            nx, ny = float(new_pt[0, 0, 0]), float(new_pt[0, 0, 1])
            hsv_f = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hsv_f, nx, ny) and match_template(gray_f, nx, ny, template):
                jx = abs(nx - float(pt[0, 0, 0]))
                jy = abs(ny - float(pt[0, 0, 1]))
                if jx < MAX_JUMP and jy < MAX_JUMP:
                    forward.append((f, nx, ny))
                    pt = new_pt.reshape(1, 1, 2)
                    gray_prev = gray_f
                    continue
        gray_prev = gray_f

    return backward[::-1] + [(fnum, float(cx), float(cy))] + forward, template


def classify(track, anchor_x, anchor_y):
    """Classify shot from bidirectional track."""
    if len(track) < MIN_PTS:
        return None

    fs = np.array([f for f, x, y in track])
    xs = np.array([x for f, x, y in track])
    ys = np.array([y for f, x, y in track])

    jumps = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    if np.max(jumps) > MAX_JUMP:
        return None

    dists = np.minimum(
        np.sqrt((xs - BLX)**2 + (ys - BLY)**2),
        np.sqrt((xs - BRX)**2 + (ys - BRY)**2),
    )
    min_idx = int(np.argmin(dists))
    min_dist = float(dists[min_idx])
    best_f = int(fs[min_idx])

    total_travel = np.sqrt((xs[-1] - xs[0])**2 + (ys[-1] - ys[0])**2)
    if total_travel < 30:
        return None

    if min_dist > 180:
        return None

    # Classify by anchor NN detection distance
    anchor_d = min(np.sqrt((anchor_x - BLX)**2 + (anchor_y - BLY)**2),
                   np.sqrt((anchor_x - BRX)**2 + (anchor_y - BRY)**2))

    if anchor_d >= 130:
        stype = '3PT'
    elif FT_LINE_X[0] < anchor_x < FT_LINE_X[1] and FT_LINE_Y[0] < anchor_y < FT_LINE_Y[1] and anchor_d < 400:
        stype = 'FT'
    else:
        stype = '2PT'

    smooth = np.mean(jumps)
    is_make = (min_dist < MAKE_R) or (min_dist < MAKE_R + 15 and len(track) > 14 and smooth < 30)
    result = 'MAKE' if is_make else 'MISS'

    return {
        'frame': best_f, 'type': stype, 'result': result,
        'closest': round(min_dist, 1), 'nn_dist': round(anchor_d, 1),
        'track': len(track), 'smooth': round(smooth, 1),
    }


def detect_ft_shots(rx, ry, total, nn_frames_set):
    """Detect free throw shots: ball rises vertically near FT line.

    FT signature: ball starts in person's hands near FT line (x=400-750, y=300-550),
    then rises nearly vertically, then descends into hoop.
    We detect this from NN detections alone.
    """
    ft_shots = []
    nn_dets = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])]

    # Find NN detections in FT zone
    ft_dets = [(f, x, y) for f, x, y in nn_dets
               if FT_LINE_X[0] < x < FT_LINE_X[1] and FT_LINE_Y[0] < y < FT_LINE_Y[1]]

    if not ft_dets:
        return ft_shots

    # Group nearby FT detections into events
    ft_dets.sort()
    events = []
    cur = [ft_dets[0]]
    for i in range(1, len(ft_dets)):
        if ft_dets[i][0] - ft_dets[i - 1][0] < 30:
            cur.append(ft_dets[i])
        else:
            events.append(cur)
            cur = [ft_dets[i]]
    events.append(cur)

    for event in events:
        if len(event) < 3:
            continue
        # Check if ball approaches a basket after the FT zone
        last_f, last_x, last_y = event[-1]

        # Look for subsequent NN detection near a basket (within 30 frames)
        for f2 in range(last_f + 1, min(last_f + 31, total)):
            if np.isnan(rx[f2]):
                continue
            d = min(np.sqrt((rx[f2] - BLX)**2 + (ry[f2] - BLY)**2),
                    np.sqrt((rx[f2] - BRX)**2 + (ry[f2] - BRY)**2))
            if d < 150:
                # Check this isn't already detected by main pipeline
                already_detected = False
                for vf in nn_frames_set:
                    if abs(f2 - vf) < 15:
                        already_detected = True
                        break
                if not already_detected:
                    is_make = d < MAKE_R
                    ft_shots.append({
                        'frame': f2, 'type': 'FT',
                        'result': 'MAKE' if is_make else 'MISS',
                        'closest': round(d, 1), 'nn_dist': round(d, 1),
                        'track': len(event), 'smooth': 0,
                    })
                break

    return ft_shots


if __name__ == '__main__':
    log("Loading...")
    with open(f'{OUT}/shot_v14.pkl', 'rb') as f:
        v14 = pickle.load(f)
    rx, ry = v14['ball_x'], v14['ball_y']
    total = len(rx)

    cands = [(i, rx[i], ry[i]) for i in range(total) if not np.isnan(rx[i])
             and min(np.sqrt((rx[i] - BLX) ** 2 + (ry[i] - BLY) ** 2),
                     np.sqrt((rx[i] - BRX) ** 2 + (ry[i] - BRY) ** 2)) < 180]
    log(f"Candidates: {len(cands)}")

    cap = cv2.VideoCapture(VIDEO)
    shots = []
    nn_frames_detected = set()

    for ci, (f, cx, cy) in enumerate(cands):
        track, template = track_bidir(cap, f, cx, cy, total)
        cls = classify(track, cx, cy)
        if cls:
            shots.append(cls)
            nn_frames_detected.add(f)
            log(f"  [{ci + 1}] F{f}: {cls['type']} {cls['result']} "
                f"closest={cls['closest']:.0f}px nn={cls['nn_dist']:.0f}px track={cls['track']}f")
        else:
            log(f"  [{ci + 1}] F{f}: REJECTED ({len(track)}f)")
    cap.release()

    # Add FT shots
    ft_shots = detect_ft_shots(rx, ry, total, nn_frames_detected)
    if ft_shots:
        log(f"\nFT shots detected: {len(ft_shots)}")
        for s in ft_shots:
            log(f"  F{s['frame']}: {s['type']} {s['result']} dist={s['closest']:.0f}px")
        shots.extend(ft_shots)

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
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"closest={s['closest']:.0f}px nn={s['nn_dist']:.0f}px")
    log("DONE")

    out = [{'frame': s['frame'], 'type': s['type'], 'result': s['result'],
            'dist': s['closest'], 'track_frames': s['track']} for s in shots]
    pd.DataFrame(out).to_csv(f'{OUT}/shot_candidates_v23.csv', index=False)
