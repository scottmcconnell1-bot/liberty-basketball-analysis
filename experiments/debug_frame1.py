#!/usr/bin/env python3
"""
Debug script for frame 001: print hoop data, raw detections, and filtering thresholds.
"""

import cv2
import numpy as np
from ultralytics import YOLO
import os

MODEL_PATH = "yolov8s.pt"
HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    return data['frame_indices'], data['centers'], data['radii']

def get_hoop(frame_idx, f_ind, cents, rads):
    idx = np.argmin(np.abs(f_ind - frame_idx))
    return cents[idx], rads[idx], f_ind[idx]

def main():
    model = YOLO(MODEL_PATH)
    f_ind, cents, rads = load_hoop()
    frame_idx = 1
    path = os.path.join(FRAME_DIR, f"frame_{frame_idx:04d}.jpg")
    img = cv2.imread(path)
    print(f"Image shape: {img.shape}")
    
    hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, f_ind, cents, rads)
    print(f"Hoop data for frame {frame_idx} (nearest hoop frame {hoop_frame_idx}):")
    print(f"  center: {hoop_center}")
    print(f"  radius_px: {hoop_radius_px}")
    
    # Constants
    HOOP_RADIUS_FT = 0.75
    BALL_DIAM_FT = 0.79
    HALF_WIDTH_FT = 6.0
    HALF_HEIGHT_FT = 8.0
    CONF_THRESH = 0.005
    
    if hoop_radius_px <= 0:
        ft_per_px = 0.005
    else:
        ft_per_px = HOOP_RADIUS_FT / hoop_radius_px
    print(f"  ft_per_px: {ft_per_px}")
    
    half_w_px = HALF_WIDTH_FT / ft_per_px
    half_h_px = HALF_HEIGHT_FT / ft_per_px
    print(f"  ROI half-width px: {half_w_px}")
    print(f"  ROI half-height px: {half_h_px}")
    print(f"  ROI x range: [{hoop_center[0] - half_w_px:.1f}, {hoop_center[0] + half_w_px:.1f}]")
    print(f"  ROI y range: [{hoop_center[1] - half_h_px:.1f}, {hoop_center[1] + half_h_px:.1f}]")
    
    expected_diam_px = BALL_DIAM_FT / ft_per_px
    print(f"  expected ball diameter px: {expected_diam_px}")
    
    # Run YOLO
    results = model(img, conf=CONF_THRESH, verbose=False)[0]
    boxes = results.boxes.xyxy.cpu().numpy()
    confs = results.boxes.conf.cpu().numpy()
    clss = results.boxes.cls.cpu().numpy()
    print(f"  Raw detections: {len(boxes)}")
    ball_mask = (clss == 32)  # sports ball
    print(f"  Sports ball class detections: {np.sum(ball_mask)}")
    ball_boxes = boxes[ball_mask]
    ball_confs = confs[ball_mask]
    for i, (box, conf) in enumerate(zip(ball_boxes, ball_confs)):
        x1, y1, x2, y2 = box
        cx = (x1 + x2)/2
        cy = (y1 + y2)/2
        width = x2 - x1
        height = y2 - y1
        diam_est = (width + height)/2
        print(f"    Ball {i}: box [{x1:.1f},{y1:.1f},{x2:.1f},{y2:.1f}] conf={conf:.3f} center=({cx:.1f},{cy:.1f}) size=({width:.1f}x{height:.1f}) diam_est={diam_est:.1f}")
        in_roi = (hoop_center[0] - half_w_px <= cx <= hoop_center[0] + half_w_px and
                  hoop_center[1] - half_h_px <= cy <= hoop_center[1] + half_h_px)
        size_ok = (0.3 * expected_diam_px <= diam_est <= 3.0 * expected_diam_px)
        print(f"      in_roi: {in_roi}, size_ok: {size_ok}")
    
    # Also draw debug image
    dbg = img.copy()
    # draw all raw detections in blue
    for box in boxes:
        x1, y1, x2, y2 = box
        cv2.rectangle(dbg, (int(x1), int(y1)), (int(x2), int(y2)), (255,0,0), 1)
    # draw ball detections in green
    for box in ball_boxes:
        x1, y1, x2, y2 = box
        cv2.rectangle(dbg, (int(x1), int(y1)), (int(x2), int(y2)), (0,255,0), 2)
    # draw hoop centre and radius
    cv2.circle(dbg, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (0,0,255), 2)
    cv2.circle(dbg, (int(hoop_center[0]), int(hoop_center[1])), 3, (255,255,255), -1)
    # draw ROI rectangle
    x1_roi = int(max(0, hoop_center[0] - half_w_px))
    y1_roi = int(max(0, hoop_center[1] - half_h_px))
    x2_roi = int(min(img.shape[1]-1, hoop_center[0] + half_w_px))
    y2_roi = int(min(img.shape[0]-1, hoop_center[1] + half_h_px))
    cv2.rectangle(dbg, (x1_roi, y1_roi), (x2_roi, y2_roi), (0,255,255), 2)
    
    out_path = f"debug_frame_{frame_idx:04d}.jpg"
    cv2.imwrite(out_path, dbg)
    print(f"Saved debug image to {out_path}")

if __name__ == "__main__":
    main()