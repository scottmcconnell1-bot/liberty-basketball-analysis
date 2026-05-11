#!/usr/bin/env python

import cv2
from ultralytics import YOLO
from event_generator import main as generate_events
import sqlite3
import sys
import numpy as np

from config import AnalysisConfig
from settings_store import AI_DEFAULTS, load_all_settings


def resolve_detector_model(ai_settings):
    selected_model = (ai_settings.get("detector_model") or AI_DEFAULTS["detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_detector_model") or "").strip()
        return custom_model or AI_DEFAULTS["detector_model"]
    return selected_model


def bbox_to_points(x1, y1, x2, y2, num_points=8):
    """Generate tracking points inside a bbox using a grid pattern."""
    xs = np.linspace(x1 + 5, x2 - 5, num_points // 2, dtype=np.float32)
    ys = np.linspace(y1 + 5, y2 - 5, 2, dtype=np.float32)
    points = []
    for y in ys:
        for x in xs:
            points.append([x, y])
    return np.array(points, dtype=np.float32).reshape(-1, 1, 2)


def points_to_bbox(points):
    """Convert tracked points back to a bounding box."""
    pts = points.reshape(-1, 2)
    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)
    return int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min)


def run_ai_analysis(db_path, video_path, game_id):
    """Run object detection + optical flow tracking on a video and save results to the database.

    Strategy:
    - Run YOLO detection every N frames (detection_stride) for anchor detections
    - Between anchors, use Lucas-Kanade optical flow to propagate player positions
    - Ball is only searched on anchor frames (moves too fast for flow tracking)
    - This gives per-frame position data at a fraction of the compute cost

    Performance: ~3-5 min for a 90-min game on CPU (vs 30-45 min with detection-only)
    """
    print(f"[AI] Starting analysis for {game_id} on {video_path}")
    ai_settings = dict(AI_DEFAULTS)

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
        detection_stride = max(1, int(ai_settings.get("detection_stride", 15)))

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[AI] Error: Could not open video file {video_path}")
            cap.release()
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"[AI] Video: {total_frames} frames @ {fps:.1f}fps, "
              f"YOLO every {detection_stride} frames, optical flow between")

        frame_number = 0
        db = get_db()

        # Optical flow tracking state
        # Each entry: (tracker_id, points, prev_gray_frame)
        active_trackers = []
        next_tracker_id = 1
        prev_gray = None

        # Lucas-Kanade parameters
        lk_params = dict(
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
        )

        predict_kwargs = {"verbose": False}
        if inference_device == "cpu":
            predict_kwargs["device"] = "cpu"
        elif inference_device == "cuda":
            predict_kwargs["device"] = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # --- Phase 1: Update optical flow trackers on every frame ---
            flow_detections = []
            still_active = []
            for tid, points, prev_frame in active_trackers:
                if prev_frame is None or points is None or len(points) == 0:
                    continue

                # Forward flow: track points from prev frame to current
                new_points, status, err = cv2.calcOpticalFlowPyrLK(
                    prev_frame, gray, points, None, **lk_params
                )

                if new_points is not None:
                    # Filter to only good points
                    good = status.reshape(-1) == 1
                    if good.sum() >= 3:  # Need at least 3 good points
                        valid_pts = new_points[good]
                        x, y, w, h = points_to_bbox(valid_pts)

                        # Sanity check
                        fh, fw = frame.shape[:2]
                        if 0 <= x < fw and 0 <= y < fh and 10 < w < fw // 2 and 10 < h < fh // 2:
                            flow_detections.append((
                                game_id, frame_number, timestamp_ms,
                                'person', 0.5,
                                x + w // 2, y + h // 2, w, h, tid
                            ))
                            # Update points for next iteration (only keep good ones)
                            still_active.append((tid, valid_pts.reshape(-1, 1, 2), gray))
                # If too many points lost, tracker drops (player left frame or heavy occlusion)

            active_trackers = still_active

            # --- Phase 2: Run YOLO detection on anchor frames ---
            yolo_person_boxes = {}
            ball_detections = []

            if frame_number % detection_stride == 0:
                # Clear old flow trackers — re-detect and re-initialize
                active_trackers = []

                try:
                    # Detect persons with ByteTrack for consistent IDs
                    track_results = model.track(frame, persist=True, tracker="bytetrack.yaml",
                                                classes=[0], **predict_kwargs)

                    for result in track_results:
                        if result.boxes.id is not None:
                            for box in result.boxes:
                                tid = int(box.id[0])
                                class_id = int(box.cls[0])
                                raw_class_name = model.names[class_id]
                                if raw_class_name == 'person':
                                    confidence = float(box.conf[0])
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    yolo_person_boxes[tid] = (game_id, frame_number, timestamp_ms,
                                                              'person', confidence,
                                                              (x1 + x2) // 2, (y1 + y2) // 2,
                                                              x2 - x1, y2 - y1, tid)

                                    # Initialize optical flow points for this player
                                    pts = bbox_to_points(x1, y1, x2, y2)
                                    active_trackers.append((tid, pts, gray))

                except (TypeError, AttributeError):
                    # Fallback: detect without ByteTrack
                    results = model(frame, classes=[0], **predict_kwargs)
                    local_id = next_tracker_id
                    for result in results:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            if model.names[class_id] == 'person':
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                yolo_person_boxes[local_id] = (game_id, frame_number, timestamp_ms,
                                                               'person', confidence,
                                                               (x1 + x2) // 2, (y1 + y2) // 2,
                                                               x2 - x1, y2 - y1, local_id)
                                pts = bbox_to_points(x1, y1, x2, y2)
                                active_trackers.append((local_id, pts, gray))
                                local_id += 1
                    next_tracker_id = local_id

                # Ball detection on anchor frames only (class 32 = sports ball in COCO)
                try:
                    ball_results = model(frame, classes=[32], **predict_kwargs)
                    for result in ball_results:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            raw_class_name = model.names[class_id]
                            if raw_class_name in ['sports ball', 'sports_ball']:
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                ball_detections.append((
                                    game_id, frame_number, timestamp_ms, 'ball', confidence,
                                    (x1 + x2) // 2, (y1 + y2) // 2, x2 - x1, y2 - y1, None
                                ))
                except Exception:
                    pass  # Ball detection is best-effort

            # --- Phase 3: Write all detections for this frame ---
            all_detections = []
            all_detections.extend(flow_detections)              # Optical flow tracked positions
            all_detections.extend(yolo_person_boxes.values())   # YOLO anchor detections
            all_detections.extend(ball_detections)              # Ball on anchor frames

            if all_detections:
                cursor = db.cursor()
                cursor.executemany(
                    '''INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height, tracker_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    all_detections
                )
                db.commit()

            frame_number += 1
            if frame_number % 500 == 0:
                elapsed = frame_number / fps
                pct = frame_number / total_frames * 100 if total_frames > 0 else 0
                print(f"[AI] Frame {frame_number}/{total_frames} ({pct:.0f}%) "
                      f"@ {elapsed:.0f}s elapsed, {len(active_trackers)} active trackers")

            prev_gray = gray

    except Exception as e:
        print(f"[AI] An error occurred during analysis: {e}")
        import traceback
        traceback.print_exc()
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
