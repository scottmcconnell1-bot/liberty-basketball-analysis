#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sqlite3
from scipy.signal import argrelextrema

# Load hoop params base
hoop_path = 'hoop_params.json'
with open(hoop_path) as f:
    hoop = json.load(f)
hoop_center_px_base = np.array(hoop['hoop_center_px'])  # [x, y]
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']

print(f'Base hoop center: {hoop_center_px_base}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')

# Convert hoop to real-world feet
hoop_center_ft_base = hoop_center_px_base * scale_ft_per_px
hoop_radius_ft = hoop_radius_px * scale_ft_per_px
print(f'Hoop center (ft): {hoop_center_ft_base}, radius: {hoop_radius_ft} ft')

# Parameters
SMOOTH_WINDOW = 5
PEAK_ORDER = 1
MIN_VERTICAL_RISE_FT = 0.6
MAKE_FRAMES_BELOW = 1
THREEPT_DISTANCE_FT = 22.0
SIGNAL_WINDOW_SEC = 0.3
INTERP_MAX_GAP = 15
FPS = 3.75

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

def detect_shot_attempts(ball_df, fps):
    frames = ball_df['frame'].values
    raw_y = ball_df['y'].values
    frames_full, y_interp = interpolate_trajectory(frames, raw_y, max_gap=INTERP_MAX_GAP)
    smooth_y = smooth_series(y_interp, window=SMOOTH_WINDOW)
    valid = ~np.isnan(smooth_y)
    if not np.any(valid):
        return np.array([]), np.array([]), np.array([]), np.array([]), smooth_y, frames_full
    first_valid_idx = np.where(valid)[0][0]
    start_y = smooth_y[first_valid_idx]
    rise = start_y - smooth_y
    min_idx = argrelextrema(smooth_y, np.less_equal, order=PEAK_ORDER)[0]
    candidates = []
    for idx in min_idx:
        if idx > first_valid_idx and rise[idx] >= MIN_VERTICAL_RISE_FT / scale_ft_per_px:
            candidates.append(idx)
    attempt_frames = frames_full[candidates]
    attempt_times = attempt_frames / fps
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
    df['foot_x'] = df['x_center']
    df['foot_y'] = df['y_center'] + df['height'] / 2.0
    return df

def associate_shooter(attempt_frame, person_df, hoop_center_px, scale_ft_per_px, max_frame_diff=1):
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

def detect_make_miss(smooth_y, attempt_idx, fps, hoop_y_px, hoop_radius_px):
    threshold_px = hoop_y_px + hoop_radius_px
    start = attempt_idx
    max_look_ahead = int(1.5 * fps)
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
    
    ball_df = load_ball_detections(ball_csv)
    signal_df = load_referee_signals(signal_csv)
    person_df = load_person_detections(db_path, '299q1')
    
    print(f'FPS: {FPS}')
    print(f'Ball detections: {len(ball_df)}')
    print(f'Person detections: {len(person_df)}')
    
    # Detect attempts once (they depend only on ball data)
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full = detect_shot_attempts(ball_df, FPS)
    print(f'Detected {len(attempt_frames)} raw shot attempts')
    
    # Precompute indices mapping from attempt frame to smooth_y index
    frame_to_idx = {frame: idx for idx, frame in enumerate(frames_full)}
    
    # Test a range of hoop y values (pixel y)
    # Original hoop y = 345
    # We'll test from 100 to 345 in steps of 20
    test_ys = list(range(100, 346, 20))
    # Also include original
    if 345 not in test_ys:
        test_ys.append(345)
    test_ys.sort()
    
    print('\nTesting hoop y values:')
    for hoop_y_px in test_ys:
        hoop_center_px = np.array([hoop_center_px_base[0], hoop_y_px])
        hoop_center_ft = hoop_center_px * scale_ft_per_px
        
        events = []
        for i, (aframe, atime, pframe, py) in enumerate(zip(attempt_frames, attempt_times, peak_frames, peak_y)):
            shooter_ft = associate_shooter(aframe, person_df, hoop_center_px, scale_ft_per_px)
            shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
            idx_in_smooth = frame_to_idx.get(aframe, 0)
            made = detect_make_miss(smooth_y, idx_in_smooth, FPS, hoop_y_px, hoop_radius_px)
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
                'shot_type_initial': shot_type,
                'made_initial': bool(made),
                'signal_override': signal_override,
                'shot_type_final': final_shot_type,
                'made_final': final_made
            })
        
        # Summary
        if events:
            made_2pt = sum(1 for e in events if e['shot_type_final'] == '2PT' and e['made_final'])
            made_3pt = sum(1 for e in events if e['shot_type_final'] == '3PT' and e['made_final'])
            attempts_2pt = sum(1 for e in events if e['shot_type_final'] == '2PT')
            attempts_3pt = sum(1 for e in events if e['shot_type_final'] == '3PT')
            points = made_2pt*2 + made_3pt*3
            print(f'Hoop y={hoop_y_px:3d} px -> 2PT: {made_2pt}/{attempts_2pt}, 3PT: {made_3pt}/{attempts_3pt}, Points: {points}')
            # If we get close to target, break and suggest
            if made_2pt >= 2 and made_3pt >= 1 and points >= 8:
                print(f'  --> TARGET MET or exceeded!')
                break

if __name__ == '__main__':
    main()