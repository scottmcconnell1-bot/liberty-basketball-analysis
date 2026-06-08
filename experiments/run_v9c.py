"""Streaming Q1 analysis v9c - improved ball tracking + checkpointing."""
import cv2, numpy as np, pandas as pd, os, sys, time, pickle
from ultralytics import YOLO
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
os.makedirs(OUT, exist_ok=True)
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
BALL_CONF, COURT_CONF = 0.10, 0.05
TOPK_BALLS = 3  # keep top 3 ball candidates per frame

TACT_KPS = np.array([(0,0),(0,35),(0,60),(0,78),(0,104),(0,161),(150,161),(150,0),
    (85,60),(85,78),(300,161),(300,104),(300,78),(300,60),(300,35),(300,0),(215,60),(215,78)], dtype=np.float32)
BASKET_TACTICAL = np.array([150.0, 161.0 - 1.2192/(15.0/161.0)])
THREE_PT_R = 6.02/(15.0/161.0)

# Court physical dimensions (ft): width=50, baseline_to_foul=19, FT_line=15 from baseline
# Basket is 1.2192m (4ft) from baseline = 1.2192/(50/161) tactical units
COURT_W_FT = 50.0
COURT_H_FT = 94.0  # full court

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
            court_dict[fn] = (H, bp)
        except: pass

def get_nearest_court(fn, scf, court_dict):
    best, bd = None, 999
    for cfn in scf:
        d = abs(cfn-fn)
        if d < bd: bd, best = d, court_dict[cfn]
    return best if bd < 30 else None

# ===== CHECKPOINT: Try to load Pass 1 results =====
ball_csv = f'{OUT}/v9c_balls.csv'
hoop_csv = f'{OUT}/v9c_hoops.csv'
court_pkl = f'{OUT}/v9c_court.pkl'
player_pkl = f'{OUT}/v9c_players.pkl'

if os.path.exists(ball_csv) and os.path.exists(court_pkl):
    log("Loading cached Pass 1 results...")
    ball_df = pd.read_csv(ball_csv)
    ball_list = list(ball_df.itertuples(index=False, name=None))
    hoop_df = pd.read_csv(hoop_csv)
    hoop_list = list(hoop_df.itertuples(index=False, name=None))
    with open(court_pkl,'rb') as f: court_dict = pickle.load(f)
    with open(player_pkl,'rb') as f: player_dict = pickle.load(f)
    log(f"Loaded: {len(ball_list)} balls, {len(hoop_list)} hoops, {len(court_dict)} courts")
else:
    # ===== PASS 1: Detection =====
    log("Loading models...")
    ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')
    court_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt')
    log("Models loaded.")

    log("Pass 1: Detection...")
    cap = cv2.VideoCapture(VIDEO)
    fps = cap.get(cv2.CAP_PROP_FPS)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ball_list, hoop_list, player_dict, court_dict = [], [], defaultdict(list), {}
    court_imgs, court_fns = [], []
    fn = 0

    while True:
        ret, frame = cap.read()
        if not ret: break

        if fn % 5 == 0:
            r = ball_m.predict(frame, conf=BALL_CONF, verbose=False)[0]
            if r.boxes is not None:
                frame_balls = []
                best_hoop = None
                for box in r.boxes:
                    cls = ball_m.names[int(box.cls[0])]
                    cf = float(box.conf[0])
                    x1,y1,x2,y2 = box.xyxy[0].tolist()
                    cx, cy = (x1+x2)/2, (y1+y2)/2
                    if cls == 'Ball' and cf > BALL_CONF:
                        frame_balls.append((fn, cx, cy, cf))
                    elif cls == 'Hoop' and cf > 0.1 and (best_hoop is None or cf > best_hoop[2]):
                        best_hoop = (fn, cx, cy, cf)
                    elif cls == 'Player' and cf > 0.25:
                        player_dict[fn].append((cx, y2, cf))
                # Keep top-K balls by confidence
                frame_balls.sort(key=lambda x: -x[3])
                ball_list.extend(frame_balls[:TOPK_BALLS])
                if best_hoop: hoop_list.append(best_hoop)

        if fn % 10 == 0:
            court_imgs.append(frame); court_fns.append(fn)
            if len(court_imgs) >= 20:
                process_court(court_m, court_imgs, court_fns, court_dict)
                court_imgs, court_fns = [], []

        fn += 1
        if fn % 500 == 0:
            log(f"  {fn}/{total}")

    if court_imgs:
        process_court(court_m, court_imgs, court_fns, court_dict)

    cap.release()
    log(f"Pass 1 done. Balls:{len(ball_list)} Hoops:{len(hoop_list)} Court:{len(court_dict)}")

    # Save checkpoint
    pd.DataFrame(ball_list, columns=['frame','cx','cy','conf']).to_csv(ball_csv, index=False)
    pd.DataFrame(hoop_list, columns=['frame','cx','cy','conf']).to_csv(hoop_csv, index=False)
    with open(court_pkl,'wb') as f: pickle.dump(court_dict, f)
    with open(player_pkl,'wb') as f: pickle.dump(dict(player_dict), f)
    log("Checkpoint saved.")

# ===== PASS 2: Ball tracking - pick best ball per frame =====
log("Pass 2: Ball tracking...")

# Group balls by frame
balls_by_frame = defaultdict(list)
for fn, cx, cy, cf in ball_list:
    balls_by_frame[fn].append((cx, cy, cf))

scf = sorted(court_dict.keys())
all_frames = sorted(balls_by_frame.keys())

# For each frame with court calibration, compute basket position
# Then pick the ball that forms the smoothest trajectory
# Strategy: use basket proximity as a prior + temporal smoothness

# First, get basket position for each frame with balls
frame_basket = {}
for fn in all_frames:
    c = get_nearest_court(fn, scf, court_dict)
    if c:
        frame_basket[fn] = c[1]  # basket pixel coords (bx, by)

# For each frame, rank balls by distance to basket + temporal continuity
# Greedy approach: walk through frames, pick ball closest to previous pick
selected_balls = {}  # fn -> (cx, cy, cf, dist_to_basket)

prev_x, prev_y = None, None
for fn in all_frames:
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
        # Score: balance basket proximity and temporal smoothness
        score = dist_basket * 0.3 + dist_temporal * 0.7
        if score < best_score:
            best_score = score
            best = (cx, cy, cf, dist_basket)
    
    if best:
        selected_balls[fn] = best
        prev_x, prev_y = best[0], best[1]

log(f"Selected ball track: {len(selected_balls)} frames with ball")

# ===== PASS 3: Shot detection =====
log("Pass 3: Shot detection...")

bc = [(fn, b[0], b[1], b[2], b[3]) for fn, b in selected_balls.items()]
bc.sort()

shots, used = [], set()
for i in range(len(bc)):
    fn, cx, cy, cf, dist = bc[i]
    if fn in used: continue
    pd2 = [bc[j][4] for j in range(max(0,i-5),i)]
    nd2 = [bc[j][4] for j in range(i+1,min(len(bc),i+6))]
    if not pd2 or not nd2: continue
    if dist < min(pd2) and dist < min(nd2) and dist < 350:
        # Find shooter distance
        sd = None
        for pfn in range(fn-15, fn+16):
            if pfn in player_dict:
                c = get_nearest_court(fn, scf, court_dict)
                if c:
                    H = c[0]
                    for px,py,pc in player_dict[pfn]:
                        try:
                            tp = cv2.perspectiveTransform(np.array([[px,py]],dtype=np.float32).reshape(-1,1,2),H).reshape(2)
                            d = np.sqrt((tp[0]-150)**2+(tp[1]-BASKET_TACTICAL[1])**2)
                            if sd is None or d < sd: sd = d
                        except: pass
                if sd: break
        st = '3PT' if sd and sd > THREE_PT_R else '2PT'
        mk = dist < 60
        shots.append({'frame':fn,'bx':cx,'by':cy,'dist':round(dist,1),'type':st,
                      'result':'MAKE' if mk else 'MISS','shooter':round(sd,1) if sd else None,
                      'conf':round(cf,3)})
        for df in range(-20,21): used.add(fn+df)

log(f"Shots found: {len(shots)}")

# Save shots
shots_df = pd.DataFrame(shots)
if len(shots_df) > 0:
    shots_df.to_csv(f'{OUT}/shots_v9c.csv', index=False)
    log("Shots saved to shots_v9c.csv")
else:
    log("WARNING: No shots found!")

# ===== PASS 4: Stats =====
log("="*50)
t2=[s for s in shots if s['type']=='2PT']
t3=[s for s in shots if s['type']=='3PT']
mk=[s for s in shots if s['result']=='MAKE']
log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
log(f"Points: {sum(2 for s in t2 if s['result']=='MAKE')+sum(3 for s in t3 if s['result']=='MAKE')}")
log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
for s in shots:
    log(f"  F{s['frame']}: {s['type']} {s['result']} dist={s['dist']}px shooter={s['shooter']}ft")
log(f"Time: {time.time()-start:.0f}s")
