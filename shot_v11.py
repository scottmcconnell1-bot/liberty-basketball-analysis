#!/usr/bin/env python3
"""
Shot detection v11: Two-model approach
=======================================
- Ball detection: fine-tuned best.pt (fast, 0.4s/frame) every frame
- Hoop detection: ball_detector.pt (has Hoop class) every 30 frames only
- Then interpolate hoop positions between detections
This gives us both ball + hoop at acceptable speed (~30 min total)
"""

import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from ultralytics import YOLO
from collections import defaultdict

VIDEO       = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT         = 'pipeline_output'
BALL_MODEL  = 'ball_finetune/runs/finetune2/weights/best.pt'   # Ball only, fast
HOOP_MODEL  = 'models/ball_detector.pt'                         # Ball + Hoop + Player
COURT_MODEL = 'models/court_keypoint_detector.pt'

BALL_CONF    = 0.0002   # fine-tuned model has very low conf (0.0005-0.0016)
BALL_IOU     = 0.4
HOOP_CONF    = 0.1
HOOP_STRIDE  = 30     # detect hoops every N frames
COURT_CONF   = 0.3
COURT_STRIDE = 10
MAX_JUMP     = 80       # relaxed - ball moves fast between frames
HOOP_PROX    = 150
MAKE_RADIUS  = 40
TH_PT_THRESH = 120
DEDUP_RANGE  = 20
PEAK_DIST    = 15

os.makedirs(OUT, exist_ok=True)

class DevNull:
    def write(self, x): pass
    def flush(self): pass

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)
    try:
        with open(f'{OUT}/shot_v11.log', 'a') as f:
            f.write(line + '\n')
    except: pass

TACT_KPS = np.array([
    (0,0),(0,35),(0,60),(0,78),(0,104),(0,161),(150,161),(150,0),
    (85,60),(85,78),(300,161),(300,104),(300,78),(300,60),(300,35),(300,0),(215,60),(215,78)
], dtype=np.float32)
BASKET_TACT = np.array([150.0, 161.0 - 1.2192/(15.0/161.0)])

def process_court_batch(imgs, fns, model, kp_arr, court_dict, conf):
    try:
        results = model.predict(imgs, conf=conf, verbose=False)
        for cfn, cr in zip(fns, results):
            if cr.keypoints is None or len(cr.keypoints.xy) == 0: continue
            kps_xy = cr.keypoints.xy[0].cpu().numpy()
            kps_cf = cr.keypoints.conf[0].cpu().numpy()
            valid = (kps_xy[:,0]>1)&(kps_xy[:,1]>1)&(kps_cf>0.2)
            vi = np.where(valid)[0]
            if len(vi)<4: continue
            try:
                H,_ = cv2.findHomography(kps_xy[vi], TACT_KPS[vi], cv2.RANSAC, 5.0)
                if H is None: continue
                bp = cv2.perspectiveTransform(
                    np.array([BASKET_TACT],dtype=np.float32).reshape(-1,1,2),H
                ).reshape(2)
                if -100<bp[0]<1400 and -100<bp[1]<900:
                    court_dict[cfn] = (H,bp)
                    kp_arr[cfn] = kps_xy
            except: pass
    except: pass

if __name__ == '__main__':
    sys.stderr = DevNull()
    START = time.time()

    log("Loading models...")
    ball_m  = YOLO(BALL_MODEL, verbose=False)    # fast, ball only
    hoop_m  = YOLO(HOOP_MODEL, verbose=False)    # slower, has Hoop
    court_m = YOLO(COURT_MODEL, verbose=False)   # court keypoints
    log(f"Ball model: {ball_m.names}")
    log(f"Hoop model: {hoop_m.names}")

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)
    log(f"Video: {total} frames @ {fps:.1f}fps")

    # Per-frame storage
    ball_raw  = []   # (fn, cx, cy, cf) or None (color-ok only)
    hoops_by_frame = defaultdict(list)  # fn -> [(cx,cy,cf)]
    kp_arr    = np.full((total, 18, 2), np.nan)
    court_dict = {}
    court_imgs, court_fns = [], []
    ball_count = 0

    fn = 0
    log("Phase 2: Detection pass...")

    while True:
        ret, frame = cap.read()
        if not ret or fn >= total:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # --- Ball: fast fine-tuned model ---
        rb = ball_m.predict(frame, conf=BALL_CONF, iou=BALL_IOU, verbose=False)[0]
        best_ball, best_bcf = None, 0

        if rb.boxes is not None:
            for box in rb.boxes:
                cls = ball_m.names[int(box.cls[0])]
                cf  = float(box.conf[0])
                if cls == 'Ball' and cf > best_bcf:
                    x1,y1,x2,y2 = box.xyxy[0].tolist()
                    best_bcf  = cf
                    best_ball = (fn, (x1+x2)/2, (y1+y2)/2, cf)

        if best_ball is not None:
            _,cx,cy,cf = best_ball
            ix,iy = int(cx),int(cy)
            color_ok = False
            if 0<=ix<frame.shape[1] and 0<=iy<frame.shape[0]:
                px = hsv[iy,ix]
                if 3<=px[0]<=30 and px[1]>15: color_ok = True
            if color_ok:
                ball_raw.append(best_ball); ball_count += 1
            else:
                ball_raw.append(None)
        else:
            ball_raw.append(None)

        # --- Hoop: slower model every HOOP_STRIDE frames ---
        if fn % HOOP_STRIDE == 0:
            rh = hoop_m.predict(frame, conf=HOOP_CONF, verbose=False)[0]
            if rh.boxes is not None:
                frame_hoops = []
                for box in rh.boxes:
                    cls = hoop_m.names[int(box.cls[0])]
                    cf  = float(box.conf[0])
                    if cls == 'Hoop' and cf > HOOP_CONF:
                        x1,y1,x2,y2 = box.xyxy[0].tolist()
                        frame_hoops.append(((x1+x2)/2, (y1+y2)/2, cf))
                if frame_hoops:
                    hoops_by_frame[fn] = frame_hoops

        # --- Court keypoints ---
        if fn % COURT_STRIDE == 0:
            court_imgs.append(frame); court_fns.append(fn)
            if len(court_imgs) >= 20:
                process_court_batch(court_imgs, court_fns, court_m, kp_arr, court_dict, COURT_CONF)
                court_imgs, court_fns = [], []

        fn += 1
        if fn % 500 == 0:
            elapsed = time.time() - START
            log(f"  {fn}/{total}, {ball_count} balls, {len(hoops_by_frame)} hoop-frames, {fn/elapsed:.1f} fps")

    if court_imgs:
        process_court_batch(court_imgs, court_fns, court_m, kp_arr, court_dict, COURT_CONF)

    cap.release()
    log(f"Phase 2 done: {ball_count} balls, {len(hoops_by_frame)} hoop-frames, {len(court_dict)} courts")

    # Interpolate hoop positions to all frames
    log("Interpolating hoop positions...")
    hoop_cx = np.full(total, np.nan)
    hoop_cy = np.full(total, np.nan)
    sorted_hoop_fs = sorted(hoops_by_frame.keys())
    if sorted_hoop_fs:
        # For each frame, use nearest hoop detection
        for i in range(total):
            nearest = min(sorted_hoop_fs, key=lambda hf: abs(hf - i))
            if abs(nearest - i) <= HOOP_STRIDE * 2:  # only use if within 2 strides
                # Average all hoop detections at that frame
                hs = hoops_by_frame[nearest]
                if hs:
                    hoop_cx[i] = np.mean([h[0] for h in hs])
                    hoop_cy[i] = np.mean([h[1] for h in hs])

    log(f"Hoop position available for {int(np.sum(~np.isnan(hoop_cx)))} frames")

    # Phase 3: Ball tracking
    log("Phase 3: Ball tracking...")
    ball_clean = []
    last_good, removed = None, 0
    for b in ball_raw:
        if b is None:
            ball_clean.append(None)
            continue
        _, cx, cy, cf = b
        if last_good is not None:
            _, lx, ly, _ = last_good
            if np.sqrt((cx-lx)**2 + (cy-ly)**2) > MAX_JUMP:
                ball_clean.append(None)
                removed += 1
                continue
        ball_clean.append(b)
        last_good = b  # update even if gaps exist
    log(f"Kept {ball_count-removed}, removed {removed}")

    # Phase 4: Interpolate
    ball_cx = np.full(total, np.nan)
    ball_cy = np.full(total, np.nan)
    ball_cf = np.zeros(total)
    for b in ball_clean:
        if b is not None:
            f,cx,cy,cf = b; ball_cx[f]=cx; ball_cy[f]=cy; ball_cf[f]=cf
    nan_m = np.isnan(ball_cx)
    if np.any(~nan_m):
        idx = np.arange(total)
        ball_cx[nan_m] = np.interp(idx[nan_m],idx[~nan_m],ball_cx[~nan_m])
        ball_cy[nan_m] = np.interp(idx[nan_m],idx[~nan_m],ball_cy[~nan_m])

    # Interpolate court KPIs
    for k in range(18):
        last = np.array([np.nan,np.nan])
        for i in range(total):
            if not np.isnan(kp_arr[i,k,0]): last = kp_arr[i,k].copy()
            elif not np.isnan(last[0]): kp_arr[i,k] = last
        last = np.array([np.nan,np.nan])
        for i in range(total-1,-1,-1):
            if not np.isnan(kp_arr[i,k,0]): last = kp_arr[i,k].copy()
            elif not np.isnan(last[0]): kp_arr[i,k] = last

    # Phase 5: Shot detection
    log("Phase 5: Shot detection...")

    # Ball-to-hoop distance signal
    hsig = np.full(total, np.nan)
    for i in range(total):
        if np.isnan(ball_cx[i]) or np.isnan(hoop_cx[i]): continue
        hsig[i] = np.sqrt((ball_cx[i]-hoop_cx[i])**2 + (ball_cy[i]-hoop_cy[i])**2)

    # Method 1: Proximity (ball within HOOP_PROX of hoop)
    prox = []
    for i in range(total):
        if not np.isnan(hsig[i]) and hsig[i] < HOOP_PROX:
            prox.append({'frame':i, 'bcx':ball_cx[i], 'bcy':ball_cy[i],
                         'hcx':hoop_cx[i], 'hcy':hoop_cy[i],
                         'dist':hsig[i], 'bcf':ball_cf[i], 'hcf':0,
                         'interp':ball_cf[i]==0, 'method':'prox'})
    log(f"  Proximity: {len(prox)}")

    # Method 2: Peak-finding (local minima in ball-hoop distance)
    vs = hsig.copy(); vs[np.isnan(vs)] = HOOP_PROX*3; vs[vs>HOOP_PROX*3] = HOOP_PROX*3
    pk_idx,_ = find_peaks(-vs, distance=PEAK_DIST, height=-HOOP_PROX)
    peaks_list = [{'frame':int(p),'bcx':ball_cx[p],'bcy':ball_cy[p],
                   'hcx':hoop_cx[p],'hcy':hoop_cy[p],
                   'dist':hsig[p],'bcf':ball_cf[p],'hcf':0,
                   'interp':ball_cf[p]==0,'method':'peak'}
                  for p in pk_idx if hsig[p] < HOOP_PROX]
    log(f"  Peaks: {len(peaks_list)}")

    # Method 3: Gap shots (color-ok ball disappears near hoop)
    gaps = []
    for gfn in range(20, total):
        lr = None
        for prev in range(gfn-1,max(0,gfn-40),-1):
            if ball_cf[prev]>0: lr=prev; break
        if lr is None: continue
        gap = gfn-lr
        if gap<3 or gap>35: continue
        if not np.isnan(hsig[lr]) and hsig[lr]<HOOP_PROX:
            gaps.append({'frame':lr,'bcx':ball_cx[lr],'bcy':ball_cy[lr],
                         'hcx':hoop_cx[lr],'hcy':hoop_cy[lr],
                         'dist':hsig[lr],'bcf':ball_cf[lr],'hcf':0,
                         'interp':False,'method':'gap'})
    log(f"  Gaps: {len(gaps)}")

    # Phase 6: Union + dedup
    log("Phase 6: Deduplicating...")
    all_c = sorted(prox+peaks_list+gaps, key=lambda c:c['frame'])
    deduped = []
    i = 0
    while i < len(all_c):
        j = i+1
        while j<len(all_c) and all_c[j]['frame']-all_c[j-1]['frame']<DEDUP_RANGE: j+=1
        grp = all_c[i:j]; noni=[c for c in grp if not c['interp']]
        best = min(noni if noni else grp, key=lambda c: c['dist'] if not np.isnan(c['dist']) else 9999)
        deduped.append(best); i=j
    log(f"{len(all_c)} -> {len(deduped)} shots")

    # Phase 7: Classify
    shots = []
    for c in deduped:
        fn = c['frame']; d = c['dist'] if not np.isnan(c['dist']) else 9999
        shots.append({'frame':fn,'bx':round(c['bcx'],1),'by':round(c['bcy'],1),
                      'hoop_dist':round(d,1),'type':'3PT' if d>=TH_PT_THRESH else '2PT',
                      'result':'MAKE' if d<MAKE_RADIUS else 'MISS',
                      'bcf':round(c['bcf'],3),'hcf':round(c['hcf'],3),'method':c['method']})

    # Phase 8: Output
    pd.DataFrame(shots).sort_values('frame').to_csv(f'{OUT}/shot_candidates_v11.csv',index=False)
    pickle.dump({'shots':shots,'deduped':deduped,'ball_cx':ball_cx,'ball_cy':ball_cy,
                 'ball_cf':ball_cf,'hoop_cx':hoop_cx,'hoop_cy':hoop_cy,
                 'hoops_by_frame':dict(hoops_by_frame),'court_dict':court_dict},
                open(f'{OUT}/shot_v11.pkl','wb'))

    # Phase 9: Viz
    log("Phase 9: Visualizations...")
    cap = cv2.VideoCapture(VIDEO)
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s['frame']); ret,frame = cap.read()
        if not ret: continue
        bx,by = int(s['bx']),int(s['by'])
        cv2.circle(frame,(bx,by),15,(0,165,255),3)
        hcx,hcy = int(s.get('hcx',0)) if not np.isnan(s.get('hcx',np.nan)) else None, None
        cv2.putText(frame,f"F{s['frame']}: {s['type']} {s['result']} {s['hoop_dist']:.0f}px",
                    (10,30),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,255),2)
        cv2.imwrite(f'{OUT}/shot_candidate_v11_{s["frame"]:04d}.jpg',frame)
    cap.release()

    # Summary
    log("="*60)
    t2=[s for s in shots if s['type']=='2PT']; t3=[s for s in shots if s['type']=='3PT']
    mk=[s for s in shots if s['result']=='MAKE']
    pts=sum(2 for s in t2 if s['result']=='MAKE')+sum(3 for s in t3 if s['result']=='MAKE')
    log(f"RESULTS: {len(shots)} shots | "
        f"2PT {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)} | "
        f"3PT {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)} | "
        f"{len(mk)} makes, {pts}pts")
    log("Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"dist={s['hoop_dist']:5.1f}px bcf={s['bcf']:.3f} [{s['method']}]")
    log("DONE")
