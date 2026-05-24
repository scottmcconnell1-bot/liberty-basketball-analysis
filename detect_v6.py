#!/usr/bin/env python3
"""
Shot detection v6: Combine gesture + ball separation.
A real shot has:
1. Player's wrist moving rapidly upward (gesture)
2. Ball appearing/detecting near the wrist, then accelerating AWAY from the player
3. Ball trajectory is parabolic (in world coords)

This combines the best of both approaches.
"""

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import csv
import os

VIDEO_PATH = "uploads/Liberty_Vs_Riverstone_Q1.webm"
POSE_MODEL = "pose_landmarker.task"
BALL_CSV = "ball_v5_per_frame.csv"
OUT_CSV = "shots_v6.csv"
OUT_DIR = "v6_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2
MAX_FRAMES = None

# Color thresholds for ball detection
HUE_LOW=0; HUE_HIGH=25; SAT_MIN=60; VAL_MIN=60; VAL_MAX=255

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

def get_landmark(landmarks, idx):
    return np.array([landmarks[idx].x, landmarks[idx].y])

def main():
    # Load ball detections
    ball_dets = {}
    with open(BALL_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ball_dets[int(row['frame'])] = {
                'cx': float(row['cx']), 'cy': float(row['cy']), 'diam': float(row['diam'])
            }
    
    print(f"Ball detections: {len(ball_dets)} frames")

    cap = cv2.VideoCapture(VIDEO_PATH)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Background subtractor for ball detection on the fly
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=POSE_MODEL),
        running_mode=VisionRunningMode.IMAGE,
        num_poses=10,
        min_pose_detection_confidence=0.3,
        min_pose_presence_confidence=0.3,
        min_tracking_confidence=0.3
    )
    landmarker = PoseLandmarker.create_from_options(options)

    prev_frame_data = None
    frame_idx = 0
    shot_events = []
    bg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=False)
    
    # Warmup
    for _ in range(50):
        ret, f = cap.read()
        if not ret: break
        bg.apply(f)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    while True:
        ret, frame = cap.read()
        if not ret: break
        if MAX_FRAMES and frame_idx >= MAX_FRAMES: break
        if frame_idx % STRIDE != 0:
            frame_idx += 1; continue

        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect(mp_image)
        
        fg = bg.apply(frame)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel, iterations=1)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        # Get ball position for this frame
        ball = ball_dets.get(frame_idx, None)
        
        # Also detect ball on the fly (more reliable)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        cmask = cv2.inRange(hsv, np.array([HUE_LOW, SAT_MIN, VAL_MIN]),
                           np.array([HUE_HIGH, 255, VAL_MAX]))
        combined = cv2.bitwise_and(fg, cmask)
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best_ball = None
        for c in contours:
            a = cv2.contourArea(c)
            if a < 10 or a > 2000: continue
            (x,y), r = cv2.minEnclosingCircle(c)
            d = 2*r
            if not (7 <= d <= 40): continue
            circ = a / (np.pi * r * r) if r > 0 else 0
            if circ < 0.2: continue
            M = cv2.moments(c)
            if M["m00"] == 0: continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            if best_ball is None or circ > best_ball['circ']:
                best_ball = {'cx': cx, 'cy': cy, 'diam': d, 'circ': circ}
        
        # Process poses
        curr_poses = []
        if result.pose_landmarks:
            for pose in result.pose_landmarks:
                lw = get_landmark(pose, 15)
                rw = get_landmark(pose, 16)
                le = get_landmark(pose, 13)
                re = get_landmark(pose, 14)
                ls = get_landmark(pose, 11)
                rs = get_landmark(pose, 12)
                lh = get_landmark(pose, 23)
                rh = get_landmark(pose, 24)
                hip_c = (lh + rh) / 2
                
                curr_poses.append({
                    'hip': hip_c, 'lw': lw, 'rw': rw, 'le': le, 're': re,
                    'ls': ls, 'rs': rs
                })

        # Detect shot: gesture + ball separation
        if prev_frame_data and curr_poses:
            prev_poses = prev_frame_data['poses']
            prev_ball = prev_frame_data['ball']
            
            for pi, curr in enumerate(curr_poses):
                # Find same player in previous frame
                best_prev = None
                best_dist = float('inf')
                for pp in prev_poses:
                    d = np.linalg.norm(curr['hip'] - pp['hip'])
                    if d < best_dist:
                        best_dist = d; best_prev = pp
                
                if best_prev is None or best_dist > 0.15:
                    continue
                
                # Wrist movement for each hand
                for side in ['left', 'right']:
                    if side == 'left':
                        pw = best_prev['lw']; cw = curr['lw']
                        pe = best_prev['le']; ce = curr['le']; cs = curr['ls']
                    else:
                        pw = best_prev['rw']; cw = curr['rw']
                        pe = best_prev['re']; ce = curr['re']; cs = curr['rs']
                    
                    wrist_dy = cw[1] - pw[1]
                    wrist_speed = np.linalg.norm(cw - pw)
                    
                    # Is wrist rising fast?
                    rising_fast = wrist_dy < -0.02 and wrist_speed > 0.03
                    
                    # Is arm extended?
                    elbow_angle = angle_at_joint(cs, ce, cw)
                    arm_extended = elbow_angle > 140
                    
                    # Is ball near this wrist?
                    ball_near_wrist = False
                    ball_away = False
                    if best_ball:
                        wrist_px = np.array([cw[0] * w, cw[1] * h])
                        ball_px = np.array([best_ball['cx'], best_ball['cy']])
                        dist = np.linalg.norm(wrist_px - ball_px)
                        
                        if dist < 60:  # within 60px
                            ball_near_wrist = True
                        
                        # Check if ball is moving away from player
                        if prev_ball:
                            prev_ball_px = np.array([prev_ball['cx'], prev_ball['cy']])
                            prev_dist = np.linalg.norm(prev_ball_px - wrist_px)
                            curr_dist = np.linalg.norm(ball_px - wrist_px)
                            if curr_dist > prev_dist + 5 and dist > 30:
                                ball_away = True
                    
                    # Shot = rising wrist + arm extended + ball near wrist then separating
                    score = 0.0
                    if rising_fast: score += 0.25
                    if arm_extended: score += 0.2
                    if ball_near_wrist: score += 0.25
                    if ball_away: score += 0.3
                    
                    if score >= 0.5:
                        shot_events.append({
                            'frame': frame_idx,
                            'side': side,
                            'score': round(score, 2),
                            'wrist_y': round(cw[1], 3),
                            'elbow_angle': round(elbow_angle, 0),
                            'wrist_speed': round(wrist_speed, 3),
                            'ball_near': ball_near_wrist,
                            'ball_away': ball_away,
                            'player_x': round(curr['hip'][0], 3),
                            'player_y': round(curr['hip'][1], 3)
                        })

        prev_frame_data = {'poses': curr_poses, 'ball': best_ball}

        if frame_idx % (STRIDE * 200) == 0:
            print(f"F{frame_idx}: {len(curr_poses)} poses, ball={'yes' if best_ball else 'no'}, shots={len(shot_events)}")

        frame_idx += 1

    cap.release()
    landmarker.close()
    
    print(f"\nRaw shot events: {len(shot_events)}")
    print(f"Ball detected in {sum(1 for _ in ball_dets)} frames")
    
    # Cluster nearby frames
    shot_events.sort(key=lambda x: x['frame'])
    merged = []
    i = 0
    while i < len(shot_events):
        group = [shot_events[i]]
        j = i + 1
        while j < len(shot_events) and shot_events[j]['frame'] - group[-1]['frame'] < 20:
            group.append(shot_events[j]); j += 1
        best = max(group, key=lambda s: s['score'])
        merged.append(best)
        i = j
    
    print(f"\nMerged shots: {len(merged)}")
    for s in merged:
        print(f"  F{s['frame']:4d} score={s['score']:.2f} {s['side']:5s} "
              f"angle={s['elbow_angle']:3.0f}° speed={s['wrist_speed']:.3f} "
              f"ball_near={'Y' if s['ball_near'] else 'N'} away={'Y' if s['ball_away'] else 'N'}")
    
    with open(OUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['frame','side','score','wrist_y','elbow_angle','wrist_speed','ball_near','ball_away','player_x','player_y'])
        w.writeheader()
        for s in merged:
            w.writerow(s)
    print(f"Saved to {OUT_CSV}")

def angle_at_joint(a, b, c):
    ba = a - b; bc = c - b
    cos_a = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return np.degrees(np.arccos(np.clip(cos_a, -1, 1)))

if __name__ == "__main__":
    main()
