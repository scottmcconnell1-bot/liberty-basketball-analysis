#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sqlite3
from scipy.signal import argrelextrema

# Load ball detections
ball_df = pd.read_csv('/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_q1_conf0001_stride4.csv')
ball_df = ball_df.sort_values('frame').reset_index(drop=True)
print(f'Ball detections: {len(ball_df)}')

# Load person detections
conn = sqlite3.connect('/home/monk-admin/PROJECTS/liberty-basketball-analysis/film_analysis.db')
person_df = pd.read_sql_query("""
    SELECT frame_number, timestamp_ms, x_center, y_center, width, height, confidence
    FROM detections
    WHERE game_id = '299q1' AND object_class = 'person'
""", conn)
conn.close()
person_df['foot_x'] = person_df['x_center']
person_df['foot_y'] = person_df['y_center'] + person_df['height'] / 2.0
print(f'Person detections: {len(person_df)}')

# Load hoop params (original)
with open('/home/monk-admin/PROJECTS/liberty-basketball-analysis/hoop_params.json') as f:
    hoop = json.load(f)
hoop_center_px_orig = np.array(hoop['hoop_center_px'])
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']
print(f'Original hoop centre px: {hoop_center_px_orig}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')

# Parameters
SMOOTH_WINDOW = 5
PEAK_ORDER = 1
MIN_VERTICAL_RISE_FT = 0.6
MAKE_WINDOW_SEC = 0.8
THREEPT_DISTANCE_FT = 22.0
INTERP_MAX_GAP = 15

def smooth_series(series, window=SMOOTH_WINDOW):
    return pd.Series(series).rolling(window, center=True, min_periods=1).mean().values

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

def associate_shooter(attempt_frame, person_df, hoop_center_px, max_frame_diff=1):
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
    fps = 3.75
    attempt_frames, attempt_times, peak_frames, peak_y, smooth_y, frames_full = detect_shot_attempts(ball_df, fps)
    print(f'Detected {len(attempt_frames)} raw shot attempts')
    # Try different hoop centre y values
    hoop_x = hoop_center_px_orig[0]  # keep x from original
    hoop_y_orig = hoop_center_px_orig[1]
    print(f'Original hoop y: {hoop_y_orig} px')
    # We'll test a range of hoop y values from 100 to 300 px
    test_ys = [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300]
    for hoop_y in test_ys:
        hoop_center_px = np.array([hoop_x, hoop_y])
        hoop_center_ft = hoop_center_px * scale_ft_per_px
        hoop_radius_ft = hoop_radius_px * scale_ft_per_px
        makes = 0
        attempts_2pt = 0
        attempts_3pt = 0
        makes_2pt = 0
        makes_3pt = 0
        for i in range(len(attempt_frames)):
            aframe = attempt_frames[i]
            try:
                idx_in_smooth = np.where(frames_full == aframe)[0][0]
            except:
                idx_in_smooth = 0
            shooter_ft = associate_shooter(aframe, person_df, hoop_center_px)
            shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else 'unknown'
            made = detect_make_from_y(smooth_y, idx_in_smooth, fps, hoop_y, hoop_radius_px)
            if shot_type == '2PT':
                attempts_2pt += 1
                if made:
                    makes_2pt += 1
            elif shot_type == '3PT':
                attempts_3pt += 1
                if made:
                    makes_3pt += 1
        print(f'Hoop y={hoop_y} px (ft y={hoop_center_ft[1]:.2f}): 2PT attempts={attempts_2pt}, 3PT attempts={attempts_3pt}, 2PT makes={makes_2pt}, 3PT makes={makes_3pt}')
        if attempts_2pt + attempts_3pt > 0:
            points = makes_2pt * 2 + makes_3pt * 3
            print(f'  Points: {points}')
        print()

if __name__ == '__main__':
    main()