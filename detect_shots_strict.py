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
MAKE_FRAMES_BELOW = 1  # consecutive frames below rim to count as make
THREEPT_DISTANCE_FT = 22.0
BALL_NEAR_HOOP_THRESH_PX = 30  # stricter: ball must be within 30 px of hoop centre
SIGNAL_LOOKAHEAD_SEC = 0.3  # seconds after signal to look for ball crossing/downward motion
SIGNAL_LOOKBEHIND_SEC = 0.3  # seconds before signal to allow ball peak
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
    output_csv = f'{base}/final_events_strict.csv'
    
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
    
    events = []
    
    # Process each referee signal
    for _, row in signal_df.iterrows():
        signal_time_ms = row['timestamp_ms']
        signal_frame = signal_time_ms * FPS / 1000.0
        signal_type = row['signal']  # 1 for one-hand (attempt), 2 for both-hands (made)
        
        # Determine time window around signal to search for ball
        start_frame = max(0, int(signal_frame) - int(SIGNAL_LOOKBEHIND_SEC * FPS))
        end_frame = min(len(frames_full)-1, int(signal_frame) + int(SIGNAL_LOOKAHEAD_SEC * FPS))
        
        # Look for ball detection in this window that is near hoop and moving downward
        found = False
        made_from_signal = (signal_type == 2)
        for f in range(start_frame, end_frame+1):
            if f < 0 or f >= len(smooth_x):
                continue
            # distance to hoop
            dist_to_hoop = np.sqrt((smooth_x[f] - hoop_center_px[0])**2 + (smooth_y[f] - hoop_center_px[1])**2)
            if dist_to_hoop < BALL_NEAR_HOOP_THRESH_PX and vy[f] > 0:  # near hoop and moving downward
                found = True
                # Use this frame as the attempt time (could refine to peak, but we'll use signal frame)
                attempt_frame = f
                attempt_time = f / FPS
                break
        
        if not found:
            # No ball near hoop with downward motion in window -> treat as no shot
            continue
        
        # Associate shooter
        shooter_ft = associate_shooter(attempt_frame, person_df)
        hoop_center_ft = hoop_center_px * scale_ft_per_px
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else ('3PT' if signal_type in (1,2) else 'unknown')
        # Override: if signal indicates 3PT, we keep 3PT regardless of distance? We'll keep classification for now.
        # Make/miss: if signal both-hands, we already know made; else compute via ball crossing
        if signal_type == 2:
            made = True  # both-hands signal = made
        else:
            # one-hand signal: need to see if ball goes below hoop after this point
            made = detect_make_miss(smooth_y, attempt_frame, FPS)  # attempt_frame is index in smooth arrays
        
        events.append({
            'attempt_id': len(events),
            'frame': int(attempt_frame),
            'time_s': round(attempt_time, 3),
            'shooter_ft_x': round(shooter_ft[0], 3) if shooter_ft is not None else None,
            'shooter_ft_y': round(shooter_ft[1], 3) if shooter_ft is not None else None,
            'shot_type_initial': '3PT' if signal_type in (1,2) else 'unknown',
            'made_initial': bool(made_from_signal),
            'shot_type_final': shot_type,
            'made_final': bool(made)
        })
    
    # Now detect 2PT attempts from ball trajectory in remaining time (not covered by signal windows)
    # We'll use the crossing method as before, but only consider frames not already assigned to a signal attempt
    # Build a set of frames covered by signal attempts (plus/minus some window to avoid double counting)
    covered_frames = set()
    for ev in events:
        f = ev['frame']
        # mark a window around each signal attempt as covered
        start = max(0, f - int(0.5 * FPS))
        end = min(len(frames_full)-1, f + int(0.5 * FPS))
        covered_frames.update(range(start, end+1))
    
    # Detect 2PT shot attempts: ball crossing hoop plane with downward motion after a rise
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
    for peak_idx in peak_candidates:
        # Look ahead from peak_idx for crossing
        search_start = peak_idx
        search_end = min(len(smooth_y), peak_idx + int(2 * FPS))  # look up to 2 seconds ahead
        for i in range(search_start, search_end):
            if smooth_y[i] > hoop_threshold_px and vy[i] > 0:  # crossing downward
                attempt_frames_2pt.append(frames_full[i])
                attempt_times_2pt.append(frames_full[i] / FPS)
                break  # take first crossing after peak
    
    print(f'Detected {len(attempt_frames_2pt)} raw 2PT shot attempts (crossing method)')
    
    # Filter out those that are too close to signal attempts (already covered)
    attempt_2pt_filtered = []
    for aframe, atime in zip(attempt_frames_2pt, attempt_times_2pt):
        if aframe not in covered_frames:
            attempt_2pt_filtered.append((aframe, atime))
    
    print(f'After removing overlap with signal windows, {len(attempt_2pt_filtered)} 2PT attempts remain')
    
    # Process filtered 2PT attempts
    for aframe, atime in attempt_2pt_filtered:
        # Associate shooter
        shooter_ft = associate_shooter(aframe, person_df)
        hoop_center_ft = hoop_center_px * scale_ft_per_px
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else '2PT'
        # Make/miss
        try:
            idx_in_smooth = np.where(frames_full == aframe)[0][0]
        except:
            idx_in_smooth = 0
        made = detect_make_miss(smooth_y, idx_in_smooth, FPS)
        events.append({
            'attempt_id': len(events),
            'frame': int(aframe),
            'time_s': round(atime, 3),
            'shooter_ft_x': round(shooter_ft[0], 3) if shooter_ft is not None else None,
            'shooter_ft_y': round(shooter_ft[1], 3) if shooter_ft is not None else None,
            'shot_type_initial': '2PT',
            'made_initial': bool(made),
            'shot_type_final': shot_type,
            'made_final': bool(made)
        })
    
    # Sort events by time
    events.sort(key=lambda x: x['time_s'])
    # Re-index attempt_id
    for i, ev in enumerate(events):
        ev['attempt_id'] = i
    
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
        # Also show breakdown by initial type
        print('\nInitial shot type breakdown:')
        for init in ['2PT', '3PT', 'unknown']:
            sub = events_df[events_df['shot_type_initial']==init]
            if len(sub) > 0:
                made_sum = sub['made_final'].sum()
                print(f'Initial {init}: {len(sub)} events, made {made_sum}')

if __name__ == '__main__':
    main()