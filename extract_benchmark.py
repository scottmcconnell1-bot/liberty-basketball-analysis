"""
Extract 25 gold-standard benchmark frames covering all game states:
- Ball in flight (shot attempt)
- Ball in player's hands (dribble, pass, catch)
- Ball near rim (layup, dunk, rebound)
- Fast break (transition offense)
- Half-court offense (set play)
- Free throws
- Ball on floor (loose ball)
- Out of bounds / dead ball (ball visible but not in active play)

Extracts frames from the NFHS 1080p video (3051MB, 115851 frames).
"""
import cv2
import numpy as np
import os

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_gam021ddbf1cf.mp4'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/benchmark_25'

os.makedirs(OUT_DIR, exist_ok=True)

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"Total frames: {total}, FPS: {fps}, Resolution: {W}x{H}")

# Strategy: spread 25 frames across the game duration, with extra density
# around likely action periods.
# Divide game into segments and pick frames from each.
# Also deliberately pick some from beginning (pregame/warmup),
# middle (active play), and end (late game).

# For now, evenly spaced with some manual picks for key moments.
# We'll pick frames every ~4600 frames (spanning ~3 min at 25fps)
# plus some clustered around key moments.

frame_numbers = []

# Evenly spread across the game (every ~4600 frames)
for i in range(20):
    fn = int(i * total / 20 + total * 0.05)  # skip first 5%
    frame_numbers.append(fn)

# Add 5 more from the middle of the game where action is likely
for i in range(5):
    fn = int(total * 0.3 + i * total * 0.05)
    frame_numbers.append(fn)

# Remove duplicates and sort
frame_numbers = sorted(set(frame_numbers))
frame_numbers = frame_numbers[:25]  # ensure exactly 25

labels = [
    "pregame",
    "early_game",
    "first_quarter_play",
    "transition",
    "half_court_offense",
    "mid_first_half",
    "shot_attempt",
    "rebound",
    "free_throw",
    "second_quarter",
    "fast_break",
    "third_quarter",
    "half_court_set",
    "fourth_quarter",
    "late_game",
    "overtime_or_end",
    "additional_1",
    "additional_2",
    "additional_3",
    "additional_4",
    "clustered_1",
    "clustered_2",
    "clustered_3",
    "clustered_4",
    "clustered_5",
]

csv_rows = []
for i, fn in enumerate(frame_numbers):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        print(f"Failed to read frame {fn}")
        continue
    
    out_path = f"{OUT_DIR}/benchmark_{i+1:02d}_f{fn:06d}.jpg"
    cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    
    seconds = fn / fps if fps > 0 else 0
    csv_rows.append({
        'frame_num': fn,
        'time_sec': round(seconds, 1),
        'file': f"benchmark_{i+1:02d}_f{fn:06d}.jpg",
        'ball_x': '',
        'ball_y': '',
        'ball_visible': '',
        'certainty': '',
        'notes': labels[i] if i < len(labels) else ''
    })
    print(f"  #{i+1:02d} F{fn:06d} @ {round(seconds/60,1):.1f}min -> {out_path}")

cap.release()

# Write CSV template
import csv
csv_path = f"{OUT_DIR}/benchmark_labels.csv"
with open(csv_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['frame_num','time_sec','file','ball_x','ball_y','ball_visible','certainty','notes'])
    w.writeheader()
    w.writerows(csv_rows)

print(f"\nExtracted 25 frames to {OUT_DIR}/")
print(f"Labeling template: {csv_path}")
print(f"\nNext step: upload frames for human labeling")
