"""
Detect score scoreboard changes in the NFHS video to find basketball event anchors.
The scoreboard region should be relatively stable in the frame since the camera
auto-tracks but the scoreboard is at a fixed position (usually top or bottom).

Strategy:
1. Sample frames every 5 seconds
2. Crop a region where the scoreboard is likely located (usually top of frame)
3. Use simple frame differencing to detect score changes
4. Output timestamps where score likely changed
"""
import cv2
import numpy as np
import os

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_gam021ddbf1cf.mp4'
OUTPUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/scoreboard_changes.csv'

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"{total} frames, {fps}fps, {W}x{H}")

# Scoreboard is typically in the top portion of the frame
# Crop top 15% of frame where scoreboard graphics appear
y_start = 0
y_end = int(H * 0.15)
x_start = int(W * 0.2)
x_end = int(W * 0.8)

print(f"Scoreboard ROI: x=[{x_start},{x_end}], y=[{y_start},{y_end}]")

prev_hist = None
changes = []
sample_interval = int(fps * 5)  # sample every 5 seconds

for fn in range(0, total, sample_interval):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        break
    
    roi = frame[y_start:y_end, x_start:x_end]
    
    # Convert to grayscale histogram
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    
    if prev_hist is not None:
        # Correlation: 1.0 = identical, 0.0 = completely different
        corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
        if corr < 0.95:  # scoreboard content changed
            seconds = fn / fps
            minutes = seconds / 60
            changes.append({
                'frame': fn,
                'time_sec': round(seconds, 1),
                'time_min': round(minutes, 2),
                'correlation': round(corr, 4)
            })
            print(f"Change at {minutes:.1f}min (F{fn}, corr={corr:.4f})")
    
    prev_hist = hist

cap.release()

# Write results
import csv
with open(OUTPUT, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['frame','time_sec','time_min','correlation'])
    w.writeheader()
    w.writerows(changes)

print(f"\nFound {len(changes)} scoreboard changes")
print(f"Saved to {OUTPUT}")
