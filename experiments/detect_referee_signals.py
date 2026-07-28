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

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path='pose_landmarker.task'),
        running_mode=VisionRunningMode.IMAGE,
        num_poses=1)
    
    # Note: We need to download the pose_landmarker.task model.
    # If not present, we can use a fallback or download it.
    # For simplicity, we assume the model is in the current directory.
    # If not, we'll try to load from a default location.
    model_path = 'pose_landmarker.task'
    if not os.path.exists(model_path):
        # Try to look in the current directory or subdirs
        import urllib.request
        import zipfile
        print(f"Model {model_path} not found. Attempting to download...")
        # Download from MediaPipe's official release
        model_url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
        try:
            urllib.request.urlretrieve(model_url, model_path)
            print(f"Downloaded model to {model_path}")
        except Exception as e:
            print(f"Failed to download model: {e}")
            print("Please ensure pose_landmarker.task is available in the current directory.")
            return

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
            # Convert to MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            # Detect pose landmarks
            pose_landmarker_result = landmarker.detect(mp_image)
            signal = 0  # none
            if pose_landmarker_result.pose_landmarks:
                # Take the first pose (assuming one person)
                lm = pose_landmarker_result.pose_landmarks[0]
                # Get landmarks (normalized coordinates)
                # Indices: left shoulder=11, right shoulder=12, left wrist=15, right wrist=16
                left_shoulder = lm[11]
                right_shoulder = lm[12]
                left_wrist = lm[15]
                right_wrist = lm[16]
                # Check visibility
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
        cap.release()
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