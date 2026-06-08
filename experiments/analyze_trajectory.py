"""
Analyze player detector output to find shooting poses.
Use player bounding box aspect ratio changes as a proxy for shooting motion.
"""
import cv2, numpy as np, pickle
import pandas as pd

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

# Load shot_v4 data (has player detections)
with open(OUT + '/shot_v4.pkl', 'rb') as f:
    d = pickle.load(f)

# We don't have player data in shot_v4 (only court + ball + motion)
# Let me check what we have
print("Keys in shot_v4.pkl:", list(d.keys()))

# Load the hybrid2 data which has more info
print("\nLoading hybrid2 ball detections...")
balls = pd.read_csv(OUT + '/hybrid2_ball_detections.csv')
print("Hybrid2 detections:", len(balls))

# The key insight: instead of detecting shots from ball position,
# let's look at the BALL'S TRAJECTORY SHAPE
# A shot has a characteristic arc (even with camera tracking)
# The ball accelerates toward the basket

# Let's compute ball velocity and acceleration
ball_cx = d['ball_cx']
ball_cy = d['ball_cy']
total = len(ball_cx)

# Compute velocity (pixel/frame)
vx = np.full(total, np.nan)
vy = np.full(total, np.nan)
speed = np.full(total, np.nan)

for fn in range(1, total):
    if not np.isnan(ball_cx[fn]) and not np.isnan(ball_cx[fn-1]):
        vx[fn] = ball_cx[fn] - ball_cx[fn-1]
        vy[fn] = ball_cy[fn] - ball_cy[fn-1]
        speed[fn] = np.sqrt(vx[fn]**2 + vy[fn]**2)

# Find high-speed ball movements (potential shots)
print("\nBall speed statistics:")
v = speed[~np.isnan(speed)]
if len(v) > 0:
    for pct in [50, 75, 90, 95, 99]:
        print("  %dth pctl: %.1f px/frame" % (pct, np.percentile(v, pct)))
    print("  Max: %.1f px/frame" % np.max(v))

# Find frames where ball speed > threshold AND ball is moving toward basket
high_speed_thresh = np.percentile(v, 95) if len(v) > 0 else 50
print("\nHigh speed threshold (95th pctl): %.1f" % high_speed_thresh)

# For each high-speed frame, check if ball is moving toward a basket
high_speed_frames = np.where(speed > high_speed_thresh)[0]
print("High-speed frames: %d" % len(high_speed_frames))

# Group consecutive high-speed frames
speed_events = []
in_event = False
event_start = 0
for fn in range(total):
    if speed[fn] > high_speed_thresh and not np.isnan(speed[fn]):
        if not in_event:
            in_event = True
            event_start = fn
    else:
        if in_event:
            speed_events.append((event_start, fn-1))
            in_event = False
if in_event:
    speed_events.append((event_start, total-1))

print("High-speed events: %d" % len(speed_events))

# For each event, check if it's near a basket
for s, e in speed_events[:20]:
    dur = e - s + 1
    max_spd = float(np.max(speed[s:e+1]))
    avg_dist = float(np.nanmean(d['dist_to_basket'][s:e+1]))
    print("  F%d-F%d (%d frames): max_speed=%.1f avg_dist_to_basket=%.0f" % (
        s, e, dur, max_spd, avg_dist))
