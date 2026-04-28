#!/usr/bin/env python

import cv2
from ultralytics import YOLO
from event_generator import main as generate_events
import sqlite3

def run_ai_analysis(db_path, video_path, game_id):
    frame_number = 0  # start at 0 so it always exists
    """Run object detection on a video and save results to the database."""
    print(f"[AI] Starting analysis for {game_id} on {video_path}")
    
    # The function now runs in a separate process, so it needs to connect to the DB on its own.
    def get_db():
        db = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
        db.row_factory = sqlite3.Row
        return db

    try:
        model = YOLO('yolov8n.pt')
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[AI] Error: Could not open video file {video_path}")
            cap.release()
            return

        frame_number = 0
        db = get_db()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            results = model(frame, verbose=False)
            detections_to_add = []

            for result in results:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    # Normalize class names to pipeline canonical values
                    raw_class_name = model.names[class_id]
                    class_name = raw_class_name
                    if raw_class_name in ['sports ball', 'sports_ball']:
                        class_name = 'ball'
                    if class_name in ['person', 'ball']:
                        confidence = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        # tracker_id placeholder (None for now) — will be filled when tracking is added
                        tracker_id = None
                        detections_to_add.append((
                            game_id, frame_number, timestamp_ms, class_name, confidence,
                            (x1 + x2) // 2, (y1 + y2) // 2, x2 - x1, y2 - y1, tracker_id
                        ))
            
            if detections_to_add:
                cursor = db.cursor()
                cursor.executemany(
                    '''INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height, tracker_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    detections_to_add
                )
                db.commit()

            frame_number += 1
            if frame_number % 100 == 0:
                print(f"[AI] Processed frame {frame_number} for {game_id}")

    except Exception as e:
        print(f"[AI] An error occurred during analysis: {e}")
    finally:
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        if 'db' in locals():
            db.close()
        print(f"[AI] Finished analysis for {game_id}. Processed {frame_number} frames.")
        generate_events(game_id, db_path)
