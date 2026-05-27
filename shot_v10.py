#!/usr/bin/env python3
"""
Shot detection v10: Best of v8 + v9f
======================================
- Fine-tuned ball model at conf=0.0002 + color filter
- Ball tracking: 25px max jump + interpolation
- Triple-signal shot detection: proximity + peaks + gap
- Make/miss, 2PT/3PT classification
- Output: CSV, PKL, + per-shot visualization JPGs
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

# ============================================================
# CONFIG
# ============================================================
VIDEO       = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT         = 'pipeline_output'
BALL_MODEL  = 'ball_finetune/runs/finetune2/weights/best.pt'
COURT_MODEL = 'models/court_keypoint_detector.pt'

BALL_CONF    = 0.0002
BALL_IOU     = 0.3
COURT_CONF   = 0.3
MAX_JUMP     = 25
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
        with open(f'{OUT}/shot_v10.log', 'a') as f:
            f.write(line + '\n')
    except:
        pass

# ============================================================
# COURT BATCH PROCESSOR (defined before use)
# ============================================================
TACT_KPS = np.array([
    (0,0),(0,35),(0,60),(0,78),(0,104),(0,161),(150,161),(150,0),
    (85,60),(85,78),(300,161),(300,104),(300,78),(300,60),(300,35),(300,0),(215,60),(215,78)
], dtype=np.float32)
BASKET_TACT = np.array([150.0, 161.0 - 1.2192/(15.0/161.0)])

def process_court_batch(imgs, fns, model, kp_arr, court_dict, conf):
    try:
        results = model.predict(imgs, conf=conf, verbose=False)
        for cfn, cr in zip(fns, results):
            if cr.keypoints is None or len(cr.keypoints.xy) == 0:
                continue
            kps_xy = cr.keypoints.xy[0].cpu().numpy()
            kps_cf = cr.keypoints.conf[0].cpu().numpy()
            valid = (kps_xy[:,0] > 1) & (kps_xy[:,1] > 1) & (kps_cf > 0.2)
            vi = np.where(valid)[0]
            if len(vi) < 4:
                continue
            try:
                H, _ = cv2.findHomography(kps_xy[vi], TACT_KPS[vi], cv2.RANSAC, 5.0)
                if H is None:
                    continue
                bp = cv2.perspectiveTransform(
                    np.array([BASKET_TACT], dtype=np.float32).reshape(-1,1,2), H
                ).reshape(2)
                if -100 < bp[0] < 1400 and -100 < bp[1] < 900:
                    court_dict[cfn] = (H, bp)
                    kp_arr[cfn] = kps_xy
            except:
                pass
    except:
        pass

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':

    sys.stderr = DevNull()
    START = time.time()

    # ---- PHASE 1: Load models ----
    log("Loading models...")
    ball_m  = YOLO(BALL_MODEL, verbose=False)
    court_m = YOLO(COURT_MODEL, verbose=False)
    log(f"Models loaded. Ball classes: {ball_m.names}")

    # ---- PHASE 2: Per-frame detection ----
    log("Phase 2: Per-frame detection...")

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)
    log(f"Video: {total} frames @ {fps:.1f}fps")

    ball_raw = []
    hoops_by_frame = defaultdict(list)
    kp_arr = np.full((total, 18, 2), np.nan)
    court_dict = {}
    court_imgs, court_fns = [], []
    ball_count = 0
    fn = 0

    while True:
        ret, frame = cap.read()
        if not ret or fn >= total:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        r = ball_m.predict(frame, conf=BALL_CONF, iou=BALL_IOU, verbose=False)[0]
        best_ball = None
        best_bcf  = 0
        frame_hoops = []

        if r.boxes is not None:
            for box in r.boxes:
                cls_name = ball_m.names[int(box.cls[0])]
                cf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1+x2)/2, (y1+y2)/2

                if cls_name == 'Ball' and cf > best_bcf:
                    best_bcf  = cf
                    best_ball = (fn, cx, cy, cf)
                elif cls_name == 'Hoop' and cf > 0.1:
                    frame_hoops.append((cx, cy, cf))

        # Color check
        if best_ball is not None:
            _, bcx, bcy, bcf = best_ball
            ix, iy = int(bcx), int(bcy)
            color_ok = False
            if 0 <= ix < frame.shape[1] and 0 <= iy < frame.shape[0]:
                px = hsv[iy, ix]
                if 3 <= px[0] <= 30 and px[1] > 15:
                    color_ok = True
            if color_ok:
                ball_raw.append(best_ball)
                ball_count += 1
            else:
                ball_raw.append(None)
        else:
            ball_raw.append(None)

        if frame_hoops:
            hoops_by_frame[fn] = frame_hoops

        # Court keypoints
        if fn % 10 == 0:
            court_imgs.append(frame)
            court_fns.append(fn)
            if len(court_imgs) >= 20:
                process_court_batch(court_imgs, court_fns, court_m, kp_arr, court_dict, COURT_CONF)
                court_imgs, court_fns = [], []

        fn += 1
        if fn % 200 == 0:
            elapsed = time.time() - START
            fps_now  = fn / elapsed if elapsed > 0 else 0
            log(f"  {fn}/{total}, {ball_count} balls, {fps_now:.1f} fps")

    if court_imgs:
        process_court_batch(court_imgs, court_fns, court_m, kp_arr, court_dict, COURT_CONF)

    cap.release()
    log(f"Phase 2 done: {ball_count} color-ok balls, {len(hoops_by_frame)} hoop-frames, {len(court_dict)} courts")

    # ---- PHASE 3: Ball tracking filter ----
    log("Phase 3: Ball tracking filter...")

    ball_clean = []
    last_good  = None
    for b in ball_raw:
        if b is None:
            ball_clean.append(None)
            continue
        _, cx, cy, cf = b
        if last_good is not None:
            _, lx, ly, _ = last_good
            jump = np.sqrt((cx-lx)**2 + (cy-ly)**2)
            if jump > MAX_JUMP:
                ball_clean.append(None)
                continue
        ball_clean.append(b)
        last_good = b

    kept = sum(1 for b in ball_clean if b is not None)
    log(f"After filter: {kept} balls (removed {ball_count - kept})")

    # ---- PHASE 4: Interpolate ----
    log("Phase 4: Interpolating ball positions...")

    ball_cx   = np.full(total, np.nan)
    ball_cy   = np.full(total, np.nan)
    ball_conf_arr = np.zeros(total)

    for b in ball_clean:
        if b is not None:
            f, cx, cy, cf = b
            ball_cx[f] = cx
            ball_cy[f] = cy
            ball_conf_arr[f] = cf

    nan_mask = np.isnan(ball_cx)
    if np.any(~nan_mask):
        idx = np.arange(total)
        ball_cx[nan_mask] = np.interp(idx[nan_mask], idx[~nan_mask], ball_cx[~nan_mask])
        ball_cy[nan_mask] = np.interp(idx[nan_mask], idx[~nan_mask], ball_cy[~nan_mask])

    log(f"Interpolated {int(np.sum(nan_mask))} frames")

    # ---- PHASE 5: Interpolate court keypoints ----
    log("Phase 5: Interpolating court keypoints...")

    for kp_idx in range(18):
        last = np.array([np.nan, np.nan])
        for i in range(total):
            if not np.isnan(kp_arr[i, kp_idx, 0]):
                last = kp_arr[i, kp_idx].copy()
            elif not np.isnan(last[0]):
                kp_arr[i, kp_idx] = last
        last = np.array([np.nan, np.nan])
        for i in range(total-1, -1, -1):
            if not np.isnan(kp_arr[i, kp_idx, 0]):
                last = kp_arr[i, kp_idx].copy()
            elif not np.isnan(last[0]):
                kp_arr[i, kp_idx] = last

    # ---- PHASE 6: Shot detection (triple signal) ----
    log("Phase 6: Shot detection...")

    # Method 1: Ball-hoop proximity
    prox_cands = []
    for hf in sorted(hoops_by_frame.keys()):
        for hcx, hcy, hcf in hoops_by_frame[hf]:
            for offset in range(-3, 4):
                bf = hf + offset
                if bf < 0 or bf >= total or np.isnan(ball_cx[bf]):
                    continue
                dist = np.sqrt((ball_cx[bf]-hcx)**2 + (ball_cy[bf]-hcy)**2)
                if dist < HOOP_PROX:
                    prox_cands.append({
                        'frame': bf, 'hcx': hcx, 'hcy': hcy,
                        'bcx': ball_cx[bf], 'bcy': ball_cy[bf],
                        'dist': dist, 'bcf': ball_conf_arr[bf], 'hcf': hcf,
                        'interp': (ball_conf_arr[bf] == 0), 'method': 'prox'
                    })
    log(f"  Proximity: {len(prox_cands)} candidates")

    # Method 2: Peak-finding on ball-to-nearest-hoop distance
    hoop_dist_sig = np.full(total, np.nan)
    all_hoop_fs = sorted(hoops_by_frame.keys())
    for i in range(total):
        if np.isnan(ball_cx[i]):
            continue
        min_d = np.inf
        for hf in all_hoop_fs:
            if abs(hf - i) > 30:
                continue
            for hcx, hcy, _ in hoops_by_frame[hf]:
                d = np.sqrt((ball_cx[i]-hcx)**2 + (ball_cy[i]-hcy)**2)
                min_d = min(min_d, d)
        if min_d < HOOP_PROX * 2:
            hoop_dist_sig[i] = min_d

    valid_sig = hoop_dist_sig.copy()
    valid_sig[np.isnan(valid_sig)] = HOOP_PROX * 3
    peaks, _ = find_peaks(-valid_sig, distance=PEAK_DIST, height=-HOOP_PROX)

    peak_cands = []
    for p in peaks:
        if hoop_dist_sig[p] < HOOP_PROX:
            peak_cands.append({
                'frame': int(p), 'hcx': np.nan, 'hcy': np.nan,
                'bcx': ball_cx[p], 'bcy': ball_cy[p],
                'dist': hoop_dist_sig[p], 'bcf': ball_conf_arr[p], 'hcf': 0,
                'interp': (ball_conf_arr[p] == 0), 'method': 'peak'
            })
    log(f"  Peaks: {len(peak_cands)} candidates")

    # Method 3: Gap shots
    gap_cands = []
    for gap_fn in range(20, total):
        last_real = None
        for prev in range(gap_fn-1, max(0, gap_fn-40), -1):
            if ball_conf_arr[prev] > 0:
                last_real = prev
                break
        if last_real is None:
            continue
        gap = gap_fn - last_real
        if gap < 3 or gap > 35:
            continue
        lcx, lcy = ball_cx[last_real], ball_cy[last_real]
        near_hoop = False
        best_d = np.inf
        best_h = (np.nan, np.nan)
        for hf in all_hoop_fs:
            if abs(hf - last_real) > 10:
                continue
            for hcx, hcy, _ in hoops_by_frame[hf]:
                d = np.sqrt((lcx-hcx)**2 + (lcy-hcy)**2)
                if d < HOOP_PROX and d < best_d:
                    near_hoop = True
                    best_d = d
                    best_h = (hcx, hcy)
        if near_hoop:
            gap_cands.append({
                'frame': last_real, 'hcx': best_h[0], 'hcy': best_h[1],
                'bcx': lcx, 'bcy': lcy,
                'dist': best_d, 'bcf': ball_conf_arr[last_real], 'hcf': 0,
                'interp': False, 'method': 'gap'
            })
    log(f"  Gaps: {len(gap_cands)} candidates")

    # ---- PHASE 7: Union + deduplicate ----
    log("Phase 7: Deduplicating...")

    all_cands = sorted(prox_cands + peak_cands + gap_cands, key=lambda c: c['frame'])

    deduped = []
    i = 0
    while i < len(all_cands):
        j = i + 1
        while j < len(all_cands) and all_cands[j]['frame'] - all_cands[j-1]['frame'] < DEDUP_RANGE:
            j += 1
        group = all_cands[i:j]
        non_interp = [c for c in group if not c['interp']]
        if non_interp:
            best = min(non_interp, key=lambda c: c['dist'] if not np.isnan(c['dist']) else 9999)
        else:
            best = min(group, key=lambda c: c['dist'] if not np.isnan(c['dist']) else 9999)
        deduped.append(best)
        i = j

    log(f"Deduped: {len(all_cands)} -> {len(deduped)} shots")

    # ---- PHASE 8: Classify ----
    log("Phase 8: Classifying shots...")

    shots = []
    for c in deduped:
        fn = c['frame']
        dist = c['dist'] if not np.isnan(c['dist']) else 9999
        result = 'MAKE' if dist < MAKE_RADIUS else 'MISS'
        shot_type = '3PT' if dist >= TH_PT_THRESH else '2PT'
        shots.append({
            'frame': fn,
            'bx': round(c['bcx'], 1), 'by': round(c['bcy'], 1),
            'hoop_dist': round(dist, 1),
            'type': shot_type, 'result': result,
            'bcf': round(c['bcf'], 3), 'hcf': round(c['hcf'], 3),
            'method': c['method']
        })

    # ---- PHASE 9: Write output ----
    log("Phase 9: Writing output...")

    shots_df = pd.DataFrame(shots).sort_values('frame')
    shots_df.to_csv(f'{OUT}/shot_candidates_v10.csv', index=False)

    results = {
        'shots': shots, 'deduped': deduped,
        'ball_cx': ball_cx, 'ball_cy': ball_cy, 'ball_conf': ball_conf_arr,
        'ball_raw': ball_raw, 'ball_clean': ball_clean,
        'hoops_by_frame': dict(hoops_by_frame),
        'court_dict': court_dict, 'kp_arr': kp_arr,
    }
    with open(f'{OUT}/shot_v10.pkl', 'wb') as f:
        pickle.dump(results, f)

    # ---- PHASE 10: Visualization ----
    log("Phase 10: Generating visualizations...")

    cap = cv2.VideoCapture(VIDEO)
    for s in shots:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s['frame'])
        ret, frame = cap.read()
        if not ret:
            continue
        bx, by = int(s['bx']), int(s['by'])
        cv2.circle(frame, (bx, by), 15, (0, 165, 255), 3)
        if not np.isnan(s.get('hcx', np.nan)):
            hc = (int(s['hcx']), int(s['hcy']))
            cv2.circle(frame, hc, 20, (255, 0, 0), 3)
            cv2.line(frame, (bx, by), hc, (0, 255, 0), 2)
        label = (f"F{s['frame']}: {s['type']} {s['result']} "
                 f"dist={s['hoop_dist']:.0f}px [{s['method']}]")
        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        cv2.imwrite(f'{OUT}/shot_candidate_v10_{s["frame"]:04d}.jpg', frame)
    cap.release()

    # ---- SUMMARY ----
    log("=" * 60)
    t2 = [s for s in shots if s['type'] == '2PT']
    t3 = [s for s in shots if s['type'] == '3PT']
    makes = [s for s in shots if s['result'] == 'MAKE']
    pts = sum(2 for s in t2 if s['result']=='MAKE') + sum(3 for s in t3 if s['result']=='MAKE')

    log(f"v10 RESULTS: {len(shots)} shots")
    log(f"2PT: {sum(1 for s in t2 if s['result']=='MAKE')}/{len(t2)}")
    log(f"3PT: {sum(1 for s in t3 if s['result']=='MAKE')}/{len(t3)}")
    log(f"Total makes: {len(makes)}, Points: {pts}")
    log(f"Target: 2PT 2/7, 3PT 1/2, FT 1/3 = 8pts")
    for s in shots:
        log(f"  F{s['frame']:4d}: {s['type']:3s} {s['result']:4s} "
            f"dist={s['hoop_dist']:5.1f}px bcf={s['bcf']:.3f} [{s['method']}]")
    log(f"DONE - output in {OUT}/")
