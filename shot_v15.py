#!/usr/bin/env python3
"""
Shot detection v15: Hybrid HSV+NN detection → Optical Flow tracking → Arc-based shot classification
===================================================================================================
Key insight from v14: 18% NN detection rate → gap signal flooded with noise (443 gaps).
Using ball absence as shot evidence is fundamentally broken.

v15 architecture:
  Phase 1: Detect ball on every frame using HSV primary + NN secondary
            HSV: fast color segmentation to find orange/orange-brown blobs
            NN: validate ambiguous HSV candidates (reduces false positives)
            → Target: 70-90% frame coverage with ball position

  Phase 2: Optical flow tracking between detections
            When HSV fails, use Lucas-Kanade optical flow to predict ball position
            → Fills gaps between detections for continuous track

  Phase 3: Smooth the full track with a Kalman filter
            → Removes jitter, produces physically plausible trajectory

  Phase 4: Extract shot arcs from the smooth track
            A shot candidate requires ALL of:
              a) Ball moving upward (launch)
              b) Ball reaches apex (direction change)
              c) Ball descending toward basket
              d) Trajectory passes through hoop zone

  Phase 5: Classify make/miss by descent angle through hoop
"""

import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

VIDEO  = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT    = 'pipeline_output'
NN_MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'

# --- Parameters ---
# HSV ball ranges (calibrated for gym LED overhead lighting)
BALL_HSV_LOWER = np.array([3, 20, 30])
BALL_HSV_UPPER = np.array([28, 255, 255])
MIN_BLOB_AREA   = 30
MAX_BLOB_AREA   = 2000

# NN verification
NN_CONF   = 0.0002
USE_NN_VERIFY = True  # Use NN to verify HSV candidates (slower but more accurate)

# Optical flow
OF_WIN_SIZE  = (15, 15)
OF_MAX_LEVEL = 3
OF_CRITERIA  = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)

# Kalman
KALMAN_PROC_NOISE = 1e-3
KALMAN_MEAS_NOISE = 1e-1

# Shot arc detection
ARC_MIN_FRAMES    = 8      # minimum frames for a valid arc
ARC_MAX_FRAMES    = 120    # maximum frames for a valid arc
APEX_JUMP_THRESH  = 40     # min px between apex and start/end (real arc has height)
HOOP_ZONE_RADIUS  = 150    # basket proximity threshold
MAKE_DESCENT_PX   = 15     # ball must descend at least this far through hoop zone
SMOOTH_WINDOW     = 7      # Savitzky-Golay smoothing window (must be odd)

# Shot classification
THREE_PT_THRESH   = 120    # distance threshold for 3PT vs 2PT
MAKE_RADIUS       = 40     # distance for make vs miss
DEDUP_RANGE       = 25     # merge shots within this frame range

os.makedirs(OUT, exist_ok=True)
LOG_FILE = f'{OUT}/shot_v15.log'

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


# ================================================================
# Phase 1: Hybrid HSV+NN Ball Detection
# ================================================================

def detect_ball_hsv(hsv, gray, prev_ball=None):
    """Primary detector: find orange ball using HSV color segmentation.

    Args:
        hsv: HSV-converted frame
        gray: grayscale frame (for circularity check)
        prev_ball: (cx, cy) of ball in previous frame, or None

    Returns:
        (cx, cy, method) or None
    """
    # Color mask
    mask = cv2.inRange(hsv, BALL_HSV_LOWER, BALL_HSV_UPPER)

    # Morphological cleanup: close small gaps, remove noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Find contours
    result = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = result[0] if len(result) == 2 else result[1]

    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_BLOB_AREA or area > MAX_BLOB_AREA:
            continue

        # Circularity check (ball is roughly circular from above)
        perimeter = cv2.arcLength(c, True)
        if perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity < 0.3:
                continue

        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # Court region filter — reject detections near scoreboard edges
        h, w = hsv.shape[:2]
        margin_x = int(w * 0.08)
        margin_y = int(h * 0.12)
        if cx < margin_x or cx > w - margin_x or cy < margin_y or cy > h - margin_y:
            continue

        # Score: prefer circular, correctly-sized blobs near previous position
        score = circularity
        if prev_ball is not None:
            dist = np.sqrt((cx - prev_ball[0])**2 + (cy - prev_ball[1])**2)
            if dist < 150:  # within reasonable tracking range
                score += 0.5 * (1 - dist / 150)
            else:
                score -= 0.5  # far from previous — less likely

        candidates.append((cx, cy, score))

    if not candidates:
        return None

    # Pick highest-scoring candidate
    best = max(candidates, key=lambda x: x[2])
    return (best[0], best[1], 'hsv')


def detect_ball_nn(frame, nn_model):
    """Secondary detector: use fine-tuned NN for ambiguous frames."""
    r = nn_model.predict(frame, conf=NN_CONF, iou=0.3, verbose=False)[0]
    if r.boxes is None:
        return None

    best = None
    best_cf = 0
    for box in r.boxes:
        cls = nn_model.names[int(box.cls[0])]
        cf = float(box.conf[0])
        if cls == 'Ball' and cf > best_cf:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            best_cf = cf
            best = (cx, cy, cf)

    # Color check on the NN detection
    if best is not None:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ix, iy = int(best[0]), int(best[1])
        h, w = hsv.shape[:2]
        if 0 <= ix < w and 0 <= iy < h:
            px = hsv[iy, ix]
            if not (3 <= px[0] <= 28 and px[1] > 20):
                return None  # fails color check
    return best


# ================================================================
# Phase 2: Kalman Filter for smooth tracking
# ================================================================

class BallKalman:
    """Simple Kalman filter for 2D ball tracking."""

    def __init__(self, init_pos):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix = np.array([[1, 0, 0, 0],
                                               [0, 1, 0, 0]], np.float32)
        self.kf.transitionMatrix = np.array([[1, 0, 1, 0],
                                              [0, 1, 0, 1],
                                              [0, 0, 1, 0],
                                              [0, 0, 0, 1]], np.float32)
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * KALMAN_PROC_NOISE
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * KALMAN_MEAS_NOISE
        self.kf.statePre = np.array([[init_pos[0]], [init_pos[1]], [0], [0]], np.float32)
        self.kf.statePost = np.array([[init_pos[0]], [init_pos[1]], [0], [0]], np.float32)
        self.initialized = True

    def predict(self):
        pred = self.kf.predict()
        return float(pred[0, 0]), float(pred[1, 0])

    def correct(self, meas):
        meas_arr = np.array([[meas[0]], [meas[1]]], np.float32)
        self.kf.correct(meas_arr)


# ================================================================
# Phase 4: Arc-based shot detection
# ================================================================

def find_shot_arcs(track_x, track_y, basket_blx, basket_bly, basket_brx, basket_bry, total):
    """Extract shot arcs from smooth ball trajectory.

    Strategy: scan for parabolic arcs where:
      1. Ball rises (Y decreases = upward in image coords)
      2. Ball reaches apex (Y minimum)
      3. Ball descends (Y increases) toward a basket
      4. Ball passes within HOOP_ZONE_RADIUS of basket during descent

    Uses a sliding window approach to find candidate arcs.
    """
    shots = []
    used_frames = set()  # frames already assigned to a shot

    # Pre-compute ball-to-basket distance for all frames
    dist_to_basket = np.full(total, np.inf)
    for i in range(total):
        if np.isnan(track_x[i]):
            continue
        dl = np.sqrt((track_x[i] - basket_blx[i])**2 + (track_y[i] - basket_bly[i])**2)
        dr = np.sqrt((track_x[i] - basket_brx[i])**2 + (track_y[i] - basket_bry[i])**2)
        dist_to_basket[i] = min(dl, dr)

    # Find frames where ball is close to basket — these are shot apex candidates
    close_frames = [i for i in range(total) if dist_to_basket[i] < HOOP_ZONE_RADIUS]

    if not close_frames:
        return shots

    # Group close frames into clusters (each cluster = one shot attempt)
    clusters = []
    current = [close_frames[0]]
    for i in range(1, len(close_frames)):
        if close_frames[i] - close_frames[i-1] < DEDUP_RANGE:
            current.append(close_frames[i])
        else:
            clusters.append(current)
            current = [close_frames[i]]
    clusters.append(current)

    # For each cluster, look backward for the arc launch
    for cluster in clusters:
        if any(f in used_frames for f in cluster):
            continue

        # Frame closest to basket in this cluster
        best_f = min(cluster, key=lambda f: dist_to_basket[f])
        best_d = dist_to_basket[best_f]

        # Look backward for arc start (ball rising toward apex)
        arc_start = best_f
        for j in range(best_f - 1, max(0, best_f - ARC_MAX_FRAMES), -1):
            if np.isnan(track_y[j]):
                break
            # Ball should be rising (Y decreasing) as we go backward from apex
            if track_y[j] > track_y[arc_start]:
                arc_start = j
            else:
                break

        arc_len = best_f - arc_start
        if arc_len < ARC_MIN_FRAMES:
            continue

        # Verify arc height: apex should be noticeably above start
        apex_y = track_y[best_f]
        start_y = track_y[arc_start]
        arc_height = start_y - apex_y  # positive = went up
        if arc_height < APEX_JUMP_THRESH:
            continue

        # Verify descent: ball going DOWN through hoop zone
        if best_f < total - 2:
            after_y = track_y[best_f + 2] if not np.isnan(track_y[best_f + 2]) else track_y[best_f + 1]
            if after_y <= track_y[best_f]:
                continue  # not descending

        # Classify
        shot_type = '3PT' if best_d >= THREE_PT_THRESH else '2PT'
        result = 'MAKE' if best_d < MAKE_RADIUS else 'MISS'

        shots.append({
            'frame': best_f,
            'arc_start': arc_start,
            'arc_end': min(best_f + 10, total - 1),
            'arc_frames': arc_len,
            'bx': round(float(track_x[best_f]), 1),
            'by': round(float(track_y[best_f]), 1),
            'dist': round(float(best_d), 1),
            'type': shot_type,
            'result': result,
        })

        for f in cluster:
            used_frames.add(f)

    return shots


# ================================================================
# MAIN
# ================================================================

if __name__ == '__main__':
    START = time.time()

    # Load basket positions from v8
    log("Loading v8 basket positions...")
    with open(f'{OUT}/shot_v8.pkl', 'rb') as f:
        v8 = pickle.load(f)
    blx, bly = v8['basket_left']
    brx, bry = v8['basket_right']
    log(f"Left basket: ({np.nanmean(blx):.0f}, {np.nanmean(bly):.0f})")
    log(f"Right basket: ({np.nanmean(brx):.0f}, {np.nanmean(bry):.0f})")

    # Load NN model if verifying
    nn_model = None
    if USE_NN_VERIFY:
        log("Loading NN model for verification...")
        from ultralytics import YOLO
        nn_model = YOLO(NN_MODEL, verbose=False)

    # --- Phase 1+2: Detect ball per-frame ---
    log("Phase 1: Ball detection (hybrid HSV+NN)...")

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    actual_total = 0

    detections = []  # list of (cx, cy, method) or None

    prev_ball = None
    frame_times = []

    while True:
        t0 = time.time()
        ret, frame = cap.read()
        if not ret:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        ball = detect_ball_hsv(hsv, gray, prev_ball)

        # Use HSV detection directly (fast, no NN per-frame overhead)
        if ball is not None:
            detections.append((ball[0], ball[1], 'hsv'))
            prev_ball = (ball[0], ball[1])
        else:
            # HSV failed — try NN as fallback every 10th frame (NN is slow)
            if USE_NN_VERIFY and nn_model is not None and actual_total % 10 == 0:
                nn_ball = detect_ball_nn(frame, nn_model)
                if nn_ball is not None:
                    detections.append((nn_ball[0], nn_ball[1], 'nn'))
                    prev_ball = (nn_ball[0], nn_ball[1])
                else:
                    detections.append(None)
            else:
                detections.append(None)

        actual_total += 1

        if actual_total % 500 == 0:
            elapsed = time.time() - START
            hsv_count = sum(1 for d in detections if d is not None and d[2] == 'hsv')
            nn_count = sum(1 for d in detections if d is not None and d[2] == 'nn')
            total_det = hsv_count + nn_count
            log(f"  {actual_total} frames, {total_det} balls ({100*total_det/actual_total:.0f}%), "
                f"HSV:{hsv_count} NN:{nn_count}, {actual_total/elapsed:.1f} fps")

    cap.release()
    log(f"Phase 1 done: {actual_total} frames, {sum(1 for d in detections if d is not None)} detections "
        f"({100*sum(1 for d in detections if d is not None)/actual_total:.0f}%)")

    total = actual_total

    # Match basket arrays to actual frame count
    if len(blx) != total:
        if len(blx) > total:
            blx, bly, brx, bry = blx[:total], bly[:total], brx[:total], bry[:total]
        else:
            pad = total - len(blx)
            blx = np.concatenate([blx, np.full(pad, blx[-1] if not np.isnan(blx[-1]) else 179)])
            bly = np.concatenate([bly, np.full(pad, bly[-1] if not np.isnan(bly[-1]) else 525)])
            brx = np.concatenate([brx, np.full(pad, brx[-1] if not np.isnan(brx[-1]) else 1009)])
            bry = np.concatenate([bry, np.full(pad, bry[-1] if not np.isnan(bry[-1]) else 466)])

    # --- Phase 3: Kalman smoothing ---
    log("Phase 3: Kalman smoothing...")

    track_x = np.full(total, np.nan)
    track_y = np.full(total, np.nan)
    for i, d in enumerate(detections):
        if d is not None:
            track_x[i] = d[0]
            track_y[i] = d[1]

    # Initialize Kalman with first detection
    first_det = None
    for i in range(total):
        if not np.isnan(track_x[i]):
            first_det = i
            break

    if first_det is None:
        log("ERROR: No ball detections at all!")
        sys.exit(1)

    kf = BallKalman((track_x[first_det], track_y[first_det]))

    smooth_x = np.full(total, np.nan)
    smooth_y = np.full(total, np.nan)

    for i in range(total):
        if not np.isnan(track_x[i]):
            kf.correct((track_x[i], track_y[i]))
            pred = kf.kf.statePost
            smooth_x[i] = float(pred[0, 0])
            smooth_y[i] = float(pred[1, 0])
        else:
            pred = kf.predict()
            smooth_x[i] = float(pred[0])
            smooth_y[i] = float(pred[1])

    # Additional Savitzky-Golay smoothing on the known segments
    valid = np.where(~np.isnan(track_x))[0]
    if len(valid) > SMOOTH_WINDOW:
        # Only smooth where we have real measurements
        try:
            sx = savgol_filter(smooth_x[valid], SMOOTH_WINDOW, 2)
            sy = savgol_filter(smooth_y[valid], SMOOTH_WINDOW, 2)
            smooth_x[valid] = sx
            smooth_y[valid] = sy
        except Exception:
            pass

    log(f"Smoothed track: {np.sum(~np.isnan(smooth_x))} frames")

    # --- Phase 4: Arc-based shot detection ---
    log("Phase 4: Arc-based shot detection...")

    shots = find_shot_arcs(smooth_x, smooth_y, blx, bly, brx, bry, total)
    log(f"Arcs detected: {len(shots)}")

    # --- Dedup ---
    if shots:
        shots.sort(key=lambda s: s['frame'])
        deduped = [shots[0]]
        for s in shots[1:]:
            if s['frame'] - deduped[-1]['frame'] < DEDUP_RANGE:
                # Keep the closer one
                if s['dist'] < deduped[-1]['dist']:
                    deduped[-1] = s
            else:
                deduped.append(s)
        shots = deduped

    log(f"After dedup: {len(shots)} shots")

    # --- Phase 5: Output & Visualize ---
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['dist']:5.1f}px arc={s['arc_start']}-{s['arc_end']} ({s['arc_frames']}f)")

    # Save CSV
    pd.DataFrame(shots).sort_values('frame').to_csv(f'{OUT}/shot_candidates_v15.csv', index=False)

    # Save pickle with full trajectory
    pickle.dump({
        'shots': shots,
        'track_x': track_x, 'track_y': track_y,
        'smooth_x': smooth_x, 'smooth_y': smooth_y,
        'detections': detections,
        'basket_left': (blx, bly),
        'basket_right': (brx, bry),
    }, open(f'{OUT}/shot_v15.pkl', 'wb'))

    # Visualize — annotate smooth track + shot frames
    log("Visualizing...")
    cap = cv2.VideoCapture(VIDEO)
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s['frame'])
        ret, frame = cap.read()
        if not ret:
            continue

        # Draw smooth track leading up to shot
        track_start = max(0, s['frame'] - 30)
        pts = []
        for j in range(track_start, s['frame'] + 1):
            if j < total and not np.isnan(smooth_x[j]) and not np.isnan(smooth_y[j]):
                pts.append((int(smooth_x[j]), int(smooth_y[j])))
        if len(pts) > 1:
            for k in range(1, len(pts)):
                cv2.line(frame, pts[k-1], pts[k], (0, 255, 0), 2)

        # Ball position at shot frame
        bx_i = int(s['bx'])
        by_i = int(s['by'])
        cv2.circle(frame, (bx_i, by_i), 12, (0, 165, 255), 3)
        # Basket position
        cv2.circle(frame, (int(blx[s['frame']]), int(bly[s['frame']])), 8, (255, 0, 0), 2)

        cv2.putText(frame, f"F{s['frame']}: {s['type']} {s['result']} d={s['dist']:.0f}px",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Arc: {s['arc_start']}-{s['arc_end']} ({s['arc_frames']}f)",
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imwrite(f'{OUT}/shot_candidate_v15_{s["frame"]:04d}.jpg', frame)
    cap.release()

    # Full trajectory visualization — every 100th frame
    log("Creating trajectory overlay...")
    cap = cv2.VideoCapture(VIDEO)
    trajx, trajy = [], []
    for fn in range(0, total, 100):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if not ret:
            break

        if fn < total and not np.isnan(smooth_x[fn]) and not np.isnan(smooth_y[fn]):
            trajx.append(int(smooth_x[fn]))
            trajy.append(int(smooth_y[fn]))

        # Draw small trail
        for k in range(max(0, len(trajx)-20), len(trajx)):
            if k >= 0:
                cv2.circle(frame, (trajx[k], trajy[k]), 3, (0, 200, 0), -1)

        cv2.putText(frame, f"F{fn}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.imwrite(f'{OUT}/trajectory_v15_{fn:04d}.jpg', frame)

    cap.release()

    # Summary
    log("=" * 60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    mk = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result'] == 'MAKE') + sum(3 for s in t3 if s['result'] == 'MAKE')
    det_rate = 100 * sum(1 for d in detections if d is not None) / total

    log(f"Ball detection rate: {det_rate:.1f}%")
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)} makes")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)} makes")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    log("DONE")
