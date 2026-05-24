#!/usr/bin/env python3
"""
Filtered ball detection for sample frames.
- Uses fine-tuned YOLOv8s (best.pt)
- Applies hoop-based ROI (per-frame from hoop_Q1.npy)
- Tight orange/brown colour mask
- Aspect ratio & size filter (based on hoop radius)
- Optional template match (normalized cross-correlation)
- ByteTrack linking (optional, not implemented for sample frames)
"""

import cv2
import numpy as np
from ultralytics import YOLO
import os
import json

# Paths
MODEL_PATH = "runs/detect/train-2/weights/best.pt"
HOOP_PATH = "hoop_Q1.npy"
SAMPLE_FRAMES_DIR = "sample_frames"
OUTPUT_DIR = "sample_frames_filtered"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Parameters
CONF_THRESH = 0.15  # detection confidence
# Colour ranges in HSV (H 0-180, S 0-255, V 0-255)
ORANGE_LOW = np.array([10, 150, 150])
ORANGE_HIGH = np.array([30, 255, 255])
BROWN_LOW = np.array([0, 80, 80])
BROWN_HIGH = np.array([20, 150, 150])
MIN_COLOUR_RATIO = 0.25  # at least 25% of box pixels must be orange/brown
ASPECT_MIN, ASPECT_MAX = 0.7, 1.3
# Size filter will be computed per frame from hoop radius
# Template match
USE_TEMPLATE = True
TEMPLATE_THRESH = 0.4

def load_hoop_data():
    hoop_raw = np.load(HOOP_PATH, allow_pickle=True).item()
    frame_indices = hoop_raw['frame_indices']  # array of frame numbers
    centers = hoop_raw['centers']              # (N,2) float
    radii = hoop_raw['radii']                  # (N,) float
    return frame_indices, centers, radii

def get_hoop_for_frame(frame_idx, frame_indices, centers, radii):
    # Find nearest hoop entry by frame index
    idx = np.argmin(np.abs(frame_indices - frame_idx))
    return centers[idx], radii[idx], frame_indices[idx]

def create_template(diameter):
    # Binary circle template
    size = int(diameter) + 2
    template = np.zeros((size, size), dtype=np.uint8)
    cx = cy = size // 2
    radius = diameter // 2
    cv2.circle(template, (cx, cy), radius, 255, -1)
    return template.astype(np.float32)

def colour_mask_ratio(roi_hsv):
    mask_orange = cv2.inRange(roi_hsv, ORANGE_LOW, ORANGE_HIGH)
    mask_brown = cv2.inRange(roi_hsv, BROWN_LOW, BROWN_HIGH)
    mask = cv2.bitwise_or(mask_orange, mask_brown)
    return np.count_nonzero(mask) / mask.size

def main():
    model = YOLO(MODEL_PATH)
    frame_indices, centers, radii = load_hoop_data()
    
    # Get list of sample frames
    sample_files = sorted([f for f in os.listdir(SAMPLE_FRAMES_DIR) if f.endswith('.jpg') and not f.endswith('_det.jpg') and not f.endswith('_det_orange.jpg') and not f.endswith('_orange.jpg')])
    print(f"Found {len(sample_files)} sample frames: {sample_files}")
    
    for fname in sample_files:
        frame_num = int(fname.split('_')[1].split('.')[0])  # frame_001.jpg -> 1
        img_path = os.path.join(SAMPLE_FRAMES_DIR, fname)
        img = cv2.imread(img_path)
        if img is None:
            print(f"Failed to load {img_path}")
            continue
        
        # Run YOLO detection
        results = model(img, conf=CONF_THRESH, verbose=False)[0]
        boxes = results.boxes.xyxy.cpu().numpy()  # (N,4) x1,y1,x2,y2
        confs = results.boxes.conf.cpu().numpy()
        classes = results.boxes.cls.cpu().numpy()  # should be 0 for ball if model trained correctly
        
        # Get hoop data for this frame (nearest)
        hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop_for_frame(frame_num, frame_indices, centers, radii)
        # Scale: ft per px from hoop radius (known inner radius = 0.75 ft)
        ft_per_px = 0.75 / hoop_radius_px if hoop_radius_px > 0 else 0.005  # fallback
        
        # ROI half-sizes in ft -> convert to px
        half_width_ft = 4.0   # +/- 4 ft horizontally from hoop
        half_height_ft = 6.0  # +/- 6 ft vertically
        half_width_px = half_width_ft / ft_per_px
        half_height_px = half_height_ft / ft_per_px
        
        # Prepare template if needed
        if USE_TEMPLATE:
            # Use average detected box size? We'll compute per box later.
            pass
        
        filtered_boxes = []
        filtered_confs = []
        filtered_clses = []
        
        for (x1, y1, x2, y2), conf, cls in zip(boxes, confs, classes):
            # 1. Hoop ROI filter
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            if not (hoop_center[0] - half_width_px <= cx <= hoop_center[0] + half_width_px and
                    hoop_center[1] - half_height_px <= cy <= hoop_center[1] + half_height_px):
                continue
            
            # 2. Colour mask ratio
            x1i, y1i, x2i, y2i = map(int, [x1, y1, x2, y2])
            # Clamp to image bounds
            x1i = max(0, x1i); y1i = max(0, y1i)
            x2i = min(img.shape[1]-1, x2i); y2i = min(img.shape[0]-1, y2i)
            if x2i <= x1i or y2i <= y1i:
                continue
            roi = img[y1i:y2i, x1i:x2i]
            if roi.size == 0:
                continue
            roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            colour_ratio = colour_mask_ratio(roi_hsv)
            if colour_ratio < MIN_COLOUR_RATIO:
                continue
            
            # 3. Aspect ratio
            width = x2 - x1
            height = y2 - y1
            if width <= 0 or height <= 0:
                continue
            aspect = width / height
            if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
                continue
            
            # 4. Size filter based on hoop radius: expected ball diameter in px
            # Known ball diameter = 0.25 ft (radius 0.125 ft? Wait: basketball diameter ~9.5 inches = 0.79 ft)
            # Actually NBA ball diameter ~9.5 inches = 0.7917 ft, radius 0.3958 ft.
            # But we can use ratio: ball diameter / hoop radius = (0.7917 ft) / (0.75 ft) ≈ 1.0556
            # So expected ball diameter in px ≈ hoop_radius_px * 1.0556 * 2? Wait hoop_radius_px is radius of hoop.
            # Hoop inner radius = 0.75 ft. So scale ft/px = 0.75 / hoop_radius_px.
            # Ball diameter in ft = 0.7917 ft => diameter_px = 0.7917 / (ft_per_px) = 0.7917 * hoop_radius_px / 0.75 = hoop_radius_px * (0.7917/0.75) ≈ hoop_radius_px * 1.0556
            expected_diam_px = hoop_radius_px * 1.0556
            # Accept range 0.5x to 1.5x expected diameter
            diam_px = (width + height) / 2.0
            if not (0.5 * expected_diam_px <= diam_px <= 1.5 * expected_diam_px):
                continue
            
            # 5. Template match (optional)
            if USE_TEMPLATE:
                # Create template of size expected_diam_px
                template = create_template(expected_diam_px)
                # Resize roi to template size for TM_CCOEFF_NORMED
                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                roi_resized = cv2.resize(roi_gray, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_LINEAR)
                # Normalize
                res = cv2.matchTemplate(roi_resized, template, cv2.TM_CCOEFF_NORMED)
                if res < TEMPLATE_THRESH:
                    continue
            
            # Passed all filters
            filtered_boxes.append([x1, y1, x2, y2])
            filtered_confs.append(conf)
            filtered_clses.append(cls)
        
        print(f"Frame {frame_num}: {len(boxes)} raw detections -> {len(filtered_boxes)} after filtering")
        
        # Draw filtered boxes on image
        for (x1, y1, x2, y2), conf in zip(filtered_boxes, filtered_confs):
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(img, f"{conf:.2f}", (int(x1), int(y1)-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        
        # Also draw hoop centre and radius for reference
        cv2.circle(img, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (255,0,0), 2)
        cv2.circle(img, (int(hoop_center[0]), int(hoop_center[1])), 3, (0,0,255), -1)
        
        out_path = os.path.join(OUTPUT_DIR, f"frame_{frame_num:03d}_filtered.jpg")
        cv2.imwrite(out_path, img)
        print(f"Saved {out_path}")
    
    print("Done.")

if __name__ == "__main__":
    main()