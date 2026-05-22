#!/usr/bin/env python3
import cv2
import numpy as np
import pandas as pd
import sys
import os
from ultralytics import YOLO

def main(video_path, output_csv, conf_thresh=0.02, stride=2):
    model = YOLO('yolov8n.pt')
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video {video_path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'Video: {frame_count} frames @ {fps:.2f} fps')
    print(f'Using conf={conf_thresh}, stride={stride}')
    
    detections = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        # Run YOLO, we only need class 32 (sports ball)
        results = model(frame, classes=[32], conf=conf_thresh, verbose=False)[0]
        boxes = results.boxes
        if len(boxes) > 0:
            # pick detection with highest confidence
            confs = boxes.conf.cpu().numpy()
            best = np.argmax(confs)
            xyxy = boxes.xyxy[best].cpu().numpy()
            conf = confs[best]
            x_center = (xyxy[0] + xyxy[2]) / 2.0
            y_center = (xyxy[1] + xyxy[3]) / 2.0
            detections.append({
                'frame': frame_idx,
                'timestamp_ms': frame_idx * 1000.0 / fps,
                'x': x_center,
                'y': y_center,
                'conf': conf
            })
        frame_idx += 1
        if frame_idx % (stride*100) == 0:
            print(f'Processed {frame_idx} / {frame_count} frames')
    cap.release()
    df = pd.DataFrame(detections)
    df.to_csv(output_csv, index=False)
    print(f'Saved {len(df)} detections to {output_csv}')

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Usage: python detect_ball_full.py <video_path> <output_csv> <conf_thresh> [stride]')
        sys.exit(1)
    video_path = sys.argv[1]
    output_csv = sys.argv[2]
    conf_thresh = float(sys.argv[3])
    stride = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    main(video_path, output_csv, conf_thresh, stride)
