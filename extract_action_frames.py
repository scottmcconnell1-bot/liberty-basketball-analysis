"""
Extract targeted benchmark frames for specific game states.
Uses scene detection to find likely action moments, then picks frames
from different game phases.
"""
import cv2
import numpy as np
import os

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_gam021ddbf1cf.mp4'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/benchmark_25'

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))  # height
H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))   # width

print(f"Total: {total} frames, {fps} fps, {W}x{H}")

# Use scene detection to find moments of high activity (likely game action)
# Compare histogram differences between consecutive frames
# High difference = scene change or fast motion

print("Scanning for high-activity frames...")
sample_interval = 25  # check every second
diffs = []

prev_hist = None
for fn in range(0, total, sample_interval):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        break
    
    # Downscale for speed
    small = cv2.resize(frame, (320, 180))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    
    if prev_hist is not None:
        diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
        diffs.append((fn, diff))
    
    prev_hist = hist

# Sort by difference (highest = most scene change / motion)
diffs.sort(key=lambda x: x[1], reverse=True)

# Take top 30 high-activity frames, then filter to ensure minimum spacing
min_spacing = int(fps * 10)  # at least 10 seconds apart
selected = []
for fn, diff in diffs:
    if all(abs(fn - s) >= min_spacing for s in selected):
        selected.append(fn)
    if len(selected) >= 30:
        break

selected.sort()
print(f"Selected {len(selected)} high-activity frames")

# Now extract these frames
import csv

csv_rows = []
for i, fn in enumerate(selected):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue
    
    out_path = f"{OUT_DIR}/action_{i+1:02d}_f{fn:06d}.jpg"
    cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    
    seconds = fn / fps
    csv_rows.append({
        'frame_num': fn,
        'time_sec': round(seconds, 1),
        'file': f"action_{i+1:02d}_f{fn:06d}.jpg",
        'ball_x': '',
        'ball_y': '',
        'ball_visible': '',
        'certainty': '',
        'notes': f'high_activity_scene_change'
    })
    print(f"  action #{i+1:02d} F{fn:06d} @ {round(seconds/60,1):.1f}min (diff={diffs[i][1]:.3f})")

cap.release()

# Append to existing CSV
csv_path = f"{OUT_DIR}/benchmark_labels.csv"
with open(csv_path, 'a', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['frame_num','time_sec','file','ball_x','ball_y','ball_visible','certainty','notes'])
    w.writerows(csv_rows)

print(f"\nExtracted {len(csv_rows)} action frames")
print(f"Total frames in benchmark: {19 + len(csv_rows)}")
print(f"CSV: {csv_path}")
