"""
Generate visualization images for shot events and close approaches.
"""
import cv2
import numpy as np
import pandas as pd
import os

VIDEO_PATH = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
OUTPUT_DIR = 'pipeline_output/vis'
os.makedirs(OUTPUT_DIR, exist_ok=True)

df_ball = pd.read_csv('pipeline_output/ball_dets_full.csv') if os.path.exists('pipeline_output/ball_dets_full.csv') else pd.read_csv('pipeline_output/ball_detections.csv')
df_shots = pd.read_csv('pipeline_output/shot_events.csv')

print("Ball columns:", df_ball.columns.tolist())
print("Shot columns:", df_shots.columns.tolist())

# Shot frames
shot_frames = set(df_shots['frame'].tolist())

# Also get frames from top closest approaches (from log output)
closest_frames = [1936, 1938, 798, 796, 1930, 1962, 792]

all_viz_frames = sorted(set(shot_frames) | set(closest_frames))
print(f"\nVisualizing {len(all_viz_frames)} frames...")

cap = cv2.VideoCapture(VIDEO_PATH)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_FRAME_COUNT)) if hasattr(cv2, 'CAP_PROP_FRAME_FRAME_COUNT') else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

for fn in all_viz_frames:
    # Get ball detection for this exact frame
    this_ball = df_ball[df_ball['frame'] == fn]
    # Get nearby ball detections (±10 frames)
    nearby_ball = df_ball[(df_ball['frame'] >= fn - 10) & (df_ball['frame'] <= fn + 10)]
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue
    
    # Draw nearby ball detections (small yellow)
    for _, b in nearby_ball.iterrows():
        bx, by = int(b['x']), int(b['y'])
        bf = int(b['frame'])
        if bf == fn:
            # Current frame: large green circle
            cv2.circle(frame, (bx, by), 12, (0, 255, 0), 2)
            cv2.putText(frame, f"Ball {b['conf']:.2f}", (bx+14, by), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        else:
            # Nearby: small yellow
            cv2.circle(frame, (bx, by), 5, (0, 200, 200), 1)
    
    # If shot frame, add annotation
    if fn in shot_frames:
        shot_row = df_shots[df_shots['frame'] == fn].iloc[0]
        label = f"SHOT: {shot_row['shot_type']} {shot_row['result']} | dist={shot_row['basket_dist_px']:.0f}px | conf={shot_row['conf']:.2f}"
        cv2.putText(frame, label, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Draw ball position with crosshair
        bx, by = int(shot_row['ball_x']), int(shot_row['ball_y'])
        cv2.drawMarker(frame, (bx, by), (0, 255, 0), cv2.MARKER_CROSS, 20, 3)
    
    cv2.putText(frame, f"Frame {fn}", (10, frame.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    
    out_path = f'{OUTPUT_DIR}/frame_{fn:05d}.jpg'
    cv2.imwrite(out_path, frame)
    print(f"  Saved {out_path}")

cap.release()
print(f"\nDone. {len(all_viz_frames)} images in {OUTPUT_DIR}/")
