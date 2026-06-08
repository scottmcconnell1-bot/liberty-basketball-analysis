#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sqlite3
from scipy.signal import argrelextrema
from scipy import interpolate

# Load hoop params (current)
with open('hoop_params.json') as f:
    hoop = json.load(f)
hoop_center_px = np.array(hoop['hoop_center_px'])
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']
print(f'Hoop center: {hoop_center_px}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')

# Load ball and signal data
ball_df = pd.read_csv('ball_q1_conf0001_stride4.csv')
signal_df = pd.read_csv('signal_full.csv')
signal_df = signal_df[signal_df['signal'].isin([1,2])]
person_conn = sqlite3.connect('film_analysis.db')
person_df = pd.read_sql_query("""
    SELECT frame_number, timestamp_ms, x_center, y_center, width, height, confidence
    FROM detections
    WHERE game_id = '299q1' AND object_class = 'person'
""", person_conn)
person_conn.close()
person_df['foot_x'] = person_df['x_center']
person_df['foot_y'] = person_df['y_center'] + person_df['height'] / 2.0

# Smooth ball trajectory
frames = ball_df['frame'].values
raw_x = ball_df['x'].values
raw_y = ball_df['y'].values
frames_full, x_interp = interpolate_trajectory(frames, raw_x, max_gap=15)
_, y_interp = interpolate_trajectory(frames, raw_y, max_gap=15)
smooth_x = pd.Series(x_interp).rolling(5, center=True, min_periods=1).mean().values
smooth_y = pd.Series(y_interp).rolling(5, center=True, min_periods=1).mean().values

# Detect 2PT attempts via crossing method (as before)
valid = ~np.isnan(smooth_y)
if not np.any(valid):
    print('No valid ball y')
    exit()
first_valid_idx = np.where(valid)[0][0]
start_y = smooth_y[first_valid_idx]
rise = start_y - smooth_y
min_idx = argrelextrema(smooth_y, np.less_equal, order=1)[0]
peak_candidates = []
for idx in min_idx:
    if idx > first_valid_idx and rise[idx] >= 0.6 / scale_ft_per_px:
        peak_candidates.append(idx)
hoop_y_px = hoop_center_px[1]
hoop_threshold_px = hoop_y_px + hoop_radius_px
attempt_frames = []
attempt_times = []
for peak_idx in peak_candidates:
    search_start = peak_idx
    search_end = min(len(smooth_y), peak_idx + int(2 * 3.75))
    for i in range(search_start, search_end):
        if smooth_y[i] > hoop_threshold_px and np.gradient(smooth_y)[i] > 0:
            attempt_frames.append(frames_full[i])
            attempt_times.append(frames_full[i] / 3.75)
            break

print(f'Detected {len(attempt_frames)} raw 2PT attempts via crossing')
# For each, compute shooter distance
distances = []
for aframe, atime in zip(attempt_frames, attempt_times):
    # find nearest person detection within +/-1 frame
    mask = (person_df['frame_number'] >= aframe-1) & (person_df['frame_number'] <= aframe+1)
    candidates = person_df[mask]
    if candidates.empty:
        continue
    hoop_x, hoop_y = hoop_center_px
    candidates['dist_px'] = np.sqrt((candidates['foot_x'] - hoop_x)**2 + (candidates['foot_y'] - hoop_y)**2)
    best = candidates.loc[candidates['dist_px'].idxmin()]
    dist_px = best['dist_px']
    dist_ft = dist_px * scale_ft_per_px
    distances.append(dist_ft)
    print(f'Attempt frame {aframe}: shooter distance {dist_ft:.2f} ft')
if distances:
    print(f'Average shooter distance: {np.mean(distances):.2f} ft')
    print(f'Min: {np.min(distances):.2f} ft, Max: {np.max(distances):.2f} ft')
    # What threshold would give us e.g., 2 makes out of 7 attempts? We don't have makes yet.
    # Let's also compute makes assuming we need to go below hoop for MAKE_FRAMES_BELOW frames
    made_count = 0
    for aframe in attempt_frames:
        try:
            idx_in_smooth = np.where(frames_full == aframe)[0][0]
        except:
            idx_in_smooth = 0
        # detect make: need consecutive frames below hoop threshold
        hoop_y_px = hoop_center_px[1]
        threshold_px = hoop_y_px + hoop_radius_px
        below = 0
        for i in range(idx_in_smooth, min(len(smooth_y), idx_in_smooth + int(1.5*3.75))):
            if smooth_y[i] > threshold_px:
                below += 1
                if below >= 1:
                    made_count += 1
                    break
            else:
                below = 0
    print(f'Number of makes (crude): {made_count} out of {len(attempt_frames)}')
else:
    print('No shooter distances computed')