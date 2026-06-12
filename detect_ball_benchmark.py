#!/usr/bin/env python3
"""Quick detector benchmark on 2-min 1080p clip."""
import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd

VIDEO = 'videos/nfhs_1080p_clip2min.mp4'
MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
OUT_DIR = 'pipeline_output'
CONF = 0.0002
IOU = 0.3
STRIDE = 1  # every frame
COURT_X_MIN, COURT_X_MAX = 150, 1770
COURT_Y_MIN, COURT_Y_MAX = 150, 975

def log(msg):
    print(f"[{time.time()-START:.0f}s] {msg}", flush=True)

def in_court(cx, cy):
    return COURT_X_MIN <= cx <= COURT_X_MAX and COURT_Y_MIN <= cy <= COURT_Y_MAX

if __name__ == '__main__':
    START = time.time()
    from ultralytics import YOLO
    m = YOLO(MODEL, verbose=False)
    log(f"Model loaded")

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    log(f"Clip: {total} frames, {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)}")

    results = [None] * total
    frame_idx = 0
    ball_count = 0
    t_infer_total = 0
    n_infer = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % STRIDE == 0:
            t0 = time.time()
            r = m.predict(frame, conf=CONF, iou=IOU, verbose=False)[0]
            t_infer = time.time() - t0
            t_infer_total += t_infer
            n_infer += 1

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

            if best and in_court(best[0], best[1]):
                results[frame_idx] = best
                ball_count += 1

        frame_idx += 1
        if frame_idx % 500 == 0:
            fps = frame_idx / (time.time()-START)
            log(f"  {frame_idx}/{total} ({frame_idx/total*100:.0f}%), {ball_count} balls, {fps:.1f} fps")

    cap.release()
    elapsed = time.time() - START

    # Stats
    avg_infer = t_infer_total / n_infer if n_infer else 0
    non_none = [r for r in results if r is not None]
    if non_none:
        confs = [r[2] for r in non_none]
        log(f"\nBall detections: {ball_count}/{total} frames ({ball_count/total*100:.1f}%)")
        log(f"Avg inference: {avg_infer:.3f}s/frame")
        log(f"Total time: {elapsed:.1f}s for {total} frames")
        log(f"Throughput: {total/elapsed:.1f} fps")
        log(f"Full game est (stride=1): {115851*avg_infer/3600:.1f} hours")
        log(f"Conf stats: min={min(confs):.4f} med={np.median(confs):.4f} max={max(confs):.4f}")
    else:
        log("NO BALL DETECTED")

    # Save
    out_path = os.path.join(OUT_DIR, 'detections_clip_1080p.pkl')
    with open(out_path, 'wb') as f:
        pickle.dump({'video': VIDEO, 'total_frames': total, 'stride': STRIDE,
                     'ball_detections': results, 'model': MODEL, 'conf': CONF}, f)
    log(f"Saved: {out_path}")

    # Quick visual — annotate frames 100-120
    cap = cv2.VideoCapture(VIDEO)
    for fn in range(100, min(120, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if not ret: continue
        if results[fn]:
            cx, cy, cf = results[fn]
            cv2.circle(frame, (int(cx), int(cy)), 20, (0, 255, 0), 3)
            cv2.putText(frame, f"F{fn} conf={cf:.3f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imwrite(f'{OUT_DIR}/clip_audit_{fn:04d}.jpg', frame)
    cap.release()
    log("Audit frames saved")

    log("DONE")
