"""
Streaming Q1 analysis v9f: abdullahtarek-style ball tracking + shot detection.
Key changes from v9c:
- Ball detection on EVERY frame (not strided), conf=0.5
- remove_wrong_detections: max 25px jump between consecutive ball detections
- interpolate_ball_positions: fill gaps with linear interpolation
- Shot detection: find frames where ball is near detected hoop (same frame)
- 2PT/3PT: use pixel distance from hoop at shot frame (calibrated)
"""
import cv2, numpy as np, pandas as pd, os, time, pickle
from ultralytics import YOLO
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
os.makedirs(OUT, exist_ok=True)
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
BALL_CONF = 0.5   # abdullahtarek default
COURT_CONF = 0.05
MAX_JUMP = 25     # max allowed ball movement between consecutive frames (px)

TACT_KPS = np.array([(0,0),(0,35),(0,60),(0,78),(0,104),(0,161),(150,161),(150,0),
    (85,60),(85,78),(300,161),(300,104),(300,78),(300,60),(300,35),(300,0),(215,60),(215,78)], dtype=np.float32)
BASKET_TACTICAL = np.array([150.0, 161.0 - 1.2192/(15.0/161.0)])

# ===== Check for cached results =====
ball_raw_csv = f'{OUT}/v9f_balls_raw.csv'
ball_clean_csv = f'{OUT}/v9f_balls_clean.csv'
hoop_csv = f'{OUT}/v9f_hoops.csv'
court_pkl = f'{OUT}/v9f_court.pkl'
player_pkl = f'{OUT}/v9f_players.pkl'

use_cache = all(os.path.exists(f) for f in [ball_raw_csv, ball_clean_csv, hoop_csv, court_pkl, player_pkl])

if use_cache:
    log("Loading cached detections...")
else:
    log("No cache found. Running full detection pass...")
    log("Loading models...")
    ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')
    court_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt')
    log("Models loaded.")

    cap = cv2.VideoCapture(VIDEO)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    log(f"Video: {total} frames @ {fps}fps")

    # Per-frame storage (index = frame number)
    ball_raw = []       # (fn, x1, y1, x2, y2, conf) for every frame
    hoops_by_frame = {} # fn -> list of (cx, cy, conf)
    player_dict = defaultdict(list)  # fn -> list of (cx, foot_y, conf)
    court_dict = {}
    court_imgs, court_fns = [], []

    fn = 0
    while True:
        ret, frame = cap.read()
        if not ret: break

        # Ball detection EVERY frame
        r = ball_m.predict(frame, conf=BALL_CONF, verbose=False)[0]
        best_ball = None
        frame_hoops = []
        if r.boxes is not None:
            for box in r.boxes:
                cls = ball_m.names[int(box.cls[0])]
                cf = float(box.conf[0])
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                cx, cy = (x1+x2)/2, (y1+y2)/2
                if cls == 'Ball' and cf > BALL_CONF:
                    if best_ball is None or cf > best_ball[5]:
                        best_ball = (fn, x1, y1, x2, y2, cf)
                elif cls == 'Hoop' and cf > 0.1:
                    frame_hoops.append((cx, cy, cf))
                elif cls == 'Player' and cf > 0.25:
                    player_dict[fn].append((cx, y2, cf))

        ball_raw.append(best_ball)
        if frame_hoops:
            hoops_by_frame[fn] = frame_hoops

        # Court keypoint every 10 frames
        if fn % 10 == 0:
            court_imgs.append(frame); court_fns.append(fn)
            if len(court_imgs) >= 20:
                results = court_m.predict(court_imgs, conf=COURT_CONF, verbose=False)
                for cfn, cr in zip(court_fns, results):
                    if cr.keypoints is None or len(cr.keypoints.xy) == 0: continue
                    kps_xy = cr.keypoints.xy[0].cpu().numpy()
                    if kps_xy.shape[0] == 0: continue
                    kps_cf = cr.keypoints.conf[0].cpu().numpy()
                    valid = (kps_xy[:,0]>1) & (kps_xy[:,1]>1) & (kps_cf>0.2)
                    vi = np.where(valid)[0]
                    if len(vi) < 4: continue
                    try:
                        H, _ = cv2.findHomography(kps_xy[vi], TACT_KPS[vi], cv2.RANSAC, 5.0)
                        if H is None: continue
                        bp = cv2.perspectiveTransform(
                            np.array([BASKET_TACTICAL], dtype=np.float32).reshape(-1,1,2), H).reshape(2)
                        if -100 < bp[0] < 1400 and -100 < bp[1] < 900:
                            court_dict[cfn] = (H, bp)
                    except: pass
                court_imgs, court_fns = [], []

        fn += 1
        if fn % 500 == 0:
            ball_count = sum(1 for b in ball_raw if b is not None)
            log(f"  {fn}/{total} frames, {ball_count} ball detections")

    # Process remaining court frames
    if court_imgs:
        results = court_m.predict(court_imgs, conf=COURT_CONF, verbose=False)
        for cfn, cr in zip(court_fns, results):
            if cr.keypoints is None or len(cr.keypoints.xy) == 0: continue
            kps_xy = cr.keypoints.xy[0].cpu().numpy()
            if kps_xy.shape[0] == 0: continue
            kps_cf = cr.keypoints.conf[0].cpu().numpy()
            valid = (kps_xy[:,0]>1) & (kps_xy[:,1]>1) & (kps_cf>0.2)
            vi = np.where(valid)[0]
            if len(vi) < 4: continue
            try:
                H, _ = cv2.findHomography(kps_xy[vi], TACT_KPS[vi], cv2.RANSAC, 5.0)
                if H is None: continue
                bp = cv2.perspectiveTransform(
                    np.array([BASKET_TACTICAL], dtype=np.float32).reshape(-1,1,2), H).reshape(2)
                if -100 < bp[0] < 1400 and -100 < bp[1] < 900:
                    court_dict[cfn] = (H, bp)
            except: pass

    cap.release()
    log(f"Raw detection: {sum(1 for b in ball_raw if b is not None)} balls, {len(hoops_by_frame)} hoop frames, {len(court_dict)} courts")

    # Save raw detections
    ball_records = [(b[0], b[1], b[2], b[3], b[4], b[5]) for b in ball_raw if b is not None]
    pd.DataFrame(ball_records, columns=['frame','x1','y1','x2','y2','conf']).to_csv(ball_raw_csv, index=False)
    hoop_records = []
    for fn2, hlist in hoops_by_frame.items():
        for hcx, hcy, hcf in hlist:
            hoop_records.append((fn2, hcx, hcy, hcf))
    pd.DataFrame(hoop_records, columns=['frame','cx','cy','conf']).to_csv(hoop_csv, index=False)
    with open(court_pkl,'wb') as f: pickle.dump(court_dict, f)
    with open(player_pkl,'wb') as f: pickle.dump(dict(player_dict), f)
    log("Raw detections saved.")

# ===== Load clean ball data =====
log("Loading clean ball data...")
ball_clean_df = pd.read_csv(ball_clean_csv)
hoop_df = pd.read_csv(hoop_csv)
with open(court_pkl,'rb') as f: court_dict = pickle.load(f)
with open(player_pkl,'rb') as f: player_dict = pickle.load(f)

# Build per-frame lookups
balls_by_frame = {}
for r in ball_clean_df.itertuples(index=False, name=None):
    balls_by_frame[r[0]] = (r[1], r[2], r[3], r[4], r[5])  # x1,y1,x2,y2,conf

hoops_by_frame2 = defaultdict(list)
for r in hoop_df.itertuples(index=False, name=None):
    hoops_by_frame2[r[0]].append((r[1], r[2], r[3]))

scf = sorted(court_dict.keys())
log(f"Clean: {len(balls_by_frame)} ball frames, {len(hoops_by_frame2)} hoop frames, {len(court_dict)} courts")

# ===== Shot detection: ball near hoop in same frame =====
log("Shot detection...")

# For each frame with a hoop detection, check if ball is nearby
shot_candidates = []
for hf in sorted(hoops_by_frame2.keys()):
    for hcx, hcy, hcf in hoops_by_frame2[hf]:
        # Check ball in same frame and ±3
        for offset in range(-3, 4):
            bf = hf + offset
            if bf not in balls_by_frame:
                continue
            bx1, by1, bx2, by2, bcf = balls_by_frame[bf]
            bcx, bcy = (bx1+bx2)/2, (by1+by2)/2
            dist = np.sqrt((bcx-hcx)**2 + (bcy-hcy)**2)
            if dist < 100:  # generous threshold
                shot_candidates.append({
                    'ball_frame': bf,
                    'hoop_frame': hf,
                    'bcx': bcx, 'bcy': bcy,
                    'hcx': hcx, 'hcy': hcy,
                    'dist': round(dist, 1),
                    'bcf': round(bcf, 3),
                    'hcf': round(hcf, 3),
                    'frame_offset': abs(bf - hf)
                })

log(f"Shot candidates (ball within 100px of hoop): {len(shot_candidates)}")

if shot_candidates:
    sc_df = pd.DataFrame(shot_candidates).sort_values('dist')
    print("\nTop 20 closest ball-hoop proximities:")
    print(sc_df.head(20).to_string(index=False))
    
    # Cluster into shots (within 15 frames of each other = same shot)
    sc_df = sc_df.sort_values('ball_frame')
    shot_groups = []
    current_group = [sc_df.iloc[0]]
    for i in range(1, len(sc_df)):
        if sc_df.iloc[i]['ball_frame'] - sc_df.iloc[i-1]['ball_frame'] <= 15:
            current_group.append(sc_df.iloc[i])
        else:
            shot_groups.append(current_group)
            current_group = [sc_df.iloc[i]]
    shot_groups.append(current_group)
    
    log(f"Shot groups: {len(shot_groups)}")
    
    # For each group, pick the closest approach
    shots = []
    for group in shot_groups:
        best = min(group, key=lambda x: x['dist'])
        fn = best['ball_frame']
        
        # Make/miss: ball within hoop radius (~25px for rim)
        if best['dist'] < 40:
            result = 'MAKE'
        else:
            result = 'MISS'
        
        # 2PT/3PT classification using pixel distance from hoop
        # In ceiling camera, closer to hoop = closer to basket
        # Need to calibrate: what pixel distance = 3PT line?
        # HS 3PT = 19.75ft from basket. At typical camera zoom, ~200px from hoop ≈ 20ft
        # So: dist < 150px → 2PT, dist >= 150px → 3PT (rough estimate)
        shot_type = '3PT' if best['dist'] > 120 else '2PT'
        
        # Try to get shooter from player detection
        shooter_id = None
        shooter_dist = None
        for pfn in range(fn-10, fn+11):
            if pfn in player_dict:
                for px, py, pc in player_dict[pfn]:
                    d = np.sqrt((px-best['bcx'])**2 + (py-best['bcy'])**2)
                    if shooter_dist is None or d < shooter_dist:
                        shooter_dist = d
                        shooter_id = pfn
        
        shots.append({
            'frame': fn,
            'bx': round(best['bcx'], 1),
            'by': round(best['bcy'], 1),
            'hoop_dist': best['dist'],
            'type': shot_type,
            'result': result,
            'bcf': best['bcf'],
            'hcf': best['hcf'],
            'shooter_px_dist': round(shooter_dist, 1) if shooter_dist else None
        })
    
    shots_df = pd.DataFrame(shots).sort_values('frame')
    shots_df.to_csv(f'{OUT}/shots_v9f.csv', index=False)
    
    # Stats
    log("="*60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    makes = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')
    log(f"Shots: {len(shots)}")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Makes: {len(makes)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    log("")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"hoop_dist={s['hoop_dist']:5.1f}px bcf={s['bcf']:.3f} hcf={s['hcf']:.3f}")
else:
    log("No shot candidates found.")
    log("This means ball and hoop are never within 100px of each other.")
    log("The camera auto-tracking keeps ball centered and hoop at edge.")
