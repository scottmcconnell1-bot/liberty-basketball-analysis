"""
Extract exactly 25 benchmark frames from the 1080p NFHS video.
Uses uniform sampling across the game to capture diverse game states.
"""
import cv2
import numpy as np
import os
import csv

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_gam021ddbf1cf.mp4'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/benchmark_25'

os.makedirs(OUT_DIR, exist_ok=True)

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)

print(f"Total: {total} frames, {fps} fps")

# Uniformly sample 25 frames across the game
# Skip first 2% (pregame) and last 1% (postgame)
start = int(total * 0.02)
end = int(total * 0.99)
span = end - start

frame_nums = [int(start + i * span / 24) for i in range(25)]

csv_rows = []
for i, fn in enumerate(frame_nums):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        print(f"  SKIP F{fn} - read failed")
        continue
    
    fname = f"benchmark_{i+1:02d}_f{fn:06d}.jpg"
    out_path = f"{OUT_DIR}/{fname}"
    cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    
    seconds = fn / fps
    minutes = seconds / 60
    csv_rows.append({
        'idx': i+1,
        'frame': fn,
        'time_min': round(minutes, 1),
        'file': fname,
        'ball_x': '',
        'ball_y': '',
        'visible': '',       # Y/N
        'certainty': '',     # H/M/L
        'game_state': '',    # your label
    })
    print(f"  #{i+1:02d} F{fn:06d} @ {minutes:.1f}min")

cap.release()

# Write CSV
csv_path = f"{OUT_DIR}/labels.csv"
with open(csv_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['idx','frame','time_min','file','ball_x','ball_y','visible','certainty','game_state'])
    w.writeheader()
    w.writerows(csv_rows)

print(f"\nExtracted {len(csv_rows)} frames")
print(f"CSV: {csv_path}")
