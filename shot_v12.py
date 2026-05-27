#!/usr/bin/env python3
"""
Shot detection v12: Color-based ball + NN-based hap detection
==============================================================
- Ball: HSV color segmentation (orange blob) — fast, finds ball on ~95% of frames
- Hoop: ball_detector.pt NN every 30 frames, interpolated between
- Court: court_keypoint_detector.pt every 10 frames
- Triple-signal shot detection: proximity + peaks + gap
- Estimated runtime: ~12 min for 2701 frames
"""

import os, sys, time, pickle
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from ultralytics import YOLO
from collections import defaultdict

VIDEO       = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT         = 'pipeline_output'
HOOP_MODEL  = 'models/ball_detector.pt'
COURT_MODEL = 'models/court_keypoint_detector.pt'

HOOP_CONF    = 0.1
HOOP_STRIDE  = 30
COURT_CONF   = 0.3
BALL_H_MIN   = 3
BALL_H_MAX   = 30
BALL_S_MIN   = 30
BALL_AREA_MIN= 30
BALL_AREA_MAX= 5000
BALL_CIRC_MIN= 0.4
MAX_JUMP     = 100   # px between consecutive ball detections (color can jump)
HOOP_PROX    = 150
MAKE_RADIUS  = 40
TH_PT_THRESH = 120
DEDUP_RANGE  = 20
PEAK_DIST    = 10

os.makedirs(OUT, exist_ok=True)

class DevNull:
    def write(self, x): pass
    def flush(self): pass

def log(msg):
    t = time.time() - START
    line = f"[{t:.0f}s] {msg}"
    print(line, flush=True)
    try:
        with open(f'{OUT}/shot_v12.log', 'a') as f:
            f.write(line + '\n')
    except: pass

def detect_ball_color(frame, hsv):
    """Detect orange basketball using HSV color segmentation."""
    mask = cv2.inRange(hsv,
        np.array([BALL_H_MIN, BALL_S_MIN, 30]),
        np.array([BALL_H_MAX, 255, 255]))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < BALL_AREA_MIN or area > BALL_AREA_MAX:
            continue
        (x, y), _ = cv2.minEnclosingCircle(cnt)
        perim = cv2.arcLength(cnt, True)
        if perim == 0: continue
        circ = 4 * np.pi * area / (perim * perim)
        if circ < BALL_CIRC_MIN: continue
        if best is None or area > best[2]:
            best = (int(x), int(y), area, circ)
    return best  # (cx, cy, area, circularity) or None

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
                H,_ = cv2.findHomography(kps_xy[vi],TACT_KPS[vi],cv2.RANSAC,5.0)
                if H is None: continue
                bp = cv2.perspectiveTransform(
                    np.array([BASKET_TACT],dtype=np.float32).reshape(-1,1,2),H).reshape(2)
                if -100<bp[0]<1400 and -100<bp[1]<900:
                    court_dict[cfn] = (H,bp); kp_arr[cfn] = kps_xy
            except: pass
    except: pass

if __name__ == '__main__':
    sys.stderr = DevNull()
    START = time.time()

    log("Loading models...")
    hoop_m  = YOLO(HOOP_MODEL, verbose=False)
    court_m = YOLO(COURT_MODEL, verbose=False)
    log(f"Hoop classes: {hoop_m.names}")

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_v = cap.get(cv2.CAP_PROP_FPS)
    log(f"Video: {total} frames @ {fps_v:.1f}fps")

    # === Phase 2: Detection ===
    log("Phase 2: Detection pass...")
    ball_raw  = []
    hoops_by_frame = defaultdict(list)
    kp_arr    = np.full((total, 18, 2), np.nan)
    court_dict = {}
    court_imgs, court_fns = [], []
    ball_count = 0
    fn = 0

    while True:
        ret, frame = cap.read()
        if not ret or fn >= total: break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Ball: color detection
        ball = detect_ball_color(frame, hsv)
        if ball is not None:
            ball_raw.append((fn, ball[0], ball[1], ball[2]))
            ball_count += 1
        else:
            ball_raw.append(None)

        # Hoop: NN every HOOP_STRIDE frames
        if fn % HOOP_STRIDE == 0:
            rh = hoop_m.predict(frame, conf=HOOP_CONF, verbose=False)[0]
            if rh.boxes is not None:
                fhs = []
                for box in rh.boxes:
                    cls = hoop_m.names[int(box.cls[0])]
                    cf  = float(box.conf[0])
                    if cls == 'Hoop' and cf > HOOP_CONF:
                        x1,y1,x2,y2 = box.xyxy[0].tolist()
                        fhs.append(((x1+x2)/2, (y1+y2)/2, cf))
                if fhs: hoops_by_frame[fn] = fhs

        # Court keypoints
        if fn % 10 == 0:
            court_imgs.append(frame); court_fns.append(fn)
            if len(court_imgs) >= 20:
                process_court_batch(court_imgs, court_fns, court_m, kp_arr, court_dict, COURT_CONF)
                court_imgs, court_fns = [], []

        fn += 1
        if fn % 500 == 0:
            elapsed = time.time() - START
            log(f"  {fn}/{total}, {ball_count} balls, {len(hoops_by_frame)} hf, {fn/elapsed:.1f} fps")

    if court_imgs:
        process_court_batch(court_imgs, court_fns, court_m, kp_arr, court_dict, COURT_CONF)
    cap.release()
    log(f"Phase 2 done: {ball_count} balls, {len(hoops_by_frame)} hoop-frames, {len(court_dict)} courts")

    # === Phase 3: Interpolate hoop positions ===
    log("Interpolating hoop positions...")
    hoop_cx = np.full(total, np.nan)
    hoop_cy = np.full(total, np.nan)
    sorted_hf = sorted(hoops_by_frame.keys())
    for i in range(total):
        nearest = min(sorted_hf, key=lambda hf: abs(hf-i))
        if abs(nearest - i) <= HOOP_STRIDE * 2:
            hs = hoops_by_frame[nearest]
            if hs:
                hoop_cx[i] = np.mean([h[0] for h in hs])
                hoop_cy[i] = np.mean([h[1] for h in hs])
    valid_hoops = int(np.sum(~np.isnan(hoop_cx)))
    log(f"Hoop position for {valid_hoops}/{total} frames")

    # === Phase 4: Ball tracking ===
    log("Phase 4: Ball tracking...")
    ball_clean = []
    last_good, removed = None, 0
    for b in ball_raw:
        if b is None: ball_clean.append(None); continue
        _,cx,cy,area = b
        if last_good is not None:
            _,lx,ly,_ = last_good
            if np.sqrt((cx-lx)**2+(cy-ly)**2) > MAX_JUMP:
                ball_clean.append(None); removed += 1; continue
        ball_clean.append(b); last_good = b
    log(f"Kept {ball_count-removed}, removed {removed}")

    # === Phase 5: Interpolate ball ===
    ball_cx = np.full(total, np.nan)
    ball_cy = np.full(total, np.nan)
    ball_cf = np.zeros(total)
    for b in ball_clean:
        if b is not None:
            f,cx,cy,area = b; ball_cx[f]=cx; ball_cy[f]=cy; ball_cf[f]=area
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

    # === Phase 6: Shot detection ===
    log("Phase 6: Shot detection...")
    hsig = np.full(total, np.nan)
    for i in range(total):
        if np.isnan(ball_cx[i]) or np.isnan(hoop_cx[i]): continue
        hsig[i] = np.sqrt((ball_cx[i]-hoop_cx[i])**2 + (ball_cy[i]-hoop_cy[i])**2)

    # Proximity
    prox = [{'frame':i,'bcx':ball_cx[i],'bcy':ball_cy[i],'hcx':hoop_cx[i],'hcy':hoop_cy[i],
             'dist':hsig[i],'bcf':ball_cf[i],'hcf':0,'interp':ball_cf[i]==0,'method':'prox'}
            for i in range(total) if not np.isnan(hsig[i]) and hsig[i]<HOOP_PROX]
    log(f"  Proximity: {len(prox)}")

    # Peaks
    vs = hsig.copy(); vs[np.isnan(vs)]=HOOP_PROX*3
    pk_idx,_ = find_peaks(-vs,distance=PEAK_DIST,height=-HOOP_PROX)
    peaks = [{'frame':int(p),'bcx':ball_cx[p],'bcy':ball_cy[p],'hcx':hoop_cx[p],'hcy':hoop_cy[p],
              'dist':hsig[p],'bcf':ball_cf[p],'hcf':0,'interp':ball_cf[p]==0,'method':'peak'}
             for p in pk_idx if hsig[p]<HOOP_PROX]
    log(f"  Peaks: {len(peaks)}")

    # Gaps
    gaps = []
    for gfn in range(20, total):
        lr = None
        for prev in range(gfn-1,max(0,gfn-40),-1):
            if ball_cf[prev]>0: lr=prev; break
        if lr is None: continue
        gap=gfn-lr
        if gap<3 or gap>35: continue
        if not np.isnan(hsig[lr]) and hsig[lr]<HOOP_PROX:
            gaps.append({'frame':lr,'bcx':ball_cx[lr],'bcy':ball_cy[lr],
                         'hcx':hoop_cx[lr],'hcy':hoop_cy[lr],'dist':hsig[lr],
                         'bcf':ball_cf[lr],'hcf':0,'interp':False,'method':'gap'})
    log(f"  Gaps: {len(gaps)}")

    # === Phase 7: Dedup ===
    all_c = sorted(prox+peaks+gaps, key=lambda c:c['frame'])
    deduped = []
    i = 0
    while i < len(all_c):
        j=i+1
        while j<len(all_c) and all_c[j]['frame']-all_c[j-1]['frame']<DEDUP_RANGE: j+=1
        grp=all_c[i:j]; noni=[c for c in grp if not c['interp']]
        best=min(noni if noni else grp, key=lambda c: c['dist'] if not np.isnan(c['dist']) else 9999)
        deduped.append(best); i=j
    log(f"{len(all_c)} -> {len(deduped)} shots")

    # === Phase 8: Classify ===
    shots = []
    for c in deduped:
        fn=c['frame']; d=c['dist'] if not np.isnan(c['dist']) else 9999
        shots.append({'frame':fn,'bx':round(c['bcx'],1),'by':round(c['bcy'],1),
                      'hoop_dist':round(d,1),'type':'3PT' if d>=TH_PT_THRESH else '2PT',
                      'result':'MAKE' if d<MAKE_RADIUS else 'MISS',
                      'bcf':round(c['bcf'],3),'hcf':0,'method':c['method']})

    # === Phase 9: Output ===
    pd.DataFrame(shots).sort_values('frame').to_csv(f'{OUT}/shot_candidates_v12.csv',index=False)
    pickle.dump({'shots':shots,'ball_cx':ball_cx,'ball_cy':ball_cy,'ball_cf':ball_cf,
                 'hoop_cx':hoop_cx,'hoop_cy':hoop_cy,'hoops_by_frame':dict(hoops_by_frame)},
                open(f'{OUT}/shot_v12.pkl','wb'))

    # === Phase 10: Viz ===
    log("Phase 10: Visualizations...")
    cap = cv2.VideoCapture(VIDEO)
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s['frame']); ret,frame = cap.read()
        if not ret: continue
        bx,by = int(s['bx']),int(s['by'])
        cv2.circle(frame,(bx,by),15,(0,165,255),3)
        cv2.putText(frame,f"F{s['frame']}: {s['type']} {s['result']} {s['hoop_dist']:.0f}px [{s['method']}]",
                    (10,30),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,255),2)
        cv2.imwrite(f'{OUT}/shot_candidate_v12_{s["frame"]:04d}.jpg',frame)
    cap.release()

    # Summary
    log("="*60)
    t2=[s for s in shots if s['type']=='2PT']; t3=[s for s in shots if s['type']=='3PT']
    mk=[s for s in shots if s['result']=='MAKE']
    pts=sum(2 for s in t2 if s['result']=='MAKE')+sum(3 for s in t3 if s['result']=='MAKE')
    log(f"RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)} "
        f"({'no attempts' if not t2 else ', '.join('F'+str(s['frame']) for s in t2)})")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)} "
        f"({'no attempts' if not t3 else ', '.join('F'+str(s['frame']) for s in t3)})")
    log(f"Makes: {len(mk)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} dist={s['hoop_dist']:5.1f}px [{s['method']}]")
    log("DONE")
