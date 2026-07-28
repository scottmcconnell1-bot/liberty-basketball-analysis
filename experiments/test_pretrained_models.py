"""
Test the pretrained abdullahtarek models on Liberty Q1 video.
Step 1: Run ball detector, court keypoint detector, and player detector on sample frames.
Step 2: Visualize results to verify quality.
Step 3: If good, run full pipeline.
"""
import cv2
import numpy as np
import os
import csv
from ultralytics import YOLO

VIDEO_PATH = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
MODELS_DIR = 'models'
OUTPUT_DIR = 'pretrained_test_output'
SAMPLE_FRAMES = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1500, 1800, 2100, 2400, 2700]

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load models
print("Loading models...")
ball_model = YOLO(f'{MODELS_DIR}/ball_detector.pt')
court_model = YOLO(f'{MODELS_DIR}/court_keypoint_detector.pt')
player_model = YOLO(f'{MODELS_DIR}/player_detector.pt')
print("Models loaded.")

# Read video
cap = cv2.VideoCapture(VIDEO_PATH)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Video: {W}x{H}, {total_frames} frames, {fps} fps")

# Extract sample frames
frames = {}
for fn in SAMPLE_FRAMES:
    if fn >= total_frames:
        continue
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if ret:
        frames[fn] = frame
cap.release()
print(f"Extracted {len(frames)} sample frames")

# Run ball detector on sample frames
print("\n=== BALL DETECTOR ===")
ball_results = {}
for fn, frame in frames.items():
    results = ball_model.predict(frame, conf=0.3, verbose=False)
    dets = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = ball_model.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            dets.append({'cls': cls_name, 'conf': conf, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
    ball_results[fn] = dets
    balls = [d for d in dets if d['cls'] == 'Ball']
    hoops = [d for d in dets if d['cls'] == 'Hoop']
    players = [d for d in dets if d['cls'] == 'Player']
    print(f"  Frame {fn}: {len(dets)} dets - Ball:{len(balls)} Hoop:{len(hoops)} Player:{len(players)}")

# Run court keypoint detector on sample frames
print("\n=== COURT KEYPOINT DETECTOR ===")
court_results = {}
for fn, frame in frames.items():
    results = court_model.predict(frame, conf=0.3, verbose=False)
    keypoints_list = []
    for r in results:
        if r.keypoints is not None:
            kps = r.keypoints.xy.cpu().numpy()  # (N, K, 2)
            confs = r.keypoints.conf.cpu().numpy()  # (N, K)
            keypoints_list.append({'xy': kps, 'conf': confs})
    court_results[fn] = keypoints_list
    n_insts = len(keypoints_list)
    if n_insts > 0:
        n_kps = keypoints_list[0]['xy'].shape[1] if len(keypoints_list[0]['xy']) > 0 else 0
        print(f"  Frame {fn}: {n_insts} court detections, {n_kps} keypoints each")
    else:
        print(f"  Frame {fn}: No court keypoints detected")

# Run player detector on sample frames
print("\n=== PLAYER DETECTOR ===")
player_results = {}
for fn, frame in frames.items():
    results = player_model.predict(frame, conf=0.3, verbose=False)
    dets = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = player_model.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            dets.append({'cls': cls_name, 'conf': conf, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
    player_results[fn] = dets
    players = [d for d in dets if d['cls'] == 'Player']
    balls = [d for d in dets if d['cls'] == 'Ball']
    refs = [d for d in dets if d['cls'] == 'Ref']
    print(f"  Frame {fn}: {len(dets)} dets - Player:{len(players)} Ball:{len(balls)} Ref:{len(refs)}")

# Draw visualizations
print("\n=== Drawing visualizations ===")
for fn in frames:
    frame = frames[fn].copy()
    
    # Draw ball detections (green)
    for d in ball_results.get(fn, []):
        color = (0, 255, 0) if d['cls'] == 'Ball' else (255, 255, 0) if d['cls'] == 'Hoop' else (128, 128, 128)
        cv2.rectangle(frame, (int(d['x1']), int(d['y1'])), (int(d['x2']), int(d['y2'])), color, 2)
        cv2.putText(frame, f"{d['cls']} {d['conf']:.2f}", (int(d['x1']), int(d['y1'])-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    
    # Draw court keypoints (red circles)
    for kps_dict in court_results.get(fn, []):
        if len(kps_dict['xy']) > 0:
            for inst_kps in kps_dict['xy']:
                for kp in inst_kps:
                    x, y = int(kp[0]), int(kp[1])
                    if x > 0 and y > 0:
                        cv2.circle(frame, (x, y), 5, (0, 0, 255), -1)
    
    # Draw player detections (blue)
    for d in player_results.get(fn, []):
        if d['cls'] == 'Player':
            cv2.rectangle(frame, (int(d['x1']), int(d['y1'])), (int(d['x2']), int(d['y2'])), (255, 0, 0), 2)
    
    cv2.imwrite(f'{OUTPUT_DIR}/frame_{fn:05d}.jpg', frame)

print(f"\nVisualizations saved to {OUTPUT_DIR}/")

# Summary stats
print("\n=== SUMMARY ===")
total_balls = sum(len([d for d in ball_results[fn] if d['cls'] == 'Ball']) for fn in ball_results)
total_hoops = sum(len([d for d in ball_results[fn] if d['cls'] == 'Hoop']) for fn in ball_results)
total_players_ball = sum(len([d for d in ball_results[fn] if d['cls'] == 'Player']) for fn in ball_results)
total_players = sum(len([d for d in player_results[fn] if d['cls'] == 'Player']) for fn in player_results)
courts_detected = sum(1 for fn in court_results if len(court_results[fn]) > 0)
total_court_frames = len(court_results)

print(f"Ball detections (ball model): {total_balls}")
print(f"Hoop detections (ball model): {total_hoops}")
print(f"Player detections (ball model): {total_players_ball}")
print(f"Player detections (player model): {total_players}")
print(f"Court keypoint detections: {courts_detected}/{total_court_frames} frames")
