"""
Full Q1 analysis pipeline using abdullahtarek pretrained models.
Optimized for CPU: batched inference, court KP every Nth frame with interpolation.

Pipeline:
1. Court keypoint detection (every 10th frame) → homography → rim position
2. Ball detection (every 2nd frame) → track
3. Player detection (every 5th frame) → shooter ID
4. Shot detection via ball trajectory toward rim
5. Classify: make/miss, 2PT/3PT, shooter
"""
import cv2
import numpy as np
import pandas as pd
import os
import sys
import time
from ultralytics import YOLO
from collections import defaultdict

# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)

# === CONFIG ===
VIDEO_PATH = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
BALL_STRIDE = 2
COURT_STRIDE = 10
PLAYER_STRIDE = 5
BALL_CONF = 0.2
COURT_CONF = 0.1
PLAYER_CONF = 0.3

TACTICAL_W = 300
TACTICAL_H = 161
COURT_W_METERS = 28
COURT_H_METERS = 15

# 18 tactical court keypoints
TACTICAL_KEYPOINTS = np.array([
    (0, 0), (0, 35), (0, 60), (0, 78), (0, 104), (0, 161),
    (150, 161), (150, 0),
    (85, 60), (85, 78),
    (300, 161), (300, 104), (300, 78), (300, 60), (300, 35), (300, 0),
    (215, 60), (215, 78)
], dtype=np.float32)

# Basket: 4ft from baseline, centered
BASKET_Y = 161.0 - (1.2192 / (COURT_H_METERS / TACTICAL_H))
BASKET_X = 150.0
THREE_PT_RADIUS_PX = 6.02 / (COURT_H_METERS / TACTICAL_H)

os.makedirs('pipeline_output', exist_ok=True)
start_time = time.time()

def log(msg):
    elapsed = time.time() - start_time
    print(f"[{elapsed:.0f}s] {msg}", flush=True)

log("Loading models...")
ball_model = YOLO('models/ball_detector.pt')
court_model = YOLO('models/court_keypoint_detector.pt')
player_model = YOLO('models/player_detector.pt')
log("Models loaded.")

# === READ VIDEO ===
log("Reading video...")
cap = cv2.VideoCapture(VIDEO_PATH)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Read all frames into memory (2701 frames * 1280*720*3 = ~7GB — too much)
# Instead, read on-demand
log(f"Video: {W}x{H}, {total_frames} frames @ {fps}fps")

ball_frames = list(range(0, total_frames, BALL_STRIDE))
court_frames = list(range(0, total_frames, COURT_STRIDE))
player_frames = list(range(0, total_frames, PLAYER_STRIDE))
all_frames = sorted(set(ball_frames + court_frames + player_frames))
log(f"Ball frames: {len(ball_frames)}, Court frames: {len(court_frames)}, Player frames: {len(player_frames)}")

# === STEP 1: COURT KEYPOINT DETECTION (batched) ===
log("Step 1: Court keypoint detection (batched)...")
court_data = {}

for i in range(0, len(court_frames), 20):
    batch_fns = court_frames[i:i+20]
    batch_images = []
    valid_fns = []
    for fn in batch_fns:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if ret:
            batch_images.append(frame)
            valid_fns.append(fn)
    
    if not batch_images:
        continue
    
    results = court_model.predict(batch_images, conf=COURT_CONF, verbose=False)
    
    for fn, r in zip(valid_fns, results):
        if r.keypoints is None or r.keypoints.xy.shape[0] == 0:
            continue
        
        kps_xy = r.keypoints.xy[0].cpu().numpy()
        kps_conf = r.keypoints.conf[0].cpu().numpy()
        
        valid_mask = (kps_xy[:, 0] > 1) & (kps_xy[:, 1] > 1) & (kps_conf > 0.3)
        valid_indices = np.where(valid_mask)[0]
        
        if len(valid_indices) < 4:
            continue
        
        src_pts = kps_xy[valid_indices]
        dst_pts = TACTICAL_KEYPOINTS[valid_indices]
        
        try:
            H_matrix, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if H_matrix is None:
                continue
            
            basket_tactical = np.array([[BASKET_X, BASKET_Y]], dtype=np.float32).reshape(-1, 1, 2)
            basket_px = cv2.perspectiveTransform(basket_tactical, H_matrix).reshape(2)
            
            court_data[fn] = {
                'H': H_matrix,
                'basket_px': basket_px,
                'n_kps': len(valid_indices),
            }
        except Exception:
            continue
    
    if i % 100 == 0:
        log(f"  Court: batch {i}, {len(court_data)} frames with homography")

log(f"Court homography: {len(court_data)}/{len(court_frames)} frames")

# Interpolate homography for frames between court detections
log("Interpolating homography for missing frames...")
all_H = {}
sorted_court_fns = sorted(court_data.keys())

for fn in all_frames:
    # Find nearest court detections before and after
    prev_fn = None
    next_fn = None
    for cfn in sorted_court_fns:
        if cfn <= fn:
            prev_fn = cfn
        if cfn >= fn and next_fn is None:
            next_fn = cfn
    
    if prev_fn is not None and prev_fn in court_data:
        all_H[fn] = court_data[prev_fn]
    elif next_fn is not None and next_fn in court_data:
        all_H[fn] = court_data[next_fn]

log(f"Homography available for {len(all_H)}/{len(all_frames)} frames")

# === STEP 2: BALL DETECTION (batched) ===
log("Step 2: Ball detection (batched)...")
ball_detections = []

for i in range(0, len(ball_frames), 20):
    batch_fns = ball_frames[i:i+20]
    batch_images = []
    valid_fns = []
    for fn in batch_fns:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if ret:
            batch_images.append(frame)
            valid_fns.append(fn)
    
    if not batch_images:
        continue
    
    results = ball_model.predict(batch_images, conf=BALL_CONF, verbose=False)
    
    for fn, r in zip(valid_fns, results):
        best_ball = None
        best_conf = 0
        all_dets = []
        
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = ball_model.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx, cy = (x1+x2)/2, (y1+y2)/2
            all_dets.append({'cls': cls_name, 'conf': conf, 'cx': cx, 'cy': cy, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
            
            if cls_name == 'Ball' and conf > best_conf:
                best_conf = conf
                best_ball = (fn, cx, cy, conf, x2-x1, y2-y1)
        
        if best_ball:
            ball_detections.append(best_ball)
    
    if i % 200 == 0:
        log(f"  Ball: frame {i}/{len(ball_frames)}, {len(ball_detections)} detections")

cap.release()
log(f"Ball detections: {len(ball_detections)}")

df_ball = pd.DataFrame(ball_detections, columns=['frame', 'x', 'y', 'conf', 'w', 'h'])
df_ball.to_csv('pipeline_output/ball_detections.csv', index=False)

# === STEP 3: PLAYER DETECTION (batched) ===
log("Step 3: Player detection (batched)...")
player_detections = defaultdict(list)
cap = cv2.VideoCapture(VIDEO_PATH)

for i in range(0, len(player_frames), 20):
    batch_fns = player_frames[i:i+20]
    batch_images = []
    valid_fns = []
    for fn in batch_fns:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if ret:
            batch_images.append(frame)
            valid_fns.append(fn)
    
    if not batch_images:
        continue
    
    results = player_model.predict(batch_images, conf=PLAYER_CONF, verbose=False)
    
    for fn, r in zip(valid_fns, results):
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = player_model.names[cls_id]
            conf = float(box.conf[0])
            if cls_name == 'Player' and conf > PLAYER_CONF:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                foot_x = (x1 + x2) / 2
                foot_y = y2
                player_detections[fn].append({'x': foot_x, 'y': foot_y, 'conf': conf})
    
    if i % 200 == 0:
        log(f"  Players: frame {i}/{len(player_frames)}")

cap.release()
log(f"Player frames: {len(player_detections)}")

# === STEP 4: COMPUTE BALL-TO-BASKET DISTANCES ===
log("Step 4: Computing ball-to-basket distances...")
df_ball = df_ball.sort_values('frame').reset_index(drop=True)

basket_dists = []
for _, row in df_ball.iterrows():
    fn = int(row['frame'])
    if fn in all_H:
        bx, by = all_H[fn]['basket_px']
        dist = np.sqrt((row['x'] - bx)**2 + (row['y'] - by)**2)
        basket_dists.append({'basket_dist': dist, 'basket_x': bx, 'basket_y': by, 'has_court': True})
    else:
        basket_dists.append({'basket_dist': 9999, 'basket_x': 0, 'basket_y': 0, 'has_court': False})

df_ball = pd.concat([df_ball, pd.DataFrame(basket_dists)], axis=1)
valid_ball = df_ball[df_ball['has_court']].copy()
log(f"Ball detections with court data: {len(valid_ball)}")

# === STEP 5: SHOT DETECTION ===
log("Step 5: Shot detection...")

if len(valid_ball) > 5:
    # Find local minima in basket distance (ball reaching closest point to hoop)
    valid_ball = valid_ball.sort_values('frame').reset_index(drop=True)
    
    shot_events = []
    used_frames = set()
    
    for i in range(2, len(valid_ball)-2):
        fn = int(valid_ball.iloc[i]['frame'])
        if fn in used_frames:
            continue
        
        curr_dist = valid_ball.iloc[i]['basket_dist']
        
        # Check if this is a local minimum
        prev_dists = [valid_ball.iloc[j]['basket_dist'] for j in range(max(0,i-3), i)]
        next_dists = [valid_ball.iloc[j]['basket_dist'] for j in range(i+1, min(len(valid_ball), i+4))]
        
        if not prev_dists or not next_dists:
            continue
        
        min_prev = min(prev_dists)
        min_next = min(next_dists)
        
        # Local min: both neighbors are farther from basket
        if curr_dist < min_prev * 0.9 and curr_dist < min_next * 0.9 and curr_dist < 200:
            # This is a shot event
            shot_events.append({
                'frame': fn,
                'ball_x': valid_ball.iloc[i]['x'],
                'ball_y': valid_ball.iloc[i]['y'],
                'basket_dist': curr_dist,
                'basket_x': valid_ball.iloc[i]['basket_x'],
                'basket_y': valid_ball.iloc[i]['basket_y'],
                'conf': valid_ball.iloc[i]['conf'],
            })
            # Mark nearby frames as used
            for df_offset in range(-10, 11):
                used_frames.add(fn + df_offset * BALL_STRIDE)
    
    log(f"Shot events found: {len(shot_events)}")
    
    # === STEP 6: CLASSIFY SHOTS ===
    log("Step 6: Classifying shots...")
    shots = []
    
    for shot in shot_events:
        fn = int(shot['frame'])
        
        # Find shooter: nearest player at shot frame (or nearest player frame)
        shooter_dist = None
        best_player_frame = None
        
        for pfn in player_frames:
            if abs(pfn - fn) <= 10:
                if pfn in player_detections and player_detections[pfn]:
                    best_player_frame = pfn
                    break
        
        if best_player_frame and fn in all_H:
            H = all_H[fn]['H']
            for p in player_detections[best_player_frame]:
                pt = np.array([[p['x'], p['y']]], dtype=np.float32).reshape(-1, 1, 2)
                try:
                    tactical_pt = cv2.perspectiveTransform(pt, H).reshape(2)
                    dist_from_basket = np.sqrt((tactical_pt[0] - BASKET_X)**2 + (tactical_pt[1] - BASKET_Y)**2)
                    if shooter_dist is None or dist_from_basket < shooter_dist:
                        shooter_dist = dist_from_basket
                except Exception:
                    continue
        
        # Classify 2PT/3PT
        if shooter_dist is not None:
            shot_type = '3PT' if shooter_dist > THREE_PT_RADIUS_PX else '2PT'
        else:
            shot_type = '2PT'  # default
        
        # Make/miss: ball within 40px of basket center
        is_make = shot['basket_dist'] < 40
        
        shots.append({
            'frame': fn,
            'ball_x': shot['ball_x'],
            'ball_y': shot['ball_y'],
            'basket_dist_px': round(shot['basket_dist'], 1),
            'shot_type': shot_type,
            'result': 'MAKE' if is_make else 'MISS',
            'shooter_dist_tactical': round(shooter_dist, 1) if shooter_dist else None,
            'conf': round(shot['conf'], 3),
        })
    
    df_shots = pd.DataFrame(shots)
    df_shots.to_csv('pipeline_output/shot_events.csv', index=False)
    
    # === OUTPUT STATS ===
    log("="*60)
    log("LIBERTY vs RIVERSTONE Q1 - SHOT ANALYSIS (PRETRAINED MODELS)")
    log("="*60)
    
    if len(df_shots) > 0:
        twos = df_shots[df_shots['shot_type'] == '2PT']
        threes = df_shots[df_shots['shot_type'] == '3PT']
        makes = df_shots[df_shots['result'] == 'MAKE']
        
        log(f"\nTotal shots: {len(df_shots)}")
        log(f"2PT: {twos['result'].value_counts().get('MAKE',0)}/{len(twos)}")
        log(f"3PT: {threes['result'].value_counts().get('MAKE',0)}/{len(threes)}")
        log(f"Makes: {len(makes)} | Misses: {len(df_shots) - len(makes)}")
        log(f"Est. points: {twos['result'].value_counts().get('MAKE',0)*2 + threes['result'].value_counts().get('MAKE',0)*3}")
        
        log(f"\nTarget (your count): 2PT 2/7, 3PT 1/2, FT 1/3 = 8 pts")
        log(f"Note: FT not detected by this pipeline")
        
        log(f"\nShot details:")
        for _, s in df_shots.iterrows():
            log(f"  Frame {int(s['frame'])}: {s['shot_type']} {s['result']} (basket_dist={s['basket_dist_px']:.0f}px, shooter={s['shooter_dist_tactical']}tactical_px, conf={s['conf']})")
    else:
        log("NO SHOTS DETECTED")
    
    # Also show closest basket approaches
    log("\nTop 10 closest ball-to-basket approaches:")
    closest = valid_ball.nsmallest(10, 'basket_dist')
    for _, r in closest.iterrows():
        log(f"  Frame {int(r['frame'])}: {r['basket_dist']:.1f}px (ball {r['x']:.0f},{r['y']:.0f} basket {r['basket_x']:.0f},{r['basket_y']:.0f})")

else:
    log(f"Not enough valid ball detections ({len(valid_ball)}) for shot detection")
    log("Ball detections per frame range:")
    if len(df_ball) > 0:
        log(f"  Min dist to basket: {df_ball['basket_dist'].min():.1f}px")
        log(f"  Median: {df_ball['basket_dist'].median():.1f}px")
        log(f"  Frames with court data: {df_ball['has_court'].sum()}")

log(f"\nDone! Output in pipeline_output/")
log(f"Total time: {time.time()-start_time:.0f}s")
