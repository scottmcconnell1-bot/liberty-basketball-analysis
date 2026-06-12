#!/usr/bin/env python3
"""
Fast ball detection on 1080p video.
Uses stride to achieve ~15-20fps processing rate on CPU.
Ball detector model: fine-tuned best.pt (full model, but on strided frames)
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
STRIDE = 3  # process every 3rd frame (every 0.12s at 25fps)

# Court region (scaled for 1080p)
COURT_X_MIN = 150
COURT_X_MAX = 1770
COURT_Y_MIN = 150
COURT_Y_MAX = 975

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)

def is_in_court(cx, cy):
    return COURT_X_MIN <= cx <= COURT_X_MAX and COURT_Y_MIN <= cy <= COURT_Y_MAX

if __name__ == '__main__':
    output_name = sys.argv[1] if len(sys.argv) > 1 else 'detections_1080p_fast'
    os.makedirs(OUT_DIR, exist_ok=True)
    pklpath = os.path.join(OUT_DIR, f'{output_name}.pkl')

    START = time.time()

    log(f"Loading YOLO model from {MODEL}")
    from ultralytics import YOLO
    m = YOLO(MODEL, verbose=False)

    log(f"Opening video: {VIDEO}")
    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    log(f"Video: {total} frames, {width}x{height}, {fps} fps")
    log(f"Stride: {STRIDE} (processing ~{total//STRIDE} frames)")

    # Results indexed by frame number
    results = [None] * total
    frame_idx = 0
    processed = 0
    ball_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % STRIDE == 0:
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
                results[frame_idx] = best
                ball_count += 1
            processed += 1

            if processed % 2000 == 0:
                elapsed = time.time() - START
                fps_proc = processed / elapsed
                pct_done = frame_idx / total * 100
                eta_sec = (total - frame_idx) / (processed / elapsed)
                log(f"  processed {processed} strided frames ({pct_done:.0f}%), {ball_count} balls, {fps_proc:.1f} fps_proc, ETA {eta_sec/60:.0f}min")

        frame_idx += 1

    cap.release()

    elapsed = time.time() - START
    log(f"Done: {processed} strided frames in {elapsed/60:.1f} min, {ball_count} balls")

    output_data = {
        'video': VIDEO,
        'total_frames': total,
        'stride': STRIDE,
        'ball_detections': results,
        'params': {'conf': CONF, 'iou': IOU, 'model': MODEL, 'stride': STRIDE}
    }
    with open(pklpath, 'wb') as f:
        pickle.dump(output_data, f)
    log(f"Saved: {pklpath} ({os.path.getsize(pklpath)/1024/1024:.1f}MB)")

    # Also save CSV of detections only
    import pandas as pd
    detected = [(i, r[0], r[1], r[2]) for i, r in enumerate(results) if r is not None]
    csvpath = os.path.join(OUT_DIR, f'{output_name}.csv')
    df = pd.DataFrame(detected, columns=['frame', 'cx', 'cy', 'conf'])
    df.to_csv(csvpath, index=False)
    log(f"Saved: {csvpath} ({len(df)} detections)")
    log("DONE")
