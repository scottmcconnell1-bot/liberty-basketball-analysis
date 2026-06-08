#!/usr/bin/env python3
"""
Ball detection using motion (background subtraction) + color on full Q1 video.
- Processes Q1 video at configurable stride.
- Uses MOG2 background subtractor to find moving objects.
- Within motion mask, filters by orange/brown color and circular shape.
- Tracks across frames using nearest neighbor.
- Outputs: CSV, track visualizations, sample overlaid frames.
"""

import cv2
import numpy as np
import os
import csv

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
OUT_CSV = "ball_motion_q1.csv"
VIS_DIR = "motion_vis"
os.makedirs(VIS_DIR, exist_ok=True)

STRIDE = 2   # process every Nth frame
MAX_FRAMES = 500  # limit for quick test (set to None for all)

# Color ranges in HSV
HUE_LOW = 0
HUE_HIGH = 25
SAT_MIN = 60
VAL_MIN = 60
VAL_MAX = 255

# Background subtractor
BG_SUB = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=False)

# Tracker params
MAX_LINK_DIST = 80  # max pixel distance for frame-to-frame linking
MIN_TRACK_HITS = 2  # min hits to keep a track
MIN_TRACK_AGE_TO_SAVE = 3  # min age to save sample visualization

def fg_mask(frame, bg_sub):
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
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
        if a < 20 or a > 5000:
            continue
        (x,y), r = cv2.minEnclosingCircle(c)
        d = 2*r
        if not (8 <= d <= 120):
            continue
        rx,ry,rw,rh = cv2.boundingRect(c)
        if rw==0 or rh==0:
            continue
        asp = rw/rh
        if not (0.4 <= asp <= 1.6):
            continue
        hull = cv2.convexHull(c)
        ha = cv2.contourArea(hull)
        if ha == 0:
            continue
        sol = a/ha
        if sol < 0.3:
            continue
        circ = a/(np.pi*r*r) if r>0 else 0
        if circ < 0.15:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        dets.append({'cx':M["m10"]/M["m00"], 'cy':M["m01"]/M["m00"],
                     'diam':d, 'area':a, 'circ':circ, 'sol':sol})
    return dets, combined

def link_tracks(prev, curr, max_dist):
    if not prev:
        return [{'pts':[(d['cx'],d['cy'])], 'd':d, 'hits':1, 'age':1} for d in curr]
    if not curr:
        for t in prev:
            t['age'] += 1
        return prev
    
    cost = np.array([[np.sqrt((p['pts'][-1][0]-c['cx'])**2 + (p['pts'][-1][1]-c['cy'])**2) for c in curr] for p in prev])
    used_c = set()
    used_p = set()
    result = []
    
    if cost.size > 0:
        flat = sorted([(cost[i,j], i, j) for i in range(cost.shape[0]) for j in range(cost.shape[1])])
        for c,i,j in flat:
            if i in used_p or j in used_c or c > max_dist:
                continue
            prev[i]['pts'].append((curr[j]['cx'], curr[j]['cy']))
            prev[i]['d'] = curr[j]
            prev[i]['hits'] += 1
            prev[i]['age'] += 1
            result.append(prev[i])
            used_p.add(i); used_c.add(j)
    for i,t in enumerate(prev):
        if i not in used_p:
            t['age'] += 1
            result.append(t)
    for j,d in enumerate(curr):
        if j not in used_c:
            result.append({'pts':[(d['cx'],d['cy'])], 'd':d, 'hits':1, 'age':1})
    return result

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print("Failed to open video")
        return
    
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Video: {total} frames, {fps} fps")
    
    all_dets = []
    tracks = []
    frame_idx = 0
    saved_samples = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if MAX_FRAMES and frame_idx >= MAX_FRAMES * STRIDE:
            break
        
        if frame_idx % STRIDE != 0:
            frame_idx += 1
            continue
        
        fg = fg_mask(frame, BG_SUB)
        dets, mask = detect_in_frame(frame, fg)
        tracks = link_tracks(tracks, dets, MAX_LINK_DIST)
        
        # Save from tracks
        for t in tracks:
            if t['hits'] >= MIN_TRACK_HITS:
                d = t['d']
                all_dets.append({'frame':frame_idx,'cx':d['cx'],'cy':d['cy'],
                                 'diam':d['diam'],'area':d['area'],'circ':d['circ'],'sol':d['sol'],
                                 'track_hits':t['hits'],'track_age':t['age']})
        
        # Save visualization for promising tracks
        if saved_samples < 20:
            vis = frame.copy()
            # motion overlay
            mo = np.zeros_like(vis)
            mo[fg>0] = [255,255,255]
            vis = cv2.addWeighted(vis, 1.0, mo, 0.15, 0)
            # detections
            for d in dets:
                cv2.circle(vis, (int(d['cx']),int(d['cy'])), int(d['diam']/2), (0,255,0), 2)
            # tracks
            for t in tracks:
                if t['hits'] >= MIN_TRACK_HITS:
                    pts = np.array(t['pts'], dtype=np.int32)
                    if len(pts) >= 2:
                        cv2.polylines(vis, [pts], False, (0,255,255), 2)
            n_active = len([t for t in tracks if t['hits']>=MIN_TRACK_HITS])
            cv2.putText(vis, f"F:{frame_idx} {len(dets)}d {n_active}t",
                        (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
            cv2.imwrite(f"{VIS_DIR}/f{frame_idx:05d}.jpg", vis)
            saved_samples += 1
        
        if frame_idx % (STRIDE*20) == 0:
            n_tracks = len([t for t in tracks if t['hits']>=MIN_TRACK_HITS])
            print(f"Frame {frame_idx}/{total}: {len(dets)} dets, {n_tracks} active tracks")
        
        frame_idx += 1
    
    cap.release()
    
    # Save CSV
    if all_dets:
        with open(OUT_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['frame','cx','cy','diam','area','circ','sol','track_hits','track_age'])
            writer.writeheader()
            for d in all_dets:
                writer.writerow(d)
        print(f"\nSaved {len(all_dets)} detections to {OUT_CSV}")
    
    # Track summary
    good_tracks = [t for t in tracks if t['hits'] >= MIN_TRACK_HITS]
    print(f"\nFinished: {len(tracks)} total tracks, {len(good_tracks)} with >={MIN_TRACK_HITS} hits")
    for i,t in enumerate(good_tracks[:20]):
        start = t['pts'][0]
        end = t['pts'][-1]
        dist = np.sqrt((end[0]-start[0])**2+(end[1]-start[1])**2)
        print(f"  Track {i}: {t['hits']} hits, {t['pts'][0]} -> {t['pts'][-1]}, moved {dist:.0f}px")

if __name__ == "__main__":
    main()
