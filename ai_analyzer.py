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


def run_ai_analysis(db_path, video_path, game_id):
    """Run object detection + tracking on a video and save results to the database.

    Strategy:
    - Run YOLO detection on every frame (~0.04s/frame, ~9 min total)
    - Maintain a pool of active tracks with last known positions
    - Match YOLO detections to nearest active track (greedy, max 200px)
    - Tracks not matched for 120 frames are retired
    - New detections far from all active tracks create new tracker IDs
    """
    print(f"[AI] Starting analysis for {game_id} on {video_path}")
    ai_settings = dict(AI_DEFAULTS)
    frame_number = 0

    def get_db():
        db = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout = 10000")
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

        cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print(f"[AI] Error: Could not open video file {video_path}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        detect_stride = int(ai_settings.get("detect_stride", 1))
        if detect_stride < 1:
            detect_stride = 1
        print(f"[AI] Video: {total_frames} frames @ {fps:.2f}fps, YOLO every {detect_stride} frame(s)")

        frame_number = 0
        db = get_db()

        # Active tracks: dict of tracker_id -> (cx, cy, last_seen_frame)
        tracks = {}
        next_tracker_id = 1
        ball_positions_all = []
        MAX_MATCH_DIST = 200  # Max pixel distance to match a detection to a track
        MAX_TRACK_GAP = max(30, 120 // detect_stride)  # Retire tracks not seen in this many detection cycles

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)

            # --- Run YOLO person detection (every Nth frame based on stride) ---
            new_detections = []
            if frame_number % detect_stride == 0:
                results = model(frame, classes=[0], conf=0.25, verbose=False)
                for result in results:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        if model.names[class_id] == 'person':
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                            new_detections.append((cx, cy, confidence, x1, y1, x2, y2, x2-x1, y2-y1))

            # --- Match detections to active tracks (greedy nearest-neighbor) ---
            person_rows = []
            used_tracks = set()
            used_dets = set()

            # Build all (distance, det_idx, track_id) pairs for active tracks
            match_pairs = []
            for det_idx, (cx, cy, conf, x1, y1, x2, y2, w, h) in enumerate(new_detections):
                for tid, (track_cx, track_cy, last_frame) in tracks.items():
                    if frame_number - last_frame > MAX_TRACK_GAP:
                        continue
                    dist = math.sqrt((cx - track_cx)**2 + (cy - track_cy)**2)
                    if dist < MAX_MATCH_DIST:
                        match_pairs.append((dist, det_idx, tid))

            # Sort by distance — assign closest pairs first
            match_pairs.sort(key=lambda x: x[0])

            for dist, det_idx, tid in match_pairs:
                if det_idx in used_dets or tid in used_tracks:
                    continue
                cx, cy, conf, x1, y1, x2, y2, w, h = new_detections[det_idx]
                used_dets.add(det_idx)
                used_tracks.add(tid)
                tracks[tid] = (cx, cy, frame_number)
                person_rows.append((game_id, frame_number, timestamp_ms, 'person', conf, cx, cy, w, h, tid))

            # Create new tracks for unmatched detections
            for i, (cx, cy, conf, x1, y1, x2, y2, w, h) in enumerate(new_detections):
                if i not in used_dets:
                    tid = next_tracker_id
                    next_tracker_id += 1
                    tracks[tid] = (cx, cy, frame_number)
                    person_rows.append((game_id, frame_number, timestamp_ms, 'person', conf, cx, cy, w, h, tid))

            # Retire stale tracks
            stale_tids = [tid for tid, (cx, cy, lf) in tracks.items()
                          if frame_number - lf > MAX_TRACK_GAP]
            for tid in stale_tids:
                del tracks[tid]

            # --- Ball detection (every 5th frame) ---
            ball_rows = []
            player_centers = [(cx, cy) for cx, cy, conf, x1, y1, x2, y2, w, h in new_detections]

            if frame_number % 5 == 0:
                ball_positions = []
                try:
                    ball_results = model(frame, classes=[32], conf=0.01, verbose=False)
                    for result in ball_results:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            raw_class_name = model.names[class_id]
                            if raw_class_name in ['sports ball', 'sports_ball']:
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                w_box, h_box = x2 - x1, y2 - y1
                                if 8 < w_box < 80 and 8 < h_box < 80 and 0.3 < w_box/max(h_box,1) < 3.0:
                                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                                    ball_positions.append((cx, cy, confidence, x1, y1, x2, y2))
                except Exception:
                    pass

                if len(ball_positions) == 0 and len(player_centers) > 0:
                    if len(ball_positions_all) > 0:
                        last_ball = ball_positions_all[-1]
                        last_bx, last_by = last_ball[0], last_ball[1]
                        nearest = min(player_centers, key=lambda p: (p[0]-last_bx)**2 + (p[1]-last_by)**2)
                        est_x = int(last_bx * 0.3 + nearest[0] * 0.7)
                        est_y = int(last_by * 0.3 + nearest[1] * 0.7)
                        ball_positions.append((est_x, est_y, 0.1, est_x-10, est_y-10, est_x+10, est_y+10))
                    else:
                        fh = frame.shape[0]
                        court_players = [(cx, cy) for cx, cy in player_centers if cy > fh * 0.3]
                        if court_players:
                            frame_cx = frame.shape[1] // 2
                            best = min(court_players, key=lambda p: abs(p[0]-frame_cx) + abs(p[1]-fh//2))
                            ball_positions.append((best[0], best[1]-15, 0.08, best[0]-10, best[1]-25, best[0]+10, best[1]-5))

                ball_positions_all.extend(ball_positions)
                if len(ball_positions_all) > 300:
                    ball_positions_all = ball_positions_all[-300:]

                for (cx, cy, conf, x1, y1, x2, y2) in ball_positions:
                    ball_rows.append((
                        game_id, frame_number, timestamp_ms, 'ball', max(conf, 0.05),
                        cx, cy, max(x2-x1, 10), max(y2-y1, 10), None
                    ))

            # --- Write detections ---
            all_detections = person_rows + ball_rows
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
                step = f"Detecting objects: frame {frame_number}/{total_frames}"
                print(f"[AI] Frame {frame_number}/{total_frames} ({pct:.0f}%) "
                      f"@ {elapsed:.0f}s, {len(tracks)} active, {next_tracker_id-1} total IDs")
                # Write progress to DB
                try:
                    _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
                    _pconn.execute(
                        "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE game_id=? AND status='running'",
                        (int(pct), step, game_id)
                    )
                    _pconn.commit()
                    _pconn.close()
                except Exception:
                    pass

    except Exception as e:
        print(f"[AI] An error occurred during analysis: {e}")
        import traceback
        traceback.print_exc()
        # Mark analysis_runs as failed
        try:
            _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
            _pconn.execute(
                "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE game_id=? AND status='running'",
                (str(e)[:500], game_id)
            )
            _pconn.commit()
            _pconn.close()
        except Exception:
            pass
    else:
        # Only run post-processing if no exception occurred
        print(f"[AI] Finished detection for {game_id}. Processed {frame_number} frames.")
        # Update progress: detection done
        try:
            _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
            _pconn.execute(
                "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE game_id=? AND status='running'",
                (50, "Generating events…", game_id)
            )
            _pconn.commit()
            _pconn.close()
        except Exception:
            pass

        generate_events(game_id, db_path)

        # Update progress: events done
        try:
            _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
            _pconn.execute(
                "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE game_id=? AND status='running'",
                (75, "Running enhanced analysis…", game_id)
            )
            _pconn.commit()
            _pconn.close()
        except Exception:
            pass

        try:
            from film_analysis import run_enhanced_analysis
            cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            cap.release()
            run_enhanced_analysis(db_path, game_id, fps)
        except Exception as e:
            print(f"[AI] Enhanced analysis failed: {e}")
    finally:
        if cap is not None and cap.isOpened():
            cap.release()
        if db is not None:
            db.close()


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: ai_analyzer.py <db_path> <video_path> <game_id>")
        sys.exit(1)

    db_path, video_path, game_id = sys.argv[1], sys.argv[2], sys.argv[3]

    _conn = sqlite3.connect(db_path)
    _conn.execute(
        "UPDATE analysis_runs SET status='running', started_at=CURRENT_TIMESTAMP WHERE game_id=? AND status='pending'",
        (game_id,)
    )
    _conn.commit()
    _conn.close()

    try:
        run_ai_analysis(db_path, video_path, game_id)
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
