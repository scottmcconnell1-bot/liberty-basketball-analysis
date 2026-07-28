"""Step 2: Clean ball detections + shot detection for v9f.
Uses cached raw detections from run_v9f.py detection pass.
Applies abdullahtarek-style ball cleaning:
  1. remove_wrong_detections (25px max jump)
  2. interpolate_ball_positions (fill gaps)
Then detects shots via same-frame ball-hoop proximity.
"""
import cv2, numpy as np, pandas as pd, os, time, pickle
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

# ===== Load raw data =====
log("Loading raw detections...")
raw_df = pd.read_csv(f'{OUT}/v9f_balls_raw.csv')
hoop_df = pd.read_csv(f'{OUT}/v9f_hoops.csv')
with open(f'{OUT}/v9f_court.pkl','rb') as f: court_dict = pickle.load(f)
with open(f'{OUT}/v9f_players.pkl','rb') as f: player_dict = pickle.load(f)

max_frame = max(raw_df['frame'].max(), hoop_df['frame'].max()) + 1
total_frames = max(2701, max_frame)
log(f"Raw: {len(raw_df)} ball dets, {len(hoop_df)} hoop dets, {len(court_dict)} courts")
log(f"Frame range: 0-{total_frames-1}")

# Build per-frame ball array (index = frame number)
ball_bboxes = [None] * total_frames  # each entry: [x1,y1,x2,y2,conf] or None
for r in raw_df.itertuples(index=False, name=None):
    fn = r[0]
    if fn < total_frames:
        ball_bboxes[fn] = [r[1], r[2], r[3], r[4], r[5]]

# ===== Step 1: remove_wrong_detections (25px max jump) =====
log("Removing wrong ball detections (max 25px jump)...")
MAX_JUMP = 25
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
log(f"Removed {removed} false positives, kept {kept} detections")

# ===== Step 2: interpolate_ball_positions =====
log("Interpolating ball positions...")
records = []
for i in range(total_frames):
    if ball_bboxes[i] is not None:
        records.append((i, *ball_bboxes[i]))
    else:
        records.append((i, np.nan, np.nan, np.nan, np.nan, np.nan))

df = pd.DataFrame(records, columns=['frame','x1','y1','x2','y2','conf'])
df = df.interpolate().bfill().ffill()

# Save clean ball data
clean_records = []
for _, row in df.iterrows():
    if not np.isnan(row['x1']):
        clean_records.append({
            'frame': int(row['frame']),
            'x1': round(row['x1'], 2), 'y1': round(row['y1'], 2),
            'x2': round(row['x2'], 2), 'y2': round(row['y2'], 2),
            'conf': round(row['conf'], 3)
        })

clean_df = pd.DataFrame(clean_records)
clean_df.to_csv(f'{OUT}/v9f_balls_clean.csv', index=False)
log(f"Clean ball data saved: {len(clean_df)} frames")

# Build per-frame lookup
balls_by_frame = {}
for _, row in clean_df.iterrows():
    fn = int(row['frame'])
    cx = (row['x1'] + row['x2']) / 2
    cy = (row['y1'] + row['y2']) / 2
    balls_by_frame[fn] = (cx, cy, row['conf'])

hoops_by_frame = defaultdict(list)
for r in hoop_df.itertuples(index=False, name=None):
    hoops_by_frame[r[0]].append((r[1], r[2], r[3]))

log(f"Clean track: {len(balls_by_frame)} ball frames, {len(hoops_by_frame)} hoop frames")

# ===== Step 3: Shot detection - ball near hoop =====
log("Detecting shots (ball within proximity of hoop)...")
shot_candidates = []

for hf in sorted(hoops_by_frame.keys()):
    for hcx, hcy, hcf in hoops_by_frame[hf]:
        for offset in range(-3, 4):
            bf = hf + offset
            if bf not in balls_by_frame:
                continue
            bcx, bcy, bcf = balls_by_frame[bf]
            dist = np.sqrt((bcx - hcx)**2 + (bcy - hcy)**2)
            if dist < 120:
                shot_candidates.append({
                    'ball_frame': bf, 'hoop_frame': hf,
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
    
    # Cluster into shots (within 10 frames)
    sc_df = sc_df.sort_values('ball_frame')
    groups = []
    current = [sc_df.iloc[0]]
    for i in range(1, len(sc_df)):
        if sc_df.iloc[i]['ball_frame'] - sc_df.iloc[i-1]['ball_frame'] <= 10:
            current.append(sc_df.iloc[i])
        else:
            groups.append(current)
            current = [sc_df.iloc[i]]
    groups.append(current)
    
    log(f"Shot groups: {len(groups)}")
    
    shots = []
    for group in groups:
        best = min(group, key=lambda x: x['dist'])
        fn = int(best['ball_frame'])
        
        # Make if ball within rim radius (~30px)
        result = 'MAKE' if best['dist'] < 35 else 'MISS'
        
        # 2PT/3PT: use pixel distance heuristic
        # Need calibration. For now: < 100px = 2PT, >= 100px = 3PT
        shot_type = '3PT' if best['dist'] > 100 else '2PT'
        
        # Find nearest player for shooter info
        shooter_dist = None
        for pfn in range(fn-10, fn+11):
            if pfn in player_dict:
                for px, py, pc in player_dict[pfn]:
                    d = np.sqrt((px-best['bcx'])**2 + (py-best['bcy'])**2)
                    if shooter_dist is None or d < shooter_dist:
                        shooter_dist = d
        
        shots.append({
            'frame': int(fn), 'bx': best['bcx'], 'by': best['bcy'],
            'hoop_dist': best['dist'], 'type': shot_type,
            'result': result, 'bcf': best['bcf'], 'hcf': best['hcf'],
            'shooter_px': round(shooter_dist,1) if shooter_dist else None
        })
    
    shots_df = pd.DataFrame(shots).sort_values('frame')
    shots_df.to_csv(f'{OUT}/shots_v9f.csv', index=False)
    
    # Stats
    log("="*60)
    t2 = [s for s in shots if s['type']=='2PT']
    t3 = [s for s in shots if s['type']=='3PT']
    makes = [s for s in shots if s['result']=='MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')
    log(f"Shots: {len(shots)}")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(makes)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['hoop_dist']:5.1f}px bcf={s['bcf']:.3f} hcf={s['hcf']:.3f}")
else:
    log("No shots found.")
