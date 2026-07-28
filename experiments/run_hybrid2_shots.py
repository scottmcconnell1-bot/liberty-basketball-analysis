"""
Shot detection v3: Ball-hoop proximity + gap analysis.
"""
import cv2, numpy as np, pickle
import pandas as pd
from ultralytics import YOLO
from collections import defaultdict

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

# ---- Step 1: Load ball detections ----
print("Loading ball detections...")
balls = pd.read_csv(OUT + '/hybrid2_ball_detections.csv')
print("  %d detections" % len(balls))

# ---- Step 2: Detect hoops using YOLO abdullahtarek ----
print("\nDetecting hoops (every 5th frame)...")
ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

hoops_by_frame = {}
fn = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    if fn % 5 == 0:
        r = ball_m.predict(frame, conf=0.05, verbose=False)[0]
        if r.boxes is not None:
            for box in r.boxes:
                cls = ball_m.names[int(box.cls[0])]
                cf = float(box.conf[0])
                if cls == 'Hoop' and cf > 0.05:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cx, cy = (x1+x2)/2, (y1+y2)/2
                    if fn not in hoops_by_frame:
                        hoops_by_frame[fn] = []
                    hoops_by_frame[fn].append({
                        'cx': cx, 'cy': cy,
                        'w': x2-x1, 'h': y2-y1, 'conf': cf
                    })

    fn += 1
    if fn % 500 == 0:
        print("  %d/%d frames" % (fn, total))

cap.release()
print("  Frames with hoop detection: %d" % len(hoops_by_frame))

# Save hoop detections
hoop_list = []
for fn in sorted(hoops_by_frame.keys()):
    for h in hoops_by_frame[fn]:
        hoop_list.append({'frame': fn, 'cx': h['cx'], 'cy': h['cy'],
                           'w': h['w'], 'h': h['h'], 'conf': round(h['conf'], 3)})
pd.DataFrame(hoop_list).to_csv(OUT + '/hybrid2_hoops.csv', index=False)
print("  Saved hybrid2_hoops.csv")

# ---- Step 3: Interpolate hoop position ----
print("\nInterpolating hoop positions...")
hoop_cx_arr = np.full(total, np.nan)
hoop_cy_arr = np.full(total, np.nan)

for fn, hoops in hoops_by_frame.items():
    best = max(hoops, key=lambda h: h['conf'])
    hoop_cx_arr[fn] = best['cx']
    hoop_cy_arr[fn] = best['cy']

# Forward fill
last_cx, last_cy = np.nan, np.nan
for fn in range(total):
    if not np.isnan(hoop_cx_arr[fn]):
        last_cx, last_cy = hoop_cx_arr[fn], hoop_cy_arr[fn]
    elif not np.isnan(last_cx):
        hoop_cx_arr[fn] = last_cx
        hoop_cy_arr[fn] = last_cy

# Backward fill
last_cx, last_cy = np.nan, np.nan
for fn in range(total-1, -1, -1):
    if not np.isnan(hoop_cx_arr[fn]):
        last_cx, last_cy = hoop_cx_arr[fn], hoop_cy_arr[fn]
    elif not np.isnan(last_cx):
        hoop_cx_arr[fn] = last_cx
        hoop_cy_arr[fn] = last_cy

filled_hoop = int(np.sum(~np.isnan(hoop_cx_arr)))
print("  Hoop positions available for %d/%d frames (%.1f%%)" % (filled_hoop, total, filled_hoop/total*100))
print("  Hoop CX: mean=%.0f std=%.0f" % (np.nanmean(hoop_cx_arr), np.nanstd(hoop_cx_arr)))
print("  Hoop CY: mean=%.0f std=%.0f" % (np.nanmean(hoop_cy_arr), np.nanstd(hoop_cy_arr)))

# ---- Step 4: Build ball position arrays ----
ball_cx = np.full(total, np.nan)
ball_cy = np.full(total, np.nan)
ball_conf_arr = np.zeros(total)

for _, r in balls.iterrows():
    fn = int(r.frame)
    if fn < total:
        if np.isnan(ball_cx[fn]) or r.conf > ball_conf_arr[fn]:
            ball_cx[fn] = r.cx
            ball_cy[fn] = r.cy
            ball_conf_arr[fn] = r.conf

ball_detected = ~np.isnan(ball_cx)
print("\nBall detected in %d/%d frames (%.1f%%)" % (int(np.sum(ball_detected)), total, np.sum(ball_detected)/total*100))

# ---- Step 5: Ball-hoop distance ----
dist_to_hoop = np.full(total, np.nan)
for fn in range(total):
    if not np.isnan(ball_cx[fn]) and not np.isnan(hoop_cx_arr[fn]):
        dist_to_hoop[fn] = np.sqrt((ball_cx[fn] - hoop_cx_arr[fn])**2 +
                                     (ball_cy[fn] - hoop_cy_arr[fn])**2)

for label, thresh in [("100px", 100), ("75px", 75), ("50px", 50), ("30px", 30)]:
    cnt = int(np.sum(dist_to_hoop < thresh))
    print("  Ball within %s of hoop: %d frames" % (label, cnt))

# ---- Step 6: Near-hoop events ----
print("\n=== NEAR-HOOP EVENTS ===")
close_threshold = 100
near_hoop_events = []
in_event = False
event_start = 0
for fn in range(total):
    if dist_to_hoop[fn] < close_threshold and not np.isnan(dist_to_hoop[fn]):
        if not in_event:
            in_event = True
            event_start = fn
    else:
        if in_event:
            near_hoop_events.append((event_start, fn-1))
            in_event = False
if in_event:
    near_hoop_events.append((event_start, total-1))

print("Near-hoop events: %d" % len(near_hoop_events))
for start, end in near_hoop_events:
    min_dist = float(np.min(dist_to_hoop[start:end+1]))
    print("  F%d-F%d (%d frames): min_dist=%.1fpx hoop=(%.0f,%.0f)" % (
        start, end, end-start+1, min_dist,
        hoop_cx_arr[start], hoop_cy_arr[start]))

# ---- Step 7: Gap-based shot detection ----
print("\n=== GAP-BASED SHOT CANDIDATES ===")
gap_shots = []
for fn in range(30, total):
    if ball_detected[fn]:
        continue

    # Find last ball detection
    last_ball_frame = None
    for prev in range(fn-1, max(0, fn-35), -1):
        if ball_detected[prev]:
            last_ball_frame = prev
            break
    if last_ball_frame is None:
        continue

    gap_size = fn - last_ball_frame
    if gap_size < 3 or gap_size > 35:
        continue

    # Distance to hoop at last detection
    if not np.isnan(hoop_cx_arr[last_ball_frame]):
        dist_at_last = np.sqrt(
            (ball_cx[last_ball_frame] - hoop_cx_arr[last_ball_frame])**2 +
            (ball_cy[last_ball_frame] - hoop_cy_arr[last_ball_frame])**2)
    else:
        dist_at_last = float('inf')

    if dist_at_last > 150:
        continue

    # Find reappearance
    next_ball_frame = None
    for nxt in range(fn, min(total, fn+35)):
        if ball_detected[nxt]:
            next_ball_frame = nxt
            break

    info = {
        'gap_start': last_ball_frame,
        'gap_end': next_ball_frame if next_ball_frame else fn,
        'gap_size': gap_size,
        'ball_x_depart': round(float(ball_cx[last_ball_frame]), 1),
        'ball_y_depart': round(float(ball_cy[last_ball_frame]), 1),
        'dist_hoop_depart': round(float(dist_at_last), 1),
        'hoop_cx': round(float(hoop_cx_arr[last_ball_frame]), 1),
        'hoop_cy': round(float(hoop_cy_arr[last_ball_frame]), 1),
    }
    if next_ball_frame:
        info['ball_x_arrive'] = round(float(ball_cx[next_ball_frame]), 1)
        info['ball_y_arrive'] = round(float(ball_cy[next_ball_frame]), 1)
    gap_shots.append(info)

print("Gap-based shot candidates: %d" % len(gap_shots))
for s in gap_shots:
    print("  F%d (gap %d): depart (%.0f,%.0f) dist_hoop=%.0f" % (
        s['gap_start'], s['gap_size'],
        s['ball_x_depart'], s['ball_y_depart'], s['dist_hoop_depart']))

# Save
pd.DataFrame(gap_shots).to_csv(OUT + '/hybrid2_gap_shots.csv', index=False)
pd.DataFrame([{'frame_start': s, 'frame_end': e} for s,e in near_hoop_events]).to_csv(OUT + '/hybrid2_near_hoop_events.csv', index=False)

print("\n=== DONE ===")
