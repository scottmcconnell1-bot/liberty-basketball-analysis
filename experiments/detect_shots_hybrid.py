#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sqlite3
from scipy.signal import argrelextrema
from scipy import interpolate

# Load hoop params
hoop_path = 'hoop_params.json'
with open(hoop_path) as f:
    hoop = json.load(f)
hoop_center_px = np.array(hoop['hoop_center_px'])  # [x, y]
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']

print(f'Hoop center: {hoop_center_px}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')

# Parameters
SMOOTH_WINDOW = 5
PEAK_ORDER = 1
MIN_VERTICAL_RISE_FT = 0.6  # for 2PT attempt detection
MAKE_FRAMES_BELOW = 1
THREEPT_DISTANCE_FT = 22.0
SIGNAL_WINDOW_SEC = 0.5  # window around referee signal to look for ball
BALL_NEAR_HOOP_THRESH_PX = 50  # max distance from hoop to consider ball near hoop for 3PT signal
FPS = 3.75
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

def load_person_detections(db_path, game_id):
    conn = sqlite3.connect(db_path)
    query = """
    SELECT frame_number, timestamp_ms, x_center, y_center, width, height, confidence
    FROM detections
    WHERE game_id = ? AND object_class = 'person'
    """
    df = pd.read_sql_query(query, conn, params=[game_id])
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
    output_csv = f'{base}/final_events_hybrid.csv'
    
    ball_df = load_ball_detections(ball_csv)
    signal_df = load_referee_signals(signal_csv)
    person_df = load_person_detections(db_path, '299q1')
    
    print(f'FPS: {FPS}')
    print(f'Ball detections: {len(ball_df)}')
    print(f'Person detections: {len(person_df)}')
    one_hand = len(signal_df[signal_df['signal'] == 1])
    both_hands = len(signal_df[signal_df['signal'] == 2])
    print(f'Referee signals: {len(signal_df)} (one-hand: {one_hand}, both-hands: {both_hands})')
    
    # Interpolate and smooth ball trajectory
    frames = ball_df['frame'].values
    raw_x = ball_df['x'].values
    raw_y = ball_df['y'].values
    frames_full, x_interp = interpolate_trajectory(frames, raw_x, max_gap=INTERP_MAX_GAP)
    _, y_interp = interpolate_trajectory(frames, raw_y, max_gap=INTERP_MAX_GAP)
    smooth_x = smooth_series(x_interp, window=SMOOTH_WINDOW)
    smooth_y = smooth_series(y_interp, window=SMOOTH_WINDOW)
    
    # Compute velocity (dy/dt) using gradient
    dt = 1.0 / FPS
    vy = np.gradient(smooth_y, dt)  # positive y is downward in image
    
    # Detect 2PT shot attempts: ball crossing hoop plane with downward motion after a rise
    # First, detect local minima in y (highest point) as before
    valid = ~np.isnan(smooth_y)
    if not np.any(valid):
        print('No valid ball y data')
        return
    first_valid_idx = np.where(valid)[0][0]
    start_y = smooth_y[first_valid_idx]
    rise = start_y - smooth_y  # positive when ball went up (y decreased)
    min_idx = argrelextrema(smooth_y, np.less_equal, order=PEAK_ORDER)[0]
    peak_candidates = []
    for idx in min_idx:
        if idx > first_valid_idx and rise[idx] >= MIN_VERTICAL_RISE_FT / scale_ft_per_px:
            peak_candidates.append(idx)
    # For each peak, look for a crossing of the hoop plane (y > hoop_y + radius) with downward velocity (vy > 0) after the peak
    hoop_y_px = hoop_center_px[1]
    hoop_threshold_px = hoop_y_px + hoop_radius_px
    attempt_frames_2pt = []
    attempt_times_2pt = []
    peak_frames_2pt = []
    peak_y_2pt = []
    for peak_idx in peak_candidates:
        # Look ahead from peak_idx for crossing
        search_start = peak_idx
        search_end = min(len(smooth_y), peak_idx + int(2 * FPS))  # look up to 2 seconds ahead
        for i in range(search_start, search_end):
            if smooth_y[i] > hoop_threshold_px and vy[i] > 0:  # crossing downward
                attempt_frames_2pt.append(frames_full[i])
                attempt_times_2pt.append(frames_full[i] / FPS)
                peak_frames_2pt.append(frames_full[peak_idx])
                peak_y_2pt.append(smooth_y[peak_idx])
                break  # take first crossing after peak
    
    print(f'Detected {len(attempt_frames_2pt)} raw 2PT shot attempts (crossing method)')
    
    # Process referee signals for 3PT
    attempt_frames_3pt = []
    attempt_times_3pt = []
    made_3pt_from_signal = []  # True if both-hands signal
    for _, row in signal_df.iterrows():
        signal_time_ms = row['timestamp_ms']
        signal_frame = signal_time_ms * FPS / 1000.0
        signal_type = row['signal']  # 1 for one-hand (attempt), 2 for both-hands (made)
        # Look for ball near hoop in a window around signal_frame
        window_frames = int(SIGNAL_WINDOW_SEC * FPS)
        start_frame = max(0, int(signal_frame) - window_frames)
        end_frame = min(len(frames_full)-1, int(signal_frame) + window_frames)
        # Check if any ball detection in this window is near the hoop
        near_hoop = False
        for f in range(start_frame, end_frame+1):
            if f < 0 or f >= len(smooth_x):
                continue
            dist_to_hoop = np.sqrt((smooth_x[f] - hoop_center_px[0])**2 + (smooth_y[f] - hoop_center_px[1])**2)
            if dist_to_hoop < BALL_NEAR_HOOP_THRESH_PX:
                near_hoop = True
                break
        if near_hoop:
            attempt_frames_3pt.append(int(signal_frame))
            attempt_times_3pt.append(signal_time_ms / 1000.0)
            made_3pt_from_signal.append(signal_type == 2)
    
    print(f'Detected {len(attempt_frames_3pt)} 3PT shot attempts from referee signals')
    
    # Combine attempts, avoiding duplicates (if a referee signal is close to a 2PT attempt, we prefer the referee signal for 3PT)
    # We'll simple concatenate and then later we can deduplicate by time if needed.
    all_attempt_frames = attempt_frames_2pt + attempt_frames_3pt
    all_attempt_times = attempt_times_2pt + attempt_times_3pt
    all_peak_frames = peak_frames_2pt + [0]*len(attempt_frames_3pt)  # placeholder for 3PT
    all_peak_y = peak_y_2pt + [0]*len(attempt_frames_3pt)
    all_made_initial = [False]*len(attempt_frames_2pt) + made_3pt_from_signal  # 2PT initial made false, 3PT from signal
    all_shot_type_initial = ['2PT']*len(attempt_frames_2pt) + ['3PT']*len(attempt_frames_3pt)
    
    # Now associate shooter and classify (may override based on distance)
    events = []
    for i, (aframe, atime, pframe, py, made_init, shot_init) in enumerate(zip(all_attempt_frames, all_attempt_times, all_peak_frames, all_peak_y, all_made_initial, all_shot_type_initial)):
        # For 3PT from signal, we still want to associate shooter to confirm it's beyond three-point line?
        shooter_ft = associate_shooter(aframe, person_df)
        hoop_center_ft = hoop_center_px * scale_ft_per_px
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else shot_init
        # For 3PT from signal, we might override to 3PT regardless of distance? But let's keep classification.
        # Make/miss: for 2PT we compute, for 3PT from signal we already know made from signal (if both-hands)
        if shot_init == '3PT':
            made = made_init  # from signal
        else:
            # 2PT: compute make/miss
            idx_in_smooth = None
            # Find index in smooth_y corresponding to aframe
            try:
                idx_in_smooth = np.where(frames_full == aframe)[0][0]
            except:
                idx_in_smooth = 0
            made = detect_make_miss(smooth_y, idx_in_smooth, FPS)
        # Build event
        events.append({
            'attempt_id': i,
            'frame': int(aframe),
            'time_s': round(atime, 3),
            'peak_frame': int(pframe) if pframe != 0 else None,
            'peak_y_px': round(float(py), 2) if py != 0 else None,
            'shooter_ft_x': round(shooter_ft[0], 3) if shooter_ft is not None else None,
            'shooter_ft_y': round(shooter_ft[1], 3) if shooter_ft is not None else None,
            'shot_type_initial': shot_init,
            'made_initial': bool(made_init),
            'shot_type_final': shot_type,
            'made_final': bool(made)
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
        # Also show breakdown by signal override (we didn't store signal, but we can check initial type)
        print('\nInitial shot type breakdown:')
        for init in ['2PT', '3PT']:
            sub = events_df[events_df['shot_type_initial']==init]
            if len(sub) > 0:
                made_sum = sub['made_final'].sum()
                print(f'Initial {init}: {len(sub)} events, made {made_sum}')

if __name__ == '__main__':
    main()