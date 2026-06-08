"""Streaming Q1 analysis v9d - same-frame ball+hoop for make/miss + calibrated 2PT/3PT."""
import cv2, numpy as np, pandas as pd, os, sys, time, pickle
from ultralytics import YOLO
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
os.makedirs(OUT, exist_ok=True)
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
BALL_CONF, COURT_CONF = 0.10, 0.05
TOPK_BALLS = 3

TACT_KPS = np.array([(0,0),(0,35),(0,60),(0,78),(0,104),(0,161),(150,161),(150,0),
    (85,60),(85,78),(300,161),(300,104),(300,78),(300,60),(300,35),(300,0),(215,60),(215,78)], dtype=np.float32)
BASKET_TACTICAL = np.array([150.0, 161.0 - 1.2192/(15.0/161.0)])
THREE_PT_R_FT = 19.75  # HS 3PT line in ft
# Tactical units: 150 units = 50ft, so 1 unit = 1/3 ft
THREE_PT_R_TACT = THREE_PT_R_FT / 3.0

def process_court(model, imgs, fns, court_dict):
    results = model.predict(imgs, conf=COURT_CONF, verbose=False)
    for fn, r in zip(fns, results):
        if r.keypoints is None: continue
        if len(r.keypoints.xy) == 0: continue
        kps_xy = r.keypoints.xy[0].cpu().numpy()
        if kps_xy.shape[0] == 0: continue
        kps_cf = r.keypoints.conf[0].cpu().numpy()
        valid = (kps_xy[:,0]>1) & (kps_xy[:,1]>1) & (kps_cf>0.2)
        vi = np.where(valid)[0]
        if len(vi) < 4: continue
        try:
            H, _ = cv2.findHomography(kps_xy[vi], TACT_KPS[vi], cv2.RANSAC, 5.0)
            if H is None: continue
            bp = cv2.perspectiveTransform(np.array([BASKET_TACTICAL], dtype=np.float32).reshape(-1,1,2), H).reshape(2)
            # Quality check: basket should be within frame bounds (with margin)
            if not (-100 < bp[0] < 1400 and -100 < bp[1] < 900):
                continue
            court_dict[fn] = (H, bp)
        except: pass

def get_nearest_court(fn, scf, court_dict):
    best, bd = None, 999
    for cfn in scf:
        d = abs(cfn-fn)
        if d < bd: bd, best = d, court_dict[cfn]
    return best if bd < 30 else None

# ===== Load cached Pass 1 from v9c =====
ball_csv = f'{OUT}/v9c_balls.csv'
court_pkl = f'{OUT}/v9c_court.pkl'
player_pkl = f'{OUT}/v9c_players.pkl'

log("Loading cached detections from v9c...")
ball_df = pd.read_csv(ball_csv)
ball_list = list(ball_df.itertuples(index=False, name=None))
with open(court_pkl,'rb') as f: court_dict = pickle.load(f)
with open(player_pkl,'rb') as f: player_dict = pickle.load(f)
hoop_df = pd.read_csv(f'{OUT}/v9c_hoops.csv')
hoop_list = list(hoop_df.itertuples(index=False, name=None))
log(f"Loaded: {len(ball_list)} balls, {len(hoop_list)} hoops, {len(court_dict)} courts")

# ===== Build per-frame lookup =====
# Balls by frame (all candidates)
balls_by_frame = defaultdict(list)
for fn, cx, cy, cf in ball_list:
    balls_by_frame[fn].append((cx, cy, cf))

# Hoops by frame (all detections)
hoops_by_frame = defaultdict(list)
for fn, cx, cy, cf in hoop_list:
    hoops_by_frame[fn].append((cx, cy, cf))

# ===== Ball tracking - pick best ball per frame =====
log("Ball tracking...")
scf = sorted(court_dict.keys())

frame_basket = {}
for fn in sorted(balls_by_frame.keys()):
    c = get_nearest_court(fn, scf, court_dict)
    if c:
        frame_basket[fn] = c[1]

# Greedy temporal smoothness tracking
selected_balls = {}
prev_x, prev_y = None, None
for fn in sorted(balls_by_frame.keys()):
    if fn not in frame_basket:
        continue
    bx, by = frame_basket[fn]
    candidates = balls_by_frame[fn]
    best = None
    best_score = 999999
    for cx, cy, cf in candidates:
        dist_basket = np.sqrt((cx-bx)**2 + (cy-by)**2)
        if prev_x is not None:
            dist_temporal = np.sqrt((cx-prev_x)**2 + (cy-prev_y)**2)
        else:
            dist_temporal = 0
        score = dist_basket * 0.3 + dist_temporal * 0.7
        if score < best_score:
            best_score = score
            best = (cx, cy, cf, dist_basket)
    if best:
        selected_balls[fn] = best
        prev_x, prev_y = best[0], best[1]

log(f"Selected ball track: {len(selected_balls)} frames")

# ===== Shot detection =====
log("Shot detection...")

bc = [(fn, b[0], b[1], b[2], b[3]) for fn, b in selected_balls.items()]
bc.sort()

# Phase 1: Find local minima in ball-to-basket distance
shots, used = [], set()
for i in range(len(bc)):
    fn, cx, cy, cf, dist = bc[i]
    if fn in used: continue
    prev_dists = [bc[j][4] for j in range(max(0,i-6),i)]
    next_dists = [bc[j][4] for j in range(i+1,min(len(bc),i+7))]
    if not prev_dists or not next_dists: continue
    if dist < min(prev_dists) and dist < min(next_dists) and dist < 400:
        # This is a local minimum in ball-to-basket distance = shot attempt
        shots.append({'frame':fn,'bx':cx,'by':cy,'dist':round(dist,1),'conf':round(cf,3)})
        for df in range(-20,21): used.add(fn+df)

log(f"Shot attempts (local minima): {len(shots)}")

# Phase 2: For each shot, determine MAKE/MISS using same-frame hoop detection
for s in shots:
    fn = s['frame']
    bx, by = s['bx'], s['by']
    
    # Look for hoop detection in nearby frames (within ±5 frames)
    best_hoop_dist = 9999
    best_hoop_size = 0
    for offset in range(-5, 6):
        hf = fn + offset
        if hf in hoops_by_frame:
            for hcx, hcy, hcf in hoops_by_frame[hf]:
                # Distance from ball to hoop center
                d = np.sqrt((bx-hcx)**2 + (by-hcy)**2)
                if d < best_hoop_dist:
                    best_hoop_dist = d
                    best_hoop_size = 30  # estimated hoop radius in pixels
    
    # Make if ball is within/close to hoop bounding box
    # Typical hoop detection is ~40-60px wide, so rim radius ~20-30px
    # Ball within 1.5 hoop radii of center = going through
    s['hoop_dist'] = round(best_hoop_dist, 1)
    if best_hoop_dist < 60:  # ball overlaps or is very close to hoop
        s['result'] = 'MAKE'
    else:
        s['result'] = 'MISS'
    
    # Phase 3: Classify 2PT vs 3PT using hoop distance + ball height
    # In ceiling camera: closer to hoop in pixels ~ closer to basket in reality
    # But we need actual distance. Use a simple heuristic:
    # - If ball_y is well above hoop_y: likely close to basket (layup/short 2PT)
    # - If ball is far from hoop in pixels: likely 3PT or long 2PT
    # Better: use the homography (only if reliable)
    
    c = get_nearest_court(fn, scf, court_dict)
    shooter_dist = None
    stype = '2PT'  # default
    
    if c:
        H, bp = c
        # Find nearest player to ball in this frame
        best_player_dist = None
        for pfn in range(fn-10, fn+11):
            if pfn in player_dict:
                for px, py, pc in player_dict[pfn]:
                    # Distance from player to ball in pixels
                    pdist = np.sqrt((px-bx)**2 + (py-by)**2)
                    if best_player_dist is None or pdist < best_player_dist:
                        best_player_dist = pdist
        
        # Use homography to get player distance to basket
        # But only if the homography gives reasonable results
        for pfn in range(fn-10, fn+11):
            if pfn in player_dict:
                for px, py, pc in player_dict[pfn]:
                    try:
                        tp = cv2.perspectiveTransform(
                            np.array([[px, py]], dtype=np.float32).reshape(-1,1,2), H).reshape(2)
                        d_tac = np.sqrt((tp[0]-150)**2 + (tp[1]-BASKET_TACTICAL[1])**2)
                        d_ft = d_tac / 3.0  # convert tactical to feet
                        if 5 < d_ft < 40:  # reasonable range
                            if shooter_dist is None or abs(d_ft - 20) < abs(shooter_dist - 20):
                                shooter_dist = d_ft
                    except: pass
                if shooter_dist is not None:
                    break
    
    if shooter_dist is not None:
        s['shooter_dist_ft'] = round(shooter_dist, 1)
        if shooter_dist > THREE_PT_R_FT:
            stype = '3PT'
        else:
            stype = '2PT'
    else:
        # Fallback: use pixel distance from basket
        # Calibrate: in this footage, ~200px basket dist ~ 20ft real dist
        est_dist_ft = s['dist'] * (20.0 / 200.0) if s['dist'] > 0 else 99
        s['shooter_dist_ft'] = round(est_dist_ft, 1)
        stype = '3PT' if est_dist_ft > THREE_PT_R_FT else '2PT'
    
    s['type'] = stype

# Save
shots_df = pd.DataFrame(shots)
if len(shots_df) > 0:
    shots_df.to_csv(f'{OUT}/shots_v9d.csv', index=False)

# ===== Stats =====
log("="*50)
t2 = [s for s in shots if s['type'] == '2PT']
t3 = [s for s in shots if s['type'] == '3PT']
makes = [s for s in shots if s['result'] == 'MAKE']
log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
log(f"Total makes: {len(makes)}")
log(f"Points: {sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')}")
log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
log("")
for s in shots:
    log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
        f"basket_dist={s['dist']:6.1f}px hoop_dist={s.get('hoop_dist','N/A'):6s} "
        f"shooter={s.get('shooter_dist_ft','N/A')}ft conf={s['conf']:.3f}")
log(f"Time: {time.time()-start:.0f}s")
