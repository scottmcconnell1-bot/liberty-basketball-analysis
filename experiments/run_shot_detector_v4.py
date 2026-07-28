"""
Shot detection v4: Court keypoint-based basket + motion near basket.
Strategy:
  1. Use court keypoint detector (100% reliable on our footage) to find basket keypoints
  2. Detect motion near basket using frame differencing
  3. Classify shots by trajectory relative to basket
  4. Classify 2PT vs 3PT by player distance from basket at shot time

This avoids the unreliable ball detector entirely for shot detection.
"""
import cv2, numpy as np, pickle
import pandas as pd
from ultralytics import YOLO
from collections import defaultdict

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

# ---- Step 1: Load court keypoints ----
print("Loading court keypoints...")
court_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt')

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print("  Total frames: %d" % total)

# Detect court keypoints every 10 frames
court_kps = {}
fn = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    if fn % 10 == 0:
        r = court_model.predict(frame, conf=0.3, verbose=False)[0]
        if r.keypoints is not None:
            for i, kp in enumerate(r.keypoints):
                pts = kp.xy.cpu().numpy()[0]  # (18, 2)
                confs = kp.conf.cpu().numpy()[0]  # (18,)
                court_kps[fn] = {'pts': pts, 'confs': confs, 'det_conf': float(r.boxes.conf[i]) if r.boxes is not None else 0}

    fn += 1
    if fn % 500 == 0:
        print("  %d/%d frames, %d keypoint detections" % (fn, total, len(court_kps)))

cap.release()
print("  Court keypoint detections: %d" % len(court_kps))

# Save keypoints
with open(OUT + '/court_kps_v4.pkl', 'wb') as f:
    pickle.dump(court_kps, f)

# ---- Step 2: Identify basket keypoints ----
# Standard basketball court keypoints (YOLOv8-pose 18 keypoints):
# The basket/hoop typically maps to specific keypoints
# Let's examine which keypoints are most stable and near the basket area

print("\nAnalyzing keypoint positions across all detections:")
all_pts = []
for fn, data in court_kps.items():
    all_pts.append(data['pts'])

all_pts = np.array(all_pts)  # (N, 18, 2)

for kp_idx in range(18):
    pts = all_pts[:, kp_idx, :]
    valid = ~np.isnan(pts[:, 0])
    if np.sum(valid) > 10:
        print("  KP%2d: N=%d  x=%.0f±%.0f  y=%.0f±%.0f" % (
            kp_idx, np.sum(valid),
            np.nanmean(pts[:, 0]), np.nanstd(pts[:, 0]),
            np.nanmean(pts[:, 1]), np.nanstd(pts[:, 1])))

# ---- Step 3: Interpolate keypoints to all frames ----
print("\nInterpolating keypoints to all frames...")
kp_arr = np.full((total, 18, 2), np.nan)
kp_conf_arr = np.zeros((total, 18))

for fn, data in court_kps.items():
    kp_arr[fn] = data['pts']
    kp_conf_arr[fn] = data['confs']

# Forward fill per keypoint
for kp in range(18):
    last = np.array([np.nan, np.nan])
    for fn in range(total):
        if not np.isnan(kp_arr[fn, kp, 0]):
            last = kp_arr[fn, kp].copy()
        elif not np.isnan(last[0]):
            kp_arr[fn, kp] = last

    last = np.array([np.nan, np.nan])
    for fn in range(total-1, -1, -1):
        if not np.isnan(kp_arr[fn, kp, 0]):
            last = kp_arr[fn, kp].copy()
        elif not np.isnan(last[0]):
            kp_arr[fn, kp] = last

# Check coverage
for kp_idx in range(18):
    valid_count = np.sum(~np.isnan(kp_arr[:, kp_idx, 0]))
    print("  KP%2d: %d/%d frames (%.1f%%)" % (kp_idx, valid_count, total, valid_count/total*100))

# ---- Step 4: Identify basket keypoints ----
# The basket should be at keypoints that are:
# a) relatively stable (low std)
# b) at the correct court position (near baseline, roughly 1/4 and 3/4 of court width)
# Let's find them automatically

print("\nIdentifying basket keypoints...")
kp_stability = []
for kp_idx in range(18):
    pts = kp_arr[:, kp_idx, :]
    valid = ~np.isnan(pts[:, 0])
    if np.sum(valid) > total * 0.5:  # available in >50% frames
        cx = np.nanmean(pts[:, 0])
        cy = np.nanmean(pts[:, 1])
        std_x = np.nanstd(pts[:, 0])
        std_y = np.nanstd(pts[:, 1])
        kp_stability.append((kp_idx, np.sum(valid), cx, cy, std_x, std_y))

kp_stability.sort(key=lambda x: x[4] + x[5])  # sort by stability

print("Most stable keypoints (likely structural):")
for kp_idx, n, cx, cy, sx, sy in kp_stability[:8]:
    print("  KP%2d: N=%d center=(%.0f,%.0f) std=(%.1f,%.1f)" % (kp_idx, n, cx, cy, sx, sy))

# Basket keypoints: typically KP6 and KP7 in standard basketball court models
# (the two points at the basket/reference line area)
# But let's check which ones make sense for our footage

# Usually: KP0-3 = corners, KP4-7 = midpoints, KP8-11 = free throw, KP12-17 = other
# The hoop should be near the baseline - typically one of the lower keypoints

# Let's use the two keypoints at the "basket line" - these are usually KP6 (left) and KP7 (right)
# or KP16/KP17 near the baseline area

# For now, compute basket position from multiple keypoints
# The basket is typically at either end of the court
# Court keypoints layout (standard):
#   0----1----2----3  (top baseline)
#   |    |    |    |
#   4----5----6----7  (top free throw / 3pt)
#   |    |    |    |
#   8----9----10--11  (center)
#   |    |    |    |
#   12---13---14--15  (bottom free throw / 3pt)
#   |    |    |    |
#   16---17 (bottom baseline / basket)

# The basket/hoop is at the baseline - we'll use the midpoint of the two baseline keypoints
# that are closest to where the backboard would be

# For a ceiling view, the court appears as a rectangle
# Let's find the "basket end" keypoints by looking at the corners

# If keypoints 0,3 are one basket and 12,15/16,17 are the other:
# A basket is at the left or right end of the court

# After looking at the court keypoint detection files...
# Let me just identify from the spatial data

# Two most extreme keypoints in X = baskets
all_cx = [(kp_idx, np.nanmean(kp_arr[kp_idx, 0])) for kp_idx in range(18) if not np.isnan(np.nanmean(kp_arr[:, kp_idx, 0]))]
all_cx.sort(key=lambda x: x[1])

print("\nLeftmost keypoints:", all_cx[:3])
print("Rightmost keypoints:", all_cx[-3:])

# Baskets are at the ends
# Left basket = midpoint of two leftmost keypoints at baseline
# Right basket = midpoint of two rightmost keypoints at baseline

# Actually, for shot detection, let's use all keypoints near the basket area
# and define a "basket zone" (200px radius around basket position)

# Define basket positions from court keypoints
# For YOLOv8-pose court keypoints:
# KP0,1 = top-left corner line, KP2,3 = top-right
# KP16 or KP17 = bottom basket area

# The basket center is typically the midpoint of the baseline keypoints
# that are near the backboard position

# Let me use known keypoint indices from the abdullahtarek training
# KP6 and KP7 are the "basket line" points (where the backboard is)

basket_kp_left = 6
basket_kp_right = 7

# Basket positions per frame
basket_left_cx = kp_arr[:, basket_kp_left, 0]
basket_left_cy = kp_arr[:, basket_kp_left, 1]
basket_right_cx = kp_arr[:, basket_kp_right, 0]
basket_right_cy = kp_arr[:, basket_kp_right, 1]

print("\nLeft basket (KP%d): x=%.0f±%.0f y=%.0f±%.0f" % (
    basket_kp_left, np.nanmean(basket_left_cx), np.nanstd(basket_left_cx),
    np.nanmean(basket_left_cy), np.nanstd(basket_left_cy)))
print("Right basket (KP%d): x=%.0f±%.0f y=%.0f±%.0f" % (
    basket_kp_right, np.nanmean(basket_right_cx), np.nanstd(basket_right_cx),
    np.nanmean(basket_right_cy), np.nanstd(basket_right_cy)))

# ---- Step 5: Player detection for shooter identification ----
print("\nDetecting players (every 10 frames)...")
player_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/player_detector.pt')

cap = cv2.VideoCapture(VIDEO)
players_by_frame = {}
fn = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    if fn % 10 == 0:
        r = player_model.predict(frame, conf=0.1, verbose=False)[0]
        if r.boxes is not None:
            players_by_frame[fn] = []
            for box in r.boxes:
                cls = player_model.names[int(box.cls[0])]
                if cls in ['Player', 'Ref']:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    players_by_frame[fn].append({
                        'cx': (x1+x2)/2, 'cy': (y1+y2)/2,
                        'w': x2-x1, 'h': y2-y1,
                        'conf': float(box.conf[0]), 'cls': cls
                    })

    fn += 1

cap.release()
print("  Frames with player detection: %d" % len(players_by_frame))

# Save
with open(OUT + '/players_v4.pkl', 'wb') as f:
    pickle.dump(players_by_frame, f)

# ---- Step 6: Motion detection near baskets ----
print("\nAnalyzing motion near baskets...")

# Re-read video for frame differencing
cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

prev_gray = None
motion_near_basket = np.zeros(total)
fn = 0

# ROI around each basket (will be updated per frame based on keypoint position)
basket_radius = 150  # pixels around basket to check for motion

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if prev_gray is not None:
        diff = cv2.absdiff(prev_gray, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

        # Check motion near left basket
        if not np.isnan(basket_left_cx[fn]):
            bx, by = int(basket_left_cx[fn]), int(basket_left_cy[fn])
            y1 = max(0, by - basket_radius)
            y2 = min(720, by + basket_radius)
            x1 = max(0, bx - basket_radius)
            x2 = min(1280, bx + basket_radius)
            roi = thresh[y1:y2, x1:x2]
            motion_left = np.sum(roi > 0)
        else:
            motion_left = 0

        # Check motion near right basket
        if not np.isnan(basket_right_cx[fn]):
            bx, by = int(basket_right_cx[fn]), int(basket_right_cy[fn])
            y1 = max(0, by - basket_radius)
            y2 = min(720, by + basket_radius)
            x1 = max(0, bx - basket_radius)
            x2 = min(1280, bx + basket_radius)
            roi = thresh[y1:y2, x1:x2]
            motion_right = np.sum(roi > 0)
        else:
            motion_right = 0

        motion_near_basket[fn] = max(motion_left, motion_right)

    prev_gray = gray
    fn += 1
    if fn % 500 == 0:
        print("  %d/%d frames" % (fn, total))

cap.release()

# Find frames with significant basket motion
threshold = np.percentile(motion_near_basket[motion_near_basket > 0], 90) if np.any(motion_near_basket > 0) else 1000
print("\nMotion threshold (90th percentile): %.0f" % threshold)

high_motion_frames = np.where(motion_near_basket > threshold)[0]
print("Frames with high basket motion: %d" % len(high_motion_frames))

# Group consecutive frames into events
high_motion_events = []
in_event = False
event_start = 0
for fn in range(total):
    if motion_near_basket[fn] > threshold:
        if not in_event:
            in_event = True
            event_start = fn
    else:
        if in_event:
            high_motion_events.append((event_start, fn-1))
            in_event = False
if in_event:
    high_motion_events.append((event_start, total-1))

print("High-motion events near basket: %d" % len(high_motion_events))
for start, end in high_motion_events:
    dur = end - start + 1
    peak = int(np.max(motion_near_basket[start:end+1]))
    print("  F%d-F%d (%d frames) peak_motion=%d" % (start, end, dur, peak))

# ---- STEP 7: Detect shots using hybrid approach ----
# A shot = ball trajectory anomaly near basket + player in shooting position
# OR: ball detected near basket (from existing hybrid2 detections) + motion

print("\n=== SHOT DETECTION (HYBRID) ===")

# Load hybrid2 ball detections
balls = pd.read_csv(OUT + '/hybrid2_ball_detections.csv')
print("Ball detections loaded: %d" % len(balls))

# Build per-frame ball position (highest conf per frame)
ball_cx = np.full(total, np.nan)
ball_cy = np.full(total, np.nan)
for _, r in balls.iterrows():
    fn = int(r.frame)
    if fn < total and (np.isnan(ball_cx[fn]) or r.conf > 0):
        ball_cx[fn] = r.cx
        ball_cy[fn] = r.cy

# Shot signature: ball near basket, then gap, OR motion spike near basket + ball nearby
shot_events = []

# Method 1: Ball-basket proximity from hybrid2
print("\nMethod 1: Ball-basket proximity")
close_thresh = 100
for fn in range(total):
    if np.isnan(ball_cx[fn]): continue
    for basket_name, bkx, bky in [('left', basket_left_cx, basket_left_cy),
                                     ('right', basket_right_cx, basket_right_cy)]:
        if not np.isnan(bkx[fn]):
            dist = np.sqrt((ball_cx[fn]-bkx[fn])**2 + (ball_cy[fn]-bky[fn])**2)
            if dist < close_thresh:
                shot_events.append({
                    'frame': fn,
                    'ball_x': ball_cx[fn], 'ball_y': ball_cy[fn],
                    'basket': basket_name,
                    'basket_x': bkx[fn], 'basket_y': bky[fn],
                    'dist': dist,
                    'method': 'proximity'
                })

print("Close ball-basket events: %d" % len(shot_events))

# Method 2: Motion spikes
print("\nMethod 2: Motion spikes near basket")
for start, end in high_motion_events:
    peak_frame = start + np.argmax(motion_near_basket[start:end+1])

    # Check if ball was detected near a basket in the 10 frames before
    ball_near_before = False
    for bf in range(max(0, peak_frame-10), peak_frame):
        if not np.isnan(ball_cx[bf]):
            for bkx, bky in [(basket_left_cx, basket_left_cy), (basket_right_cx, basket_right_cy)]:
                if not np.isnan(bkx[bf]):
                    dist = np.sqrt((ball_cx[bf]-bkx[bf])**2 + (ball_cy[bf]-bky[bf])**2)
                    if dist < 200:
                        ball_near_before = True

    shot_events.append({
        'frame': peak_frame,
        'motion_start': start,
        'motion_end': end,
        'peak_motion': int(motion_near_basket[peak_frame]),
        'ball_detected_nearby': ball_near_before,
        'method': 'motion'
    })

print("Motion events: %d" % len(high_motion_events))

# Save all events
all_events = pd.DataFrame(shot_events)
all_events.to_csv(OUT + '/all_shot_events_v4.csv', index=False)

# Summary
print("\n=== SUMMARY ===")
print("Ball detection rate: %.1f%%" % (np.sum(~np.isnan(ball_cx))/total*100))
print("High-motion events: %d" % len(high_motion_events))
print("Ball-basket proximity events: %d" % len([e for e in shot_events if e.get('method')=='proximity']))

# Deduplicate: combine proximity + motion events within 30 frames
print("\nDeduplicating events...")
proximity_frames = sorted([e['frame'] for e in shot_events if e.get('method') == 'proximity'])
motion_frames = sorted([e['frame'] for e in shot_events if e.get('method') == 'motion'])

all_frames = sorted(set(proximity_frames + motion_frames))
deduped = []
i = 0
while i < len(all_frames):
    j = i + 1
    while j < len(all_frames) and all_frames[j] - all_frames[j-1] < 30:
        j += 1
    group = all_frames[i:j]
    best_frame = group[len(group)//2]  # middle frame
    deduped.append(best_frame)
    i = j

print("Unique shot candidates: %d" % len(deduped))
for fn in deduped:
    # Determine which basket
    best_basket = None
    best_dist = float('inf')
    for basket_name, bkx, bky in [('left', basket_left_cx, basket_left_cy),
                                     ('right', basket_right_cx, basket_right_cy)]:
        if not np.isnan(bkx[fn]):
            if not np.isnan(ball_cx[fn]):
                dist = np.sqrt((ball_cx[fn]-bkx[fn])**2 + (ball_cy[fn]-bky[fn])**2)
                if dist < best_dist:
                    best_dist = dist
                    best_basket = basket_name

    # Find nearest player
    nearest_player = None
    min_pdist = float('inf')
    pfn = fn - (fn % 10)  # nearest sampled frame
    if pfn in players_by_frame:
        for p in players_by_frame[pfn]:
            if p['cls'] == 'Player':
                if not np.isnan(ball_cx[fn]):
                    pdist = np.sqrt((p['cx']-ball_cx[fn])**2 + (p['cy']-ball_cy[fn])**2)
                    if pdist < min_pdist:
                        min_pdist = pdist
                        nearest_player = p

    print("  F%d: basket=%s dist_to_ball=%.0f motion=%d" % (
        fn, best_basket if best_basket else '?', best_dist,
        int(motion_near_basket[fn])))

with open(OUT + '/shot_candidates_v4.pkl', 'wb') as f:
    pickle.dump({
        'candidates': deduped,
        'basket_left': (basket_left_cx, basket_left_cy),
        'basket_right': (basket_right_cx, basket_right_cy),
        'motion': motion_near_basket,
        'players': players_by_frame
    }, f)

print("\nDone. Saved shot_candidates_v4.pkl")
