#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import os
from scipy.signal import argrelextrema

# Load hoop params
hoop_path = 'hoop_params.json'
with open(hoop_path) as f:
    hoop = json.load(f)
hoop_center_px = np.array(hoop['hoop_center_px'])  # [x, y]
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']
print(f'Hoop center: {hoop_center_px}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')

# Convert hoop to real-world feet
hoop_center_ft = hoop_center_px * scale_ft_per_px
hoop_radius_ft = hoop_radius_px * scale_ft_per_px
print(f'Hoop center (ft): {hoop_center_ft}, radius: {hoop_radius_ft} ft')

# Parameters
SMOOTH_WINDOW = 5  # frames for moving average
PEAK_ORDER = 1     # how many points on each side to use for argrelextrema
MIN_VERTICAL_RISE_FT = 1.0  # minimum rise from start to peak to count as shot attempt
MAKE_FRAMES_BELOW = 2       # consecutive frames below rim to count as make
THREEPT_DISTANCE_FT = 22.0  # corner three distance

def smooth_series(series, window=SMOOTH_WINDOW):
    return pd.Series(series).rolling(window, center=True, min_periods=1).mean().values

def load_ball_detections(csv_path):
    df = pd.read_csv(csv_path)
    # Ensure sorted by frame
    df = df.sort_values('frame').reset_index(drop=True)
    return df

def interpolate_trajectory(frames, values, max_gap=5):
    """Linear interpolation for short gaps, leave NaN for longer gaps."""
    df = pd.DataFrame({'frame': frames, 'value': values})
    df = df.set_index('frame')
    # Create full range
    full_idx = np.arange(df.index.min(), df.index.max()+1)
    df_full = df.reindex(full_idx)
    # Interpolate limit
    df_full['value'] = df_full['value'].interpolate(method='linear', limit=max_gap)
    return df_full.index.values, df_full['value'].values

def detect_shot_attempts(ball_df, fps):
    # We'll work with y coordinate (image y increases downward)
    frames = ball_df['frame'].values
    raw_y = ball_df['y'].values  # pixel y
    # Smooth y
    smooth_y = smooth_series(raw_y, window=SMOOTH_WINDOW)
    # In image coords, smaller y is higher. So ball rise corresponds to decreasing y.
    # We'll look for local minima in smooth_y (peak height)
    # But we also want to ensure there was sufficient upward movement before.
    # Compute difference from start to each point: start_y - y (positive if went up)
    start_y = smooth_y[0]
    rise = start_y - smooth_y  # positive when ball went up (since y decreased)
    # Find local minima in smooth_y
    min_idx = argrelextrema(smooth_y, np.less_equal, order=PEAK_ORDER)[0]
    # Filter those with sufficient rise
    candidates = []
    for idx in min_idx:
        if rise[idx] >= MIN_VERTICAL_RISE_FT / scale_ft_per_px:  # convert ft to px
            candidates.append(idx)
    # Convert indices to frame numbers and timestamp
    attempt_frames = frames[candidates]
    attempt_times = attempt_frames / fps  # seconds
    # For each attempt, get peak frame (the min idx) and peak y
    peak_frames = frames[candidates]
    peak_y = smooth_y[candidates]
    return attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames

def associate_shooter(attempt_frame, pose_df):
    """Find nearest person using ankle keypoints."""
    # We'll use left and right ankle if visible, else fallback to bbox? We don't have bbox here.
    # For simplicity, use average of visible ankles.
    row = pose_df[pose_df['frame'] == attempt_frame]
    if row.empty:
        return None
    ankles = []
    if row.iloc[0]['left_ankle_visibility'] > 0.5:
        ankles.append([row.iloc[0]['left_ankle_x'], row.iloc[0]['left_ankle_y']])
    if row.iloc[0]['right_ankle_visibility'] > 0.5:
        ankles.append([row.iloc[0]['right_ankle_x'], row.iloc[0]['right_ankle_y']])
    if not ankles:
        return None
    ankle_mean = np.mean(ankles, axis=0)
    # Convert to feet
    shooter_ft = ankle_mean * scale_ft_per_px
    return shooter_ft

def classify_shot_type(shooter_ft, hoop_center_ft):
    if shooter_ft is None:
        return 'unknown'
    dist = np.linalg.norm(shooter_ft - hoop_center_ft)
    if dist >= THREEPT_DISTANCE_FT:
        return '3PT'
    else:
        return '2PT'

def detect_make_miss(ball_df, attempt_idx, smooth_y, frames, fps):
    """Check if after peak frame, ball goes below hoop plane for MAKE_FRAMES_BELOW consecutive frames."""
    # Find index in smooth_y corresponding to attempt_idx (peak frame)
    # We'll search forward from peak frame for consecutive frames where y > hoop_y + radius (i.e., below rim)
    hoop_y_px = hoop_center_px[1]  # y center
    hoop_y_plus_px = hoop_y_px + hoop_radius_px  # pixel y of bottom of hoop (since y increases down)
    # Actually, ball center below rim means y_center > hoop_y + radius? Wait: image y increases downward, hoop center y, radius extends outward.
    # The bottom of the hoop is at y_center + radius (since down is positive). Ball center must be greater than that to be below rim.
    threshold_px = hoop_y_px + hoop_radius_px
    # Get smooth_y values after peak
    start = attempt_idx
    # We'll look ahead up to maybe 2 seconds
    max_look_ahead = int(2 * fps)
    below_count = 0
    for i in range(start, min(len(smooth_y), start+max_look_ahead)):
        if smooth_y[i] > threshold_px:
            below_count += 1
            if below_count >= MAKE_FRAMES_BELOW:
                return True  # made
        else:
            below_count = 0  # reset
    return False  # missed

def load_referee_signals(csv_path):
    df = pd.read_csv(csv_path)
    # Expect columns: frame, timestamp_ms, signal
    return df

def main():
    # Paths
    ball_csv = 'ball_q1_conf001_stride8.csv'  # from earlier run
    pose_csv = 'pose_keypoints_full.csv'
    signal_csv = 'signal_full.csv'
    output_csv = 'final_events_improved.csv'
    
    # Load data
    ball_df = load_ball_detections(ball_csv)
    pose_df = pd.read_csv(pose_csv)
    signal_df = load_referee_signals(signal_csv)
    
    # FPS from video (we can get from ball_df timestamp diff)
    fps = 1000.0 / ball_df['timestamp_ms'].diff().median()
    print(f'FPS estimated: {fps}')
    
    # Detect attempts
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, all_frames = detect_shot_attempts(ball_df, fps)
    print(f'Detected {len(attempt_frames)} raw shot attempts')
    
    events = []
    for i, (aframe, atime, pframe, py) in enumerate(zip(attempt_frames, attempt_times, peak_frames, peak_y)):
        # Associate shooter
        shooter_ft = associate_shooter(aframe, pose_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
        # Make/miss
        # Find index in smooth_y corresponding to aframe
        try:
            idx_in_smooth = np.where(all_frames == aframe)[0][0]
        except:
            idx_in_smooth = 0
        made = detect_make_miss(ball_df, idx_in_smooth, smooth_y, all_frames, fps)
        # Referee signal override
        signal_window = 0.5  # seconds
        signal_rows = signal_df[(signal_df['timestamp_ms'] >= (atime*1000 - signal_window*1000)) &
                                (signal_df['timestamp_ms'] <= (atime*1000 + signal_window*1000))]
        signal_override = None
        if not signal_rows.empty:
            # take max signal (2 > 1 > 0)
            signal_override = int(signal_rows['signal'].max())
        # Apply override
        final_shot_type = shot_type
        final_made = bool(made)
        if signal_override == 1:
            final_shot_type = '3PT'
        elif signal_override == 2:
            final_shot_type = '3PT'
            final_made = True
        # Build event
        events.append({
            'attempt_id': i,
            'frame': int(aframe),
            'time_s': round(atime, 3),
            'peak_frame': int(pframe),
            'peak_y_px': round(float(py), 2),
            'shooter_ft_x': round(shooter_ft[0], 3) if shooter_ft is not None else None,
            'shooter_ft_y': round(shooter_ft[1], 3) if shooter_ft is not None else None,
            'shot_type_initial': shot_type,
            'made_initial': bool(made),
            'signal_override': signal_override,
            'shot_type_final': final_shot_type,
            'made_final': final_made
        })
    
    events_df = pd.DataFrame(events)
    events_df.to_csv(output_csv, index=False)
    print(f'Saved {len(events_df)} events to {output_csv}')
    # Summary
    if not events_df.empty:
        print('\nSummary:')
        print(events_df['shot_type_final'].value_counts())
        print('Made:', events_df['made_final'].sum())
        # Compute points
        points = 0
        for _, row in events_df.iterrows():
            if row['shot_type_final'] == '2PT' and row['made_final']:
                points += 2
            elif row['shot_type_final'] == '3PT' and row['made_final']:
                points += 3
            # FT not detected yet
        print(f'Total points: {points}')
    
if __name__ == '__main__':
    main()