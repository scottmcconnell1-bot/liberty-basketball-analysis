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


def resolve_ball_detector_model(ai_settings):
    selected_model = (ai_settings.get("ball_detector_model") or AI_DEFAULTS["ball_detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_ball_detector_model") or "").strip()
        return custom_model or AI_DEFAULTS["ball_detector_model"]
    return selected_model


def ball_detector_settings(ai_settings):
    try:
        class_id = int(ai_settings.get("ball_class_id", AI_DEFAULTS["ball_class_id"]))
    except (TypeError, ValueError):
        class_id = AI_DEFAULTS["ball_class_id"]

    try:
        confidence = float(ai_settings.get("ball_confidence", AI_DEFAULTS["ball_confidence"]))
    except (TypeError, ValueError):
        confidence = AI_DEFAULTS["ball_confidence"]

    return resolve_ball_detector_model(ai_settings), class_id, max(0.01, min(confidence, 0.99))


def person_detector_settings(ai_settings):
    try:
        confidence = float(ai_settings.get("person_confidence", AI_DEFAULTS["person_confidence"]))
    except (TypeError, ValueError):
        confidence = AI_DEFAULTS["person_confidence"]
    return max(0.01, min(confidence, 0.99))


def run_ai_analysis(db_path, video_path, game_id, relational_game_id=None):
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
        person_model_path = resolve_detector_model(ai_settings)
        ball_model_path, ball_class_id, ball_confidence = ball_detector_settings(ai_settings)
        person_confidence = person_detector_settings(ai_settings)

        from helpers import validate_model_weights

        for label, path in (
            ("Person detector", person_model_path),
            ("Ball detector", ball_model_path),
        ):
            ok, message = validate_model_weights(path)
            if not ok:
                raise RuntimeError(f"{label}: {message}")

        model = YOLO(person_model_path)
        ball_model = model if ball_model_path == person_model_path else YOLO(ball_model_path)
        inference_device = ai_settings["inference_device"]

        cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if total_frames <= 0 and orig_w <= 0 and orig_h <= 0:
            raise RuntimeError(f"Video has no readable frames: {video_path}")
        detect_stride = int(ai_settings.get("detection_stride") or ai_settings.get("frame_stride") or 1)
        if detect_stride < 1:
            detect_stride = 1
        tracker_backend = str(ai_settings.get("tracker_backend") or "bytetrack").lower()
        jersey_ocr_enabled = bool(ai_settings.get("jersey_ocr_enabled", True))
        jersey_ocr_stride = max(1, int(ai_settings.get("jersey_ocr_stride", 5)))
        infer_size = 640
        scale_x = orig_w / infer_size
        scale_y = orig_h / infer_size
        print(f"[AI] Video: {total_frames} frames @ {fps:.2f}fps, {orig_w}x{orig_h}, YOLO every {detect_stride} frame(s) @ {infer_size}px, tracker={tracker_backend}")

        frame_number = 0
        db = get_db()

        if relational_game_id is None:
            from helpers import resolve_relational_game_id_for_analysis
            relational_game_id = resolve_relational_game_id_for_analysis(db_path, game_id)
            if relational_game_id:
                print(f"[AI] Resolved relational_game_id={relational_game_id} for {game_id}")

        # Ensure game row exists so relational_game_id resolves
        try:
            gid_int = int(game_id)
            row = db.execute("SELECT id FROM games WHERE id = ?", (gid_int,)).fetchone()
            if not row:
                db.execute(
                    "INSERT INTO games (id, source_type, source_key, created_at, updated_at) VALUES (?, 'analysis', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (gid_int, str(game_id)),
                )
                db.commit()
                print(f"[AI] Created games row id={gid_int}")
            if relational_game_id is None:
                relational_game_id = gid_int
        except (TypeError, ValueError):
            pass

        # Active tracks: dict of tracker_id -> (cx, cy, last_seen_frame)
        tracks = {}
        next_tracker_id = 1
        ball_positions_all = []
        MAX_MATCH_DIST = int(ai_settings.get("tracker_max_distance") or 200)
        track_gap_setting = int(ai_settings.get("tracker_max_frame_gap") or 5)
        MAX_TRACK_GAP = max(30, 120 // detect_stride) if track_gap_setting <= 5 else track_gap_setting
        track_device = None if inference_device in (None, "", "auto") else inference_device

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)

            # --- Run YOLO person detection (every Nth frame based on stride) ---
            new_detections = []
            person_rows = []
            if frame_number % detect_stride == 0:
                if tracker_backend == "bytetrack":
                    track_kwargs = {
                        "persist": True,
                        "tracker": "bytetrack.yaml",
                        "classes": [0],
                        "conf": person_confidence,
                        "verbose": False,
                        "imgsz": infer_size,
                    }
                    if track_device:
                        track_kwargs["device"] = track_device
                    results = model.track(frame, **track_kwargs)
                    for result in results:
                        if result.boxes is None:
                            continue
                        for box in result.boxes:
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            x1 = int(x1 * scale_x)
                            y1 = int(y1 * scale_y)
                            x2 = int(x2 * scale_x)
                            y2 = int(y2 * scale_y)
                            x1 = max(0, min(x1, orig_w - 1))
                            y1 = max(0, min(y1, orig_h - 1))
                            x2 = max(0, min(x2, orig_w - 1))
                            y2 = max(0, min(y2, orig_h - 1))
                            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                            w, h = x2 - x1, y2 - y1
                            tid = None
                            if box.id is not None:
                                tid = int(box.id.item())
                            if tid is None:
                                tid = next_tracker_id
                                next_tracker_id += 1
                            jersey_read, jersey_conf = None, None
                            if jersey_ocr_enabled and frame_number % jersey_ocr_stride == 0:
                                from jersey_ocr import read_jersey_from_bbox
                                jersey_read, jersey_conf = read_jersey_from_bbox(frame, x1, y1, x2, y2)
                            person_rows.append((
                                game_id, relational_game_id, frame_number, timestamp_ms,
                                'person', confidence, cx, cy, w, h, tid, jersey_read, jersey_conf,
                            ))
                            new_detections.append((cx, cy, confidence, x1, y1, x2, y2, w, h))
                else:
                    results = model(frame, classes=[0], conf=person_confidence, verbose=False, imgsz=infer_size)
                    for result in results:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            if model.names[class_id] == 'person':
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                x1 = int(x1 * scale_x)
                                y1 = int(y1 * scale_y)
                                x2 = int(x2 * scale_x)
                                y2 = int(y2 * scale_y)
                                x1 = max(0, min(x1, orig_w - 1))
                                y1 = max(0, min(y1, orig_h - 1))
                                x2 = max(0, min(x2, orig_w - 1))
                                y2 = max(0, min(y2, orig_h - 1))
                                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                                new_detections.append((cx, cy, confidence, x1, y1, x2, y2, x2-x1, y2-y1))

            if tracker_backend != "bytetrack":
                # --- Match detections to active tracks (greedy nearest-neighbor) ---
                used_tracks = set()
                used_dets = set()

                match_pairs = []
                for det_idx, (cx, cy, conf, x1, y1, x2, y2, w, h) in enumerate(new_detections):
                    for tid, (track_cx, track_cy, last_frame) in tracks.items():
                        if frame_number - last_frame > MAX_TRACK_GAP:
                            continue
                        dist = math.sqrt((cx - track_cx)**2 + (cy - track_cy)**2)
                        if dist < MAX_MATCH_DIST:
                            match_pairs.append((dist, det_idx, tid))

                match_pairs.sort(key=lambda x: x[0])

                for dist, det_idx, tid in match_pairs:
                    if det_idx in used_dets or tid in used_tracks:
                        continue
                    cx, cy, conf, x1, y1, x2, y2, w, h = new_detections[det_idx]
                    used_dets.add(det_idx)
                    used_tracks.add(tid)
                    tracks[tid] = (cx, cy, frame_number)
                    jersey_read, jersey_conf = None, None
                    if jersey_ocr_enabled and frame_number % jersey_ocr_stride == 0:
                        from jersey_ocr import read_jersey_from_bbox
                        jersey_read, jersey_conf = read_jersey_from_bbox(frame, x1, y1, x2, y2)
                    person_rows.append((
                        game_id, relational_game_id, frame_number, timestamp_ms,
                        'person', conf, cx, cy, w, h, tid, jersey_read, jersey_conf,
                    ))

                for i, (cx, cy, conf, x1, y1, x2, y2, w, h) in enumerate(new_detections):
                    if i not in used_dets:
                        tid = next_tracker_id
                        next_tracker_id += 1
                        tracks[tid] = (cx, cy, frame_number)
                        jersey_read, jersey_conf = None, None
                        if jersey_ocr_enabled and frame_number % jersey_ocr_stride == 0:
                            from jersey_ocr import read_jersey_from_bbox
                            jersey_read, jersey_conf = read_jersey_from_bbox(frame, x1, y1, x2, y2)
                        person_rows.append((
                            game_id, relational_game_id, frame_number, timestamp_ms,
                            'person', conf, cx, cy, w, h, tid, jersey_read, jersey_conf,
                        ))

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
                    ball_results = ball_model(frame, classes=[ball_class_id], conf=ball_confidence, verbose=False, imgsz=640)
                    for result in ball_results:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            if class_id == ball_class_id:
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                if ball_model is model and ball_class_id == 32:
                                    # Preserve the legacy COCO sports-ball coordinate handling.
                                    x1 = int(x1 * scale_x)
                                    y1 = int(y1 * scale_y)
                                    x2 = int(x2 * scale_x)
                                    y2 = int(y2 * scale_y)
                                # Clamp to frame bounds (YOLO boxes can overflow at edges)
                                x1 = max(0, min(x1, orig_w - 1))
                                y1 = max(0, min(y1, orig_h - 1))
                                x2 = max(0, min(x2, orig_w - 1))
                                y2 = max(0, min(y2, orig_h - 1))
                                w_box, h_box = x2 - x1, y2 - y1
                                if ball_model is model and ball_class_id == 32 and not (8 < w_box < 80 and 8 < h_box < 80 and 0.3 < w_box/max(h_box,1) < 3.0):
                                    continue

                                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                                # Filter 1: Reject detections in top 15% of frame (exit signs, ceiling fixtures)
                                if ball_model is model and ball_class_id == 32 and cy < orig_h * 0.15:
                                    continue

                                # Filter 2: Color check — basketball is orange/brown
                                # Exit signs are white/red, reflections are gray/white
                                roi = frame[max(0,y1):min(orig_h,y2), max(0,x1):min(orig_w,x2)]
                                if ball_model is model and ball_class_id == 32 and roi.size > 0:
                                    roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                                    mask_orange = cv2.inRange(roi_hsv, np.array([10, 150, 150]), np.array([30, 255, 255]))
                                    mask_brown = cv2.inRange(roi_hsv, np.array([0, 80, 80]), np.array([20, 150, 150]))
                                    colour_ratio = np.count_nonzero(cv2.bitwise_or(mask_orange, mask_brown)) / roi.size
                                    if colour_ratio < 0.15:
                                        continue

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
                        game_id, relational_game_id, frame_number, timestamp_ms, 'ball', max(conf, 0.05),
                        cx, cy, max(x2-x1, 10), max(y2-y1, 10), None, None, None,
                    ))

            # --- Write detections ---
            all_detections = person_rows + ball_rows
            if all_detections:
                cursor = db.cursor()
                cursor.executemany(
                    '''INSERT INTO detections
                       (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                        confidence, x_center, y_center, width, height, tracker_id,
                        jersey_read, jersey_confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
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
                        "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE analysis_key=? AND status='running'",
                        (int(pct), step, game_id)
                    )
                    _pconn.commit()
                    _pconn.close()
                except Exception:
                    pass

        if frame_number == 0:
            raise RuntimeError(f"No frames processed from video: {video_path}")

    except Exception as e:
        print(f"[AI] An error occurred during analysis: {e}")
        import traceback
        traceback.print_exc()
        # Mark analysis_runs as failed
        try:
            _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
            _pconn.execute(
                "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE analysis_key=? AND status='running'",
                (str(e)[:500], game_id)
            )
            _pconn.commit()
            _pconn.close()
        except Exception:
            pass
        raise
    else:
        # Only run post-processing if no exception occurred
        print(f"[AI] Finished detection for {game_id}. Processed {frame_number} frames.")
        # Update progress: detection done
        try:
            _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
            _pconn.execute(
                "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE analysis_key=? AND status='running'",
                (50, "Generating events…", game_id)
            )
            _pconn.commit()
            _pconn.close()
        except Exception:
            pass

        if generate_events(game_id, db_path, relational_game_id=relational_game_id) is False:
            raise RuntimeError(
                "Event generation failed. Install scikit-learn (pip install scikit-learn) "
                "and regenerate events without re-running detection."
            )

        detection_count = db.execute(
            """SELECT COUNT(*) FROM detections
               WHERE game_id = ?
                  OR (? IS NOT NULL AND relational_game_id = ?)""",
            (game_id, relational_game_id, relational_game_id),
        ).fetchone()[0]
        if frame_number > 0 and detection_count == 0:
            raise RuntimeError(
                f"Processed {frame_number} frames but wrote 0 detections for {game_id}. "
                "Check AI model weights and video playback."
            )

        # Assign possessions after events are generated
        if relational_game_id:
            try:
                from helpers import assign_possessions_for_game
                assign_possessions_for_game(db, relational_game_id)
                print(f"[AI] Possessions assigned for game_id={relational_game_id}")
            except Exception as e:
                print(f"[AI] Possession assignment failed: {e}")
        else:
            print("[AI] Skipping possession assignment: no relational_game_id set")

        # Update progress: events done
        try:
            _pconn = sqlite3.connect(f'file:{db_path}?mode=rwc', uri=True)
            _pconn.execute(
                "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE analysis_key=? AND status='running'",
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
            run_enhanced_analysis(db_path, game_id, fps, detect_stride=detect_stride)
        except Exception as e:
            print(f"[AI] Enhanced analysis failed: {e}")

        try:
            from track_identity import build_identity_report, auto_apply_cluster_jerseys

            identity_report = build_identity_report(db, game_id, ai_settings)
            print(
                f"[AI] Jersey identity: {identity_report['ocr_read_count']} OCR reads, "
                f"{len(identity_report['cluster_suggestions'])} cluster suggestions"
            )
            if ai_settings.get("auto_apply_jersey_mapping", True):
                applied = auto_apply_cluster_jerseys(db, game_id, ai_settings)
                print(
                    f"[AI] Auto-applied {applied.get('applied', 0)} jersey mappings, "
                    f"{applied.get('events_updated', 0)} events updated"
                )
        except Exception as e:
            print(f"[AI] Jersey identity step failed: {e}")
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
        "UPDATE analysis_runs SET status='running', started_at=CURRENT_TIMESTAMP, progress_pct=0, progress_step='Loading AI models…' WHERE analysis_key=? AND status='pending'",
        (game_id,)
    )

    # Resolve relational game_id for NFHS/library analysis keys.
    from helpers import resolve_relational_game_id_for_analysis

    _relational_game_id = resolve_relational_game_id_for_analysis(db_path, game_id)
    if _relational_game_id is None:
        try:
            gid_int = int(game_id)
            row = _conn.execute("SELECT id FROM games WHERE id = ?", (gid_int,)).fetchone()
            if not row:
                _conn.execute(
                    "INSERT INTO games (id, source_type, source_key, created_at, updated_at) VALUES (?, 'analysis', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (gid_int, game_id),
                )
                _relational_game_id = gid_int
            else:
                _relational_game_id = row[0]
        except (TypeError, ValueError):
            pass

    _conn.commit()
    _conn.close()

    try:
        run_ai_analysis(db_path, video_path, game_id, relational_game_id=_relational_game_id)
        _conn = sqlite3.connect(db_path)
        _conn.execute(
            "UPDATE analysis_runs SET status='completed', progress_pct=100, progress_step='Done', completed_at=CURRENT_TIMESTAMP WHERE analysis_key=? AND status='running'",
            (game_id,),
        )
        _conn.commit()
        _conn.close()
        print(f"[AI] analysis_runs updated to 'completed' for {game_id}")
    except Exception as e:
        _conn = sqlite3.connect(db_path)
        _conn.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE analysis_key=?",
            (str(e), game_id)
        )
        _conn.commit()
        _conn.close()
        print(f"[AI] analysis_runs updated to 'failed' for {game_id}: {e}")
        sys.exit(1)
