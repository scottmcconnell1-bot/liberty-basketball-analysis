import cv2
import numpy as np
import json
import os

video_path = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
template_path = 'hoop_template.png'

# Load template
template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
if template is None:
    raise FileNotFoundError(f'Template not found at {template_path}')
t_h, t_w = template.shape[:2]
print(f'Template size: {t_w}x{t_h} pixels')

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError(f'Cannot open video {video_path}')
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
print(f'Video: {frame_count} frames @ {fps:.2f} fps')

stride = 4  # process every 4th frame for speed
matches = []
widths = []
heights = []
confidences = []

frame_idx = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % stride != 0:
        frame_idx += 1
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val > 0.3:  # confidence threshold
        matches.append((frame_idx, max_val, max_loc))
        widths.append(t_w)
        heights.append(t_h)
        confidences.append(max_val)
    if frame_idx % 100 == 0:
        print(f'Processed {frame_idx}/{frame_count} frames')
    frame_idx += 1

cap.release()
print(f'Total matches: {len(matches)}')
if len(matches) == 0:
    raise RuntimeError('No hoop matches found; try lowering threshold or different template')
avg_width = np.mean(widths)
avg_height = np.mean(heights)
avg_conf = np.mean(confidences)
print(f'Average template match size: {avg_width:.1f} x {avg_height:.1f} px (conf={avg_conf:.2f})')

# Assume hoop diameter is 1.5 ft (inner diameter). Use width as diameter.
ft_per_px = 1.5 / avg_width
print(f'Scale: {ft_per_px:.5f} ft/px (1 px = {ft_per_px*12:.3f} in)')

# Estimate hoop center from matches (average location)
xs = [loc[0] + t_w//2 for _, _, loc in matches]
ys = [loc[1] + t_h//2 for _, _, loc in matches]
center_x = int(np.mean(xs))
center_y = int(np.mean(ys))
print(f'Average hoop center: ({center_x}, {center_y}) pixels')

data = {
    'hoop_center_px': [center_x, center_y],
    'hoop_width_px': avg_width,
    'hoop_height_px': avg_height,
    'scale_ft_per_px': ft_per_px,
    'scale_in_per_px': ft_per_px * 12,
    'num_matches': len(matches),
    'avg_confidence': avg_conf
}
with open('hoop_params.json', 'w') as f:
    json.dump(data, f, indent=2)
print('Saved hoop_params.json')