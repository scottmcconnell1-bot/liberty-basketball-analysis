#!/usr/bin/env python3
"""Test C: 720p clip, stride=1, JUST 50 frames. Quick throughput check."""
import os, sys, time
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

VIDEO = '/tmp/clip_720p.mp4'
MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
MAX_FRAMES = 50  # Just 50 frames to get a quick number
CONF = 0.0002
IOU = 0.3

t_start = time.time()
m = YOLO(MODEL, verbose=False)
print(f"[{time.time()-t_start:.0f}s] Model loaded")

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"[{time.time()-t_start:.0f}s] Video: {total} frames, {w}x{h}")

# First frame inference time
ret, frame = cap.read()
t0 = time.time()
r = m.predict(frame, conf=CONF, iou=IOU, verbose=False)[0]
t1 = time.time()
print(f"[{time.time()-t_start:.0f}s] First inference: {t1-t0:.3f}s")

# Run MAX_FRAMES at stride=1
ball_count = 0
results = []
for i in range(MAX_FRAMES):
    if i > 0:
        ret, frame = cap.read()
        if not ret:
            break
    t0 = time.time()
    r = m.predict(frame, conf=CONF, iou=IOU, verbose=False)[0]
    infer_t = time.time() - t0
    
    best = None
    best_cf = 0
    if r.boxes is not None:
        for box in r.boxes:
            cls = m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball' and cf > best_cf:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1+x2)/2, (y1+y2)/2
                best_cf = cf
                best = (cx, cy, cf)
    
    if best and 100 <= best[0] <= 1180 and 100 <= best[1] <= 650:
        ball_count += 1
        results.append((i, best[0], best[1], best[2]))
    
    if (i+1) % 10 == 0:
        elapsed = time.time() - t_start
        fps = (i+1) / elapsed
        print(f"[{elapsed:.0f}s] {i+1}/{MAX_FRAMES} frames, {ball_count} balls, {fps:.2f} fps, last_infer={infer_t:.3f}s", flush=True)

cap.release()
elapsed = time.time() - t_start
print(f"\n=== TEST C RESULTS (720p, stride=1, {MAX_FRAMES} frames) ===")
print(f"Frames: {MAX_FRAMES}, Balls: {ball_count} ({ball_count/MAX_FRAMES*100:.0f}%)")
print(f"Total time: {elapsed:.1f}s = {MAX_FRAMES/elapsed:.2f} fps")
print(f"Full game estimate: {115851/elapsed*MAX_FRAMES/3600:.1f} hours")
if results:
    confs = [r[3] for r in results]
    print(f"Confidence range: {min(confs):.4f} - {max(confs):.4f}")
print("DONE")
