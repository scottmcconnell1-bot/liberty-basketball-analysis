#!/usr/bin/env python3
"""
Shot detection v8: Ultra-low conf ball detection + strict color + basket proximity.
Works in headless environments by avoiding any GUI/TUI calls.
"""
import cv2
import numpy as np
import pickle
import time
import pandas as pd
import os
from scipy.signal import find_peaks
from ultralytics import YOLO

# Force headless operation
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['OMP_NUM_THREADS'] = '1'

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
MODEL_PATH = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_finetune/runs/finetune2/weights/best.pt'
COURT_MODEL_PATH = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt'

print('Loading models...', flush=True)
ball_m = YOLO(MODEL_PATH, verbose=False)
court_m = YOLO(COURT_MODEL_PATH, verbose=False)

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f'Total frames: {total}', flush=True)

ball_cx = np.full(total, np.nan)
ball_cy = np.full(total, np.nan)
ball_conf = np.zeros(total)
ball_color_ok = np.zeros(total, dtype=bool)
kp_arr = np.full((total, 18, 2), np.nan)

fn = 0
start = time.time()

while True:
    ret, frame = cap.read()
    if not ret or fn >= total:
        break
    
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    r = ball_m.predict(frame, conf=0.0002, verbose=False)[0]
    if r.boxes is not None:
        best_conf = 0
        best_box = None
        for box in r.boxes:
            cls = ball_m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball' and cf > best_conf:
                best_conf = cf
                best_box = box
        if best_box is not None:
            x1, y1, x2, y2 = best_box.xyxy[0].tolist()
            cx, cy = (x1+x2)/2, (y1+y2)/2
            ball_cx[fn] = cx
            ball_cy[fn] = cy
            ball_conf[fn] = best_conf
            ix, iy = int(cx), int(cy)
            if 0 <= ix < frame.shape[1] and 0 <= iy < frame.shape[0]:
                pixel_hsv = hsv[iy, ix]
                if 3 <= pixel_hsv[0] <= 28 and pixel_hsv[1] > 20:
                    ball_color_ok[fn] = True
    
    if fn % 20 == 0:
        r = court_m.predict(frame, conf=0.3, verbose=False)[0]
        if r.keypoints is not None and len(r.keypoints) > 0:
            kp_arr[fn] = r.keypoints[0].xy.cpu().numpy()[0]
    
    fn += 1
    if fn % 500 == 0:
        elapsed = time.time() - start
        nb = int(np.sum(~np.isnan(ball_cx)))
        nc = int(np.sum(ball_color_ok))
        print(f'Progress: {fn}/{total} frames, {nb} ball det, {nc} color-ok, {elapsed:.1f}s', flush=True)

cap.release()
print('Detection finished', flush=True)

# Interpolate keypoints
for kp in range(18):
    last = np.array([np.nan, np.nan])
    for i in range(total):
        if not np.isnan(kp_arr[i, kp, 0]):
            last = kp_arr[i, kp].copy()
        elif not np.isnan(last[0]):
            kp_arr[i, kp] = last
    last = np.array([np.nan, np.nan])
    for i in range(total-1, -1, -1):
        if not np.isnan(kp_arr[i, kp, 0]):
            last = kp_arr[i, kp].copy()
        elif not np.isnan(last[0]):
            kp_arr[i, kp] = last

# Determine basket positions
kp_means = []
for kp in range(18):
    v = ~np.isnan(kp_arr[:, kp, 0])
    if np.sum(v) > total * 0.1:
        kp_means.append((kp, np.nanmean(kp_arr[v, kp, 0]), np.nanmean(kp_arr[v, kp, 1])))

kp_means.sort(key=lambda x: x[1])
if len(kp_means) > 4:
    left_kps = [k[0] for k in kp_means[:3]]
    right_kps = [k[0] for k in kp_means[-3:]]
    basket_left_x = np.nanmean(np.stack([kp_arr[:, kp, 0] for kp in left_kps], axis=1), axis=1)
    basket_left_y = np.nanmean(np.stack([kp_arr[:, kp, 1] for kp in left_kps], axis=1), axis=1)
    basket_right_x = np.nanmean(np.stack([kp_arr[:, kp, 0] for kp in right_kps], axis=1), axis=1)
    basket_right_y = np.nanmean(np.stack([kp_arr[:, kp, 1] for kp in right_kps], axis=1), axis=1)
else:
    basket_left_x = np.full(total, 200)
    basket_left_y = np.full(total, 360)
    basket_right_x = np.full(total, 1080)
    basket_right_y = np.full(total, 360)

dist_to_basket = np.full(total, np.nan)
for i in range(total):
    if not ball_color_ok[i] or np.isnan(ball_cx[i]):
        continue
    dl = np.sqrt((ball_cx[i]-basket_left_x[i])**2 + (ball_cy[i]-basket_left_y[i])**2)
    dr = np.sqrt((ball_cx[i]-basket_right_x[i])**2 + (ball_cy[i]-basket_right_y[i])**2)
    dist_to_basket[i] = min(dl, dr)

inv = -dist_to_basket.copy()
inv[np.isnan(inv)] = 0
peaks, _ = find_peaks(inv, distance=10, height=-100)
close_peaks = [p for p in peaks if dist_to_basket[p] < 150]

gap_shots = []
for fn in range(20, total):
    if ball_color_ok[fn]:
        continue
    last_fn = None
    for prev in range(fn-1, max(0, fn-30), -1):
        if ball_color_ok[prev]:
            last_fn = prev
            break
    if last_fn is None:
        continue
    gap = fn - last_fn
    if gap < 3 or gap > 25:
        continue
    if not np.isnan(dist_to_basket[last_fn]) and dist_to_basket[last_fn] < 150:
        gap_shots.append(last_fn)

all_cand = sorted(set(close_peaks) | set(gap_shots))
deduped = []
i = 0
while i < len(all_cand):
    j = i + 1
    while j < len(all_cand) and all_cand[j] - all_cand[j-1] < 30:
        j += 1
    group = all_cand[i:j]
    best = min(group, key=lambda f: dist_to_basket[f] if not np.isnan(dist_to_basket[f]) else 9999)
    deduped.append(best)
    i = j

print(f'\n=== FINAL SHOT CANDIDATES: {len(deduped)} ===')
for fn in deduped:
    d = dist_to_basket[fn]
    bc = ball_conf[fn]
    print(f'  F{fn:4d}: dist={d if not np.isnan(d) else -1:6.1f}px conf={bc:.3f}', flush=True)

results = {
    'candidates': deduped,
    'ball_cx': ball_cx,
    'ball_cy': ball_cy,
    'ball_conf': ball_conf,
    'ball_color_ok': ball_color_ok,
    'dist_to_basket': dist_to_basket,
    'basket_left': (basket_left_x, basket_left_y),
    'basket_right': (basket_right_x, basket_right_y),
    'kp_arr': kp_arr,
}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'shot_v8.pkl'), 'wb') as f:
    pickle.dump(results, f)

csv_path = os.path.join(OUT, 'shot_candidates_v8.csv')
df = pd.DataFrame([{'frame': fn, 'dist': round(float(dist_to_basket[fn]), 1) if not np.isnan(dist_to_basket[fn]) else None, 'conf': round(float(ball_conf[fn]), 3)} for fn in deduped])
df.to_csv(csv_path, index=False)

print(f'\nDone. Candidates written to {csv_path}', flush=True)