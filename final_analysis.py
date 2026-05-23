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
hoop_center_px = np.array(hoop['hoop_center_px'])
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']
hoop_center_ft = hoop_center_px * scale_ft_per_px
hoop_radius_ft = hoop_radius_px * scale_ft_per_px
print(f'Hoop center ft: {hoop_center_ft}, radius: {hoop_radius_ft} ft')

# Parameters
SMOOTH_WINDOW = 5
PEAK_ORDER = 1
MIN_VERTICAL_RISE_FT = 0.6
MAKE_WINDOW_SEC = 0.8
THREEPT_DISTANCE_FT = 22.0
SIGNAL_WINDOW_SEC = 0.3
INTERP_MAX_GAP = 15

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
    smooth_y = smooth_series(y_interp)
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

def detect_make_from_y(smooth_y, attempt_idx, fps, hoop_y_px, hoop_radius_px, make_window_sec=MAKE_WINDOW_SEC):
    threshold_px = hoop_y_px + hoop_radius_px
    start = attempt_idx
    max_look_ahead = int(make_window_sec * fps)
    for i in range(start, min(len(smooth_y), start+max_look_ahead)):
        if smooth_y[i] > threshold_px:
            return True
    return False

def main():
    base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
    ball_csv = f'{base}/ball_q1_conf0001_stride4.csv'
    db_path = f'{base}/film_analysis.db'
    signal_csv = f'{base}/signal_full.csv'
    output_csv = f'{base}/final_events_signal_refined.csv'
    
    ball_df = load_ball_detections(ball_csv)
    person_df = load_person_detections(db_path, '299q1')
    signal_df = pd.read_csv(signal_csv)
    fps = 3.75
    
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full = detect_shot_attempts(ball_df, fps)
    print(f'Detected {len(attempt_frames)} raw shot attempts')
    
    events = []
    for i, (aframe, atime, pframe, py) in enumerate(zip(attempt_frames, attempt_times, peak_frames, peak_y)):
        shooter_ft = associate_shooter(aframe, person_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
        try:
            idx_in_smooth = np.where(frames_full == aframe)[0][0]
        except:
            idx_in_smooth = 0
        made = detect_make_from_y(smooth_y, idx_in_smooth, fps, hoop_center_px[1], hoop_radius_px)
        # Signal override
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
        # Show attempts with signal override
        print('\nAttempts with signal override:')
        override_df = events_df[events_df['signal_override'] > 0]
        if not override_df.empty:
            for _, row in override_df.iterrows():
                print(f"Attempt {row['attempt_id']} at {row['time_s']}s: signal {int(row['signal_override'])}, initial {row['shot_type_initial']} ({'made' if row['made_initial'] else 'miss'}) -> final {row['shot_type_final']} ({'made' if row['made_final'] else 'miss'})")
        else:
            print("No signals matched any attempt.")
    
if __name__ == '__main__':
    main()