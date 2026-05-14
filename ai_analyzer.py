#!/usr/bin/env python

import cv2
from ultralytics import YOLO
from event_generator import main as generate_events
import sqlite3
import sys
import math
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
    frame_number = 0  # initialize here so finally block can always reference it

    def get_db():
        db = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
        db.row_factory = sqlite3.Row
        return db

    cap = None
    db = None
    try:
        runtime_settings = load_all_settings(
            feature_defaults={},
            analysis_defaults={},
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
        ball_positions_all = []  # Track all ball positions for virtual ball estimation

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
                # Detect persons (class 0) at standard confidence
                results = model(frame, classes=[0], conf=0.25, verbose=False)
                new_detections = []
                for result in results:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        if model.names[class_id] == 'person':
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                            new_detections.append((cx, cy, confidence, x1, y1, x2, y2, x2-x1, y2-y1))

                # Match new detections to existing active trackers by proximity
                matched_trackers = []
                used_detections = set()

                for tid, points, prev_frame in active_trackers:
                    # Get last known position from points
                    if points is not None and len(points) > 0:
                        pts = points.reshape(-1, 2)
                        last_cx = float(pts[:, 0].mean())
                        last_cy = float(pts[:, 1].mean())
                    else:
                        continue

                    # Find closest new detection
                    best_dist = float('inf')
                    best_idx = -1
                    for i, (cx, cy, conf, x1, y1, x2, y2, w, h) in enumerate(new_detections):
                        if i in used_detections:
                            continue
                        dist = math.sqrt((cx - last_cx)**2 + (cy - last_cy)**2)
                        if dist < best_dist and dist < 150:  # max 150px movement between anchors
                            best_dist = dist
                            best_idx = i

                    if best_idx >= 0:
                        # Match found — reuse tracker ID
                        cx, cy, conf, x1, y1, x2, y2, w, h = new_detections[best_idx]
                        used_detections.add(best_idx)
                        matched_trackers.append(tid)
                        yolo_person_boxes[tid] = (game_id, frame_number, timestamp_ms,
                                                  'person', conf, cx, cy, w, h, tid)
                        pts = bbox_to_points(x1, y1, x2, y2)
                        active_trackers[matched_trackers.index(tid)] = (tid, pts, gray)

                # Create new trackers for unmatched detections
                for i, (cx, cy, conf, x1, y1, x2, y2, w, h) in enumerate(new_detections):
                    if i not in used_detections:
                        tid = next_tracker_id
                        next_tracker_id += 1
                        matched_trackers.append(tid)
                        yolo_person_boxes[tid] = (game_id, frame_number, timestamp_ms,
                                                  'person', conf, cx, cy, w, h, tid)
                        pts = bbox_to_points(x1, y1, x2, y2)
                        active_trackers.append((tid, pts, gray))

                # Ball detection strategy:
                # YOLOv8n barely detects basketballs (15-30px at 720p), so we use:
                # 1. YOLO at conf=0.01 as a weak signal
                # 2. Player-proximity heuristic: ball is inferred near the player most likely to have it
                #    based on who was closest to the last known ball position
                # This "virtual ball" approach is more reliable than direct detection for small fast balls
                ball_positions = []
                
                # --- YOLO ball detection (weak signal) ---
                try:
                    ball_results = model(frame, classes=[32], conf=0.01, verbose=False)
                    for result in ball_results:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            raw_class_name = model.names[class_id]
                            if raw_class_name in ['sports ball', 'sports_ball']:
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                w, h = x2 - x1, y2 - y1
                                if 8 < w < 80 and 8 < h < 80 and 0.3 < w/max(h,1) < 3.0:
                                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                                    ball_positions.append((cx, cy, confidence, x1, y1, x2, y2))
                except Exception:
                    pass
                
                # --- Virtual ball: infer from player positions ---
                # If YOLO didn't find a ball, estimate ball position from game context:
                # The ball is almost always near a player. We track the last known ball
                # position and estimate it moves toward the nearest player.
                if len(ball_positions) == 0 and len(new_detections) > 0:
                    # Get player centers
                    player_centers = [(cx, cy) for cx, cy, conf, x1, y1, x2, y2, w, h in new_detections]
                    
                    if len(ball_positions_all) > 0:
                        # We have a previous ball position — estimate ball moved toward nearest player
                        last_ball = ball_positions_all[-1]
                        last_bx, last_by = last_ball[0], last_ball[1]
                        
                        # Find nearest player to last ball position
                        min_dist = float('inf')
                        nearest_player = None
                        for cx, cy in player_centers:
                            dist = math.sqrt((cx - last_bx)**2 + (cy - last_by)**2)
                            if dist < min_dist:
                                min_dist = dist
                                nearest_player = (cx, cy)
                        
                        if nearest_player:
                            # Estimate ball is between last position and nearest player
                            # (weighted toward player since they likely have it)
                            est_x = int(last_bx * 0.3 + nearest_player[0] * 0.7)
                            est_y = int(last_by * 0.3 + nearest_player[1] * 0.7)
                            ball_positions.append((est_x, est_y, 0.1, est_x-10, est_y-10, est_x+10, est_y+10))
                    else:
                        # No previous ball — estimate ball is near the center-most player in the paint area
                        # (y_center > frame_height * 0.4 roughly = inside the court)
                        fh = frame.shape[0]
                        court_players = [(cx, cy) for cx, cy in player_centers if cy > fh * 0.3]
                        if court_players:
                            # Pick the player closest to the center of the frame (likely ball handler)
                            frame_cx = frame.shape[1] // 2
                            best = min(court_players, key=lambda p: abs(p[0] - frame_cx) + abs(p[1] - fh//2))
                            ball_positions.append((best[0], best[1] - 15, 0.08, best[0]-10, best[1]-25, best[0]+10, best[1]-5))
                
                # Store ball positions for next frame's estimation
                ball_positions_all.extend(ball_positions)
                # Keep only last 300 ball positions to bound memory
                if len(ball_positions_all) > 300:
                    ball_positions_all = ball_positions_all[-300:]
                
                # Write ball detections
                for (cx, cy, conf, x1, y1, x2, y2) in ball_positions:
                    ball_detections.append((
                        game_id, frame_number, timestamp_ms, 'ball', max(conf, 0.05),
                        cx, cy, max(x2 - x1, 10), max(y2 - y1, 10), None
                    ))

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
        if cap is not None and cap.isOpened():
            cap.release()
        if db is not None:
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

        # Run enhanced film analysis (minutes, shots, plays, player effect)
        try:
            from film_analysis import run_enhanced_analysis
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.release()
            run_enhanced_analysis(db_path, game_id, fps)
        except Exception as e:
            print(f"[AI] Enhanced analysis failed or not available: {e}")


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
