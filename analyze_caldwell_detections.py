#!/usr/bin/env python3
"""
Basketball Evidence Protocol V1 — Ball Detection Analysis
Model: /home/myaccount/yolo-models/20045b81_best.pt (via remote API)
Input: videos/nfhs_gamfad8d650d0.mp4
"""
import cv2
import numpy as np
import os
import json
import requests
import time
from datetime import datetime

# === CONFIG ===
VIDEO_PATH = "/home/monk-admin/PROJECTS/liberty-basketball-analysis/videos/nfhs_gamfad8d650d0.mp4"
OUTPUT_BASE = "/home/monk-admin/PROJECTS/liberty-basketball-analysis/analysis/caldwell"
FRAMES_DIR = os.path.join(OUTPUT_BASE, "frames")
ANNOTATED_DIR = os.path.join(OUTPUT_BASE, "annotated")
CONTACT_SHEET_DIR = os.path.join(OUTPUT_BASE, "contact_sheets")
YOLO_API = "http://192.168.1.60:5555"
MODEL_NAME = "20045b81_best"
CONF_THRESH = 0.25
SAMPLE_INTERVAL = 2  # seconds

os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(ANNOTATED_DIR, exist_ok=True)
os.makedirs(CONTACT_SHEET_DIR, exist_ok=True)

# === STEP 1: Sample frames ===
print("=== STEP 1: Sampling frames ===")
cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / fps

print(f"  Video: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
print(f"  FPS: {fps}")
print(f"  Total frames: {total_frames}")
print(f"  Duration: {duration:.1f}s ({duration/60:.1f} min)")

frame_indices = list(range(0, total_frames, int(fps * SAMPLE_INTERVAL)))
print(f"  Sampling 1 frame every {SAMPLE_INTERVAL}s = {len(frame_indices)} frames")

sampled = []
for i, frame_idx in enumerate(frame_indices):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        break
    timestamp = frame_idx / fps
    fname = f"frame_{timestamp:07.2f}s.jpg"
    cv2.imwrite(os.path.join(FRAMES_DIR, fname), frame)
    sampled.append((fname, frame_idx, timestamp))
    if (i + 1) % 100 == 0:
        print(f"  Extracted {i+1}/{len(frame_indices)}")

cap.release()
print(f"  Total extracted: {len(sampled)}")

# === STEP 2: Run ball detection via YOLO API ===
print(f"\n=== STEP 2: Running ball detection (conf={CONF_THRESH}) ===")
session = requests.Session()

all_results = []  # (fname, timestamp, detections)
frames_with_dets = 0
total_dets = 0

for i, (fname, frame_idx, timestamp) in enumerate(sampled):
    fpath = os.path.join(FRAMES_DIR, fname)
    with open(fpath, 'rb') as f:
        try:
            resp = session.post(
                f"{YOLO_API}/predict?model={MODEL_NAME}&conf={CONF_THRESH}",
                files={'image': f},
                timeout=30
            )
        except requests.RequestException as e:
            print(f"  ERROR {fname}: {e}")
            continue

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code} for {fname}")
        continue

    data = resp.json()
    detections = data.get('detections', [])

    if detections:
        frames_with_dets += 1
        total_dets += len(detections)
        all_results.append((fname, timestamp, detections))

    if (i + 1) % 100 == 0:
        print(f"  Processed {i+1}/{len(sampled)}, {frames_with_dets} frames with detections so far")

print(f"  Total frames with detections: {frames_with_dets}/{len(sampled)}")
print(f"  Total detections: {total_dets}")

# === STEP 3: Save annotated frames ===
print(f"\n=== STEP 3: Saving annotated frames ===")
GREEN = (0, 255, 0)
RED = (0, 0, 255)
WHITE = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

for fname, timestamp, detections in all_results:
    img = cv2.imread(os.path.join(FRAMES_DIR, fname))
    h, w = img.shape[:2]

    for det in detections:
        cx, cy, bw, bh = det['cx'], det['cy'], det['w'], det['h']
        conf = det['confidence']
        x1 = int((cx - bw/2) * w)
        y1 = int((cy - bh/2) * h)
        x2 = int((cx + bw/2) * w)
        y2 = int((cy + bh/2) * h)
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(w, x2); y2 = min(h, y2)

        color = GREEN if conf >= 0.5 else RED
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"ball {conf:.2f}"
        cv2.putText(img, label, (x1, max(y1 - 10, 15)), FONT, 0.5, color, 1)

    cv2.imwrite(os.path.join(ANNOTATED_DIR, fname), img)

print(f"  Saved {len(all_results)} annotated frames")

# === STEP 4: Generate contact sheets ===
print(f"\n=== STEP 4: Generating contact sheets ===")

# Sort by confidence
all_results_sorted = sorted(all_results, key=lambda x: max(d['confidence'] for d in x[2]))

# 100-frame contact sheet (all detections, chronological)
contact_100 = all_results[:100] if len(all_results) >= 100 else all_results
cols, rows = 10, 10
thumb_w, thumb_h = 192, 108
grid = np.zeros((rows * thumb_h, cols * thumb_w, 3), dtype=np.uint8)

for idx, (fname, timestamp, detections) in enumerate(contact_100):
    row = idx // cols
    col = idx % cols
    img = cv2.imread(os.path.join(ANNOTATED_DIR, fname))
    thumb = cv2.resize(img, (thumb_w, thumb_h))
    best_conf = max(d['confidence'] for d in detections)
    cv2.putText(thumb, f"{best_conf:.2f}", (5, 15), FONT, 0.4, WHITE, 1)
    grid[row*thumb_h:(row+1)*thumb_h, col*thumb_w:(col+1)*thumb_w] = thumb

cv2.imwrite(os.path.join(CONTACT_SHEET_DIR, "contact_sheet_100.jpg"), grid)
print(f"  100-frame contact sheet: {len(contact_100)} frames")

# 25 highest-confidence detections
top25 = all_results_sorted[-25:][::-1]  # highest first
grid25 = np.zeros((5 * thumb_h, 5 * thumb_w, 3), dtype=np.uint8)
for idx, (fname, timestamp, detections) in enumerate(top25):
    row = idx // 5
    col = idx % 5
    img = cv2.imread(os.path.join(ANNOTATED_DIR, fname))
    thumb = cv2.resize(img, (thumb_w, thumb_h))
    best_conf = max(d['confidence'] for d in detections)
    cv2.putText(thumb, f"{best_conf:.2f}", (5, 15), FONT, 0.4, GREEN, 1)
    cv2.putText(thumb, f"{timestamp:.0f}s", (5, thumb_h-5), FONT, 0.3, WHITE, 1)
    grid25[row*thumb_h:(row+1)*thumb_h, col*thumb_w:(col+1)*thumb_w] = thumb

cv2.imwrite(os.path.join(CONTACT_SHEET_DIR, "top25_confidence.jpg"), grid25)
print(f"  Top 25 confidence sheet: {len(top25)} frames")

# 25 lowest-confidence detections
bot25 = all_results_sorted[:25]  # lowest first
grid_bot = np.zeros((5 * thumb_h, 5 * thumb_w, 3), dtype=np.uint8)
for idx, (fname, timestamp, detections) in enumerate(bot25):
    row = idx // 5
    col = idx % 5
    img = cv2.imread(os.path.join(ANNOTATED_DIR, fname))
    thumb = cv2.resize(img, (thumb_w, thumb_h))
    best_conf = max(d['confidence'] for d in detections)
    cv2.putText(thumb, f"{best_conf:.2f}", (5, 15), FONT, 0.4, RED, 1)
    cv2.putText(thumb, f"{timestamp:.0f}s", (5, thumb_h-5), FONT, 0.3, WHITE, 1)
    grid_bot[row*thumb_h:(row+1)*thumb_h, col*thumb_w:(col+1)*thumb_w] = thumb

cv2.imwrite(os.path.join(CONTACT_SHEET_DIR, "bottom25_confidence.jpg"), grid_bot)
print(f"  Bottom 25 confidence sheet: {len(bot25)} frames")

# === STEP 5: Report ===
print(f"\n=== REPORT ===")
print(f"  Frames processed:     {len(sampled)}")
print(f"  Frames with detections: {frames_with_dets}")
print(f"  Total detections:     {total_dets}")

if all_results:
    all_confs = [d['confidence'] for _, _, dets in all_results for d in dets]
    print(f"  Average confidence:   {sum(all_confs)/len(all_confs):.4f}")
    print(f"  Highest confidence:   {max(all_confs):.4f}")
    print(f"  Lowest confidence:    {min(all_confs):.4f}")

    # Find highest/lowest single detection
    highest = max(all_results, key=lambda x: max(d['confidence'] for d in x[2]))
    lowest = min(all_results, key=lambda x: max(d['confidence'] for d in x[2]))
    high_conf = max(d['confidence'] for d in highest[2])
    low_conf = max(d['confidence'] for d in lowest[2])

    print(f"\n  Highest confidence detection:")
    print(f"    Frame: {highest[0]} (t={highest[1]:.1f}s)")
    print(f"    Confidence: {high_conf:.4f}")
    for d in highest[2]:
        print(f"    Box: cx={d['cx']:.4f} cy={d['cy']:.4f} w={d['w']:.4f} h={d['h']:.4f} conf={d['confidence']:.4f}")

    print(f"\n  Lowest confidence detection:")
    print(f"    Frame: {lowest[0]} (t={lowest[1]:.1f}s)")
    print(f"    Confidence: {low_conf:.4f}")
    for d in lowest[2]:
        print(f"    Box: cx={d['cx']:.4f} cy={d['cy']:.4f} w={d['w']:.4f} h={d['h']:.4f} conf={d['confidence']:.4f}")

# Save full results
with open(os.path.join(OUTPUT_BASE, "detection_results.json"), 'w') as f:
    json.dump({
        'model': MODEL_NAME,
        'conf_threshold': CONF_THRESH,
        'frames_processed': len(sampled),
        'frames_with_detections': frames_with_dets,
        'total_detections': total_dets,
        'results': [{'frame': fname, 'timestamp': ts, 'detections': dets} for fname, ts, dets in all_results]
    }, f, indent=2)

print(f"\n  Results saved to: {OUTPUT_BASE}/detection_results.json")
print(f"  Annotated frames: {ANNOTATED_DIR}/")
print(f"  Contact sheets: {CONTACT_SHEET_DIR}/")
print("\n=== DONE ===")
