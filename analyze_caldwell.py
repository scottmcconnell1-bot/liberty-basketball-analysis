#!/usr/bin/env python3
"""
Extract frames from Caldwell game video for analysis.
Uses the remote YOLO API at 192.168.1.60:5555 for ball detection.
"""
import cv2
import numpy as np
import os
import json
import subprocess
import sys
import requests
from datetime import datetime

VIDEO_PATH = "/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_gamfad8d650d0.mp4"
OUTPUT_BASE = "/home/monk-admin/PROJECTS/liberty-basketball-analysis/analysis/caldwell"
FRAMES_DIR = os.path.join(OUTPUT_BASE, "frames")
DETECTIONS_DIR = os.path.join(OUTPUT_BASE, "detections")
YOLO_API = "http://192.168.1.60:5555"

os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(DETECTIONS_DIR, exist_ok=True)

# === STEP 1: Get video info ===
print("=== STEP 1: Video info ===")
probe = subprocess.run(
    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', '-show_format', VIDEO_PATH],
    capture_output=True, text=True)
info = json.loads(probe.stdout)
video_stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
duration = float(info['format']['duration'])
fps = eval(video_stream['r_frame_rate'])
width = int(video_stream['width'])
height = int(video_stream['height'])
total_frames = int(duration * fps)

print(f"  Resolution: {width}x{height}")
print(f"  FPS: {fps}")
print(f"  Duration: {duration:.1f}s ({duration/60:.1f} min)")
print(f"  Total frames: {total_frames}")
print(f"  File size: {os.path.getsize(VIDEO_PATH)/1024/1024/1024:.2f} GB")

# === STEP 2: Extract sample frames every N seconds ===
print(f"\n=== STEP 2: Extracting sample frames ===")
SAMPLE_INTERVAL = 10  # every 10 seconds
cap = cv2.VideoCapture(VIDEO_PATH)
frame_count = 0
extracted = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    timestamp = frame_count / fps
    if timestamp % SAMPLE_INTERVAL < (1.0 / fps):
        frame_name = f"frame_{timestamp:06.1f}s.jpg"
        cv2.imwrite(os.path.join(FRAMES_DIR, frame_name), frame)
        extracted += 1
    frame_count += 1

cap.release()
print(f"  Extracted {extracted} frames (every {SAMPLE_INTERVAL}s)")

# === STEP 3: Run ball detection via YOLO API ===
print(f"\n=== STEP 3: Running ball detection ===")
session = requests.Session()
all_detections = []

frame_files = sorted(os.listdir(FRAMES_DIR))
for i, fname in enumerate(frame_files):
    fpath = os.path.join(FRAMES_DIR, fname)
    with open(fpath, 'rb') as f:
        resp = session.post(
            f"{YOLO_API}/predict?model=ball_detector&conf=0.25",
            files={'image': f},
            timeout=30
        )
    if resp.status_code == 200:
        result = resp.json()
        detections = result.get('detections', [])
        if detections:
            all_detections.append({
                'frame': fname,
                'timestamp': float(fname.replace('frame_', '').replace('s.jpg', '')),
                'detections': detections
            })
            print(f"  {fname}: {len(detections)} detections")
    
    if (i + 1) % 50 == 0:
        print(f"  Progress: {i+1}/{len(frame_files)}")

# Save detections
with open(os.path.join(DETECTIONS_DIR, 'ball_detections.json'), 'w') as f:
    json.dump(all_detections, f, indent=2)

print(f"\n  Total frames with detections: {len(all_detections)}")
print(f"  Total detections: {sum(len(d['detections']) for d in all_detections)}")

# === STEP 4: Generate detection summary ===
print(f"\n=== STEP 4: Summary ===")
if all_detections:
    confs = [d['confidence'] for det in all_detections for d in det['detections']]
    print(f"  Confidence range: {min(confs):.3f} - {max(confs):.3f}")
    print(f"  Mean confidence: {sum(confs)/len(confs):.3f}")
    
    # Timeline
    print(f"\n  Detection timeline:")
    for det in all_detections[:20]:
        ts = det['timestamp']
        n = len(det['detections'])
        best_conf = max(d['confidence'] for d in det['detections'])
        print(f"    {ts:6.1f}s: {n} detections (best conf: {best_conf:.3f})")
    if len(all_detections) > 20:
        print(f"    ... and {len(all_detections)-20} more frames")

print("\n=== DONE ===")
