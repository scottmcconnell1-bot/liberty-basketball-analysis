#!/usr/bin/env python3
"""
Shot detection via player shooting gesture using MediaPipe Pose Landmarker task.
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
OUT_CSV = "shots_gesture.csv"
OUT_DIR = "gesture_vis"
os.makedirs(OUT_DIR, exist_ok=True)

STRIDE = 2

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

def get_landmark(landmarks, idx):
    lm = landmarks[idx]
    return np.array([lm.x, lm.y])

def angle_at_joint(a, b, c):
    ba = a - b
    bc = c - b
    cos_a = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_a = np.clip(cos_a, -1, 1)
    return np.degrees(np.arccos(cos_a))

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {total} frames")

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=POSE_MODEL),
        running_mode=VisionRunningMode.IMAGE,
        num_poses=10,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )

    landmarker = PoseLandmarker.create_from_options(options)

    prev_frame_poses = None  # list of (hip_center, left_wrist, right_wrist, left_elbow, right_elbow, left_shoulder, right_shoulder)
    frame_idx = 0
    shot_events = []
    all_poses_log = []

    while True:
        ret, frame = cap.read()
        if not ret: break
        if frame_idx % STRIDE != 0:
            frame_idx += 1; continue

        h, w, _ = frame.shape
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = landmarker.detect(mp_image)

        curr_poses = []

        if result.pose_landmarks:
            for pose_landmarks in result.pose_landmarks:
                lw = get_landmark(pose_landmarks, 15)  # LEFT_WRIST
                rw = get_landmark(pose_landmarks, 16)  # RIGHT_WRIST
                le = get_landmark(pose_landmarks, 13)  # LEFT_ELBOW
                re = get_landmark(pose_landmarks, 14)  # RIGHT_ELBOW
                ls = get_landmark(pose_landmarks, 11)  # LEFT_SHOULDER
                rs = get_landmark(pose_landmarks, 12)  # RIGHT_SHOULDER
                lh = get_landmark(pose_landmarks, 23)  # LEFT_HIP
                rh = get_landmark(pose_landmarks, 24)  # RIGHT_HIP
                hip_c = (lh + rh) / 2

                curr_poses.append({
                    'hip': hip_c, 'lw': lw, 'rw': rw, 'le': le, 're': re,
                    'ls': ls, 'rs': rs, 'lh': lh, 'rh': rh
                })

        # Detect shooting gestures
        if prev_frame_poses and curr_poses:
            for curr in curr_poses:
                # Find closest previous pose (same player)
                best_prev = None
                best_dist = float('inf')
                for prev in prev_frame_poses:
                    d = np.linalg.norm(curr['hip'] - prev['hip'])
                    if d < best_dist:
                        best_dist = d
                        best_prev = prev

                if best_prev is None or best_dist > 0.15:
                    continue

                for side in ['left', 'right']:
                    if side == 'left':
                        pw = best_prev['lw']
                        cw = curr['lw']
                        pe = best_prev['le']
                        ce = curr['le']
                        cs = curr['ls']
                    else:
                        pw = best_prev['rw']
                        cw = curr['rw']
                        pe = best_prev['re']
                        ce = curr['re']
                        cs = curr['rs']

                    # Wrist velocity (upward = negative Y)
                    wrist_dy = cw[1] - pw[1]
                    wrist_speed = abs(cw[1] - pw[1]) + abs(cw[0] - pw[0])

                    # Wrist above shoulder
                    wrist_above = cw[1] < cs[1] - 0.03

                    # Elbow angle
                    ea = angle_at_joint(cs, ce, cw)

                    # Arm height relative to body
                    body_h = curr['lh'][1] - curr['hip'][1]
                    arm_h = (curr['hip'][1] - cw[1]) / (abs(body_h) + 1e-8)

                    score = 0.0
                    if wrist_dy < -0.01: score += 0.15
                    if wrist_dy < -0.03: score += 0.15
                    if wrist_above: score += 0.2
                    if ea > 150: score += 0.2
                    elif ea > 120: score += 0.1
                    if arm_h > 1.2: score += 0.2
                    elif arm_h > 0.8: score += 0.1

                    if score >= 0.4:
                        shot_events.append({
                            'frame': frame_idx,
                            'side': side,
                            'score': round(score, 2),
                            'elbow_angle': round(ea, 0),
                            'arm_height': round(arm_h, 2),
                            'wrist_dy': round(wrist_dy, 4),
                            'player_x': round(curr['hip'][0], 3),
                            'player_y': round(curr['hip'][1], 3)
                        })

        prev_frame_poses = curr_poses
        all_poses_log.append((frame_idx, len(curr_poses)))

        if frame_idx % (STRIDE * 200) == 0:
            n_p = len(curr_poses)
            print(f"Frame {frame_idx}: {n_p} poses, {len(shot_events)} shot events")

        frame_idx += 1

    cap.release()
    landmarker.close()

    print(f"\nPoses detected: {sum(n for _, n in all_poses_log)} total across frames")
    print(f"Raw shot gesture events: {len(shot_events)}")

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

    print(f"After merge: {len(merged)} distinct shots")
    for s in merged:
        print(f"  F{s['frame']:4d} score={s['score']:.2f} {s['side']:5s} "
              f"elbow={s['elbow_angle']:3.0f}° arm_h={s['arm_height']:.1f} "
              f"wrist_dy={s['wrist_dy']:+.4f} pos=({s['player_x']:.2f},{s['player_y']:.2f})")

    with open(OUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['frame','side','score','elbow_angle','arm_height','wrist_dy','player_x','player_y'])
        w.writeheader()
        for s in merged:
            w.writerow(s)
    print(f"\nSaved to {OUT_CSV}")

if __name__ == "__main__":
    main()
