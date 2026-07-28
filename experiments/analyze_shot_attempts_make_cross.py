#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sqlite3
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
MIN_VERTICAL_RISE_FT = 0.6  # minimum rise from start to peak to count as shot attempt (feet)
MAKE_WINDOW_SEC = 0.8     # seconds after peak to look for ball below rim (for make)
THREEPT_DISTANCE_FT = 22.0  # corner three distance
SIGNAL_WINDOW_SEC = 0.3     # seconds around attempt to look for referee signal
INTERP_MAX_GAP = 15         # max frames to interpolate for ball trajectory (increase for sparse data)

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

def load_person_detections(db_path, game_id):
    conn = sqlite3.connect(db_path)
    query = """
    SELECT frame_number, timestamp_ms, x_center, y_center, width, height, confidence
    FROM detections
    WHERE game_id = ? AND object_class = 'person'
    """
    df = pd.read_sql_query(query, conn, params=(game_id,))
    conn.close()
    # Compute bottom-center (x, y + height/2) as foot proxy
    df['foot_x'] = df['x_center']
    df['foot_y'] = df['y_center'] + df['height'] / 2.0
    return df

def associate_shooter(attempt_frame, person_df, max_frame_diff=1):
    # Find person detections within max_frame_diff of attempt_frame
    mask = (person_df['frame_number'] >= attempt_frame - max_frame_diff) & (person_df['frame_number'] <= attempt_frame + max_frame_diff)
    candidates = person_df[mask]
    if candidates.empty:
        return None
    # Compute distance to hoop center in pixels for each candidate
    hoop_x, hoop_y = hoop_center_px
    candidates['dist'] = np.sqrt((candidates['foot_x'] - hoop_x)**2 + (candidates['foot_y'] - hoop_y)**2)
    # Pick the one with smallest distance
    best = candidates.loc[candidates['dist'].idxmin()]
    shooter_px = np.array([best['foot_x'], best['foot_y']])
    shooter_ft = shooter_px * scale_ft_per_px
    return shooter_ft

def classify_shot_type(shooter_ft, hoop_center_ft):
    if shooter_ft is None:
        return 'unknown'
    dist = np.linalg.norm(shooter_ft - hoop_center_ft)
    if dist >= THREEPT_DISTANCE_FT:
        return '3PT'
    else:
        return '2PT'

def detect_make_from_y(smooth_y, attempt_idx, fps, hoop_y_px, hoop_radius_px, make_window_sec=MAKE_WINDOW_SEC):
    """Check if after peak frame, ball goes below hoop plane within make_window_sec seconds."""
    threshold_px = hoop_y_px + hoop_radius_px  # pixel y of bottom of hoop
    start = attempt_idx
    max_look_ahead = int(make_window_sec * fps)  # look ahead make_window_sec seconds
    for i in range(start, min(len(smooth_y), start+max_look_ahead)):
        if smooth_y[i] > threshold_px:
            return True  # made
    return False  # missed

def load_referee_signals(csv_path):
    df = pd.read_csv(csv_path)
    return df

def main():
    base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
    ball_csv = f'{base}/ball_q1_conf0001_stride4.csv'
    pose_csv = f'{base}/pose_keypoints_full.csv'
    signal_csv = f'{base}/signal_full.csv'
    db_path = f'{base}/film_analysis.db'
    output_csv = f'{base}/final_events_make_via_cross.csv'
    
    # Load data
    ball_df = load_ball_detections(ball_csv)
    pose_df = pd.read_csv(pose_csv)
    signal_df = load_referee_signals(signal_csv)
    person_df = load_person_detections(db_path, '299q1')
    
    # FPS from video (known)
    fps = 3.75
    print(f'FPS: {fps}')
    print(f'Ball detections: {len(ball_df)}')
    print(f'Person detections: {len(person_df)}')
    
    # Detect attempts
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full = detect_shot_attempts(ball_df, fps)
    print(f'Detected {len(attempt_frames)} raw shot attempts')
    
    events = []
    for i, (aframe, atime, pframe, py) in enumerate(zip(attempt_frames, attempt_times, peak_frames, peak_y)):
        # Associate shooter using person detections
        shooter_ft = associate_shooter(aframe, person_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
        # Make/miss using new logic
        try:
            idx_in_smooth = np.where(frames_full == aframe)[0][0]
        except:
            idx_in_smooth = 0
        made = detect_make_from_y(smooth_y, idx_in_smooth, fps, hoop_center_px[1], hoop_radius_px)
        # Referee signal override
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
        # Also show breakdown by signal override
        print('\nSignal override breakdown:')
        for sig in [0,1,2]:
            sub = events_df[events_df['signal_override']==sig]
            if len(sub) > 0:
                print('Signal {}: {} events, made {}'.format(sig, len(sub), sub['made_final'].sum()))
    
if __name__ == '__main__':
    main()