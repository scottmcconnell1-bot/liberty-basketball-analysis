#!/usr/bin/env python3
"""
1. Detection heatmap: where does v14 say the ball is?
2. Top-20 audit: visualize the highest-confidence detections.
"""
import os, pickle, cv2
import numpy as np

OUT_DIR = 'pipeline_output/detector_audit'
os.makedirs(OUT_DIR, exist_ok=True)

model_path = 'ball_finetune/runs/finetune2/weights/best.pt'

# === Part 1: Heatmap ===
with open('pipeline_output/shot_v14.pkl', 'rb') as f:
    data = pickle.load(f)

bc_x, bc_y = data['ball_x'], data['ball_y']
bc_c = data.get('ball_conf', None)

detected = ~np.isnan(bc_x)
bx = bc_x[detected].astype(int)
by = bc_y[detected].astype(int)

# Get confidences per detection
confs = []
for i in range(len(bc_x)):
    if not np.isnan(bc_x[i]):
        # Find confidence from ball_detections list
        confs.append(0.0)  # placeholder

print(f"Total detections: {len(bx)}")

# Create heatmap on 1280x720 canvas (old Q1 clip resolution)
heatmap = np.zeros((720, 1280), dtype=np.float32)
for x, y in zip(bx, by):
    if 0 <= x < 1280 and 0 <= y < 720:
        # Add Gaussian blob at each detection
        cv2.circle(heatmap, (x, y), 15, 1, -1)

# Normalize and colorize
if heatmap.max() > 0:
    heatmap = heatmap / heatmap.max()

# Apply Gaussian blur for smooth heatmap
heatmap_blur = cv2.GaussianBlur(heatmap, (51, 51), 0)
if heatmap_blur.max() > 0:
    heatmap_blur = heatmap_blur / heatmap_blur.max()

# Colorize (jet colormap)
heatmap_uint8 = (heatmap_blur * 255).astype(np.uint8)
heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)

# Blend with a background frame
cap = cv2.VideoCapture('uploads/Liberty_Vs_Riverstone_Q1.webm')
ret, bg = cap.read()
cap.release()
if ret:
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    bg_rgb = cv2.cvtColor(bg_gray, cv2.COLOR_GRAY2BGR)
    blended = cv2.addWeighted(bg_rgb, 0.3, heatmap_color, 0.7, 0)
else:
    blended = heatmap_color

cv2.imwrite(f'{OUT_DIR}/detection_heatmap.jpg', blended)

# Also save raw heatmap
cv2.imwrite(f'{OUT_DIR}/detection_heatmap_raw.jpg', heatmap_color)
print("Heatmap saved")

# === Part 2: Top-20 highest confidence detections ===
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'
from ultralytics import YOLO

m = YOLO(model_path, verbose=False)

# Run detector on Q1 clip at very low conf to get ALL candidates
cap = cv2.VideoCapture('uploads/Liberty_Vs_Riverstone_Q1.webm')
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# Collect all detections with confidence
all_dets = []
fn = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    r = m.predict(frame, imgsz=480, conf=0.0001, iou=0.3, verbose=False)[0]
    if r.boxes is not None:
        for box in r.boxes:
            cls = m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball':
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                all_dets.append((fn, cf, x1, y1, x2, y2))
    
    fn += 1
    if fn % 500 == 0:
        print(f"  Processed {fn}/{total}, {len(all_dets)} detections so far")

cap.release()

# Sort by confidence descending
all_dets.sort(key=lambda d: d[1], reverse=True)

print(f"\nTotal detections: {len(all_dets)}")
print(f"Confidence range: [{all_dets[-1][1]:.6f}, {all_dets[0][1]:.6f}]")

# Save top 20 visualizations
cap = cv2.VideoCapture('uploads/Liberty_Vs_Riverstone_Q1.webm')
for rank, (frame_num, conf, x1, y1, x2, y2) in enumerate(all_dets[:20]):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        continue
    
    # Draw detection box (green)
    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 3)
    cv2.putText(frame, f"#{rank+1} conf={conf:.6f}", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"F{frame_num} ({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    # Draw a crosshair at detection center
    cx, cy = int((x1+x2)/2), int((y1+y2)/2)
    cv2.drawMarker(frame, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
    
    cv2.imwrite(f'{OUT_DIR}/top20_{rank+1:02d}_f{frame_num:04d}_conf{conf:.6f}.jpg', frame)

cap.release()

# Summary
print(f"\n=== TOP 20 HIGHEST CONFIDENCE DETECTIONS ===")
for rank, (frame_num, conf, x1, y1, x2, y2) in enumerate(all_dets[:20]):
    area = (x2-x1)*(y2-y1)
    print(f"  #{rank+1}: F{frame_num} conf={conf:.6f} box=({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f}) area={area:.0f}px²")

print(f"\nAudit files saved to {OUT_DIR}/")
print("  detection_heatmap.jpg - spatial heatmap of ALL v14 detections")
print("  top20_*.jpg - top 20 highest confidence detections")
