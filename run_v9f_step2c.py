"""Run v9f step 2c: detect shots by finding ball trajectory discontinuities.
Strategy:
1. Track ball with 25px max jump (clean tracking)
2. Find gaps where ball disappears for 3-30 frames (shot in flight)
3. Check if ball reappears near a hoop after the gap
4. Also check same-frame ball-hoop proximity for direct detections
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

max_frame = int(max(raw_df['frame'].max(), hoop_df['frame'].max())) + 1
total_frames = max(2701, max_frame)

# Build raw ball array
raw_balls = [None] * total_frames  # (cx, cy, conf) or None
for r in raw_df.itertuples(index=False, name=None):
    fn = int(r[0])
    if fn < total_frames:
        cx = (r[1]+r[3])/2
        cy = (r[2]+r[4])/2
        raw_balls[fn] = (cx, cy, r[5])

# Build hoop array
hoops_by_frame = defaultdict(list)
for r in hoop_df.itertuples(index=False, name=None):
    hoops_by_frame[int(r[0])].append((r[1], r[2], r[3]))

# ===== Ball tracking with 25px max jump =====
log("Tracking ball (25px max jump)...")
MAX_JUMP_TRACK = 25
tracked = [None] * total_frames  # (cx, cy, conf, raw_fn) or None
last_good = -1

for i in range(total_frames):
    if raw_balls[i] is None:
        continue
    if last_good == -1:
        tracked[i] = (*raw_balls[i], i)
        last_good = i
        continue
    
    frame_gap = i - last_good
    adjusted_max = MAX_JUMP_TRACK * frame_gap
    curr_cx, curr_cy = raw_balls[i][0], raw_balls[i][1]
    last_cx, last_cy = tracked[last_good][0], tracked[last_good][1]
    dist = np.sqrt((curr_cx-last_cx)**2 + (curr_cy-last_cy)**2)
    
    if dist > adjusted_max:
        pass  # skip this detection (false positive)
    else:
        tracked[i] = (*raw_balls[i], i)
        last_good = i

tracked_count = sum(1 for t in tracked if t is not None)
log(f"Tracked: {tracked_count} frames")

# ===== Find shot candidates: gaps in tracking near hoops =====
log("Finding shot candidates from tracking gaps...")
shot_events = []

# Get all tracked frame numbers
tracked_frames = [i for i in range(total_frames) if tracked[i] is not None]

# Find gaps (3-30 frames with no tracking)
gaps = []
for i in range(len(tracked_frames)-1):
    gap_start = tracked_frames[i]
    gap_end = tracked_frames[i+1]
    gap_size = gap_end - gap_start - 1
    if 2 <= gap_size <= 30:
        gaps.append((gap_start, gap_end, gap_size))

log(f"Tracking gaps (2-30 frames): {len(gaps)}")

# For each gap, check if ball reappears near a hoop
for gap_start, gap_end, gap_size in gaps:
    # Ball position before gap
    before = tracked[gap_start]
    after = tracked[gap_end]
    
    # Check for hoop detections during and after the gap
    for hf in range(gap_start-5, gap_end+15):
        if hf not in hoops_by_frame:
            continue
        for hcx, hcy, hcf in hoops_by_frame[hf]:
            # Distance from hoop to ball before gap
            d_before = np.sqrt((before[0]-hcx)**2 + (before[1]-hcy)**2)
            # Distance from hoop to ball after gap
            d_after = np.sqrt((after[0]-hcx)**2 + (after[1]-hcy)**2)
            
            # Shot: ball was far, then close to hoop, then far again
            # OR ball was close to hoop and then disappeared (ball went through)
            min_dist = min(d_before, d_after)
            
            if min_dist < 120:
                # Determine shot frame as the frame closest to hoop
                if d_before < d_after:
                    shot_frame = gap_start
                    shot_dist = d_before
                else:
                    shot_frame = gap_end
                    shot_dist = d_after
                
                shot_events.append({
                    'shot_frame': shot_frame,
                    'gap_start': gap_start,
                    'gap_end': gap_end,
                    'gap_size': gap_size,
                    'hoop_frame': hf,
                    'dist': round(min_dist, 1),
                    'd_before': round(d_before, 1),
                    'd_after': round(d_after, 1),
                    'hcf': round(hcf, 3),
                    'type': 'gap'
                })

# Also add same-frame ball-hoop proximity (from the tracked ball)
log("Finding same-frame ball-hoop proximity...")
for i in range(total_frames):
    if tracked[i] is None:
        continue
    bcx, bcy = tracked[i][0], tracked[i][1]
    
    for offset in range(-3, 4):
        hf = i + offset
        if hf not in hoops_by_frame:
            continue
        for hcx, hcy, hcf in hoops_by_frame[hf]:
            dist = np.sqrt((bcx-hcx)**2 + (bcy-hcy)**2)
            if dist < 80:
                shot_events.append({
                    'shot_frame': i,
                    'gap_start': i,
                    'gap_end': i,
                    'gap_size': 0,
                    'hoop_frame': hf,
                    'dist': round(dist, 1),
                    'd_before': round(dist, 1),
                    'd_after': round(dist, 1),
                    'hcf': round(hcf, 3),
                    'type': 'proximity'
                })

log(f"Total shot events: {len(shot_events)}")

if shot_events:
    se_df = pd.DataFrame(shot_events).sort_values('dist')
    print("\nTop 30 shot events by distance:")
    print(se_df.head(30).to_string(index=False))
    
    # Cluster into shots (within 20 frames)
    se_df = se_df.sort_values('shot_frame').reset_index(drop=True)
    groups = []
    current = [se_df.iloc[0]]
    for i in range(1, len(se_df)):
        if se_df.iloc[i]['shot_frame'] - se_df.iloc[i-1]['shot_frame'] <= 20:
            current.append(se_df.iloc[i])
        else:
            groups.append(current)
            current = [se_df.iloc[i]]
    groups.append(current)
    
    log(f"Shot groups: {len(groups)}")
    
    shots = []
    for group in groups:
        best = min(group, key=lambda x: x['dist'])
        fn = int(best['shot_frame'])
        
        result = 'MAKE' if best['dist'] < 40 else 'MISS'
        shot_type = '3PT' if best['dist'] > 100 else '2PT'
        
        # Get ball position
        if tracked[fn] is not None:
            bx, by = tracked[fn][0], tracked[fn][1]
        else:
            bx, by = 0, 0
        
        # Find shooter
        shooter_dist = None
        for pfn in range(fn-10, fn+11):
            if pfn in player_dict:
                for px, py, pc in player_dict[pfn]:
                    d = np.sqrt((px-bx)**2 + (py-by)**2)
                    if shooter_dist is None or d < shooter_dist:
                        shooter_dist = d
        
        shots.append({
            'frame': fn, 'bx': round(bx,1), 'by': round(by,1),
            'hoop_dist': best['dist'], 'type': shot_type,
            'result': result, 'gap_size': best['gap_size'],
            'det_type': best['type'], 'hcf': best['hcf'],
            'shooter_px': round(shooter_dist,1) if shooter_dist else None
        })
    
    shots_df = pd.DataFrame(shots).sort_values('frame')
    shots_df.to_csv(f'{OUT}/shots_v9f_smart.csv', index=False)
    
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
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['hoop_dist']:5.1f}px "
            f"gap={s['gap_size']:2d} type={s['det_type']:9s} hcf={s['hcf']:.3f}")
else:
    log("No shots found.")
