"""Fast streaming Q1 analysis - abdullahtarek models, 2-model approach."""
import cv2, numpy as np, pandas as pd, os, sys, time
from ultralytics import YOLO
from collections import defaultdict

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
os.makedirs(OUT, exist_ok=True)
start = time.time()
def log(msg): print(f"[{time.time()-start:.0f}s] {msg}", flush=True)

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
BALL_CONF, COURT_CONF = 0.15, 0.05
TACT_KPS = np.array([(0,0),(0,35),(0,60),(0,78),(0,104),(0,161),(150,161),(150,0),
    (85,60),(85,78),(300,161),(300,104),(300,78),(300,60),(300,35),(300,0),(215,60),(215,78)], dtype=np.float32)
BASKET = np.array([150.0, 161.0 - 1.2192/(15.0/161.0)])
THREE_PT_R = 6.02/(15.0/161.0)

def process_court(model, imgs, fns, court_dict):
    results = model.predict(imgs, conf=COURT_CONF, verbose=False)
    for fn, r in zip(fns, results):
        if r.keypoints is None: continue
        if r.keypoints.xy.shape[0] == 0: continue
        kps_xy = r.keypoints.xy[0].cpu().numpy()
        if kps_xy.shape[0] == 0: continue
        kps_cf = r.keypoints.conf[0].cpu().numpy()
        valid = (kps_xy[:,0]>1) & (kps_xy[:,1]>1) & (kps_cf>0.2)
        vi = np.where(valid)[0]
        if len(vi) < 4: continue
        try:
            H, _ = cv2.findHomography(kps_xy[vi], TACT_KPS[vi], cv2.RANSAC, 5.0)
            if H is None: continue
            bp = cv2.perspectiveTransform(np.array([BASKET], dtype=np.float32).reshape(-1,1,2), H).reshape(2)
            court_dict[fn] = (H, bp)
        except: pass

# Load models
log("Loading models...")
ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')
court_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt')
log("Models loaded.")

# === PASS 1 ===
log("Pass 1: Detection...")
cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
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
            best_ball, best_hoop = None, None
            for box in r.boxes:
                cls = ball_m.names[int(box.cls[0])]
                cf = float(box.conf[0])
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                cx, cy = (x1+x2)/2, (y1+y2)/2
                if cls == 'Ball' and cf > BALL_CONF and (best_ball is None or cf > best_ball[2]):
                    best_ball = (fn, cx, cy, cf)
                elif cls == 'Hoop' and cf > 0.1 and (best_hoop is None or cf > best_hoop[2]):
                    best_hoop = (fn, cx, cy, cf)
                elif cls == 'Player' and cf > 0.25:
                    player_dict[fn].append((cx, y2, cf))
            if best_ball: ball_list.append(best_ball)
            if best_hoop: hoop_list.append(best_hoop)

    if fn % 10 == 0:
        court_imgs.append(frame); court_fns.append(fn)
        if len(court_imgs) >= 20:
            process_court(court_m, court_imgs, court_fns, court_dict)
            court_imgs, court_fns = [], []

    fn += 1
    if fn % 1000 == 0:
        log(f"  {fn}/{total}")

if court_imgs:
    process_court(court_m, court_imgs, court_fns, court_dict)

cap.release()
log(f"Balls:{len(ball_list)} Hoops:{len(hoop_list)} Court:{len(court_dict)}")

# === PASS 2: Shot detection ===
log("Pass 2: Shot detection...")
scf = sorted(court_dict.keys())
def get_court(fn):
    best, bd = None, 999
    for cfn in scf:
        d = abs(cfn-fn)
        if d < bd: bd, best = d, court_dict[cfn]
    return best if bd < 30 else None

bc = []  # ball-court pairs
for fn, cx, cy, cf in ball_list:
    c = get_court(fn)
    if c:
        H, bp = c
        d = np.sqrt((cx-bp[0])**2+(cy-bp[1])**2)
        bc.append((fn, cx, cy, cf, d, bp[0], bp[1], H))
bc.sort()
log(f"Ball-court pairs: {len(bc)}")

shots, used = [], set()
for i in range(len(bc)):
    fn, cx, cy, cf, dist, bx, by, H = bc[i]
    if fn in used: continue
    pd = [bc[j][4] for j in range(max(0,i-5),i)]
    nd = [bc[j][4] for j in range(i+1,min(len(bc),i+6))]
    if not pd or not nd: continue
    if dist < min(pd) and dist < min(nd) and dist < 350:
        sd = None
        for pfn in range(fn-15, fn+16):
            if pfn in player_dict:
                for px,py,pc in player_dict[pfn]:
                    try:
                        tp = cv2.perspectiveTransform(np.array([[px,py]],dtype=np.float32).reshape(-1,1,2),H).reshape(2)
                        d = np.sqrt((tp[0]-150)**2+(tp[1]-BASKET[1])**2)
                        if sd is None or d < sd: sd = d
                    except: pass
                if sd: break
        st = '3PT' if sd and sd > THREE_PT_R else '2PT'
        mk = dist < 60
        shots.append({'frame':fn,'bx':cx,'by':cy,'dist':round(dist,1),'type':st,
                      'result':'MAKE' if mk else 'MISS','shooter':round(sd,1) if sd else None,
                      'conf':round(cf,3)})
        for df in range(-20,21): used.add(fn+df)

log(f"Shots: {len(shots)}")
pd.DataFrame(shots).to_csv(f'{OUT}/shots_v9.csv', index=False)

# === PASS 3: Annotated video ===
log("Pass 3: Video...")
shmap = {s['frame']:s for s in shots}
cap = cv2.VideoCapture(VIDEO)
fourcc = cv2.VideoWriter_fourcc(*'XVID')
vw = cv2.VideoWriter(f'{OUT}/annotated_q1.avi', fourcc, fps, (W,H))
fn = 0
while True:
    ret, frame = cap.read()
    if not ret: break
    for f2,cx,cy,cf in ball_list:
        if f2==fn: cv2.circle(frame,(int(cx),int(cy)),8,(0,255,0),2)
    c = get_court(fn)
    if c:
        bp=c[1]; cv2.circle(frame,(int(bp[0]),int(bp[1])),(0,0,255),2)
    if fn in shmap:
        s=shmap[fn]
        cv2.putText(frame,f"SHOT: {s['type']} {s['result']}",(10,40),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,255),2)
    vw.write(frame); fn+=1
cap.release(); vw.release()

# === STATS ===
log("="*50)
t2=[s for s in shots if s['type']=='2PT']
t3=[s for s in shots if s['type']=='3PT']
mk=[s for s in shots if s['result']=='MAKE']
log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
log(f"Points: {sum(2 for s in t2 if s['result']=='MAKE')+sum(3 for s in t3 if s['result']=='MAKE')}")
log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
for s in shots:
    log(f"  F{s['frame']}: {s['type']} {s['result']} {s['dist']}px")
log(f"Time: {time.time()-start:.0f}s")
