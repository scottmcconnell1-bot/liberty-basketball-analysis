#!/usr/bin/env python3
import cv2
import numpy as np
import json
import os

video_path = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
if not os.path.exists(video_path):
    print(f"Video not found: {video_path}")
    exit(1)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Error opening video")
    exit(1)

frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
print(f'Frames: {frame_count}, FPS: {fps}')

# Sample every N frames (e.g., 2 seconds)
sample_interval = int(round(fps * 2.0))  # 2 seconds
if sample_interval < 1:
    sample_interval = 1

detections = []
sampled = 0
for frame_idx in range(0, frame_count, sample_interval):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Blur to reduce noise
    blurred = cv2.medianBlur(gray, 5)
    # Detect circles
    circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
                               param1=50, param2=20, minRadius=70, maxRadius=180)
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for circle in circles[0, :]:
            detections.append((circle[0], circle[1], circle[2]))
    sampled += 1
    if sampled % 20 == 0:
        print(f'Sampled {sampled} frames, {len(detections)} detections so far')
cap.release()
print(f'Total sampled frames: {sampled}, total detections: {len(detections)}')

if len(detections) == 0:
    print('No hoop detections found')
    exit(1)

detections = np.array(detections)
centers = detections[:, :2]
radii = detections[:, 2]

# Filter outliers: keep radii within 2 std of median
med_r = np.median(radii)
std_r = np.std(radii)
mask = np.abs(radii - med_r) <= 2 * std_r
if np.sum(mask) < 5:
    mask = np.ones(len(radii), dtype=bool)  # fallback
centers_f = centers[mask]
radii_f = radii[mask]

median_center = np.median(centers_f, axis=0)
median_radius = np.median(radii_f)

print(f'Filtered median hoop center (x,y): {median_center}')
print(f'Filtered median radius: {median_radius} px')

# Compute scale assuming real inner radius 0.75 ft (hoop radius)
scale_ft_per_px = 0.75 / median_radius
print(f'Scale ft/px: {scale_ft_per_px}')

# Prepare hoop params
hoop_params = {
    'hoop_center_px': median_center.tolist(),
    'hoop_radius_px': float(median_radius),
    'scale_ft_per_px': float(scale_ft_per_px),
    'scale_in_per_px': float(scale_ft_per_px * 12),
    'num_detections': int(len(centers_f))
}

out_path = 'hoop_params.json'
with open(out_path, 'w') as f:
    json.dump(hoop_params, f, indent=2)
print(f'Saved hoop parameters to {out_path}')