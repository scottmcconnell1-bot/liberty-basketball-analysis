#!/usr/bin/env python3
"""
Save motion detection visualizations from the middle of Q1 where tracks are most active.
"""

import cv2
import numpy as np
import os
import csv

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
VIS_DIR = "motion_vis_mid"
os.makedirs(VIS_DIR, exist_ok=True)

STRIDE = 2
# Save frames from the middle of the game
SAVE_START_FRAME = 200
SAVE_END_FRAME = 260

HUE_LOW = 0; HUE_HIGH = 25; SAT_MIN = 60; VAL_MIN = 60; VAL_MAX = 255

BG_SUB = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=False)
MAX_LINK_DIST = 80

cap = cv2.VideoCapture(VIDEO_PATH)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Video: {total} frames")

# First pass: run background subtractor through the video to SAVE_START_FRAME
# to get it warmed up
frame_idx = 0
fg_dummy = np.zeros((720, 1280), dtype=np.uint8)
while frame_idx < SAVE_START_FRAME:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % STRIDE == 0:
        BG_SUB.apply(frame)
    frame_idx += 1

# Now process frames SAVE_START_FRAME to SAVE_END_FRAME and save visualizations
tracks = []
saved = 0
while frame_idx < SAVE_END_FRAME:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % STRIDE != 0:
        frame_idx += 1
        continue
    
    fg = BG_SUB.apply(frame)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel, iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)
    fg = cv2.dilate(fg, kernel, iterations=1)
    
    # Detect
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cmask = cv2.inRange(hsv, np.array([HUE_LOW, SAT_MIN, VAL_MIN]),
                        np.array([HUE_HIGH, 255, VAL_MAX]))
    combined = cv2.bitwise_and(fg, cmask)
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    dets = []
    for c in contours:
        a = cv2.contourArea(c)
        if a < 20 or a > 5000: continue
        (x,y), r = cv2.minEnclosingCircle(c)
        d = 2*r
        if not (8 <= d <= 120): continue
        rx,ry,rw,rh = cv2.boundingRect(c)
        if rw==0 or rh==0: continue
        asp = rw/rh
        if not (0.4 <= asp <= 1.6): continue
        hull = cv2.convexHull(c)
        ha = cv2.contourArea(hull)
        if ha==0: continue
        sol = a/ha
        if sol < 0.3: continue
        M = cv2.moments(c)
        if M["m00"]==0: continue
        dets.append({'cx':M["m10"]/M["m00"], 'cy':M["m01"]/M["m00"],
                     'diam':d, 'area':a, 'sol':sol})
    
    # Link
    new_tracks = []
    if not tracks:
        for d in dets:
            new_tracks.append({'pts':[(d['cx'],d['cy'])],'d':d,'hits':1})
    else:
        cost = np.array([[np.sqrt((t['pts'][-1][0]-d['cx'])**2+(t['pts'][-1][1]-d['cy'])**2) for d in dets] for t in tracks])
        used_d = set()
        used_t = set()
        if cost.size > 0:
            flat = sorted([(cost[i,j],i,j) for i in range(cost.shape[0]) for j in range(cost.shape[1])])
            for c,i,j in flat:
                if i in used_t or j in used_d or c > MAX_LINK_DIST: continue
                tracks[i]['pts'].append((dets[j]['cx'],dets[j]['cy']))
                tracks[i]['d'] = dets[j]
                tracks[i]['hits'] += 1
                new_tracks.append(tracks[i])
                used_t.add(i); used_d.add(j)
        for i,t in enumerate(tracks):
            if i not in used_t:
                new_tracks.append(t)
        for j,d in enumerate(dets):
            if j not in used_d:
                new_tracks.append({'pts':[(d['cx'],d['cy'])],'d':d,'hits':1})
    tracks = new_tracks
    
    # Save visualization
    vis = frame.copy()
    mo = np.zeros_like(vis)
    mo[fg>0] = [255,255,255]
    vis = cv2.addWeighted(vis, 1.0, mo, 0.15, 0)
    
    for d in dets:
        cv2.circle(vis, (int(d['cx']),int(d['cy'])), int(d['diam']/2), (0,255,0), 2)
    
    for t in tracks:
        if t['hits'] >= 2:
            pts = np.array(t['pts'], dtype=np.int32)
            if len(pts) >= 2:
                cv2.polylines(vis, [pts], False, (0,255,255), 2)
    
    n_good = len([t for t in tracks if t['hits']>=2])
    cv2.putText(vis, f"F:{frame_idx} {len(dets)}d {n_good}t",
                        (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
    cv2.imwrite(f"{VIS_DIR}/f{frame_idx:05d}.jpg", vis)
    saved += 1
    
    frame_idx += 1

cap.release()
print(f"Saved {saved} frames to {VIS_DIR}")
print(f"Active tracks at end: {len(tracks)}")
for i,t in enumerate(tracks[:10]):
    d = t['d']
    print(f"  Track {i}: {t['hits']} hits, pos=({d['cx']:.0f},{d['cy']:.0f}), diam={d['diam']:.0f}px")
