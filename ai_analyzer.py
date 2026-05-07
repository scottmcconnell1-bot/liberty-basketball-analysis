#!/usr/bin/env python

import cv2
from ultralytics import YOLO
from event_generator import main as generate_events
import sqlite3
import sys

from config import AnalysisConfig
from settings_store import AI_DEFAULTS, load_all_settings


def resolve_detector_model(ai_settings):
    selected_model = (ai_settings.get("detector_model") or AI_DEFAULTS["detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_detector_model") or "").strip()
        return custom_model or AI_DEFAULTS["detector_model"]
    return selected_model


def run_ai_analysis(db_path, video_path, game_id):
    frame_number = 0  # start at 0 so it always exists
    """Run object detection on a video and save results to the database."""
    print(f"[AI] Starting analysis for {game_id} on {video_path}")
    ai_settings = dict(AI_DEFAULTS)
    
    # The function now runs in a separate process, so it needs to connect to the DB on its own.
    def get_db():
        db = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
        db.row_factory = sqlite3.Row
        return db

    try:
        runtime_settings = load_all_settings(
            feature_defaults={},
            analysis_defaults={
                "USE_DRIBBLE_EVENTS": AnalysisConfig.USE_DRIBBLE_EVENTS,
                "USE_DRIBBLE_HEURISTICS": AnalysisConfig.USE_DRIBBLE_HEURISTICS,
            },
            ai_defaults=AI_DEFAULTS,
            db_path=db_path,
        )
        ai_settings = runtime_settings["ai"]
        model = YOLO(resolve_detector_model(ai_settings))
        inference_device = ai_settings["inference_device"]
        frame_stride = max(1, int(ai_settings["frame_stride"]))
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

            if frame_number % frame_stride != 0:
                frame_number += 1
                continue

            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            predict_kwargs = {"verbose": False}
            if inference_device == "cpu":
                predict_kwargs["device"] = "cpu"
            elif inference_device == "cuda":
                predict_kwargs["device"] = 0

            # Use ByteTrack via model.track() for production-quality tracking
            # This assigns tracker_id directly during detection, which is more
            # accurate than post-hoc centroid matching
            try:
                track_results = model.track(frame, persist=True, tracker="bytetrack.yaml",
                                            classes=[0], **predict_kwargs)  # class 0 = person
                detections_to_add = []
                ball_results = model(frame, **predict_kwargs)

                # Extract person detections with tracker IDs from ByteTrack
                person_boxes = {}  # tracker_id -> box info
                for result in track_results:
                    if result.boxes.id is not None:
                        for box in result.boxes:
                            tid = int(box.id[0])
                            class_id = int(box.cls[0])
                            raw_class_name = model.names[class_id]
                            if raw_class_name in ['person']:
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                person_boxes[tid] = (game_id, frame_number, timestamp_ms,
                                                     'person', confidence,
                                                     (x1 + x2) // 2, (y1 + y2) // 2,
                                                     x2 - x1, y2 - y1, tid)

                # Extract ball detections (no tracking needed for ball)
                for result in ball_results:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        raw_class_name = model.names[class_id]
                        if raw_class_name in ['sports ball', 'sports_ball']:
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            detections_to_add.append((
                                game_id, frame_number, timestamp_ms, 'ball', confidence,
                                (x1 + x2) // 2, (y1 + y2) // 2, x2 - x1, y2 - y1, None
                            ))

                detections_to_add.extend(person_boxes.values())

            except (TypeError, AttributeError):
                # Fallback: model.track() not available, use detect + post-hoc tracker
                results = model(frame, **predict_kwargs)
                detections_to_add = []
                for result in results:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        raw_class_name = model.names[class_id]
                        class_name = raw_class_name
                        if raw_class_name in ['sports ball', 'sports_ball']:
                            class_name = 'ball'
                        if class_name in ['person', 'ball']:
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
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
        # Attempt to assign lightweight tracker IDs before event generation
        try:
            import tracker_assigner
            print("[AI] Running tracker_assigner to populate tracker_id values...")
            tracker_assigner.main(
                db_path,
                game_id,
                int(ai_settings["tracker_max_distance"]),
                int(ai_settings["tracker_max_frame_gap"]),
            )
        except Exception as e:
            print(f"[AI] Tracker assigner failed or not available: {e}")
        # Generate events from detections (will use tracker_id if present)
        generate_events(game_id, db_path)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: ai_analyzer.py <db_path> <video_path> <game_id>")
        sys.exit(1)

    db_path, video_path, game_id = sys.argv[1], sys.argv[2], sys.argv[3]

    # Mark as running
    _conn = sqlite3.connect(db_path)
    _conn.execute(
        "UPDATE analysis_runs SET status='running', started_at=CURRENT_TIMESTAMP WHERE game_id=? AND status='pending'",
        (game_id,)
    )
    _conn.commit()
    _conn.close()

    try:
        run_ai_analysis(db_path, video_path, game_id)
        # Mark as completed
        _conn = sqlite3.connect(db_path)
        _conn.execute(
            "UPDATE analysis_runs SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE game_id=?",
            (game_id,)
        )
        _conn.commit()
        _conn.close()
        print(f"[AI] analysis_runs updated to 'completed' for {game_id}")
    except Exception as e:
        _conn = sqlite3.connect(db_path)
        _conn.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE game_id=?",
            (str(e), game_id)
        )
        _conn.commit()
        _conn.close()
        print(f"[AI] analysis_runs updated to 'failed' for {game_id}: {e}")
        sys.exit(1)
