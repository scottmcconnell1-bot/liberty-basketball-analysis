#!/usr/bin/env python3
"""
Detector quality test: Same frame at multiple imgsz values.
Measures: speed, confidence, bounding box size, what the model sees.
"""
import os, sys, time
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

VIDEO_1080P = '/tmp/clip_1080p.mp4'
VIDEO_720P = '/tmp/clip_720p.mp4'
MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
OUT_DIR = 'pipeline_output/detector_audit'
os.makedirs(OUT_DIR, exist_ok=True)

# Test on frames at different points in the clip (0%, 25%, 50%, 75% positions)
FRAME_POSITIONS = [0, 750, 1500, 2250]  # 0s, 30s, 60s, 90s into clip
IMGSZ_VALUES = [320, 480, 640, 960]

m = YOLO(MODEL, verbose=False)
print(f"Model loaded")

results = []

for src_name, video in [('1080p', VIDEO_1080P), ('720p', VIDEO_720P)]:
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    for frame_pos in FRAME_POSITIONS:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        if not ret:
            continue
        
        for imgsz in IMGSZ_VALUES:
            t0 = time.time()
            r = m.predict(frame, imgsz=imgsz, conf=0.0001, iou=0.3, verbose=False)[0]
            elapsed = time.time() - t0
            
            # Collect all ball detections
            balls = []
            if r.boxes is not None:
                for box in r.boxes:
                    cls = m.names[int(box.cls[0])]
                    cf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    bw, bh = x2-x1, y2-y1
                    area = bw * bh
                    balls.append({
                        'conf': cf, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                        'bw': bw, 'bh': bh, 'area': area,
                        'cx': (x1+x2)/2, 'cy': (y1+y2)/2
                    })
            
            # Save annotated frame for the middle frame (1500)
            if frame_pos == 1500:
                annotated = frame.copy()
                for b in balls:
                    cv2.rectangle(annotated, 
                                 (int(b['x1']), int(b['y1'])), 
                                 (int(b['x2']), int(b['y2'])), 
                                 (0, 255, 0), 2)
                    cv2.putText(annotated, f"{b['conf']:.4f}", 
                               (int(b['x1']), int(b['y1'])-5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                cv2.imwrite(f'{OUT_DIR}/f1500_{src_name}_imgsz{imgsz}.jpg', annotated)
            
            results.append({
                'source': src_name, 'frame': frame_pos, 'imgsz': imgsz,
                'time_s': elapsed, 'n_balls': len(balls),
                'best_conf': max((b['conf'] for b in balls), default=0),
                'best_area': max((b['area'] for b in balls), default=0),
                'best_bw': max((b['bw'] for b in balls), default=0),
                'best_bh': max((b['bh'] for b in balls), default=0),
                'resolution': f'{w}x{h}'
            })
    
    cap.release()

df = pd.DataFrame(results)
df.to_csv(f'{OUT_DIR}/quality_test.csv', index=False)

print("\n=== DETECTOR QUALITY TEST ===")
print(f"{'Source':<8} {'Frame':<6} {'Imgsz':<6} {'Time':<7} {'Balls':<6} {'Conf':<8} {'BoxArea':<10}")
print("-" * 60)
for _, r in df.iterrows():
    print(f"{r['source']:<8} {r['frame']:<6} {r['imgsz']:<6} {r['time_s']:.3f}s  {r['n_balls']:<6} {r['best_conf']:.4f}   {r['best_area']:.0f}")

print("\n=== BY IMGSZ (avg across sources/frames) ===")
for imgsz in IMGSZ_VALUES:
    sub = df[df['imgsz'] == imgsz]
    print(f"  imgsz={imgsz}: avg_time={sub['time_s'].mean():.3f}s, avg_balls={sub['n_balls'].mean():.1f}, best_conf={sub['best_conf'].mean():.5f}")

print("\n=== BY SOURCE (avg across imgsz/frames) ===")
for src in ['1080p', '720p']:
    sub = df[df['source'] == src]
    print(f"  {src}: avg_time={sub['time_s'].mean():.3f}s, avg_balls={sub['n_balls'].mean():.1f}, best_conf={sub['best_conf'].mean():.5f}")

print(f"\nAudit frames saved to {OUT_DIR}/")
print("DONE")
