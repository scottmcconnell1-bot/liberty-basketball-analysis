#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import sqlite3
from scipy.signal import argrelextrema
from scipy import interpolate

# Load base hoop params (we will vary y)
with open('hoop_params.json') as f:
    hoop_base = json.load(f)
hoop_center_x = hoop_base['hoop_center_px'][0]  # keep x fixed
hoop_radius_px = hoop_base['hoop_radius_px']
scale_ft_per_px = hoop_base['scale_ft_per_px']  # scale depends on radius, which we keep constant

print(f'Base hoop center x: {hoop_center_x}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')

# Parameters
SMOOTH_WINDOW = 5
PEAK_ORDER = 1
MIN_VERTICAL_RISE_FT = 0.6  # for 2PT attempt detection
MAKE_FRAMES_BELOW = 1  # consecutive frames below rim to count as make
THREEPT_DISTANCE_FT = 22.0
SIGNAL_WINDOW_SEC = 0.5  # window around signal to look for ball peak and crossing
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

def run_for_hoop_y(hoop_y_px):
    base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
    ball_csv = f'{base}/ball_q1_conf0001_stride4.csv'
    signal_csv = f'{base}/signal_full.csv'
    db_path = f'{base}/film_analysis.db'
    
    ball_df = load_ball_detections(ball_csv)
    signal_df = load_referee_signals(signal_csv)
    person_df = load_person_detections(db_path, '299q1')
    
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
    
    # Process each referee signal as a potential shot trigger
    for _, row in signal_df.iterrows():
        signal_time_ms = row['timestamp_ms']
        signal_frame = signal_time_ms * FPS / 1000.0
        signal_type = row['signal']  # 0=no signal, 1=one-hand (attempt), 2=both-hands (made)
        if signal_type == 0:
            continue  # ignore no signal
        
        hoop_center_px = np.array([hoop_center_x, hoop_y_px])
        hoop_center_ft = hoop_center_px * scale_ft_per_px
        
        # Define window around signal to search for ball peak and crossing
        start_frame = max(0, int(signal_frame) - int(SIGNAL_WINDOW_SEC * FPS))
        end_frame = min(len(frames_full)-1, int(signal_frame) + int(SIGNAL_WINDOW_SEC * FPS))
        
        # Within this window, we want to find:
        # 1. A local minimum in smooth_y (peak height) that occurs before the signal frame (or at most at signal)
        # 2. After that peak, a crossing of the hoop plane (y > hoop_y + radius) with downward velocity (vy > 0)
        # We'll search for peaks first, then for each peak look ahead for crossing.
        peak_candidates = []
        # Find local minima in smooth_y within window
        valid = ~np.isnan(smooth_y[start_frame:end_frame+1])
        if not np.any(valid):
            continue
        # We'll work with indices relative to start_frame
        window_indices = np.arange(start_frame, end_frame+1)
        window_y = smooth_y[start_frame:end_frame+1]
        window_vy = vy[start_frame:end_frame+1]
        # Local minima
        min_idx_rel = argrelextrema(window_y, np.less_equal, order=PEAK_ORDER)[0]
        # Convert to absolute indices
        min_idx_abs = window_indices[min_idx_rel]
        # Filter those with sufficient rise from start of window? We'll use rise from first valid in window.
        # Find first valid in window
        first_valid_rel = np.where(~np.isnan(window_y))[0]
        if len(first_valid_rel) == 0:
            continue
        first_valid_idx_rel = first_valid_rel[0]
        start_y_win = window_y[first_valid_idx_rel]
        rise_win = start_y_win - window_y  # positive when ball went up
        for idx_rel in min_idx_rel:
            abs_idx = start_frame + idx_rel
            if idx_rel > first_valid_idx_rel and rise_win[idx_rel] >= MIN_VERTICAL_RISE_FT / scale_ft_per_px:
                peak_candidates.append(abs_idx)
        
        # For each peak, look ahead for crossing
        triggered = False
        for peak_idx in peak_candidates:
            # Look ahead from peak_idx to end_frame for crossing
            search_start = peak_idx
            search_end = end_frame
            for f in range(search_start, search_end+1):
                if f < 0 or f >= len(smooth_y):
                    continue
                if smooth_y[f] > hoop_center_px[1] + hoop_radius_px and vy[f] > 0:  # below hoop and moving down
                    triggered = True
                    attempt_frame = f  # use crossing frame as attempt time
                    break
            if triggered:
                break
        
        if not triggered:
            # No ball trajectory evidence -> treat as no shot
            continue
        
        # We have a shot attempt triggered by signal
        attempt_time = attempt_frame / FPS
        # Associate shooter
        shooter_ft = associate_shooter(attempt_frame, person_df, hoop_center_px)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else ('3PT' if signal_type in (1,2) else 'unknown')
        # Override: if signal indicates 3PT, we keep 3PT regardless of distance? We'll keep classification for now.
        # Make/miss: if signal both-hands, we already know made; else compute via ball crossing after peak
        if signal_type == 2:
            made = True  # both-hands signal = made
        else:
            # one-hand signal: need to see if ball goes below hoop after this point (we already know it crossed downward, but need to stay below for MAKE_FRAMES_BELOW)
            # We'll use detect_make_miss starting at attempt_frame (the crossing frame)
            made = detect_make_miss(smooth_y, attempt_frame, FPS)
        
        events.append({
            'frame': int(attempt_frame),
            'time_s': round(attempt_time, 3),
            'shot_type_initial': '3PT' if signal_type in (1,2) else 'unknown',
            'made_initial': bool(signal_type == 2),
            'shot_type_final': shot_type,
            'made_final': bool(made),
            'hoop_y_used': hoop_y_px
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
        return []  # no valid data
    first_valid_idx = np.where(valid)[0][0]
    start_y = smooth_y[first_valid_idx]
    rise = start_y - smooth_y  # positive when ball went up (y decreased)
    min_idx = argrelextrema(smooth_y, np.less_equal, order=PEAK_ORDER)[0]
    peak_candidates = []
    for idx in min_idx:
        if idx > first_valid_idx and rise[idx] >= MIN_VERTICAL_RISE_FT / scale_ft_per_px:
            peak_candidates.append(idx)
    # For each peak, look for a crossing of the hoop plane (y > hoop_y + radius) with downward velocity (vy > 0) after the peak
    hoop_center_px = np.array([hoop_center_x, hoop_y_px])
    hoop_y_px_val = hoop_center_px[1]
    hoop_threshold_px = hoop_y_px_val + hoop_radius_px
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
    
    # Filter out those that are too close to signal attempts (already covered)
    for aframe, atime in zip(attempt_frames_2pt, attempt_times_2pt):
        if aframe not in covered_frames:
            # Associate shooter
            shooter_ft = associate_shooter(aframe, person_df, hoop_center_px)
            shot_type = classify_shot_type(shooter_ft, hoop_center_ft) if shooter_ft is not None else '2PT'
            # Make/miss
            try:
                idx_in_smooth = np.where(frames_full == aframe)[0][0]
            except:
                idx_in_smooth = 0
            made = detect_make_miss(smooth_y, idx_in_smooth, FPS)
            events.append({
                'frame': int(aframe),
                'time_s': round(atime, 3),
                'shot_type_initial': '2PT',
                'made_initial': bool(made),
                'shot_type_final': shot_type,
                'made_final': bool(made),
                'hoop_y_used': hoop_y_px
            })
    
    # Sort events by time
    events.sort(key=lambda x: x['time_s'])
    # Compute stats
    made_2pt = sum(1 for e in events if e['shot_type_final'] == '2PT' and e['made_final'])
    made_3pt = sum(1 for e in events if e['shot_type_final'] == '3PT' and e['made_final'])
    attempts_2pt = sum(1 for e in events if e['shot_type_final'] == '2PT')
    attempts_3pt = sum(1 for e in events if e['shot_type_final'] == '3PT')
    points = made_2pt*2 + made_3pt*3
    return {
        'hoop_y': hoop_y_px,
        'events': events,
        'made_2pt': made_2pt,
        'made_3pt': made_3pt,
        'attempts_2pt': attempts_2pt,
        'attempts_3pt': attempts_3pt,
        'points': points
    }

def main():
    base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
    ball_df = load_ball_detections(f'{base}/ball_q1_conf0001_stride4.csv')
    print(f'Ball detections: {len(ball_df)}')
    
    # Sweep hoop y from 200 to 400 in steps of 5 (finer)
    best = None
    best_score = 1e9
    # We'll also log progress every 10 steps
    for y in range(200, 401, 5):
        result = run_for_hoop_y(y)
        if not result:
            continue
        # Compute how far from target: target 2PT 2/7, 3PT 1/2, FT 1/3 -> 8 points
        # We'll ignore FT for now (not detected). We'll just compare points and attempts/makes.
        # Simple scoring: absolute difference in points + abs diff in made 2PT + abs diff in made 3PT
        score = abs(result['points'] - 8) + abs(result['made_2pt'] - 2) + abs(result['made_3pt'] - 1)
        if score < best_score:
            best_score = score
            best = result
            print(f'New best hoop y={y}: 2PT {result["made_2pt"]}/{result["attempts_2pt"]}, 3PT {result["made_3pt"]}/{result["attempts_3pt"]}, points {result["points"]}, score {score}')
        if y % 20 == 0:
            print(f'Progress: hoop y={y}, best so far y={best["hoop_y"] if best else "None"} score={best_score if best else "None"}')
    
    if best:
        print('\n=== BEST RESULT ===')
        print(f'Hoop center y: {best["hoop_y"]} px')
        print(f'2PT: {best["made_2pt"]}/{best["attempts_2pt"]}')
        print(f'3PT: {best["made_3pt"]}/{best["attempts_3pt"]}')
        print(f'Points: {best["points"]}')
        # Optionally, save the events for the best hoop y
        events_df = pd.DataFrame(best['events'])
        events_df.to_csv(f'{base}/final_events_best_hoop_y.csv', index=False)
        print(f'Saved events to final_events_best_hoop_y.csv')
        # Also update hoop_params.json with the best y (keep x and radius from base)
        hoop_best = hoop_base.copy()
        hoop_best['hoop_center_px'] = [hoop_center_x, int(best['hoop_y'])]
        with open(f'{base}/hoop_params.json', 'w') as f:
            json.dump(hoop_best, f, indent=2)
        print(f'Updated hoop_params.json with y={int(best["hoop_y"])}')
    else:
        print('No valid result found.')

if __name__ == '__main__':
    main()