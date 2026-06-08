import sqlite3
import pandas as pd
import numpy as np
import os

# Parameters
HOOP_REAL_RADIUS_FT = 0.75  # feet
WIDTH = 1280
HEIGHT = 720
PEAK_MIN_HEIGHT = 0.5   # ft above hoop to consider a shot attempt
PEAK_WINDOW = 3         # number of detections on each side to check for local max
CROSS_WINDOW = 20       # frames to search for crossing zero
HOOP_X_TOL_FT = 0.2     # tolerance for make (feet)
THREE_PT_DIST_FT = 22.0 # feet

# Paths
base_dir = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
video_path = os.path.join(base_dir, 'uploads', 'Liberty_Vs_Riverstone_20260519_103815_segment_2min.webm')
hoop_path = os.path.join(base_dir, 'hoop_2min.npy')
ball_path = os.path.join(base_dir, 'ball_finetuned_2min_stride8_xy.csv')
db_path = os.path.join(base_dir, 'film_analysis.db')

# Load hoop data
hoop_data = np.load(hoop_path, allow_pickle=True).item()
hoop_frames = hoop_data['frame_indices']          # (N,)
hoop_centers = hoop_data['centers']               # (N,2)
hoop_radii = hoop_data['radii']                   # (N,)

# Load ball detections
ball_df = pd.read_csv(ball_path)
# Ensure we have x,y columns (we added them)
if 'x' not in ball_df.columns or 'y' not in ball_df.columns:
    # compute from xc,yc if needed
    ball_df['x'] = ball_df['xc'] * WIDTH
    ball_df['y'] = ball_df['yc'] * HEIGHT
# confidence column may not exist; add default if missing
if 'conf' not in ball_df.columns:
    ball_df['conf'] = 1.0
ball_df = ball_df.sort_values('frame').reset_index(drop=True)
print(f'Loaded {len(ball_df)} ball detections')

# Function to get hoop params for a given frame (nearest)
def get_hoop_params(frame):
    idx = np.argmin(np.abs(hoop_frames - frame))
    return hoop_centers[idx], hoop_radii[idx]

# Compute world coordinates
world_coords = []
for _, row in ball_df.iterrows():
    f = int(row['frame'])
    x_px = float(row['x'])
    y_px = float(row['y'])
    center, radius = get_hoop_params(f)
    scale = HOOP_REAL_RADIUS_FT / radius  # ft per pixel
    x_ft = (x_px - center[0]) * scale
    y_ft = (center[1] - y_px) * scale   # positive above hoop
    world_coords.append({
        'frame': f,
        'x_px': x_px,
        'y_px': y_px,
        'x_ft': x_ft,
        'y_ft': y_ft,
        'conf': float(row['conf'])
    })
world_df = pd.DataFrame(world_coords)
print(f'Computed world coordinates for {len(world_df)} detections')

# Detect peaks: local maxima in y_ft above threshold
peaks = []
for i in range(PEAK_WINDOW, len(world_df) - PEAK_WINDOW):
    y = world_df.iloc[i]['y_ft']
    if y < PEAK_MIN_HEIGHT:
        continue
    # check if max in window
    window = world_df.iloc[i-PEAK_WINDOW:i+PEAK_WINDOW+1]['y_ft']
    if y == window.max():
        peaks.append(i)
print(f'Found {len(peaks)} candidate peaks')

# For each peak, attempt to find start/end crossing zero
attempts = []
for pi in peaks:
    peak_frame = world_df.iloc[pi]['frame']
    peak_y = world_df.iloc[pi]['y_ft']
    # search backward for crossing zero (from negative to positive)
    start_idx = None
    for j in range(pi-1, max(-1, pi-CROSS_WINDOW), -1):
        y_prev = world_df.iloc[j]['y_ft']
        y_curr = world_df.iloc[j+1]['y_ft']
        if y_prev <= 0 and y_curr > 0:
            start_idx = j+1
            break
    # search forward for crossing zero (from positive to negative)
    end_idx = None
    for j in range(pi, min(len(world_df)-1, pi+CROSS_WINDOW)):
        y_prev = world_df.iloc[j]['y_ft']
        y_curr = world_df.iloc[j+1]['y_ft']
        if y_prev > 0 and y_curr <= 0:
            end_idx = j+1
            break
    if start_idx is not None and end_idx is not None and end_idx > start_idx:
        attempts.append({
            'peak_idx': pi,
            'start_idx': start_idx,
            'end_idx': end_idx,
            'peak_frame': peak_frame,
            'peak_y_ft': peak_y,
            'start_frame': world_df.iloc[start_idx]['frame'],
            'end_frame': world_df.iloc[end_idx]['frame']
        })
print(f'Found {len(attempts)} shot attempts based on zero-crossings')

# For each attempt, determine make and shot type
# Helper to get nearest person distance to hoop at a given frame
def nearest_person_distance(frame):
    conn = sqlite3.connect(db_path)
    # get person detections for frames around +-2
    frame_low = max(0, frame - 2)
    frame_high = frame + 2
    query = """
        SELECT x_center, y_center, width, height
        FROM detections
        WHERE object_class = 'person'
          AND frame_number BETWEEN ? AND ?
    """
    df_persons = pd.read_sql_query(query, conn, params=(frame_low, frame_high))
    conn.close()
    if df_persons.empty:
        return float('inf')
    # compute bottom center y (y_center + height/2) as approximate foot level
    # hoop center from data (need to get for this frame)
    hoop_center, hoop_radius = get_hoop_params(frame)
    hoop_x, hoop_y = hoop_center
    min_dist = float('inf')
    for _, row in df_persons.iterrows():
        px = row['x_center']
        py = row['y_center'] + row['height']/2.0  # bottom center
        dist_px = np.sqrt((px - hoop_x)**2 + (py - hoop_y)**2)
        # convert to feet using scale from hoop radius at this frame
        scale = HOOP_REAL_RADIUS_FT / hoop_radius
        dist_ft = dist_px * scale
        if dist_ft < min_dist:
            min_dist = dist_ft
    return min_dist

# Process attempts
attempt_results = []
for att in attempts:
    f_peak = att['peak_frame']
    # Determine make: check if after peak, y_ft crosses zero going down within a small window and x near hoop
    # We'll use the end_idx we already found (where crossing from positive to negative)
    end_idx = att['end_idx']
    # Get a few points after peak to see if crossing is smooth
    make = False
    # Simple: if the end_idx crossing exists and the x_ft at that frame is within tolerance
    cross_frame = world_df.iloc[end_idx]['frame']
    # get hoop params at cross frame
    hoop_center_cross, hoop_radius_cross = get_hoop_params(int(cross_frame))
    scale_cross = HOOP_REAL_RADIUS_FT / hoop_radius_cross
    # ball x_ft at crossing
    ball_x_ft = world_df.iloc[end_idx]['x_ft']
    hoop_x_ft = 0.0  # by definition
    if abs(ball_x_ft - hoop_x_ft) <= HOOP_X_TOL_FT:
        make = True
    # Shot type
    dist_ft = nearest_person_distance(f_peak)
    if dist_ft < THREE_PT_DIST_FT:
        shot_type = '2PT'
    else:
        shot_type = '3PT'
    attempt_results.append({
        'attempt_id': len(attempt_results)+1,
        'peak_frame': f_peak,
        'peak_y_ft': att['peak_y_ft'],
        'start_frame': att['start_frame'],
        'end_frame': att['end_frame'],
        'make': make,
        'shot_type': shot_type,
        'nearest_person_dist_ft': dist_ft
    })

# Summary
print('\n=== Shot Attempt Results ===')
for res in attempt_results:
    print(f"Attempt {res['attempt_id']}: frame {res['peak_frame']} (y={res['peak_y_ft']:.2f}ft), "
          f"{res['shot_type']}, {'MAKE' if res['make'] else 'MISS'}, "
          f"nearest person {res['nearest_person_dist_ft']:.1f}ft")
print('---')
total_2pt = sum(1 for r in attempt_results if r['shot_type'] == '2PT')
total_3pt = sum(1 for r in attempt_results if r['shot_type'] == '3PT')
made_2pt = sum(1 for r in attempt_results if r['shot_type'] == '2PT' and r['make'])
made_3pt = sum(1 for r in attempt_results if r['shot_type'] == '3PT' and r['make'])
points = made_2pt*2 + made_3pt*3
print(f'2PT attempts: {total_2pt}, made: {made_2pt}')
print(f'3PT attempts: {total_3pt}, made: {made_3pt}')
print(f'Total points: {points}')
print(f'Free throws: not implemented yet')
