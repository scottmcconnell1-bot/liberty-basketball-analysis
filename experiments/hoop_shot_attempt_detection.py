#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sys
import os

def main(ball_csv, hoop_json, output_csv):
    # Load hoop params
    with open(hoop_json, 'r') as f:
        hoop = json.load(f)
    hoop_center = np.array(hoop['hoop_center_px'])  # [x, y]
    scale = hoop['scale_ft_per_px']  # ft per pixel
    # hoop radius in pixels: 0.75 ft / scale
    hoop_radius_px = 0.75 / scale
    print(f'Hoop center: {hoop_center}, scale: {scale} ft/px, hoop radius px: {hoop_radius_px:.2f}')
    
    # Load ball smooth data
    df = pd.read_csv(ball_csv)
    # Ensure smoothed columns exist
    if 'ball_x_smooth' not in df.columns:
        # compute smoothing if not present
        df['ball_x_smooth'] = df['ball_x_px'].rolling(window=5, center=True, min_periods=1).mean()
        df['ball_y_smooth'] = df['ball_y_px'].rolling(window=5, center=True, min_periods=1).mean()
    # Compute vertical velocity (dy/dt) using diff of smoothed y over frame (assuming constant fps)
    df['ball_y_smooth_diff'] = df['ball_y_smooth'].diff()
    # Detect peaks: where diff changes from negative to positive (ball stops rising, starts falling)
    # In image coords, y increases downward, so rising => dy/dt negative, falling => dy/dt positive.
    df['sign'] = np.sign(df['ball_y_smooth_diff'])
    df['sign_shift'] = df['sign'].diff()
    # Peak when previous sign was -1 (negative) and current sign is +1 (positive) => sign shift from -1 to +1 = 2
    peak_candidates = (df['sign'] == 1) & (df['sign_shift'] == 2)
    # Also ensure ball is above rim plane: ball_y < hoop_y - radius
    hoop_y_px = hoop_center[1]
    above_rim = df['ball_y_smooth'] < (hoop_y_px - hoop_radius_px)
    attempt_mask = peak_candidates & above_rim
    attempt_frames = df[attempt_mask]
    print(f'Found {len(attempt_frames)} shot attempts')
    if len(attempt_frames) == 0:
        # Fallback: use local minima of ball_y_smooth (lowest y = highest point)
        try:
            from scipy.signal import argrelextrema
            min_idx = argrelextrema(df['ball_y_smooth'].values, np.less_equal, order=5)[0]
            above = df.iloc[min_idx]['ball_y_smooth'] < (hoop_y_px - hoop_radius_px)
            attempt_frames = df.iloc[min_idx][above]
            print(f'Fallback found {len(attempt_frames)} attempts via local minima')
        except Exception as e:
            print(f'Fallback failed: {e}')
            attempt_frames = pd.DataFrame()
    # Build output
    attempts = []
    for idx, row in attempt_frames.iterrows():
        attempt_id = idx  # use frame number as id for simplicity
        # Convert ball position to feet relative to hoop center
        ball_x_ft = (row['ball_x_smooth'] - hoop_center[0]) * scale
        ball_y_ft = (row['ball_y_smooth'] - hoop_center[1]) * scale  # negative if above hoop
        attempts.append({
            'attempt_id': attempt_id,
            'frame': int(row['frame']),
            'timestamp_ms': float(row['timestamp_ms']),
            'ball_x_ft': ball_x_ft,
            'ball_y_ft': ball_y_ft
        })
    out_df = pd.DataFrame(attempts)
    out_df.to_csv(output_csv, index=False)
    print(f'Saved {len(out_df)} attempts to {output_csv}')

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Usage: python hoop_shot_attempt_detection.py <ball_csv> <hoop_json> <output_csv>')
        sys.exit(1)
    ball_csv = sys.argv[1]
    hoop_json = sys.argv[2]
    output_csv = sys.argv[3]
    main(ball_csv, hoop_json, output_csv)