#!/usr/bin/env python3
import cv2
import mediapipe as mp
import pandas as pd
import sys
import os

def main(video_path, output_csv, stride=1):
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(static_image_mode=False,
                        model_complexity=1,
                        smooth_landmarks=True,
                        enable_segmentation=False,
                        min_detection_confidence=0.5,
                        min_tracking_confidence=0.5)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {frame_count} frames @ {fps:.2f} fps")
    results = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        # Convert BGR to RGB
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Process pose
        pose_results = pose.process(image_rgb)
        signal = 0  # none
        if pose_results.pose_landmarks:
            lm = pose_results.pose_landmarks.landmark
            # Get landmarks (normalized coordinates)
            left_shoulder = lm[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_wrist = lm[mp_pose.PoseLandmark.LEFT_WRIST]
            right_wrist = lm[mp_pose.PoseLandmark.RIGHT_WRIST]
            # Check visibility
            if left_shoulder.visibility > 0.5 and left_wrist.visibility > 0.5 and \
               right_shoulder.visibility > 0.5 and right_wrist.visibility > 0.5:
                left_raised = left_wrist.y < left_shoulder.y
                right_raised = right_wrist.y < right_shoulder.y
                if left_raised and right_raised:
                    signal = 2  # both hands
                elif left_raised or right_raised:
                    signal = 1  # one hand
                else:
                    signal = 0
            # else not enough visibility => treat as none
        timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        results.append({
            'frame': frame_idx,
            'timestamp_ms': timestamp_ms,
            'signal': signal
        })
        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"Processed {frame_idx}/{frame_count} frames")
    cap.close()
    pose.close()
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False)
    print(f"Saved detection results to {output_csv}")
    # Summary
    counts = df['signal'].value_counts().sort_index()
    print("Signal counts:")
    print(f"  None (0): {counts.get(0,0)}")
    print(f"  One hand (1): {counts.get(1,0)}")
    print(f"  Both hands (2): {counts.get(2,0)}")

if __name__ == '__main__':
    video_path = sys.argv[1] if len(sys.argv) > 1 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
    output_csv = sys.argv[2] if len(sys.argv) > 2 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/referee_signal_detection.csv'
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    main(video_path, output_csv, stride)