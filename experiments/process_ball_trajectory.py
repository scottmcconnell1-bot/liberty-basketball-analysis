#!/usr/bin/env python3
import cv2
from ultralytics import YOLO
import numpy as np
import json
import csv
import os

def main():
    video_path = "uploads/Liberty_Vs_Riverstone_Q1.webm"
    hoop_params_path = "hoop_params.json"
    output_csv = "ball_shots.csv"

    # Load hoop parameters
    with open(hoop_params_path, 'r') as f:
        hoop_params = json.load(f)
    hoop_center_px = tuple(hoop_params["hoop_center_px"])  # (x, y)
    hoop_radius_px = hoop_params["hoop_radius_px"]
    scale_ft_per_px = hoop_params["scale_ft_per_px"]

    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video: {fps} fps, {total_frames} frames, {width}x{height}")

    # Load YOLO model (use nano for speed)
    model = YOLO("yolov8n.pt")
    # We'll use class 32 for sports ball (COCO)
    ball_class_id = 32
    conf_threshold = 0.2  # increased confidence

    # Storage for raw detections per frame
    raw_x = [np.nan] * total_frames
    raw_y = [np.nan] * total_frames
    raw_conf = [0.0] * total_frames

    print("Processing frames for ball detection (every 5th frame)...")
    for frame_idx in range(0, total_frames, 5):
        ret, frame = cap.read()
        if not ret:
            print(f"Warning: Failed to read frame {frame_idx}")
            break
        # Run YOLO detection
        results = model(frame, classes=[ball_class_id], conf=conf_threshold, verbose=False)
        detections = []
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                if class_id == ball_class_id:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    # Clamp to frame bounds
                    x1 = max(0, min(x1, width - 1))
                    y1 = max(0, min(y1, height - 1))
                    x2 = max(0, min(x2, width - 1))
                    y2 = max(0, min(y2, height - 1))
                    w_box, h_box = x2 - x1, y2 - y1
                    if 8 < w_box < 80 and 8 < h_box < 80 and 0.3 < w_box / max(h_box, 1) < 3.0:
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        detections.append((cx, cy, conf, x1, y1, x2, y2))
        # Choose detection with highest confidence
        if detections:
            best = max(detections, key=lambda d: d[2])
            cx, cy, conf, _, _, _, _ = best
            raw_x[frame_idx] = cx
            raw_y[frame_idx] = cy
            raw_conf[frame_idx] = conf
        # For frames we skipped, we leave as NaN (will be interpolated later)
        if frame_idx % 50 == 0:
            print(f"  Processed frame {frame_idx}/{total_frames}")

    cap.release()
    print("Detection complete.")

    # Interpolate missing values (linear interpolation)
    def interpolate_nan(arr):
        arr = np.array(arr, dtype=float)
        if np.all(np.isnan(arr)):
            return arr
        # Create indices where we have values
        good = ~np.isnan(arr)
        if not np.any(good):
            return arr
        # Interpolate
        interp = np.interp(x=np.arange(len(arr)), xp=np.where(good)[0], fp=arr[good])
        return interp

    interp_x = interpolate_nan(raw_x)
    interp_y = interpolate_nan(raw_y)

    # Smooth using moving average window 5
    def moving_average(arr, window=5):
        return np.convolve(arr, np.ones(window)/window, mode='same')

    smooth_x = moving_average(interp_x, window=5)
    smooth_y = moving_average(interp_y, window=5)

    # Convert to feet
    smooth_x_ft = smooth_x * scale_ft_per_px
    smooth_y_ft = smooth_y * scale_ft_per_px

    # Compute derivative of smooth_y (velocity in px per frame)
    dy = np.gradient(smooth_y)  # using central differences
    # Detect peaks: where dy changes from positive to negative
    # We'll look for sign change from >0 to <0
    peaks = []
    for i in range(1, len(dy)-1):
        if dy[i-1] > 0 and dy[i] < 0:
            # Potential peak at i
            peaks.append(i)

    # Filter peaks where ball is above the rim (ball_y_px < hoop_y_px - hoop_radius_px)
    hoop_y_px = hoop_center_px[1]
    rim_y_px = hoop_y_px - hoop_radius_px
    attempt_frames = []
    for peak_idx in peaks:
        if smooth_y[peak_idx] < rim_y_px:
            attempt_frames.append(peak_idx)

    # Assign attempt IDs
    attempt_id_per_frame = [0] * total_frames
    for attempt_id, frame_idx in enumerate(attempt_frames, start=1):
        attempt_id_per_frame[frame_idx] = attempt_id

    # Prepare CSV output
    print(f"Detected {len(attempt_frames)} shot attempts.")
    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["attempt_id", "frame", "timestamp_ms", "ball_x_px", "ball_y_px", "ball_x_ft", "ball_y_ft", "is_attempt"])
        for frame_idx in range(total_frames):
            timestamp_ms = (frame_idx / fps) * 1000 if fps > 0 else 0
            is_attempt = (attempt_id_per_frame[frame_idx] > 0)
            writer.writerow([
                attempt_id_per_frame[frame_idx],
                frame_idx,
                round(timestamp_ms, 2),
                round(smooth_x[frame_idx], 2),
                round(smooth_y[frame_idx], 2),
                round(smooth_x_ft[frame_idx], 4),
                round(smooth_y_ft[frame_idx], 4),
                is_attempt
            ])

    print(f"Output written to {output_csv}")

if __name__ == "__main__":
    main()