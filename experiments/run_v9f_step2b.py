"""Run v9f step 2b: relaxed max-jump threshold for ball cleaning.
Original used 25px (too aggressive for fast-moving ball).
Now trying 100px to preserve shot trajectories.
"""
import cv2, numpy as np, pandas as pd, os, time, pickle
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

MAX_JUMP = 100  # relaxed from 25px - ball can move fast during shots

# ===== Load raw data =====
log("Loading raw detections...")
raw_df = pd.read_csv(f'{OUT}/v9f_balls_raw.csv')
hoop_df = pd.read_csv(f'{OUT}/v9f_hoops.csv')
with open(f'{OUT}/v9f_court.pkl','rb') as f: court_dict = pickle.load(f)
with open(f'{OUT}/v9f_players.pkl','rb') as f: player_dict = pickle.load(f)

max_frame = max(raw_df['frame'].max(), hoop_df['frame'].max()) + 1
total_frames = max(2701, max_frame)

ball_bboxes = [None] * total_frames
for r in raw_df.itertuples(index=False, name=None):
    fn = r[0]
    if fn < total_frames:
        ball_bboxes[fn] = [r[1], r[2], r[3], r[4], r[5]]

# ===== remove_wrong_detections with relaxed threshold =====
log(f"Removing wrong detections (max {MAX_JUMP}px jump)...")
last_good_idx = -1
removed = 0
for i in range(total_frames):
    if ball_bboxes[i] is None:
        continue
    if last_good_idx == -1:
        last_good_idx = i
        continue
    frame_gap = i - last_good_idx
    adjusted_max = MAX_JUMP * frame_gap
    curr_cx = (ball_bboxes[i][0] + ball_bboxes[i][2]) / 2
    curr_cy = (ball_bboxes[i][1] + ball_bboxes[i][3]) / 2
    last_cx = (ball_bboxes[last_good_idx][0] + ball_bboxes[last_good_idx][2]) / 2
    last_cy = (ball_bboxes[last_good_idx][1] + ball_bboxes[last_good_idx][3]) / 2
    dist = np.sqrt((curr_cx - last_cx)**2 + (curr_cy - last_cy)**2)
    if dist > adjusted_max:
        ball_bboxes[i] = None
        removed += 1
    else:
        last_good_idx = i

kept = sum(1 for b in ball_bboxes if b is not None)
log(f"Removed {removed}, kept {kept}")

# ===== Interpolate =====
log("Interpolating...")
records = []
for i in range(total_frames):
    if ball_bboxes[i] is not None:
        records.append((i, *ball_bboxes[i]))
    else:
        records.append((i, np.nan, np.nan, np.nan, np.nan, np.nan))

df = pd.DataFrame(records, columns=['frame','x1','y1','x2','y2','conf'])
df = df.interpolate().bfill().ffill()

clean_records = []
for _, row in df.iterrows():
    if not np.isnan(row['x1']):
        clean_records.append({
            'frame': int(row['frame']),
            'x1': round(row['x1'],2), 'y1': round(row['y1'],2),
            'x2': round(row['x2'],2), 'y2': round(row['y2'],2),
            'conf': round(row['conf'],3)
        })
clean_df = pd.DataFrame(clean_records)
clean_df.to_csv(f'{OUT}/v9f_balls_clean_r100.csv', index=False)

# Build lookups
balls_by_frame = {}
for _, row in clean_df.iterrows():
    fn = int(row['frame'])
    cx = (row['x1'] + row['x2']) / 2
    cy = (row['y1'] + row['y2']) / 2
    balls_by_frame[fn] = (cx, cy, row['conf'])

hoops_by_frame = defaultdict(list)
for r in hoop_df.itertuples(index=False, name=None):
    hoops_by_frame[r[0]].append((r[1], r[2], r[3]))

log(f"Clean: {len(balls_by_frame)} ball frames, {len(hoops_by_frame)} hoop frames")

# ===== Shot detection =====
log("Detecting shots...")
shot_candidates = []
for hf in sorted(hoops_by_frame.keys()):
    for hcx, hcy, hcf in hoops_by_frame[hf]:
        for offset in range(-5, 6):  # wider window: ±5 frames
            bf = hf + offset
            if bf not in balls_by_frame:
                continue
            bcx, bcy, bcf = balls_by_frame[bf]
            dist = np.sqrt((bcx-hcx)**2 + (bcy-hcy)**2)
            if dist < 150:  # wider threshold
                shot_candidates.append({
                    'ball_frame': int(bf), 'hoop_frame': int(hf),
                    'bcx': round(bcx,1), 'bcy': round(bcy,1),
                    'hcx': round(hcx,1), 'hcy': round(hcy,1),
                    'dist': round(dist,1), 'bcf': round(bcf,3),
                    'hcf': round(hcf,3), 'offset': abs(bf-hf)
                })

log(f"Proximity candidates: {len(shot_candidates)}")

if shot_candidates:
    sc_df = pd.DataFrame(shot_candidates).sort_values('dist')
    print("\nTop 30 ball-hoop proximities:")
    print(sc_df.head(30).to_string(index=False))
    
    # Check distribution of distances
    print(f"\nDistance distribution:")
    for thresh in [20, 30, 50, 75, 100, 150]:
        count = (sc_df['dist'] < thresh).sum()
        print(f'  < {thresh}px: {count} events')
    
    # Cluster into shots (within 15 frames)
    sc_df_sorted = sc_df.sort_values('ball_frame').reset_index(drop=True)
    groups = []
    current = [sc_df_sorted.iloc[0]]
    for i in range(1, len(sc_df_sorted)):
        if sc_df_sorted.iloc[i]['ball_frame'] - sc_df_sorted.iloc[i-1]['ball_frame'] <= 15:
            current.append(sc_df_sorted.iloc[i])
        else:
            groups.append(current)
            current = [sc_df_sorted.iloc[i]]
    groups.append(current)
    
    log(f"Shot groups: {len(groups)}")
    
    shots = []
    for group in groups:
        best = min(group, key=lambda x: x['dist'])
        fn = int(best['ball_frame'])
        result = 'MAKE' if best['dist'] < 40 else 'MISS'
        shot_type = '3PT' if best['dist'] > 100 else '2PT'
        
        shooter_dist = None
        for pfn in range(fn-10, fn+11):
            if pfn in player_dict:
                for px, py, pc in player_dict[pfn]:
                    d = np.sqrt((px-best['bcx'])**2 + (py-best['bcy'])**2)
                    if shooter_dist is None or d < shooter_dist:
                        shooter_dist = d
        
        shots.append({
            'frame': fn, 'bx': best['bcx'], 'by': best['bcy'],
            'hoop_dist': best['dist'], 'type': shot_type,
            'result': result, 'bcf': best['bcf'], 'hcf': best['hcf'],
            'shooter_px': round(shooter_dist,1) if shooter_dist else None
        })
    
    shots_df = pd.DataFrame(shots).sort_values('frame')
    shots_df.to_csv(f'{OUT}/shots_v9f_r100.csv', index=False)
    
    t2 = [s for s in shots if s['type']=='2PT']
    t3 = [s for s in shots if s['type']=='3PT']
    makes = [s for s in shots if s['result']=='MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')
    log("="*60)
    log(f"Shots: {len(shots)}")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(makes)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['hoop_dist']:5.1f}px bcf={s['bcf']:.3f} hcf={s['hcf']:.3f}")
else:
    log("No shots found.")
