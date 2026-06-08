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

# Parameters
SMOOTH_WINDOW = 5  # for smoothing distance
PEAK_ORDER = 1     # for argrelextrema (min distance)
MIN_DIST_DROP_PX = 10  # minimum drop in distance to count as attempt
MAKE_FRAMES_BELOW = 1  # consecutive frames below rim to count as make
THREEPT_DISTANCE_FT = 22.0
SIGNAL_WINDOW_SEC = 0.3
FPS = 3.75
INTERP_MAX_GAP = 15  # frames to interpolate ball trajectory

def smooth_series(series, window=SMOOTH_WINDOW):
    return pd.Series(series).rolling(window, center=True, min_periods=1).mean().values

def load_ball_detections(csv_path):
    df = pd.read_csv(csv_path)
    df = df.sort_values('frame').reset_index(drop=True)
    return df

def interpolate_trajectory(frames, values, max_gap=INTERP_MAX_GAP):
    df = pd.DataFrame({'frame': frames, 'value': values})
    df = df.set_index('frame')
    full_idx = np.arange(df.index.min(), df.index.max()+1)
    df_full = df.reindex(full_idx)
    df_full['value'] = df_full['value'].interpolate(method='linear', limit=max_gap)
    return df_full.index.values, df_full['value'].values

def load_person_detections(db_path, game_id):
    conn = sqlite3.connect(db_path)
    query = """
    SELECT frame_number, timestamp_ms, x_center, y_center, width, height, confidence
    FROM detections
    WHERE game_id = ? AND object_class = 'person'
    """
    df = pd.read_sql_query(query, conn, params=(game_id,))
    conn.close()
    df['foot_x'] = df['x_center']
    df['foot_y'] = df['y_center'] + df['height'] / 2.0
    return df

def associate_shooter(attempt_frame, person_df, max_frame_diff=1):
    mask = (person_df['frame_number'] >= attempt_frame - max_frame_diff) & (person_df['frame_number'] <= attempt_frame + max_frame_diff)
    candidates = person_df[mask]
    if candidates.empty:
        return None
    hoop_x, hoop_y = hoop_center_px
    candidates['dist'] = np.sqrt((candidates['foot_x'] - hoop_x)**2 + (candidates['foot_y'] - hoop_y)**2)
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

def detect_make_miss(smooth_y, attempt_idx, fps):
    hoop_y_px = hoop_center_px[1]
    threshold_px = hoop_y_px + hoop_radius_px  # bottom of hoop
    start = attempt_idx
    max_look_ahead = int(1.5 * fps)  # look ahead 1.5 seconds
    below_count = 0
    for i in range(start, min(len(smooth_y), start+max_look_ahead)):
        if smooth_y[i] > threshold_px:
            below_count += 1
            if below_count >= MAKE_FRAMES_BELOW:
                return True
        else:
            below_count = 0
    return False

def load_referee_signals(csv_path):
    df = pd.read_csv(csv_path)
    return df

def main():
    base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
    ball_csv = f'{base}/ball_q1_conf0001_stride4.csv'
    signal_csv = f'{base}/signal_full.csv'
    db_path = f'{base}/film_analysis.db'
    output_csv = f'{base}/final_events_distance.csv'
    
    ball_df = load_ball_detections(ball_csv)
    signal_df = load_referee_signals(signal_csv)
    person_df = load_person_detections(db_path, '299q1')
    
    print(f'FPS: {FPS}')
    print(f'Ball detections: {len(ball_df)}')
    print(f'Person detections: {len(person_df)}')
    
    # Interpolate ball x, y to fill gaps
    frames = ball_df['frame'].values
    raw_x = ball_df['x'].values
    raw_y = ball_df['y'].values
    frames_full, x_interp = interpolate_trajectory(frames, raw_x, max_gap=INTERP_MAX_GAP)
    _, y_interp = interpolate_trajectory(frames, raw_y, max_gap=INTERP_MAX_GAP)
    # Smooth x, y
    smooth_x = smooth_series(x_interp, window=SMOOTH_WINDOW)
    smooth_y = smooth_series(y_interp, window=SMOOTH_WINDOW)
    # Compute distance to hoop for each frame
    hoop_x, hoop_y = hoop_center_px
    dist_to_hoop = np.sqrt((smooth_x - hoop_x)**2 + (smooth_y - hoop_y)**2)
    # Smooth distance
    smooth_dist = smooth_series(dist_to_hoop, window=SMOOTH_WINDOW)
    # Detect local minima in distance (closest approach)
    valid = ~np.isnan(smooth_dist)
    if not np.any(valid):
        print('No valid distance data')
        return
    first_valid_idx = np.where(valid)[0][0]
    # Look for minima after start
    min_idx = argrelextrema(smooth_dist, np.less_equal, order=PEAK_ORDER)[0]
    # Filter those with sufficient drop from previous point
    candidates = []
    for idx in min_idx:
        if idx > first_valid_idx:
            # Check drop from previous point (or from a few points before)
            # We'll compute decrease from a window before
            look_back = max(1, PEAK_ORDER)
            if idx - look_back >= 0:
                drop = smooth_dist[idx - look_back] - smooth_dist[idx]
                if drop >= MIN_DIST_DROP_PX:
                    candidates.append(idx)
    # Convert to frames
    attempt_frames = frames_full[candidates]
    attempt_times = attempt_frames / FPS
    print(f'Detected {len(attempt_frames)} raw shot attempts (distance minima)')
    
    # Map frame to index in smooth arrays
    frame_to_idx = {frame: idx for idx, frame in enumerate(frames_full)}
    
    events = []
    for i, (aframe, atime) in enumerate(zip(attempt_frames, attempt_times)):
        # Associate shooter
        shooter_ft = associate_shooter(aframe, person_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_px * scale_ft_per_px) if shooter_ft is not None else 'unknown'
        # Make/miss
        idx_in_smooth = frame_to_idx.get(aframe, 0)
        made = detect_make_miss(smooth_y, idx_in_smooth, FPS)
        # Referee signal override
        signal_window = SIGNAL_WINDOW_SEC
        signal_rows = signal_df[(signal_df['timestamp_ms'] >= (atime*1000 - signal_window*1000)) &
                                (signal_df['timestamp_ms'] <= (atime*1000 + signal_window*1000))]
        signal_override = None
        if not signal_rows.empty:
            signal_override = int(signal_rows['signal'].max())
        final_shot_type = shot_type
        final_made = bool(made)
        if signal_override == 1:
            final_shot_type = '3PT'
        elif signal_override == 2:
            final_shot_type = '3PT'
            final_made = True
        events.append({
            'attempt_id': i,
            'frame': int(aframe),
            'time_s': round(atime, 3),
            'dist_to_hoop_px': round(float(smooth_dist[frame_to_idx[aframe]]), 2) if aframe in frame_to_idx else None,
            'shooter_ft_x': round(shooter_ft[0], 3) if shooter_ft is not None else None,
            'shooter_ft_y': round(shooter_ft[1], 3) if shooter_ft is not None else None,
            'shot_type_initial': shot_type,
            'made_initial': bool(made),
            'signal_override': signal_override,
            'shot_type_final': final_shot_type,
            'made_final': final_made
        })
    
    # Save events
    events_df = pd.DataFrame(events)
    events_df.to_csv(output_csv, index=False)
    print(f'Saved {len(events_df)} events to {output_csv}')
    
    # Summary
    if not events_df.empty:
        print('\nSummary:')
        print(events_df['shot_type_final'].value_counts(dropna=False))
        print('Made:', events_df['made_final'].sum())
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