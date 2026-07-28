#!/usr/bin/env python3
import cv2
import numpy as np
import pandas as pd
import sys
import os
import json
from ultralytics import YOLO

def main(video_path, output_csv, conf_thresh=0.2, stride=2, smoothing_window=5):
    # Load hoop parameters for scaling
    hoop_params_path = 'hoop_params.json'
    with open(hoop_params_path, 'r') as f:
        hoop_params = json.load(f)
    scale_ft_per_px = hoop_params['scale_ft_per_px']
    
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
        # Process only every stride-th frame
        if frame_idx % stride == 0:
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
        else:
            # Still need to advance frame count but no detection
            # We'll store NaN later when building dataframe for all frames
            pass
        frame_idx += 1
        if frame_idx % 100 == 0:
            print('Processed {} / {} frames'.format(frame_idx, frame_count))
    cap.release()
    
    # Build dataframe for all frames (including skipped ones as NaN)
    # We'll create a list of dicts for all frames, filling NaN for skipped
    all_frames = []
    # We have detections only for processed frames; we need to map them
    # Let's create arrays of length frame_count initialized to NaN
    ball_x_px_all = np.full(frame_count, np.nan)
    ball_y_px_all = np.full(frame_count, np.nan)
    ball_conf_all = np.full(frame_count, np.nan)
    timestamp_ms_all = np.zeros(frame_count)
    
    # Fill in the processed frames
    for det in detections:
        f = det['frame']
        ball_x_px_all[f] = det['ball_x_px']
        ball_y_px_all[f] = det['ball_y_px']
        ball_conf_all[f] = det['ball_conf']
        timestamp_ms_all[f] = det['timestamp_ms']
    
    # For timestamps of skipped frames, we can compute based on frame index and fps
    # But we already captured timestamp_ms at processing time; for simplicity, we'll compute:
    for f in range(frame_count):
        if np.isnan(timestamp_ms_all[f]):
            timestamp_ms_all[f] = (f / fps) * 1000 if fps > 0 else 0
    
    df = pd.DataFrame({
        'frame': range(frame_count),
        'timestamp_ms': timestamp_ms_all,
        'ball_x_px': ball_x_px_all,
        'ball_y_px': ball_y_px_all,
        'ball_conf': ball_conf_all
    })
    
    # Interpolate missing values (linear) then apply moving average
    df['ball_x_px'] = df['ball_x_px'].interpolate(limit_direction='both')
    df['ball_y_px'] = df['ball_y_px'].interpolate(limit_direction='both')
    # Moving average window 5
    window = smoothing_window
    df['ball_x_smooth'] = df['ball_x_px'].rolling(window=window, center=True, min_periods=1).mean()
    df['ball_y_smooth'] = df['ball_y_px'].rolling(window=window, center=True, min_periods=1).mean()
    
    # Convert to feet
    df['ball_x_ft'] = df['ball_x_smooth'] * scale_ft_per_px
    df['ball_y_ft'] = df['ball_y_smooth'] * scale_ft_per_px
    
    # Save
    output_cols = ['frame', 'timestamp_ms', 'ball_x_px', 'ball_y_px', 'ball_x_ft', 'ball_y_ft']
    df[output_cols].to_csv(output_csv, index=False)
    print('Saved ball detections to {}'.format(output_csv))
    # Also compute basic stats
    valid = df['ball_conf'].notna()
    print('Frames with detection: {} / {}'.format(valid.sum(), len(df)))
    print('Average confidence when detected: {:.3f}'.format(df.loc[valid, 'ball_conf'].mean()))

if __name__ == '__main__':
    video_path = sys.argv[1] if len(sys.argv) > 1 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
    output_csv = sys.argv[2] if len(sys.argv) > 2 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_smooth.csv'
    conf_thresh = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
    stride = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    smoothing_window = int(sys.argv[5]) if len(sys.argv) > 5 else 5
    main(video_path, output_csv, conf_thresh, stride, smoothing_window)