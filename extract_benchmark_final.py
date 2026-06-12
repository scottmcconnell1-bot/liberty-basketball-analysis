"""
Extract 25 benchmark frames for ball detection evaluation.
Strategy: Since we CAN'T use the detector to find balls (it's broken),
we manually pick frames from different game phases where a human
can verify ball presence.

Approach:
- 4 quarters ≈ 77 min game at 25fps = 115,851 frames
- Pick ~4 frames from each quarter (early/mid/late)
- Add extras for free throws and dead-ball periods
- Total: 25 frames covering all game states

Frame selection is HUMAN-GUIDED, not detector-based.
"""
import cv2
import os
import csv

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_4K_gam021ddbf1cf.mp4'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/benchmark_25_final'
os.makedirs(OUT, exist_ok=True)

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"{total} frames, {fps}fps, {W}x{H}")

# Divide game into ~4 quarters + overtime
# Total ~77 min = 4620 seconds at 25fps ≈ 115,500 frames
# Q1: frames 0-28900 (0-19min)
# Q2: frames 28900-57800 (19-38min)
# Q3: frames 57800-86700 (38-57min)
# Q4: frames 86700-total (57-77min)

boundaries = [
    ("Q1_early", int(total * 0.05), int(total * 0.15)),
    ("Q1_mid", int(total * 0.15), int(total * 0.25)),
    ("Q2_early", int(total * 0.25), int(total * 0.35)),
    ("Q2_mid", int(total * 0.35), int(total * 0.45)),
    ("Q3_early", int(total * 0.45), int(total * 0.55)),
    ("Q3_mid", int(total * 0.55), int(total * 0.65)),
    ("Q4_early", int(total * 0.65), int(total * 0.75)),
    ("Q4_mid", int(total * 0.75), int(total * 0.85)),
]

# Pick 3 frames from each of 8 game phases = 24 frames
# Plus 1 pregame/warmup frame
import random
random.seed(42)

csv_rows = []
idx = 0

# Pregame frame
fn = int(total * 0.02)
cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
ret, frame = cap.read()
if ret:
    fname = f"benchmark_{idx+1:02d}_f{fn:06d}.jpg"
    cv2.imwrite(f"{OUT}/{fname}", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    csv_rows.append({'idx': idx+1, 'frame': fn, 'time_min': round(fn/fps/60,1), 'file': fname, 'phase': 'pregame', 'ball_x': '', 'ball_y': '', 'visible': '', 'certainty': ''})
    idx += 1

# 3 frames per phase
for phase, start, end in boundaries:
    span = end - start
    for j in range(3):
        fn = start + int(span * (j + 0.5) / 3)
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if not ret:
            continue
        fname = f"benchmark_{idx+1:02d}_f{fn:06d}.jpg"
        cv2.imwrite(f"{OUT}/{fname}", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        csv_rows.append({'idx': idx+1, 'frame': fn, 'time_min': round(fn/fps/60,1), 'file': fname, 'phase': phase, 'ball_x': '', 'ball_y': '', 'visible': '', 'certainty': ''})
        idx += 1

# End of game
fn = int(total * 0.95)
cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
ret, frame = cap.read()
if ret:
    fname = f"benchmark_{idx+1:02d}_f{fn:06d}.jpg"
    cv2.imwrite(f"{OUT}/{fname}", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    csv_rows.append({'idx': idx+1, 'frame': fn, 'time_min': round(fn/fps/60,1), 'file': fname, 'phase': 'end_game', 'ball_x': '', 'ball_y': '', 'visible': '', 'certainty': ''})
    idx += 1

cap.release()

# Write CSV
csv_path = f"{OUT}/benchmark_labels.csv"
with open(csv_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['idx','frame','time_min','file','phase','ball_x','ball_y','visible','certainty'])
    w.writeheader()
    w.writerows(csv_rows)

print(f"Extracted {idx} benchmark frames to {OUT}/")
print(f"CSV: {csv_path}")
for r in csv_rows:
    print(f"  #{r['idx']:02d} F{r['frame']:06d} @ {r['time_min']:.1f}min [{r['phase']}]")
