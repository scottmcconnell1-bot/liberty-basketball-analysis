#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json

# Load hoop params
with open('hoop_params.json') as f:
    hoop = json.load(f)
hoop_center = np.array(hoop['hoop_center_px'])
hoop_radius = hoop['hoop_radius_px']
scale = hoop['scale_ft_per_px']

print('Hoop center:', hoop_center, 'radius:', hoop_radius)

# Load ball detections (conf=0.001, stride=4)
ball_df = pd.read_csv('ball_q1_conf0001_stride4.csv')
print('Ball detections:', len(ball_df))
# Load signals
signal_df = pd.read_csv('signal_full.csv')
signal_df = signal_df[signal_df['signal'].isin([1,2])]
signal_df = signal_df.sort_values('timestamp_ms').reset_index(drop=True)
print('Signal rows (1 or 2):', len(signal_df))

FPS = 3.75
window_sec = 0.5
window_frames = int(window_sec * FPS)

matches = []
for idx, row in signal_df.iterrows():
    t_ms = row['timestamp_ms']
    frame_center = t_ms * FPS / 1000.0
    f_low = int(frame_center) - window_frames
    f_high = int(frame_center) + window_frames
    in_range = ball_df[(ball_df['frame'] >= f_low) & (ball_df['frame'] <= f_high)]
    if not in_range.empty:
        # compute min distance to hoop
        min_dist = None
        for _, brow in in_range.iterrows():
            dist = np.linalg.norm(np.array([brow['x'], brow['y']]) - hoop_center)
            if min_dist is None or dist < min_dist:
                min_dist = dist
        matches.append((idx, frame_center, len(in_range), min_dist))
    else:
        matches.append((idx, frame_center, 0, None))

print('Signal, frame, #ball in window, min distance to hoop (px):')
for m in matches:
    print(f"  Signal {m[0]} (type {signal_df.iloc[m[0]]['signal']}) at frame {m[1]:.1f}: {m[2]} balls, min dist {m[3] if m[3] is not None else 'None'}")

# Also compute how many signals have at least one ball within 30 px
close_matches = [m for m in matches if m[3] is not None and m[3] < 30]
print(f'\nSignals with ball within 30 px: {len(close_matches)}/{len(matches)}')
if close_matches:
    print('Details:')
    for m in close_matches:
        print(f"  Signal {m[0]} at frame {m[1]:.1f}, dist {m[3]:.1f} px")