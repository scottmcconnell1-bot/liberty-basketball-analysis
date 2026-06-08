#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
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
MIN_VERTICAL_RISE_FT = 0.8  # minimum rise from start to peak to count as shot attempt (feet)
MAKE_FRAMES_BELOW = 1       # consecutive frames below rim to count as make (at 3.75 fps, ~267ms)
THREEPT_DISTANCE_FT = 22.0  # corner three distance
SIGNAL_WINDOW_SEC = 0.5     # seconds around attempt to look for referee signal
INTERP_MAX_GAP = 10         # max frames to interpolate for ball trajectory

def smooth_series(series, window=SMOOTH_WINDOW):
    return pd.Series(series).rolling(window, center=True, min_periods=1).mean().values

def load_ball_detections(csv_path):
    df = pd.read_csv(csv_path)
    df = df.sort_values('frame').reset_index(drop=True)
    return df

def interpolate_trajectory(frames, values, max_gap=INTERP_MAX_GAP):
    """Linear interpolation for short gaps, leave NaN for longer gaps."""
    df = pd.DataFrame({'frame': frames, 'value': values})
    df = df.set_index('frame')
    # Create full range from min to max frame
    full_idx = np.arange(df.index.min(), df.index.max()+1)
    df_full = df.reindex(full_idx)
    # Interpolate limit
    df_full['value'] = df_full['value'].interpolate(method='linear', limit=max_gap)
    return df_full.index.values, df_full['value'].values

def detect_shot_attempts(ball_df, fps):
    frames = ball_df['frame'].values
    raw_y = ball_df['y'].values  # pixel y
    # Interpolate y to fill gaps
    frames_full, y_interp = interpolate_trajectory(frames, raw_y, max_gap=INTERP_MAX_GAP)
    # Smooth y
    smooth_y = smooth_series(y_interp, window=SMOOTH_WINDOW)
    # Compute rise from start (use first valid smoothed y)
    # Find first non-NaN in smooth_y
    valid = ~np.isnan(smooth_y)
    if not np.any(valid):
        return np.array([]), np.array([]), np.array([]), np.array([]), smooth_y, frames_full
    first_valid_idx = np.where(valid)[0][0]
    start_y = smooth_y[first_valid_idx]
    rise = start_y - smooth_y  # positive when ball went up (since y decreased)
    # Find local minima in smooth_y
    min_idx = argrelextrema(smooth_y, np.less_equal, order=PEAK_ORDER)[0]
    # Filter those with sufficient rise and after start
    candidates = []
    for idx in min_idx:
        if idx > first_valid_idx and rise[idx] >= MIN_VERTICAL_RISE_FT / scale_ft_per_px:
            candidates.append(idx)
    # Convert indices to frame numbers and timestamp
    attempt_frames = frames_full[candidates]
    attempt_times = attempt_frames / fps  # seconds
    peak_frames = frames_full[candidates]
    peak_y = smooth_y[candidates]
    return attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full

def associate_shooter(attempt_frame, pose_df):
    """Find nearest person using ankle keypoints."""
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

def detect_make_miss(smooth_y, attempt_idx, fps):
    """Check if after peak frame, ball goes below hoop plane for MAKE_FRAMES_BELOW consecutive frames."""
    hoop_y_px = hoop_center_px[1]
    threshold_px = hoop_y_px + hoop_radius_px  # pixel y of bottom of hoop
    start = attempt_idx
    max_look_ahead = int(1.5 * fps)  # look ahead 1.5 seconds
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
    return df

def main():
    # Paths
    ball_csv = 'ball_q1_conf0001_stride2.csv'  # from recent run
    pose_csv = 'pose_keypoints_full.csv'
    signal_csv = 'signal_full.csv'
    output_csv = 'final_events_dense.csv'
    
    # Load data
    ball_df = load_ball_detections(ball_csv)
    pose_df = pd.read_csv(pose_csv)
    signal_df = load_referee_signals(signal_csv)
    
    # FPS from video (known)
    fps = 3.75
    print(f'FPS: {fps}')
    print(f'Ball detections: {len(ball_df)}')
    
    # Detect attempts
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full = detect_shot_attempts(ball_df, fps)
    print(f'Detected {len(attempt_frames)} raw shot attempts')
    
    events = []
    for i, (aframe, atime, pframe, py) in enumerate(zip(attempt_frames, attempt_times, peak_frames, peak_y)):
        # Associate shooter
        shooter_ft = associate_shooter(aframe, pose_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
        # Make/miss
        # Find index in smooth_y corresponding to aframe
        try:
            idx_in_smooth = np.where(frames_full == aframe)[0][0]
        except:
            idx_in_smooth = 0
        made = detect_make_miss(smooth_y, idx_in_smooth, fps)
        # Referee signal override within +/- SIGNAL_WINDOW_SEC seconds
        signal_window = SIGNAL_WINDOW_SEC
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
        print(events_df['shot_type_final'].value_counts(dropna=False))
        print('Made:', events_df['made_final'].sum())
        # Compute points
        points = 0
        for _, row in events_df.iterrows():
            if row['shot_type_final'] == '2PT' and row['made_final']:
                points += 2
            elif row['shot_type_final'] == '3PT' and row['made_final']:
                points += 3
        print(f'Total points: {points}')
    
if __name__ == '__main__':
    main()