"""
Memory-efficient basketball analysis using abdullahtarek's pretrained models.
Processes video in streaming fashion — never holds all frames in memory.
Outputs annotated video + event CSVs.
"""
import cv2
import numpy as np
import pandas as pd
import os
import sys
import time
from ultralytics import YOLO
from collections import defaultdict

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)

# === CONFIG ===
VIDEO_PATH = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUTPUT_VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/annotated_q1.avi'
BALL_CONF = 0.2
COURT_CONF = 0.1
PLAYER_CONF = 0.3

TACTICAL_W, TACTICAL_H = 300, 161
COURT_W_M, COURT_H_M = 28, 15

TACTICAL_KPS = np.array([
    (0,0),(0,35),(0,60),(0,78),(0,104),(0,161),
    (150,161),(150,0),(85,60),(85,78),
    (300,161),(300,104),(300,78),(300,60),(300,35),(300,0),
    (215,60),(215,78)
], dtype=np.float32)

BASKET_X, BASKET_Y = 150.0, 161.0 - (1.2192 / (COURT_H_M / TACTICAL_H))
THREE_PT_R = 6.02 / (COURT_H_M / TACTICAL_H)
FT_LINE_Y = 78  # free throw line in tactical coords

os.makedirs('/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output', exist_ok=True)
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

# === LOAD MODELS ONE AT A TIME ===
log("Loading ball detector...")
ball_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')
log("Ball model loaded")

log("Loading court keypoint detector...")
court_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt')
log("Court model loaded")

log("Loading player detector...")
player_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/player_detector.pt')
log("Player model loaded")

# === PASS 1: Detect court keypoints, ball, player per frame ===
log("Pass 1: Running detections on all frames...")

cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
log(f"Video: {W}x{H}, {total} frames @ {fps}fps")

# Storage for detections (much lighter than storing frames)
ball_dets = []      # (frame, cx, cy, conf, w, h)
court_dets = []     # (frame, H_matrix, basket_px, n_kps)
player_dets = defaultdict(list)  # frame -> [(x,y,conf)]
hoop_dets = []      # (frame, cx, cy, conf)

frame_num = 0
court_batch_imgs = []
court_batch_fns = []
BATCH = 20

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Ball detection (every frame, but only store best ball)
    ball_results = ball_model.predict(frame, conf=BALL_CONF, verbose=False)
    best_ball = None
    best_ball_conf = 0
    for r in ball_results:
        for box in r.boxes:
            cls_name = ball_model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            x1,y1,x2,y2 = box.xyxy[0].tolist()
            cx, cy = (x1+x2)/2, (y1+y2)/2
            if cls_name == 'Ball' and conf > best_ball_conf:
                best_ball = (frame_num, cx, cy, conf, x2-x1, y2-y1)
                best_ball_conf = conf
            if cls_name == 'Hoop' and conf > 0.2:
                hoop_dets.append((frame_num, cx, cy, conf))
    if best_ball:
        ball_dets.append(best_ball)

    # Court keypoint (every 5th frame to save time)
    if frame_num % 5 == 0:
        court_batch_imgs.append(frame)
        court_batch_fns.append(frame_num)

        if len(court_batch_imgs) >= BATCH:
            # Process batch
            court_results = court_model.predict(court_batch_imgs, conf=COURT_CONF, verbose=False)
            for fn, r in zip(court_batch_fns, court_results):
                if r.keypoints is None or r.keypoints.xy.shape[0] == 0:
                    continue
                kps_xy = r.keypoints.xy[0].cpu().numpy()
                kps_conf = r.keypoints.conf[0].cpu().numpy()
                valid = (kps_xy[:,0] > 1) & (kps_xy[:,1] > 1) & (kps_conf > 0.3)
                v_idx = np.where(valid)[0]
                if len(v_idx) < 4:
                    continue
                try:
                    H_mat, _ = cv2.findHomography(kps_xy[v_idx], TACTICAL_KPS[v_idx], cv2.RANSAC, 5.0)
                    if H_mat is None: continue
                    basket_pt = cv2.perspectiveTransform(
                        np.array([[BASKET_X, BASKET_Y]], dtype=np.float32).reshape(-1,1,2), H_mat
                    ).reshape(2)
                    court_dets.append((fn, H_mat, basket_pt, len(v_idx)))
                except: pass
            court_batch_imgs = []
            court_batch_fns = []

    # Player detection (every 5th frame)
    if frame_num % 5 == 0:
        player_results = player_model.predict(frame, conf=PLAYER_CONF, verbose=False)
        for r in player_results:
            for box in r.boxes:
                cls_name = player_model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                if cls_name == 'Player' and conf > PLAYER_CONF:
                    x1,y1,x2,y2 = box.xyxy[0].tolist()
                    player_dets[frame_num].append({'x': (x1+x2)/2, 'y': y2, 'conf': conf})

    frame_num += 1
    if frame_num % 100 == 0:
        log(f"  Frame {frame_num}/{total}: {len(ball_dets)} balls, {len(court_dets)} court, {len(player_dets)} player frames")

# Process remaining court batch
if court_batch_imgs:
    court_results = court_model.predict(court_batch_imgs, conf=COURT_CONF, verbose=False)
    for fn, r in zip(court_batch_fns, court_results):
        if r.keypoints is None: continue
        kps_xy = r.keypoints.xy[0].cpu().numpy()
        kps_conf = r.keypoints.conf[0].cpu().numpy()
        valid = (kps_xy[:,0] > 1) & (kps_xy[:,1] > 1) & (kps_conf > 0.3)
        v_idx = np.where(valid)[0]
        if len(v_idx) < 4: continue
        try:
            H_mat, _ = cv2.findHomography(kps_xy[v_idx], TACTICAL_KPS[v_idx], cv2.RANSAC, 5.0)
            if H_mat is None: continue
            basket_pt = cv2.perspectiveTransform(
                np.array([[BASKET_X, BASKET_Y]], dtype=np.float32).reshape(-1,1,2), H_mat
            ).reshape(2)
            court_dets.append((fn, H_mat, basket_pt, len(v_idx)))
        except: pass

cap.release()

log(f"Pass 1 complete: {len(ball_dets)} balls, {len(court_dets)} court frames, {len(player_dets)} player frames")
log(f"Hoop detections: {len(hoop_dets)}")

# Save detections
pd.DataFrame(ball_dets, columns=['frame','x','y','conf','w','h']).to_csv(
    '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/ball_v9.csv', index=False)
pd.DataFrame(hoop_dets, columns=['frame','x','y','conf']).to_csv(
    '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/hoop_v9.csv', index=False)

# === PASS 2: Shot detection ===
log("Pass 2: Detecting shots...")

# Build court lookup by frame
court_by_frame = {}
sorted_court = sorted(court_dets, key=lambda x: x[0])
for fn, H_mat, basket_pt, n_kps in sorted_court:
    court_by_frame[fn] = {'H': H_mat, 'basket': basket_pt}

# Interpolate court for ball frames
def get_court(fn):
    if fn in court_by_frame:
        return court_by_frame[fn]
    # Find nearest
    best = None
    best_dist = 9999
    for cfn, H_mat, basket_pt, n_kps in sorted_court:
        dist = abs(cfn - fn)
        if dist < best_dist:
            best_dist = dist
            best = {'H': H_mat, 'basket': basket_pt}
    return best if best_dist < 30 else None

# Ball-to-basket distances
ball_with_court = []
for fn, cx, cy, conf, w, h in ball_dets:
    c = get_court(fn)
    if c:
        bx, by = c['basket']
        dist = np.sqrt((cx-bx)**2 + (cy-by)**2)
        ball_with_court.append((fn, cx, cy, conf, w, h, dist, bx, by, c['H']))

log(f"Ball detections with court data: {len(ball_with_court)}/{len(ball_dets)}")

# Find shot events: local minima in basket distance
ball_with_court.sort(key=lambda x: x[0])
shots = []
used = set()

for i in range(len(ball_with_court)):
    fn, cx, cy, conf, w, h, dist, bx, by, H_mat = ball_with_court[i]
    if fn in used:
        continue

    # Check if local minimum in basket distance
    prev_dists = [ball_with_court[j][6] for j in range(max(0,i-5), i)]
    next_dists = [ball_with_court[j][6] for j in range(i+1, min(len(ball_with_court), i+6))]

    if not prev_dists or not next_dists:
        continue

    min_prev = min(prev_dists) if prev_dists else 9999
    min_next = min(next_dists) if next_dists else 9999

    # Relaxed threshold — ball approaching and receding from basket
    if dist < min_prev and dist < min_next and dist < 300:
        # Find shooter: nearest player at nearest player frame
        shooter_dist = None
        for pfn in range(fn-10, fn+11):
            if pfn in player_dets:
                for p in player_dets[pfn]:
                    pt = np.array([[p['x'], p['y']]], dtype=np.float32).reshape(-1,1,2)
                    try:
                        tp = cv2.perspectiveTransform(pt, H_mat).reshape(2)
                        d = np.sqrt((tp[0]-BASKET_X)**2 + (tp[1]-BASKET_Y)**2)
                        if shooter_dist is None or d < shooter_dist:
                            shooter_dist = d
                    except: break
                if shooter_dist is not None:
                    break

        # Check if FT (player near free throw line, ball near hoop)
        is_ft = False
        if shooter_dist and abs(shooter_dist - 5.79/(COURT_W_M/TACTICAL_W)) < 5:
            is_ft = True

        shot_type = 'FT' if is_ft else ('3PT' if shooter_dist and shooter_dist > THREE_PT_R else '2PT')
        is_make = dist < 60  # ball within 60px of basket

        shots.append({
            'frame': fn, 'ball_x': cx, 'ball_y': cy,
            'basket_dist': round(dist, 1), 'shot_type': shot_type,
            'result': 'MAKE' if is_make else 'MISS',
            'shooter_dist': round(shooter_dist, 1) if shooter_dist else None,
            'conf': round(conf, 3)
        })

        for df in range(-15, 16):
            used.add(fn + df)

df_shots = pd.DataFrame(shots)
df_shots.to_csv('/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shots_v9.csv', index=False)

# === PASS 3: Generate annotated video ===
log("Pass 3: Generating annotated video...")
cap = cv2.VideoCapture(VIDEO_PATH)
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, fps, (W, H))

shot_frames = {int(s['frame']): s for s in shots}
frame_num = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Draw ball detections
    for fn, cx, cy, conf, w, h in ball_dets:
        if fn == frame_num:
            cv2.circle(frame, (int(cx), int(cy)), 8, (0, 255, 0), 2)
            cv2.putText(frame, f"Ball {conf:.2f}", (int(cx)+10, int(cy)-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # Draw court keypoints
    c = get_court(frame_num)
    if c:
        bx, by = int(c['basket'][0]), int(c['basket'][1])
        cv2.circle(frame, (bx, by), 12, (0, 0, 255), 2)
        cv2.drawMarker(frame, (bx, by), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)

    # Draw shot annotation
    if frame_num in shot_frames:
        s = shot_frames[frame_num]
        label = f"SHOT: {s['shot_type']} {s['result']} dist={s['basket_dist']:.0f}px"
        cv2.putText(frame, label, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
        cv2.circle(frame, (int(s['ball_x']), int(s['ball_y'])), 20, (0, 255, 255), 3)

    # Frame number
    cv2.putText(frame, f"F:{frame_num}", (10, H-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

    out.write(frame)
    frame_num += 1
    if frame_num % 500 == 0:
        log(f"  Writing frame {frame_num}/{total}")

cap.release()
out.release()

# === OUTPUT ===
log("="*60)
log(f"SHOTS FOUND: {len(shots)}")
log("="*60)

twos = [s for s in shots if s['shot_type'] == '2PT']
threes = [s for s in shots if s['shot_type'] == '3PT']
fts = [s for s in shots if s['shot_type'] == 'FT']
makes = [s for s in shots if s['result'] == 'MAKE']

log(f"2PT: {sum(1 for s in twos if s['result']=='MAKE')}/{len(twos)}")
log(f"3PT: {sum(1 for s in threes if s['result']=='MAKE')}/{len(threes)}")
log(f"FT:  {sum(1 for s in fts if s['result']=='MAKE')}/{len(fts)}")
log(f"Total makes: {len(makes)}/{len(shots)}")
log(f"Est. points: {sum(2 for s in twos if s['result']=='MAKE') + sum(3 for s in threes if s['result']=='MAKE') + sum(1 for s in fts if s['result']=='MAKE')}")
log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8 pts")

for s in shots:
    log(f"  Frame {s['frame']}: {s['shot_type']} {s['result']} basket_dist={s['basket_dist']}px shooter={s['shooter_dist']} conf={s['conf']}")

ball_arr = np.array([b[3] for b in ball_dets]) if ball_dets else np.array([0])
log(f"\nBall detection stats: {len(ball_dets)} total, conf mean={ball_arr.mean():.3f} max={ball_arr.max():.3f}")
log(f"Total time: {time.time()-start:.0f}s")
log("DONE. Output in pipeline_output/")
