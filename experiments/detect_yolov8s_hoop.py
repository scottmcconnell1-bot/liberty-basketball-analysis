#!/usr/bin/env python3
"""
Ball detection using pretrained YOLOv8s (sports ball class) with hoop ROI and size filtering.
"""

import cv2
import numpy as np
from ultralytics import YOLO
import os

MODEL_PATH = "yolov8s.pt"  # pretrained COCO
HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"
OUT_DIR = "sample_frames_yolov8s_hoop_filtered"
os.makedirs(OUT_DIR, exist_ok=True)

# Parameters
CONF_THRESH = 0.005  # low to catch ball
# Hoop ROI in feet
HALF_WIDTH_FT = 6.0   # increased to be safe
HALF_HEIGHT_FT = 8.0
# Known hoop inner radius ft
HOOP_RADIUS_FT = 0.75
BALL_DIAM_FT = 0.79   # ~9.5 inches

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    return data['frame_indices'], data['centers'], data['radii']

def get_hoop(frame_idx, f_ind, cents, rads):
    idx = np.argmin(np.abs(f_ind - frame_idx))
    return cents[idx], rads[idx], f_ind[idx]

def main():
    model = YOLO(MODEL_PATH)
    f_ind, cents, rads = load_hoop()
    print(f"Hoop data: {len(f_ind)} frames")
    
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])
    for fname in files:
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        
        hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, f_ind, cents, rads)
        if hoop_radius_px <= 0:
            ft_per_px = 0.005
        else:
            ft_per_px = HOOP_RADIUS_FT / hoop_radius_px
        
        half_w_px = HALF_WIDTH_FT / ft_per_px
        half_h_px = HALF_HEIGHT_FT / ft_per_px
        
        # Expected ball diameter in px
        expected_diam_px = BALL_DIAM_FT / ft_per_px
        
        # Run YOLO
        results = model(img, conf=CONF_THRESH, verbose=False)[0]
        boxes = results.boxes.xyxy.cpu().numpy()
        confs = results.boxes.conf.cpu().numpy()
        clss = results.boxes.cls.cpu().numpy()
        
        # Filter for sports ball class (class id 32 in COCO)
        ball_mask = (clss == 32)
        boxes = boxes[ball_mask]
        confs = confs[ball_mask]
        
        # Further filter by hoop ROI and size
        filtered = []
        for (x1, y1, x2, y2), conf in zip(boxes, confs):
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            if not (hoop_center[0] - half_w_px <= cx <= hoop_center[0] + half_w_px and
                    hoop_center[1] - half_h_px <= cy <= hoop_center[1] + half_h_px):
                continue
            width = x2 - x1
            height = y2 - y1
            if width <= 0 or height <= 0:
                continue
            # size filter: expect diameter around expected_diam_px
            diam_est = (width + height) / 2.0
            if not (0.3 * expected_diam_px <= diam_est <= 3.0 * expected_diam_px):  # generous
                continue
            filtered.append(((x1, y1, x2, y2), conf))
        
        print(f"Frame {frame_idx}: {len(boxes)} raw ball detections -> {len(filtered)} after ROI/size")
        
        # Draw
        for (x1, y1, x2, y2), conf in filtered:
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0,255,0), 2)
            cv2.putText(img, f"{conf:.2f}", (int(x1), int(y1)-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
        # Draw hoop centre and ROI
        cv2.circle(img, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (255,0,0), 2)
        cv2.circle(img, (int(hoop_center[0]), int(hoop_center[1])), 3, (0,0,255), -1)
        # ROI rectangle
        x1_roi = int(max(0, hoop_center[0] - half_w_px))
        y1_roi = int(max(0, hoop_center[1] - half_h_px))
        x2_roi = int(min(img.shape[1]-1, hoop_center[0] + half_w_px))
        y2_roi = int(min(img.shape[0]-1, hoop_center[1] + half_h_px))
        cv2.rectangle(img, (x1_roi, y1_roi), (x2_roi, y2_roi), (255,255,0), 1)
        
        out_path = os.path.join(OUT_DIR, f"frame_{frame_idx:03d}_yolov8s_hoop.jpg")
        cv2.imwrite(out_path, img)
        print(f"Saved {out_path}")

if __name__ == "__main__":
    main()