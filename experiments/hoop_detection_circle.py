import cv2
import numpy as np
import json
import os
import sys

video_path = sys.argv[1] if len(sys.argv) > 1 else 'uploads/Liberty_Vs_Riverstone_Q1.webm'
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError(f'Cannot open video {video_path}')
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
print(f'Video: {frame_count} frames @ {fps:.2f} fps')

stride = 8  # process every 8th frame for speed
radii = []
centers = []
frame_idx = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % stride != 0:
        frame_idx += 1
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                               param1=100, param2=30, minRadius=30, maxRadius=150)
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in range(circles.shape[1]):
            cx, cy, r = circles[0, i]
            radii.append(r)
            centers.append((cx, cy))
            break
    if frame_idx % 100 == 0:
        print(f'Processed {frame_idx}/{frame_count} frames')
    frame_idx += 1

cap.release()
print(f'Total circle detections: {len(radii)}')
if len(radii) == 0:
    raise RuntimeError('No circles detected; adjust Hough parameters')
avg_radius = np.mean(radii)
print(f'Average detected radius: {avg_radius:.1f} pixels')
# Hoop inner diameter = 1.5 ft => radius = 0.75 ft
ft_per_px = 0.75 / avg_radius
print(f'Scale: {ft_per_px:.5f} ft/px (1 px = {ft_per_px*12:.3f} in)')
# Average center
avg_center_x = int(np.mean([c[0] for c in centers]))
avg_center_y = int(np.mean([c[1] for c in centers]))
print(f'Average hoop center: ({avg_center_x}, {avg_center_y}) pixels')
data = {
    'hoop_center_px': [avg_center_x, avg_center_y],
    'hoop_radius_px': avg_radius,
    'scale_ft_per_px': ft_per_px,
    'scale_in_per_px': ft_per_px * 12,
    'num_detections': len(radii)
}
with open('hoop_params.json', 'w') as f:
    json.dump(data, f, indent=2)
print('Saved hoop_params.json')