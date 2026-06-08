"""Streaming Q1 analysis v9e: same-frame ball-in-hoop detection + relaxed thresholds."""
import cv2, numpy as np, pandas as pd, os, time, pickle
from ultralytics import YOLO
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

# ===== Load cached detections from v9c =====
log("Loading cached detections...")
ball_df = pd.read_csv(f'{OUT}/v9c_balls.csv')
hoop_df = pd.read_csv(f'{OUT}/v9c_hoops.csv')
with open(f'{OUT}/v9c_court.pkl','rb') as f: court_dict = pickle.load(f)
with open(f'{OUT}/v9c_players.pkl','rb') as f: player_dict = pickle.load(f)

balls_by_frame = defaultdict(list)
for r in ball_df.itertuples(index=False, name=None):
    balls_by_frame[r[0]].append((r[1], r[2], r[3]))

hoops_by_frame = defaultdict(list)
for r in hoop_df.itertuples(index=False, name=None):
    hoops_by_frame[r[0]].append((r[1], r[2], r[3]))

all_ball_frames = sorted(balls_by_frame.keys())
all_hoop_frames = sorted(hoops_by_frame.keys())
scf = sorted(court_dict.keys())

log(f"Balls: {len(ball_df)} dets in {len(balls_by_frame)} frames")
log(f"Hoops: {len(hoop_df)} dets in {len(hoops_by_frame)} frames")
log(f"Court: {len(court_dict)} calibrations")

# ===== Find frames where ball is near hoop (same frame or ±2) =====
log("Finding ball-hoop proximity events...")
proximity_events = []

for hf in all_hoop_frames:
    hcx, hcy, hcf = hoops_by_frame[hf][0]  # take first hoop detection
    # Hoop bbox estimate: hoop detections are ~40-60px wide
    hoop_radius = 30  # approximate rim radius in pixels
    
    # Check ball detections in same frame and ±2 frames
    for offset in range(-2, 3):
        bf = hf + offset
        if bf not in balls_by_frame:
            continue
        for bx, by, bcf in balls_by_frame[bf]:
            dist = np.sqrt((bx - hcx)**2 + (by - hcy)**2)
            if dist < hoop_radius * 3:  # ball within 3x hoop radius = possible shot
                proximity_events.append({
                    'ball_frame': bf,
                    'hoop_frame': hf,
                    'bx': bx, 'by': by,
                    'hcx': hcx, 'hcy': hcy,
                    'dist': round(dist, 1),
                    'bcf': round(bcf, 3),
                    'hcf': round(hcf, 3),
                    'frame_diff': abs(bf - hf)
                })

log(f"Proximity events (ball within 90px of hoop): {len(proximity_events)}")

if not proximity_events:
    log("No ball-hoop proximity events found. Trying wider search...")
    # Fallback: check ball detections near hoop center with wider radius
    for hf in all_hoop_frames:
        hcx, hcy, hcf = hoops_by_frame[hf][0]
        for offset in range(-5, 6):
            bf = hf + offset
            if bf not in balls_by_frame:
                continue
            for bx, by, bcf in balls_by_frame[bf]:
                dist = np.sqrt((bx - hcx)**2 + (by - hcy)**2)
                if dist < 150:
                    proximity_events.append({
                        'ball_frame': bf, 'hoop_frame': hf,
                        'bx': bx, 'by': by, 'hcx': hcx, 'hcy': hcy,
                        'dist': round(dist, 1), 'bcf': round(bcf, 3),
                        'hcf': round(hcf, 3), 'frame_diff': abs(bf - hf)
                    })
    log(f"Proximity events (wider, 150px): {len(proximity_events)}")

if proximity_events:
    pe_df = pd.DataFrame(proximity_events)
    pe_df = pe_df.sort_values('dist')
    print("\nClosest ball-hoop proximities:")
    print(pe_df.head(30).to_string(index=False))
    
    # Cluster nearby events into shots
    pe_df = pe_df.sort_values('ball_frame')
    shot_groups = []
    current_group = [pe_df.iloc[0]]
    for i in range(1, len(pe_df)):
        if pe_df.iloc[i]['ball_frame'] - pe_df.iloc[i-1]['ball_frame'] <= 10:
            current_group.append(pe_df.iloc[i])
        else:
            shot_groups.append(current_group)
            current_group = [pe_df.iloc[i]]
    shot_groups.append(current_group)
    
    log(f"\nShot groups (clustered): {len(shot_groups)}")
    
    # For each group, pick the closest ball-hoop pair as the shot
    shots = []
    for group in shot_groups:
        best = min(group, key=lambda x: x['dist'])
        shots.append(best)
    
    # Now classify and determine make/miss
    for s in shots:
        fn = s['ball_frame']
        
        # MAKE if ball is within hoop radius
        if s['dist'] < 60:
            s['result'] = 'MAKE'
        else:
            s['result'] = 'MISS'
        
        # Find shooter distance using court homography
        c = None
        bd = 999
        for cfn in scf:
            d = abs(cfn - fn)
            if d < bd: bd, c = d, court_dict[cfn]
        
        s['type'] = '2PT'  # default
        s['shooter_dist_ft'] = None
        
        if c and bd < 30:
            H, bp = c
            # Find nearest player
            for pfn in range(fn-10, fn+11):
                if pfn in player_dict:
                    for px, py, pc in player_dict[pfn]:
                        try:
                            tp = cv2.perspectiveTransform(
                                np.array([[px, py]], dtype=np.float32).reshape(-1,1,2), H).reshape(2)
                            d_tac = np.sqrt((tp[0]-150)**2 + (tp[1]-(161-4/3))**2)
                            d_ft = d_tac / 3.0
                            if 5 < d_ft < 40:
                                s['shooter_dist_ft'] = round(d_ft, 1)
                                s['type'] = '3PT' if d_ft > 19.75 else '2PT'
                                break
                        except: pass
                    if s['shooter_dist_ft'] is not None:
                        break
        
        # Fallback: estimate from pixel dist
        if s['shooter_dist_ft'] is None:
            est_ft = s['dist'] * 0.087  # rough calibration
            s['shooter_dist_ft'] = round(est_ft, 1)
            s['type'] = '3PT' if est_ft > 19.75 else '2PT'
    
    # Save
    shots_df = pd.DataFrame(shots)
    shots_df.to_csv(f'{OUT}/shots_v9e.csv', index=False)
    
    # Stats
    log("="*60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    makes = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')
    log(f"Shots found: {len(shots)}")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(makes)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    log("")
    for s in shots:
        log(f"  F{s['ball_frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"dist={s['dist']:5.1f}px shooter={s.get('shooter_dist_ft','?')}ft")
else:
    log("ERROR: No ball-hoop proximity events found at all!")
    log("The ball and hoop are never detected close together.")
    log("This means either: (a) ball detection misses during shots, or")
    log("(b) hoop detection misses when ball is near, or (c) both.")
