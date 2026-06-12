#!/usr/bin/env python3
"""
Detect ball on full-game 1080p NFHS video using fine-tuned YOLO model.

Usage: python3 detect_ball_1080p.py [output_name]
Default output: pipeline_output/detections_1080p.pkl
"""
import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np

VIDEO = 'videos/nfhs_4K_gam021ddbf1cf.mp4'
MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
OUT_DIR = 'pipeline_output'
CONF = 0.0002
IOU = 0.3

# Court region constraints (for 1080p — scaled from 720p)
# Original was x:100-1180, y:100-650 on 1280x720
# Scaled to 1920x1080: x:150-1770, y:150-975
COURT_X_MIN = 150
COURT_X_MAX = 1770
COURT_Y_MIN = 150
COURT_Y_MAX = 975

SAVE_INTERVAL = 1000  # save checkpoint every N frames

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)

def is_in_court(cx, cy):
    return COURT_X_MIN <= cx <= COURT_X_MAX and COURT_Y_MIN <= cy <= COURT_Y_MAX

if __name__ == '__main__':
    output_name = sys.argv[1] if len(sys.argv) > 1 else 'detections_1080p'
    os.makedirs(OUT_DIR, exist_ok=True)
    pklpath = os.path.join(OUT_DIR, f'{output_name}.pkl')
    csvpath = os.path.join(OUT_DIR, f'{output_name}.csv')

    START = time.time()

    # Check for existing checkpoint
    checkpoint_path = os.path.join(OUT_DIR, f'{output_name}_checkpoint.pkl')
    start_frame = 0
    results = []
    
    if os.path.exists(checkpoint_path):
        log(f"Loading checkpoint from {checkpoint_path}")
        with open(checkpoint_path, 'rb') as f:
            ckpt = pickle.load(f)
        start_frame = ckpt['frame']
        results = ckpt['results']
        log(f"Resuming from frame {start_frame}, {len(results)} results so far")

    log(f"Loading YOLO model from {MODEL}")
    from ultralytics import YOLO
    m = YOLO(MODEL, verbose=False)

    log(f"Opening video: {VIDEO}")
    cap = cv2.VideoCapture(VIDEO)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {VIDEO}")
        sys.exit(1)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    log(f"Video: {total} frames, {width}x{height}, {fps} fps")
    log(f"Estimated processing time: ~{total * 0.05 / 60:.0f} min at ~20fps inference")

    # Seek to resume point
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        log(f"Seeked to frame {start_frame}")

    frame_idx = start_frame
    ball_count = 0
    filtered_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        r = m.predict(frame, conf=CONF, iou=IOU, verbose=False)[0]
        best = None
        best_cf = 0

        if r.boxes is not None:
            for box in r.boxes:
                cls = m.names[int(box.cls[0])]
                cf = float(box.conf[0])
                if cls == 'Ball' and cf > best_cf:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    best_cf = cf
                    best = (cx, cy, cf)

        if best is not None and is_in_court(best[0], best[1]):
            results.append(best)
            ball_count += 1
        elif best is not None:
            results.append(None)
            filtered_count += 1
        else:
            results.append(None)

        frame_idx += 1

        if frame_idx % 1000 == 0:
            elapsed = time.time() - START
            fps_proc = frame_idx / elapsed
            pct = frame_idx / total * 100
            eta_sec = (total - frame_idx) / fps_proc
            log(f"  {frame_idx}/{total} ({pct:.0f}%), {ball_count} balls, {fps_proc:.1f} fps_proc, ETA {eta_sec/60:.0f}min")
            
            # Save checkpoint
            with open(checkpoint_path, 'wb') as f:
                pickle.dump({'frame': frame_idx, 'results': results}, f)
            log(f"  Checkpoint saved at frame {frame_idx}")

        if frame_idx % 10000 == 0:
            log(f"  PROGRESS: {frame_idx}/{total} frames, {ball_count} ball detections")

    cap.release()

    elapsed = time.time() - START
    log(f"Detection complete: {len(results)} frames processed in {elapsed/60:.1f} min")
    log(f"Ball detections: {ball_count}, filtered: {filtered_count}")

    # Save final pickle
    output_data = {
        'video': VIDEO,
        'total_frames': len(results),
        'ball_detections': results,  # list of (cx, cy, conf) or None per frame
        'params': {'conf': CONF, 'iou': IOU, 'model': MODEL}
    }
    with open(pklpath, 'wb') as f:
        pickle.dump(output_data, f)
    log(f"Saved: {pklpath}")

    # Remove checkpoint on success
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)

    # Quick CSV summary
    import pandas as pd
    detected = [(i, r[0], r[1], r[2]) for i, r in enumerate(results) if r is not None]
    df = pd.DataFrame(detected, columns=['frame', 'cx', 'cy', 'conf'])
    df.to_csv(csvpath, index=False)
    log(f"Saved: {csvpath} ({len(df)} detections)")

    log("DONE")
