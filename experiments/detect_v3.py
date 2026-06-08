#!/usr/bin/env python3
"""
Ball detection v3: Motion + color with proper persistent track tracking.
- Saves track IDs so we can analyze full trajectories.
- Filters tracks by ball-like characteristics (circular, parabolic, sized).
- Outputs cleaned CSV with track_id column.
- Detects shots from ball trajectories.
"""

import cv2
import numpy as np
import os
import csv

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
HOOP_PATH = "hoop_Q1.npy"
OUTPUT_CSV = "ball_v3_tracks.csv"
SHOT_CSV = "ball_v3_shots.csv"
OUT_DIR = "v3_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2
MAX_FRAMES = None  # None = all frames

# Color thresholds (HSV)
HUE_LOW = 0; HUE_HIGH = 25; SAT_MIN = 60; VAL_MIN = 60; VAL_MAX = 255

# Tracking params
MAX_LINK_DIST = 80
MIN_TRACK_HITS = 3
MAX_AGE = 5  # keep tracking this many frames without a hit

# Ball classification
BALL_MIN_DIAM = 8
BALL_MAX_DIAM = 50
BALL_MIN_CIRC = 0.15
BALL_MIN_SOL = 0.25

# Hoop data
def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    return data['frame_indices'], data['centers'], data['radii']

def get_hoop(frame_idx, f_ind, cents, rads):
    idx = np.argmin(np.abs(f_ind - frame_idx))
    return cents[idx], rads[idx], f_ind[idx]

def fg_mask(frame, bg_sub, kernel):
    mask = bg_sub.apply(frame)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask

def detect_in_frame(frame, fg):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cmask = cv2.inRange(hsv, np.array([HUE_LOW, SAT_MIN, VAL_MIN]),
                        np.array([HUE_HIGH, 255, VAL_MAX]))
    combined = cv2.bitwise_and(fg, cmask)
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    dets = []
    for c in contours:
        a = cv2.contourArea(c)
        if a < 15 or a > 5000: continue
        (x,y), r = cv2.minEnclosingCircle(c)
        d = 2*r
        if not (6 <= d <= 120): continue
        rx,ry,rw,rh = cv2.boundingRect(c)
        if rw==0 or rh==0: continue
        asp = rw/rh
        if not (0.3 <= asp <= 1.7): continue
        hull = cv2.convexHull(c)
        ha = cv2.contourArea(hull)
        if ha==0: continue
        sol = a/ha
        if sol < 0.2: continue
        circ = a/(np.pi*r*r) if r>0 else 0
        if circ < 0.1: continue
        M = cv2.moments(c)
        if M["m00"]==0: continue
        dets.append({'cx':M["m10"]/M["m00"], 'cy':M["m01"]/M["m00"],
                     'diam':d, 'area':a, 'circ':circ, 'sol':sol})
    return dets

def classify_ball_track(track):
    """Score a track for how ball-like it is. Returns 0-1 score."""
    positions = track['positions']
    diams = track['diameters']
    circs = track['circularities']
    n = len(positions)
    
    if n < 3:
        return 0.0
    
    # Diameter consistency (ball should have consistent apparent size)
    diam_mean = float(np.mean(diams))
    diam_std = float(np.std(diams))
    if diam_mean < BALL_MIN_DIAM or diam_mean > BALL_MAX_DIAM:
        return 0.0
    diam_cv = diam_std / diam_mean if diam_mean > 0 else 999
    diam_score = max(0, 1.0 - diam_cv)
    
    # Circularity
    circ_mean = float(np.mean(circs))
    circ_score = min(1.0, circ_mean / 0.4)
    
    # Trajectory smoothness
    xs = np.array([p[0] for p in positions], dtype=float)
    ys = np.array([p[1] for p in positions], dtype=float)
    
    parabola_score = 0.3
    if n >= 5:
        frames = np.array(track['frames'], dtype=float)
        try:
            if len(set(frames)) >= 3:
                coeffs = np.polyfit(frames, ys, 2)
                a = coeffs[0]
                if a > 0:
                    y_fit = np.polyval(coeffs, frames)
                    residual = float(np.mean((ys - y_fit)**2))
                    parabola_score = max(0, 1.0 - residual / 1000)
                else:
                    parabola_score = 0.1
        except Exception:
            parabola_score = 0.2
    
    dists = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
    total_dist = float(np.sum(dists))
    dist_score = min(1.0, total_dist / 200)
    
    if len(dists) > 1 and float(np.mean(dists)) > 0:
        dist_cv = float(np.std(dists)) / float(np.mean(dists))
        smooth_score = max(0, 1.0 - dist_cv / 2)
    else:
        smooth_score = 0.5
    
    score = (0.2 * diam_score + 0.2 * circ_score + 0.25 * parabola_score + 
             0.15 * dist_score + 0.2 * smooth_score)
    return score

def find_shots(ball_tracks, hoop_center, hoop_radius_px):
    """Detect shots from ball track trajectories."""
    HOOP_RADIUS_FT = 0.75
    ft_per_px = HOOP_RADIUS_FT / hoop_radius_px if hoop_radius_px > 0 else 0.0053
    
    shots = []
    for track in ball_tracks:
        positions = track['positions']
        frames = track['frames']
        if len(positions) < 5:
            continue
        
        ys = np.array([p[1] for p in positions])
        xs = np.array([p[0] for p in positions])
        
        # Find peak (minimum Y = highest point in frame)
        peak_idx = np.argmin(ys)
        peak_frame = frames[peak_idx]
        peak_x = xs[peak_idx]
        peak_y = ys[peak_idx]
        
        # Distance from hoop at peak
        dx = (peak_x - hoop_center[0]) * ft_per_px
        dy = (peak_y - hoop_center[1]) * ft_per_px
        dist_from_hoop = np.sqrt(dx**2 + dy**2)
        
        # Shot: ball peaks near hoop (within ~5ft) and changes direction
        if dist_from_hoop < 5.0:
            shot_type = "2PT" if dist_from_hoop * ft_per_px < 22/1.8 else "3PT"
            shots.append({
                'frame': peak_frame,
                'x': peak_x, 'y': peak_y,
                'dist_from_hoop_ft': dist_from_hoop,
                'shot_type': shot_type,
                'track_hits': len(positions),
                'track_score': track.get('ball_score', 0)
            })
    return shots

def main():
    f_ind, hoop_centers, hoop_radii = load_hoop()
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    bg_sub = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=20, detectShadows=False)
    
    cap = cv2.VideoCapture(VIDEO_PATH)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {total_frames} frames")
    
    # First pass: warm up background model
    warmup = min(100, total_frames // 4)
    for i in range(warmup):
        ret, frame = cap.read()
        if not ret: break
        bg_sub.apply(frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    
    tracks = []  # list of dicts: {id, positions[], frames[], diameters[], circularities[], hits, age, alive}
    next_id = 0
    frame_idx = 0
    all_rows = []
    saved_vis = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        if MAX_FRAMES and frame_idx >= MAX_FRAMES: break
        
        if frame_idx % STRIDE != 0:
            frame_idx += 1
            continue
        
        fg = fg_mask(frame, bg_sub, kernel)
        dets = detect_in_frame(frame, fg)
        
        # Link detections to existing tracks
        alive_tracks = [t for t in tracks if t['age'] <= MAX_AGE]
        
        if not alive_tracks:
            new_tracks = []
            for d in dets:
                new_tracks.append({
                    'id': next_id, 'positions': [(d['cx'], d['cy'])],
                    'frames': [frame_idx], 'diameters': [d['diam']],
                    'circularities': [d['circ']], 'hits': 1, 'age': 0, 'alive': True
                })
                next_id += 1
            alive_tracks = new_tracks
        else:
            cost = np.array([[np.sqrt((t['positions'][-1][0]-d['cx'])**2 + 
                                     (t['positions'][-1][1]-d['cy'])**2) for d in dets] for t in alive_tracks])
            flat = sorted([(float(cost[i,j]), i, j) for i in range(cost.shape[0]) for j in range(cost.shape[1])]) if cost.size > 0 else []
            used_det = set()
            used_track = set()
            new_alive = []
            for c, i, j in flat:
                if i in used_track or j in used_det or c > MAX_LINK_DIST:
                    continue
                alive_tracks[i]['positions'].append((dets[j]['cx'], dets[j]['cy']))
                alive_tracks[i]['frames'].append(frame_idx)
                alive_tracks[i]['diameters'].append(dets[j]['diam'])
                alive_tracks[i]['circularities'].append(dets[j]['circ'])
                alive_tracks[i]['hits'] += 1
                alive_tracks[i]['age'] = 0
                new_alive.append(alive_tracks[i])
                used_track.add(i); used_det.add(j)
            
            for i, t in enumerate(alive_tracks):
                if i not in used_track:
                    t['age'] += 1
                    if t['age'] <= MAX_AGE:
                        new_alive.append(t)
            
            for j, d in enumerate(dets):
                if j not in used_det:
                    new_alive.append({
                        'id': next_id, 'positions': [(d['cx'], d['cy'])],
                        'frames': [frame_idx], 'diameters': [d['diam']],
                        'circularities': [d['circ']], 'hits': 1, 'age': 0, 'alive': True
                    })
                    next_id += 1
            alive_tracks = new_alive
        
        tracks = alive_tracks
        
        # Save detection rows for tracks with enough hits
        for t in tracks:
            if t['hits'] >= MIN_TRACK_HITS:
                d = t['diameters'][-1]
                c = t['circularities'][-1]
                pos = t['positions'][-1]
                all_rows.append({
                    'track_id': t['id'], 'frame': frame_idx,
                    'cx': pos[0], 'cy': pos[1], 'diam': d, 'circ': c,
                    'track_hits': t['hits'], 'track_age': t['age']
                })
        
        # Save visualization
        if saved_vis < 30 and frame_idx % (STRIDE * 50) == 0 and frame_idx > 100:
            vis = frame.copy()
            mo = np.zeros_like(vis)
            mo[fg>0] = [255,255,255]
            vis = cv2.addWeighted(vis, 1.0, mo, 0.1, 0)
            for t in tracks:
                if t['hits'] >= 3 and len(t['positions']) >= 3:
                    pts = np.array(t['positions'][-20:], dtype=np.int32)
                    color = (0,255,0) if t['hits'] >= 5 else (0,165,255)
                    cv2.polylines(vis, [pts], False, color, 2)
            n_good = len([t for t in tracks if t['hits']>=3])
            cv2.putText(vis, f"F:{frame_idx} {n_good} tracks",
                        (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
            cv2.imwrite(f"{OUT_DIR}/f{frame_idx:05d}.jpg", vis)
            saved_vis += 1
        
        if frame_idx % (STRIDE * 100) == 0:
            n_3plus = len([t for t in tracks if t['hits']>=3])
            print(f"Frame {frame_idx}: {len(tracks)} active, {n_3plus} with 3+ hits")
        
        frame_idx += 1
    
    cap.release()
    
    print(f"\nDone. Total tracks with {MIN_TRACK_HITS}+ hits: {len(set(r['track_id'] for r in all_rows))}")
    print(f"Total detection rows: {len(all_rows)}")
    
    # Classify tracks
    unique_tracks = {}
    for r in all_rows:
        tid = r['track_id']
        if tid not in unique_tracks:
            unique_tracks[tid] = {'positions': [], 'frames': [], 'diameters': [], 'circularities': []}
        unique_tracks[tid]['positions'].append((r['cx'], r['cy']))
        unique_tracks[tid]['frames'].append(r['frame'])
        unique_tracks[tid]['diameters'].append(r['diam'])
        unique_tracks[tid]['circularities'].append(r['circ'])
    
    print(f"\nClassifying {len(unique_tracks)} unique tracks...")
    ball_tracks = []
    track_scores = []
    for tid, t in unique_tracks.items():
        score = classify_ball_track(t)
        track_scores.append((tid, score, len(t['positions']), np.mean(t['diameters'])))
        if score > 0.35:
            t['id'] = tid
            t['ball_score'] = score
            ball_tracks.append(t)
    
    track_scores.sort(key=lambda x: -x[1])
    print("\nTop 20 tracks by ball-score:")
    for tid, score, n, diam in track_scores[:20]:
        print(f"  Track {tid}: score={score:.2f}, {n} pts, avg_diam={diam:.1f}px")
    
    print(f"\nBall-like tracks (score>0.35): {len(ball_tracks)}")
    
    # Save ball track detections
    ball_rows = [r for r in all_rows if any(r['track_id'] == bt['id'] for bt in ball_tracks)]
    if ball_rows:
        with open(OUTPUT_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['track_id','frame','cx','cy','diam','circ','track_hits','track_age'])
            writer.writeheader()
            for r in ball_rows:
                writer.writerow(r)
        print(f"Saved {len(ball_rows)} ball-track detections to {OUTPUT_CSV}")
    
    # Find shots from ball tracks
    if ball_tracks:
        # Use last frame's hoop data
        hc, hr, _ = get_hoop(total_frames-1, f_ind, hoop_centers, hoop_radii)
        shots = find_shots(ball_tracks, hc, hr)
        print(f"\nDetected {len(shots)} potential shots:")
        for s in shots:
            print(f"  Frame {s['frame']}: {s['shot_type']} at ({s['x']:.0f},{s['y']:.0f}), dist={s['dist_from_hoop_ft']:.1f}ft, track_score={s['track_score']:.2f}")
        
        with open(SHOT_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['frame','x','y','dist_from_hoop_ft','shot_type','track_hits','track_score'])
            writer.writeheader()
            for s in shots:
                writer.writerow(s)

if __name__ == "__main__":
    main()
