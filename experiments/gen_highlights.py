#!/usr/bin/env python3
"""
Generate a highlight video showing candidate shot frames.
For each high-speed event, extract±15 frames and mark the ball position.
Save as a short webm that Scott can review.
"""

import csv, numpy as np, cv2, os

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
BALL_CSV = "ball_v5_per_frame.csv"
OUT_PATH = "shot_highlights.mp4"
FPS_OUT = 10

dets = []
with open(BALL_CSV) as f:
    reader = csv.DictReader(f)
    for row in reader:
        dets.append({'f': int(row['frame']), 'cx': float(row['cx']), 'cy': float(row['cy']), 'diam': float(row['diam'])})

det_lookup = {d['f']: d for d in dets}

# Get high-speed cluster frames > 100 px/frame (more lenient)
fast_frames = set()
for i in range(1, len(dets)):
    f0, f1 = dets[i-1], dets[i]
    dt = f1['f'] - f0['f']
    if dt > 10: continue
    dist = np.sqrt((f1['cx']-f0['cx'])**2 + (f1['cy']-f0['cy'])**2)
    speed = dist / dt if dt > 0 else 0
    if speed > 120:
        fast_frames.add(f1['f'])

# Cluster within 15 frames
fast_sorted = sorted(fast_frames)
clusters = []
i = 0
while i < len(fast_sorted):
    group = [fast_sorted[i]]
    j = i + 1
    while j < len(fast_sorted) and fast_sorted[j] - group[-1] < 15:
        group.append(fast_sorted[j]); j += 1
    clusters.append(group[len(group)//2])  # midpoint frame
    i = j

print(f'Highlight frames: {len(clusters)}')
print(f'Frames: {clusters[:30]}...')

# Extract ±10 frames around each cluster midpoint
HIGHLIGHT_RADIUS = 10
all_frames = set()
for mid in clusters:
    for fi in range(mid - HIGHLIGHT_RADIUS, mid + HIGHLIGHT_RADIUS + 1):
        all_frames.add(fi)

# Read video and extract frames
cap = cv2.VideoCapture(VIDEO_PATH)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(OUT_PATH, fourcc, FPS_OUT, (w, h))

frame_idx = 0
saved = 0
while True:
    ret, frame = cap.read()
    if not ret: break
    
    if frame_idx in all_frames:
        # Draw ball position if detected
        if frame_idx in det_lookup:
            d = det_lookup[frame_idx]
            cv2.circle(frame, (int(d['cx']), int(d['cy'])), int(d['diam']/2), (0,255,0), 2)
            cv2.circle(frame, (int(d['cx']), int(d['cy'])), 2, (0,0,255), -1)
        
        # Label if this is a cluster midpoint
        is_mid = frame_idx in set(clusters)
        color = (0,0,255) if is_mid else (0,255,0)
        label = "SHOT CANDIDATE" if is_mid else ""
        cv2.putText(frame, f"F{frame_idx} {label}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7 if is_mid else 0.5, color, 2 if is_mid else 1)
        out.write(frame)
        saved += 1
    
    frame_idx += 1

cap.release()
out.release()
print(f"\nSaved {saved} frames to {OUT_PATH}")
print(f"File size: {os.path.getsize(OUT_PATH) / 1024 / 1024:.1f} MB")
