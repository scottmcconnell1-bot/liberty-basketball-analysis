#!/usr/bin/env python3
"""Test A: 1080p NFHS clip. Existing v14 detector. Stride=10. Just measure."""
import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

VIDEO = '/tmp/clip_1080p.mp4'
MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
STRIDE = 10
CONF = 0.0002
IOU = 0.3
COURT_X_MIN, COURT_X_MAX = 150, 1770
COURT_Y_MIN, COURT_Y_MAX = 150, 975

t_start = time.time()
m = YOLO(MODEL, verbose=False)
print(f"[{time.time()-t_start:.0f}s] Model loaded")

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"[{time.time()-t_start:.0f}s] Video: {total} frames, {w}x{h}")
print(f"[{time.time()-t_start:.0f}s] Stride={STRIDE}, processing ~{total//STRIDE} frames")

results = []
ball_count = 0
processed = 0
t_infer_acc = 0

for frame_idx in range(total):
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % STRIDE != 0:
        continue

    t0 = time.time()
    r = m.predict(frame, conf=CONF, iou=IOU, verbose=False)[0]
    t_infer = time.time() - t0
    t_infer_acc += t_infer
    processed += 1

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

    if best and COURT_X_MIN <= best[0] <= COURT_X_MAX and COURT_Y_MIN <= best[1] <= COURT_Y_MAX:
        results.append((frame_idx, best[0], best[1], best[2]))
        ball_count += 1

    if processed % 20 == 0:
        fps_proc = processed / (time.time()-t_start)
        print(f"[{time.time()-t_start:.0f}s] {processed}/{total//STRIDE} processed, {ball_count} balls, {fps_proc:.1f} fps_proc", flush=True)

cap.release()
elapsed = time.time() - t_start
avg_infer = t_infer_acc / processed if processed else 0

print(f"\n=== TEST A RESULTS (1080p, stride={STRIDE}) ===")
print(f"Total frames in video: {total}")
print(f"Frames processed: {processed}")
print(f"Ball detections: {ball_count}")
print(f"Detection rate: {ball_count/processed*100:.1f}% of processed frames")
print(f"Avg inference time: {avg_infer:.3f}s/frame")
print(f"Processing speed: {processed/elapsed:.1f} frames/sec")
print(f"Total time: {elapsed:.1f}s")
print(f"Full game estimate (stride={STRIDE}): {115851/STRIDE * avg_infer / 3600:.1f} hours")
print(f"Full game estimate (stride=1): {115851 * avg_infer / 3600:.1f} hours")

# Save results
out = {
    'source': 'NFHS 1080p', 'stride': STRIDE, 'total_frames': total,
    'frames_processed': processed, 'ball_count': ball_count,
    'avg_infer_s': avg_infer, 'total_time_s': elapsed,
    'detections': results
}
with open('pipeline_output/testA_1080p_str10.pkl', 'wb') as f:
    pickle.dump(out, f)

# Save CSV
df = pd.DataFrame(results, columns=['frame', 'cx', 'cy', 'conf'])
df.to_csv('pipeline_output/testA_1080p_str10.csv', index=False)
if len(results) > 0:
    confs = [r[3] for r in results]
    print(f"Confidence: min={min(confs):.4f} median={np.median(confs):.4f} max={max(confs):.4f}")
print("DONE")
