#!/usr/bin/env python3
import numpy as np
import pandas as pd
import sqlite3
import cv2
import os

# Paths
base_dir = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
video_path = os.path.join(base_dir, 'uploads', 'Liberty_Vs_Riverstone_20260519_103815_segment_2min.webm')
hoop_path = os.path.join(base_dir, 'hoop_2min.npy')  # from earlier detection on 2-min segment
ball_path = os.path.join(base_dir, 'ball_yolov8s_2min_conf0001_stride4.csv')
db_path = os.path.join(base_dir, 'film_analysis.db')
signal_path = os.path.join(base_dir, 'signal_full.csv')  # optional

# Load hoop data
hoop_data = np.load(hoop_path, allow_pickle=True).item()
frame_indices = hoop_data['frame_indices']  # sampled frames
centers = hoop_data['centers']  # (N,2) [x, y]
radii = hoop_data['radii']  # (N,)

# Determine needed size: max frame from ball and hoop data
ball_df_tmp = pd.read_csv(ball_path)
max_frame_ball = ball_df_tmp['frame'].max()
max_frame_hoop = frame_indices.max() if len(frame_indices) > 0 else 0
max_frame = max(max_frame_ball, max_frame_hoop)
total_frames = max_frame + 1  # indices 0..max_frame
print(f'Max frame: {max_frame}, allocating {total_frames} frames')

# Create arrays for all frames, fill with NaN
all_centers = np.full((total_frames, 2), np.nan, dtype=float)
all_radii = np.full(total_frames, np.nan, dtype=float)
all_centers[frame_indices] = centers
all_radii[frame_indices] = radii

# Interpolate missing values (linear interpolation)
def interpolate_nan(arr):
    nans = np.isnan(arr)
    if not np.any(nans):
        return arr
    x = np.arange(len(arr))
    arr[nans] = np.interp(x[nans], x[~nans], arr[~nans])
    return arr

# Interpolate x and y separately
all_centers[:,0] = interpolate_nan(all_centers[:,0])
all_centers[:,1] = interpolate_nan(all_centers[:,1])
all_radii = interpolate_nan(all_radii)

# Compute scale and translation (world origin at hoop center)
HOOP_REAL_RADIUS_FT = 0.75  # feet
scale_ft_per_px = HOOP_REAL_RADIUS_FT / all_radii  # ft per px
# For each pixel coordinate (x_px, y_px), world coordinates:
# x_ft = (x_px - center_x) * scale_ft_per_px
# y_ft = (center_y - y_px) * scale_ft_per_px   (flip y so up is positive)

# Load ball detections
ball_df = pd.read_csv(ball_path)
print(f'Ball detections: {len(ball_df)}')
# Ensure required columns
if not {'frame','x','y'}.issubset(ball_df.columns):
    raise ValueError('CSV missing required columns')

# Sort by frame
ball_df = ball_df.sort_values('frame').reset_index(drop=True)

# Simple tracking: link detections to tracks based on distance in pixels
tracks = []  # each track is list of detections (dict with frame, x_px, y_px)
max_frame_gap = 5  # max frames to allow gap
max_dist_px = 30   # max pixel distance to link

for idx, row in ball_df.iterrows():
    f = int(row['frame'])
    x = float(row['x'])
    y = float(row['y'])
    assigned = False
    for track in tracks:
        last = track[-1]
        f_gap = f - last['frame']
        if f_gap <= max_frame_gap:
            dist = np.sqrt((x - last['x_px'])**2 + (y - last['y_px'])**2)
            if dist <= max_dist_px:
                track.append({'frame': f, 'x_px': x, 'y_px': y})
                assigned = True
                break
    if not assigned:
        tracks.append([{'frame': f, 'x_px': x, 'y_px': y}])

print(f'Number of tracks: {len(tracks)}')
# Filter tracks with at least 3 detections
tracks = [t for t in tracks if len(t) >= 3]
print(f'Tracks after filtering (len>=3): {len(tracks)}')

# Load person detections from DB for game 299q1
conn = sqlite3.connect(db_path)
person_query = """
SELECT frame_number, x_center, y_center, width, height
FROM detections
WHERE game_id = '299q1'
  AND object_class = 'person'
"""
person_df = pd.read_sql_query(person_query, conn)
conn.close()
print(f'Person detections from DB: {len(person_df)}')
# person_df columns: frame_number, x_center, y_center, width, height
# Compute bottom-center y (approx foot): y_center + height/2
person_df['foot_x'] = person_df['x_center']
person_df['foot_y'] = person_df['y_center'] + person_df['height'] / 2.0
# We'll keep as needed.

# Helper to get world coords for a given frame and pixel coords
def world_coords(frame, x_px, y_px):
    cx = all_centers[frame,0]
    cy = all_centers[frame,1]
    s = scale_ft_per_px[frame]
    x_ft = (x_px - cx) * s
    y_ft = (cy - y_px) * s  # note: image y increases down, so cy - y_px gives up positive
    return x_ft, y_ft

# Precompute person world coordinates per frame for quick lookup
# We'll group by frame
person_by_frame = {}
for _, row in person_df.iterrows():
    f = int(row['frame_number'])
    if f not in person_by_frame:
        person_by_frame[f] = []
    fx, fy = world_coords(f, row['foot_x'], row['foot_y'])
    person_by_frame[f].append((fx, fy))

# Optionally load referee signals (not used for counting, just for info)
if os.path.exists(signal_path):
    signal_df = pd.read_csv(signal_path)
    print(f'Referee signals: {len(signal_df)}')
    # Expect columns: frame, signal (1=one-hand, 2=both-hands) maybe
    # We'll just store set of frames with signals
    signal_frames = set(signal_df['frame'].tolist()) if 'frame' in signal_df.columns else set()
else:
    signal_frames = set()

# For each track, compute world coordinates and detect attempt/make
attempts = []  # each dict: frame, peak_y_ft, made, type ('2PT','3PT','UNK')
makes = []

for track in tracks:
    frames = [d['frame'] for d in track]
    x_pxs = [d['x_px'] for d in track]
    y_pxs = [d['y_px'] for d in track]
    # Compute world coordinates
    x_fts = []
    y_fts = []
    for f, xp, yp in zip(frames, x_pxs, y_pxs):
        xf, yf = world_coords(f, xp, yp)
        x_fts.append(xf)
        y_fts.append(yf)
    # Smooth y_ft with moving average (window 5)
    if len(y_fts) >= 5:
        kernel = np.ones(5)/5
        y_fts_smooth = np.convolve(y_fts, kernel, mode='same')
    else:
        y_fts_smooth = np.array(y_fts)
    # Find local maxima in y_fts_smooth (highest point)
    peaks = []
    for i in range(1, len(y_fts_smooth)-1):
        if y_fts_smooth[i] > y_fts_smooth[i-1] and y_fts_smooth[i] > y_fts_smooth[i+1]:
            peaks.append(i)
    if not peaks:
        continue
    # For each peak, check if it's a valid attempt: within vertical band near hoop (|y_ft| < 2.0 ft) and has rising/falling trend
    for peak_idx in peaks:
        # Check trend: need at least 2 frames before and after
        if peak_idx < 2 or peak_idx >= len(y_fts_smooth)-2:
            continue
        # Check rising before: y_fts_smooth[peak_idx-2] < y_fts_smooth[peak_idx-1] < y_fts_smooth[peak_idx]
        if not (y_fts_smooth[peak_idx-2] < y_fts_smooth[peak_idx-1] < y_fts_smooth[peak_idx]):
            continue
        # Check falling after: y_fts_smooth[peak_idx] > y_fts_smooth[peak_idx+1] > y_fts_smooth[peak_idx+2]
        if not (y_fts_smooth[peak_idx] > y_fts_smooth[peak_idx+1] > y_fts_smooth[peak_idx+2]):
            continue
        # Check vertical band: hoop center y_ft = 0, we want peak near hoop (within 2.0 ft?)
        y_peak = y_fts_smooth[peak_idx]
        if abs(y_peak) > 2.0:  # too far from hoop vertically
            continue
        # This is a candidate attempt
        attempt_frame = frames[peak_idx]
        # Determine make: look for continued downward motion after peak for at least 2 frames below -hoop_radius_ft
        hoop_radius_ft = HOOP_REAL_RADIUS_FT  # constant
        made = False
        # Look ahead up to 5 frames
        for ahead in range(1, 6):
            if peak_idx + ahead >= len(y_fts_smooth):
                break
            if y_fts_smooth[peak_idx + ahead] < -hoop_radius_ft:
                # found one frame below, need consecutive
                consec = 1
                for ahead2 in range(ahead+1, min(ahead+6, len(y_fts_smooth))):
                    if y_fts_smooth[ahead2] < -hoop_radius_ft:
                        consec += 1
                    else:
                        break
                if consec >= 2:
                    made = True
                break
        # Classify 2PT vs 3PT using nearest person at attempt frame
        shot_type = 'UNK'
        if attempt_frame in person_by_frame and len(person_by_frame[attempt_frame]) > 0:
            ball_x, ball_y = world_coords(attempt_frame, x_pxs[peak_idx], y_pxs[peak_idx])
            # Find nearest person
            min_dist = float('inf')
            for (px, py) in person_by_frame[attempt_frame]:
                dist = np.sqrt((ball_x - px)**2 + (ball_y - py)**2)
                if dist < min_dist:
                    min_dist = dist
            if min_dist < 22.0:  # inside three-point line
                shot_type = '2PT'
            else:
                shot_type = '3PT'
        else:
            # fallback: use heuristic based on ball x_ft (if far left/right) but unreliable
            shot_type = 'UNK'
        attempts.append({
            'frame': attempt_frame,
            'peak_y_ft': y_peak,
            'made': made,
            'type': shot_type
        })
        if made:
            makes.append(attempt_frame)

print(f'Number of attempts found: {len(attempts)}')
print(f'Number of makes: {len(makes)}')
# Summarize by type
type_counts = {}
for a in attempts:
    t = a['type']
    type_counts[t] = type_counts.get(t,0)+1
print(f'Attempts by type: {type_counts}')
make_counts = {}
for a in attempts:
    if a['made']:
        t = a['type']
        make_counts[t] = make_counts.get(t,0)+1
print(f'Makes by type: {make_counts}')

# Compute points
points = 0
for a in attempts:
    if a['type'] == '2PT':
        points += 2 if a['made'] else 0
    elif a['type'] == '3PT':
        points += 3 if a['made'] else 0
    elif a['type'] == 'FT':
        points += 1 if a['made'] else 0
    else:
        # unknown, we could assume 2PT but we'll skip for now
        pass
print(f'Total points (from classified 2PT/3PT): {points}')
# Also output a few attempts for inspection
if attempts:
    print('First few attempts:')
    for a in attempts[:10]:
        print(f"  Frame {a['frame']}: peak y_ft={a['peak_y_ft']:.2f} ft, made={a['made']}, type={a['type']}")
# Optionally, check referee signal proximity for attempts
if signal_frames:
    signal_near = 0
    for a in attempts:
        f = a['frame']
        # check if any signal frame within +/- 1 frame (at 3.75 fps, 0.3s ~ 1 frame)
        if any(abs(f - sf) <= 1 for sf in signal_frames):
            signal_near += 1
    print(f'Attempts with nearby referee signal (±1 frame): {signal_near}/{len(attempts)}')