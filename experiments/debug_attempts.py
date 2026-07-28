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
print(f'Hoop center px: {hoop_center_px}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')
print(f'Hoop center ft: {hoop_center_ft}, radius: {hoop_radius_ft} ft')

# Parameters
SMOOTH_WINDOW = 5
PEAK_ORDER = 1
MIN_VERTICAL_RISE_FT = 0.6
MAKE_WINDOW_SEC = 0.8
THREEPT_DISTANCE_FT = 22.0
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
    ball_df = load_ball_detections(ball_csv)
    person_df = load_person_detections(db_path, '299q1')
    fps = 3.75
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full = detect_shot_attempts(ball_df, fps)
    print(f'Number of attempts: {len(attempt_frames)}')
    for i in range(min(5, len(attempt_frames))):
        aframe = attempt_frames[i]
        atime = attempt_times[i]
        pframe = peak_frames[i]
        py = peak_y[i]
        try:
            idx_in_smooth = np.where(frames_full == aframe)[0][0]
        except:
            idx_in_smooth = 0
        shooter_ft = associate_shooter(aframe, person_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
        made = detect_make_from_y(smooth_y, idx_in_smooth, fps, hoop_center_px[1], hoop_radius_px)
        print(f'Attempt {i}: frame {aframe} ({atime:.1f}s), peak frame {pframe}, peak y {py:.1f} px')
        print(f'  Shooter ft: {shooter_ft}')
        print(f'  Shot type: {shot_type}')
        print(f'  Made? {made}')
        # Show ball y values around peak
        start = max(0, idx_in_smooth - 2)
        end = min(len(smooth_y), idx_in_smooth + 3)
        print(f'  Smoothed y around peak (index {idx_in_smooth}): {smooth_y[start:end]}')
        hoop_y_px = hoop_center_px[1]
        threshold_px = hoop_y_px + hoop_radius_px
        print(f'  Hoop y center: {hoop_y_px} px, threshold (bottom): {threshold_px} px')
        print()

if __name__ == '__main__':
    main()