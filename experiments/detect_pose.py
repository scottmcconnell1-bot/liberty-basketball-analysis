#!/usr/bin/env python3
import cv2
import mediapipe as mp
import pandas as pd
import sys
import os

def main(video_path, output_csv, stride=1):
    # Initialize MediaPipe Pose Landmarker
    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    model_path = 'pose_landmarker.task'
    if not os.path.exists(model_path):
        print(f"Model {model_path} not found. Please ensure pose_landmarker.task is in the current directory.")
        return

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.VIDEO,
        num_poses=1)
    
    with PoseLandmarker.create_from_options(options) as landmarker:
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
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            # Detect pose landmarks
            pose_landmarker_result = landmarker.detect_for_video(mp_image, int(frame_idx * 1000 / fps))
            # Initialize defaults
            left_ankle = {'x': None, 'y': None, 'visibility': 0.0}
            right_ankle = {'x': None, 'y': None, 'visibility': 0.0}
            signal = 0  # none
            if pose_landmarker_result.pose_landmarks:
                # Take the first pose (assuming one person)
                lm = pose_landmarker_result.pose_landmarks[0]
                # Indices: left ankle=27, right ankle=28, left shoulder=11, right shoulder=12, left wrist=15, right wrist=16
                left_ankle_lm = lm[27]
                right_ankle_lm = lm[28]
                left_shoulder = lm[11]
                right_shoulder = lm[12]
                left_wrist = lm[15]
                right_wrist = lm[16]
                # Ankle visibility
                if left_ankle_lm.visibility > 0.5:
                    left_ankle = {'x': left_ankle_lm.x, 'y': left_ankle_lm.y, 'visibility': left_ankle_lm.visibility}
                if right_ankle_lm.visibility > 0.5:
                    right_ankle = {'x': right_ankle_lm.x, 'y': right_ankle_lm.y, 'visibility': right_ankle_lm.visibility}
                # Hand raise detection (same as before)
                if (left_shoulder.visibility > 0.5 and left_wrist.visibility > 0.5 and
                    right_shoulder.visibility > 0.5 and right_wrist.visibility > 0.5):
                    left_raised = left_wrist.y < left_shoulder.y
                    right_raised = right_wrist.y < right_shoulder.y
                    if left_raised and right_raised:
                        signal = 2  # both hands
                    elif left_raised or right_raised:
                        signal = 1  # one hand
                    else:
                        signal = 0
            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            results.append({
                'frame': frame_idx,
                'timestamp_ms': timestamp_ms,
                'left_ankle_x': left_ankle['x'],
                'left_ankle_y': left_ankle['y'],
                'left_ankle_visibility': left_ankle['visibility'],
                'right_ankle_x': right_ankle['x'],
                'right_ankle_y': right_ankle['y'],
                'right_ankle_visibility': right_ankle['visibility'],
                'signal': signal
            })
            frame_idx += 1
            if frame_idx % 100 == 0:
                print(f"Processed {frame_idx}/{frame_count} frames")
        cap.release()
        df = pd.DataFrame(results)
        df.to_csv(output_csv, index=False)
        print(f"Saved pose detection results to {output_csv}")
        # Summary
        print(f"Frames with left ankle visible: {df['left_ankle_visibility'].gt(0).sum()}")
        print(f"Frames with right ankle visible: {df['right_ankle_visibility'].gt(0).sum()}")
        print(f"Signal counts: {df['signal'].value_counts().to_dict()}")

if __name__ == '__main__':
    video_path = sys.argv[1] if len(sys.argv) > 1 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
    output_csv = sys.argv[2] if len(sys.argv) > 2 else '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pose_keypoints.csv'
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    main(video_path, output_csv, stride)