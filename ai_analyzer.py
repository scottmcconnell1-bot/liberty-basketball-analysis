#!/usr/bin/env python

import cv2
import sys
import os
import sqlite3
from event_generator import main as generate_events

# Feature flag to enable tracker integration
TRACKER_ENABLED = True

# Ensure we can import tracker_wrapper from src/
_SRC_DIR = os.path.join(os.path.dirname(__file__), 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
try:
    import tracker_wrapper
except Exception:
    tracker_wrapper = None

# YOLO is imported lazily (kept optional for tests); default import if available
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

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
        # instantiate model if possible
        model = YOLO('yolov8n.pt') if YOLO is not None else None

        # Decide whether we're running on a real video file or generating
        # synthetic frames (useful for smoke tests when the detector backend
        # isn't available).
        synthetic_mode = (video_path == 'synthetic')

        frame_number = 0
        db = get_db()

        # We'll store detections per frame for tracker input. Each detection will
        # include a detection_id which maps to the DB row id.
        detections_per_frame = []

        if synthetic_mode:
            # generate a short sequence of synthetic detections and persist them
            for f in range(8):
                # simple moving objects: a ball and a person
                x1_ball = 30 + f * 5
                y1_ball = 60
                x2_ball = x1_ball + 20
                y2_ball = y1_ball + 20
                x1_person = 150 + f * 2
                y1_person = 40
                x2_person = x1_person + 20
                y2_person = y1_person + 80

                cur = db.cursor()
                cur.execute(
                    "INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height, tracker_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (game_id, f, f * 33, 'ball', 0.9, (x1_ball + x2_ball) // 2, (y1_ball + y2_ball) // 2, x2_ball - x1_ball, y2_ball - y1_ball, None),
                )
                ball_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height, tracker_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (game_id, f, f * 33, 'person', 0.95, (x1_person + x2_person) // 2, (y1_person + y2_person) // 2, x2_person - x1_person, y2_person - y1_person, None),
                )
                person_id = cur.lastrowid
                db.commit()
                detections_per_frame.append([
                    {'detection_id': ball_id, 'bbox': [x1_ball, y1_ball, x2_ball, y2_ball], 'score': 0.9, 'class': 'ball'},
                    {'detection_id': person_id, 'bbox': [x1_person, y1_person, x2_person, y2_person], 'score': 0.95, 'class': 'person'},
                ])
            # synthetic generation complete — skip video capture loop
        else:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"[AI] Error: Could not open video file {video_path}")
                cap.release()
                return

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                # Run detection if model available; otherwise skip
                results = model(frame, verbose=False) if model is not None else []

                frame_dets_for_tracker = []

                for result in results:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        # Normalize class names to pipeline canonical values
                        raw_class_name = model.names[class_id] if model is not None else str(class_id)
                        class_name = raw_class_name
                        if raw_class_name in ['sports ball', 'sports_ball']:
                            class_name = 'ball'
                        if class_name in ['person', 'ball']:
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            tracker_id = None

                            # Insert detection row immediately so we have a DB id to
                            # pass as detection_id to the tracker.
                            cursor = db.cursor()
                            cursor.execute(
                                '''INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height, tracker_id)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                (
                                    game_id, frame_number, int(timestamp_ms), class_name, confidence,
                                    (x1 + x2) // 2, (y1 + y2) // 2, x2 - x1, y2 - y1, tracker_id,
                                ),
                            )
                            det_id = cursor.lastrowid
                            db.commit()

                            frame_dets_for_tracker.append({
                                'detection_id': det_id,
                                'bbox': [x1, y1, x2, y2],
                                'score': confidence,
                                'class': class_name,
                            })

                detections_per_frame.append(frame_dets_for_tracker)

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
        # If tracker integration is enabled, run tracking and write tracker_ids
        try:
            if TRACKER_ENABLED and tracker_wrapper is not None:
                print(f"[AI] Initializing tracker for game {game_id}")
                tracker_wrapper.initialize()
                mappings = tracker_wrapper.track_frames(detections_per_frame)
                # mappings is list per frame of {detection_id: tracker_id}
                db = get_db()
                cur = db.cursor()
                updates = 0
                for frame_map in mappings:
                    for det_id_str, tid in frame_map.items():
                        # det_id_str should be int (db id)
                        det_id = int(det_id_str)
                        cur.execute('UPDATE detections SET tracker_id = ? WHERE id = ?', (int(tid), det_id))
                        updates += 1
                db.commit()
                db.close()
                print(f"[AI] Tracker assigned tracker_id to {updates} detections for game {game_id}")
            else:
                if tracker_wrapper is None:
                    print('[AI] Tracker wrapper not available; skipping tracking pass')
                else:
                    print('[AI] TRACKER_ENABLED is False; skipping tracking pass')
        except Exception as e:
            print(f"[AI] Tracker pass failed: {e}")

        # Generate events (existing behavior)
        generate_events(game_id, db_path)
