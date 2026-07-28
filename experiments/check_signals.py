#!/usr/bin/env python3
import pandas as pd
import numpy as np

signal_df = pd.read_csv('signal_full.csv')
print('Total signals:', len(signal_df))
print('Signal values:', signal_df['signal'].value_counts().sort_index())
# Only 1 and 2
signal_12 = signal_df[signal_df['signal'].isin([1,2])]
print('Signals 1 or 2:', len(signal_12))
print('First few:')
for i, row in signal_12.head(10).iterrows():
    print(f"  frame {int(row['timestamp_ms']*3.75/1000)} time {row['timestamp_ms']/1000:.2f}s signal {row['signal']}")
# Load ball detections
ball_df = pd.read_csv('ball_q1_conf0001_stride4.csv')
print('Ball detections:', len(ball_df))
print('Ball frame range:', ball_df['frame'].min(), '-', ball_df['frame'].max())
# For each signal, see if there is a ball detection within +/- 5 frames
window = 5
matches = 0
for _, row in signal_12.iterrows():
    t_ms = row['timestamp_ms']
    frame_center = t_ms * 3.75 / 1000.0
    frame_low = int(frame_center) - window
    frame_high = int(frame_center) + window
    # check if any ball detection in that range
    in_range = ball_df[(ball_df['frame'] >= frame_low) & (ball_df['frame'] <= frame_high)]
    if not in_range.empty:
        matches += 1
        # optionally print first few
        if matches <= 3:
            print(f"  Signal at frame {int(frame_center)}: matched ball detections at frames {in_range['frame'].tolist()}")
print(f'Signals with ball detection within +/-{window} frames: {matches}/{len(signal_12)}')
# Also compute distance to hoop for those matches
import json
with open('hoop_params.json') as f:
    hoop = json.load(f)
hoop_center = np.array(hoop['hoop_center_px'])
scale = hoop['scale_ft_per_px']
for _, row in signal_12.head(5).iterrows():
    t_ms = row['timestamp_ms']
    frame_center = t_ms * 3.75 / 1000.0
    frame_low = int(frame_center) - window
    frame_high = int(frame_center) + window
    in_range = ball_df[(ball_df['frame'] >= frame_low) & (ball_df['frame'] <= frame_high)]
    if not in_range.empty:
        # compute min distance
        mins = []
        for _, brow in in_range.iterrows():
            ball_xy = np.array([brow['x'], brow['y']])
            dist = np.linalg.norm(ball_xy - hoop_center)
            mins.append(dist)
        min_dist = min(mins)
        print(f"  Signal frame {int(frame_center)}: min ball-hoop distance {min_dist:.1f} px ({min_dist*scale:.2f} ft)")
    else:
        print(f"  Signal frame {int(frame_center)}: no ball detection in window")