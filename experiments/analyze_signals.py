#!/usr/bin/env python3
import pandas as pd
import numpy as np
import json
import os

# Load hoop params
hoop_path = 'hoop_params.json'
with open(hoop_path) as f:
    hoop = json.load(f)
hoop_center_px = np.array(hoop['hoop_center_px'])
hoop_radius_px = hoop['hoop_radius_px']
scale_ft_per_px = hoop['scale_ft_per_px']
print(f'Hoop center: {hoop_center_px}, radius: {hoop_radius_px} px, scale: {scale_ft_per_px} ft/px')
hoop_center_ft = hoop_center_px * scale_ft_per_px
hoop_radius_ft = hoop_radius_px * scale_ft_per_px
print(f'Hoop center ft: {hoop_center_ft}, radius: {hoop_radius_ft} ft')

# Parameters
SIGNAL_WINDOW_SEC = 1.0  # seconds around signal to look for ball
BALL_MAX_GAP_SEC = 0.5   # max gap to interpolate ball trajectory
MAKE_CONSEC_FRAMES = 1   # frames below rim to count as make (at 3.75 fps, ~267ms)
THREEPT_DISTANCE_FT = 22.0

def load_ball_detections(csv_path):
    df = pd.read_csv(csv_path)
    df = df.sort_values('frame').reset_index(drop=True)
    return df

def interpolate_ball(frames, values, fps, max_gap_sec=BALL_MAX_GAP_SEC):
    # Linear interpolation for short gaps
    max_gap_frames = int(max_gap_sec * fps)
    df = pd.DataFrame({'frame': frames, 'value': values})
    df = df.set_index('frame')
    full_idx = np.arange(df.index.min(), df.index.max()+1)
    df_full = df.reindex(full_idx)
    df_full['value'] = df_full['value'].interpolate(method='linear', limit=max_gap_frames)
    return df_full.index.values, df_full['value'].values

def associate_shooter_from_pose(attempt_frame, pose_df):
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
    return ankle_mean * scale_ft_per_px

def classify_shot_type(shooter_ft, hoop_center_ft):
    if shooter_ft is None:
        return 'unknown'
    dist = np.linalg.norm(shooter_ft - hoop_center_ft)
    if dist >= THREEPT_DISTANCE_FT:
        return '3PT'
    else:
        return '2PT'

def detect_make_from_ball(ball_df, attempt_frame, fps):
    # Check if after attempt frame, ball goes below hoop plane for MAKE_CONSEC_FRAMES consecutive frames
    hoop_y_px = hoop_center_px[1]
    threshold_px = hoop_y_px + hoop_radius_px
    # We need ball y values after attempt frame
    # Get ball df sorted
    ball_after = ball_df[ball_df['frame'] >= attempt_frame].copy()
    if ball_after.empty:
        return False
    # Interpolate if needed? We'll just use existing detections; but we can require at least MAKE_CONSEC_FRAMES detections in a row below threshold.
    # Simpler: count consecutive detections where y > threshold
    consec = 0
    for _, row in ball_after.iterrows():
        if row['y'] > threshold_px:
            consec += 1
            if consec >= MAKE_CONSEC_FRAMES:
                return True
        else:
            consec = 0
    return False

def main():
    base = '.'
    signal_csv = os.path.join(base, 'signal_full.csv')
    ball_csv = os.path.join(base, 'ball_q1_conf0005_stride8.csv')  # use existing denser-ish
    pose_csv = os.path.join(base, 'pose_keypoints_full.csv')
    output_csv = os.path.join(base, 'final_events_signal_based2.csv')
    
    signal_df = pd.read_csv(signal_csv)
    ball_df = load_ball_detections(ball_csv)
    pose_df = pd.read_csv(pose_csv)
    
    # FPS from video
    fps = 3.75
    print(f'FPS: {fps}')
    print(f'Signal rows: {len(signal_df)}')
    print(f'Ball rows: {len(ball_df)}')
    print(f'Pose rows: {len(pose_df)}')
    
    events = []
    for idx, row in signal_df.iterrows():
        if row['signal'] == 0:
            continue
        frame = int(row['frame'])
        time_s = row['timestamp_ms'] / 1000.0
        signal_type = int(row['signal'])  # 1 or 2
        # Find ball detection within window
        window_frames = int(SIGNAL_WINDOW_SEC * fps)
        ball_window = ball_df[(ball_df['frame'] >= frame - window_frames) & (ball_df['frame'] <= frame + window_frames)]
        if ball_window.empty:
            # No ball nearby, skip? Or still create event with unknown shooter?
            # We'll still create event but mark shooter unknown
            ball_feat = None
            ball_frame = None
        else:
            # pick the ball detection closest in time
            ball_window = ball_window.copy()
            ball_window['time_diff'] = np.abs(ball_window['timestamp_ms'] - row['timestamp_ms'])
            ball_feat = ball_window.loc[ball_window['time_diff'].idxmin()]
            ball_frame = int(ball_feat['frame'])
        # Shooter from pose at attempt frame (use frame of signal)
        shooter_ft = associate_shooter_from_pose(frame, pose_df)
        shot_type = classify_shot_type(shooter_ft, hoop_center_ft)
        # Determine make/miss
        made = False
        if signal_type == 2:
            # Both hands -> assume made 3PT
            made = True
            shot_type = '3PT'  # override
        else:
            # One hand -> attempt, check ball for make
            if ball_feat is not None:
                made = detect_make_from_ball(ball_df, frame, fps)
                if made:
                    shot_type = '3PT'  # if made, assume 3PT? Actually could be 2PT made. We'll keep original classification.
        events.append({
            'signal_id': idx,
            'frame': frame,
            'time_s': round(time_s, 3),
            'signal_type': signal_type,
            'ball_frame': ball_frame if ball_feat is not None else None,
            'ball_conf': float(ball_feat['conf']) if ball_feat is not None else None,
            'shooter_ft_x': round(shooter_ft[0], 3) if shooter_ft is not None else None,
            'shooter_ft_y': round(shooter_ft[1], 3) if shooter_ft is not None else None,
            'shot_type_initial': shot_type if not (signal_type==2 and made) else '3PT',
            'made_initial': made,
            'shot_type_final': '3PT' if signal_type==2 else shot_type,
            'made_final': made
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
        # Also show breakdown by signal type
        print('\nBy signal type:')
        for sig in [1,2]:
            sub = events_df[events_df['signal_type']==sig]
            print("Signal {}: {} events, made {}".format(sig, len(sub), sub["made_final"].sum()))

if __name__ == '__main__':
    main()