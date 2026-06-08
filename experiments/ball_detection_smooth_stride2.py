#!/usr/bin/env python3
import cv2
import numpy as np
import pandas as pd
import sys
import os
from ultralytics import YOLO

def main(video_path, output_csv, conf_thresh=0.2):
    # Load YOLOv8 model (nano)
    model = YOLO('yolov8n.pt')
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video {video_path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print('Video: {} frames @ {:.2f} fps'.format(frame_count, fps))
    
    detections = []  # list of dict per frame: frame, timestamp_ms, x, y, conf
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Run YOLO, we only need class 32 (sports ball)
        results = model(frame, classes=[32], conf=conf_thresh, verbose=False)[0]
        boxes = results.boxes
        if len(boxes) > 0:
            # pick detection with highest confidence
            confs = boxes.conf.cpu().numpy()
            idx = np.argmax(confs)
            box = boxes.xyxy[idx].cpu().numpy()
            x1, y1, x2, y2 = box
            xc = (x1 + x2) / 2.0
            yc = (y1 + y2) / 2.0
            conf = float(confs[idx])
        else:
            xc = yc = conf = np.nan
        timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        detections.append({
            'frame': frame_idx,
            'timestamp_ms': timestamp_ms,
            'ball_x_px': xc,
            'ball_y_px': yc,
            'ball_conf': conf
        })
        frame_idx += 1
        if frame_idx % 100 == 0:
            print('Processed {} / {} frames'.format(frame_idx, frame_count))
    cap.release()
    df = pd.DataFrame(detections)
    # Interpolate missing values (linear) then apply moving average
    df['ball_x_px'] = df['ball_x_px'].interpolate(limit_direction='both')
    df['ball_y_px'] = df['ball_y_px'].interpolate(limit_direction='both')
    # Moving average window 5
    window = 5
    df['ball_x_smooth'] = df['ball_x_px'].rolling(window=window, center=True, min_periods=1).mean()
    df['ball_y_smooth'] = df['ball_y_px'].rolling(window=window, center=True, min_periods=1).mean()
    # Save
    df.to_csv(output_csv, index=False)
    print('Saved ball detections to {}'.format(output_csv))
    # Also compute basic stats
    valid = df['ball_conf'].notna()
    print('Frames with detection: {} / {}'.format(valid.sum(), len(df)))
    print('Average confidence when detected: {:.3f}'.format(df.loc[valid, 'ball_conf'].mean()))

if __name__ == '__main__':
    video_path = sys.argv[1] if len(sys.argv) > 1 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
    output_csv = sys.argv[2] if len(sys.argv) > 2 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_smooth.csv'
    conf_thresh = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
    main(video_path, output_csv, conf_thresh)