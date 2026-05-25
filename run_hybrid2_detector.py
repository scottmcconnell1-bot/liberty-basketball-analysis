"""
Hybrid ball detector v2: YOLO primary, color+shape verification.
Strategy:
  1. Run YOLO abdullahtarek ball detector at low conf threshold (0.10)
  2. For each YOLO detection, verify with basketball color at center pixel
  3. Filter based on ball-like area/size
  4. Use temporal consistency (track across frames) to reject false positives
"""
import cv2, numpy as np, os, time, pickle
from ultralytics import YOLO
from collections import defaultdict

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

# Basketball HSV ranges (calibrated from actual footage)
# The ball appears in various shades due to gym lighting - wide range needed
BALL_HSV_RANGES = [
    (np.array([5, 30, 50]), np.array([25, 255, 255])),   # Standard orange
    (np.array([0, 40, 40]), np.array([12, 255, 255])),   # Red-orange
    (np.array([3, 20, 30]), np.array([28, 200, 200])),   # Dim/desaturated
    (np.array([5, 25, 30]), np.array([18, 180, 150])),   # Brown-worn
]

# Size constraints (calibrated for ceiling camera at 1280x720)
MIN_BALL_AREA = 50
MAX_BALL_AREA = 3000
MIN_CIRCULARITY = 0.35


def is_basketball_color(hsv_img, cx, cy, radius=5):
    """Check if pixels around (cx,cy) match basketball color ranges."""
    h, w = hsv_img.shape[:2]
    y1, y2 = max(0, cy-radius), min(h, cy+radius+1)
    x1, x2 = max(0, cx-radius), min(w, cx+radius+1)
    roi = hsv_img[y1:y2, x1:x2].reshape(-1, 3)

    for lower, upper in BALL_HSV_RANGES:
        in_range = np.all((roi >= lower) & (roi <= upper), axis=1)
        fraction = np.sum(in_range) / len(roi)
        if fraction > 0.4:  # at least 40% of pixels match
            return True, fraction
    return False, 0.0


def verify_yolo_detection(frame, box, hsv):
    """Verify a YOLO basketball detection using color and shape."""
    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
    w = x2 - x1
    h = y2 - y1
    area = w * h
    conf = float(box.conf[0])

    # Size filter
    if area < MIN_BALL_AREA or area > MAX_BALL_AREA:
        return None, 'size_rejected'

    # Circularity check
    perimeter = 2 * (w + h)
    if perimeter > 0:
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < MIN_CIRCULARITY:
            return None, 'shape_rejected'

    # Color check: sample center region of detection
    cx, cy = (x1+x2)//2, (y1+y2)//2
    color_ok, color_frac = is_basketball_color(hsv, cx, cy, radius=4)

    if not color_ok:
        # Try sampling multiple points within the detection
        offsets = [(0,0), (-w//4,0), (w//4,0), (0,-h//4), (0,h//4)]
        for dx, dy in offsets:
            color_ok, color_frac = is_basketball_color(hsv, cx+dx, cy+dy, radius=3)
            if color_ok:
                break

    if not color_ok:
        return None, 'color_rejected'

    return {
        'cx': float(cx), 'cy': float(cy),
        'w': float(w), 'h': float(h),
        'area': float(area),
        'yolo_conf': conf,
        'color_match': color_frac,
        'conf': conf * 0.6 + color_frac * 0.4
    }, 'accepted'


def detect_balls_v2(frame, yolo_model, conf_threshold=0.10):
    """Ball detection: YOLO primary + color/shape verification."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    results = yolo_model.predict(frame, conf=conf_threshold, verbose=False)[0]

    verified = []
    if results.boxes is not None:
        for box in results.boxes:
            cls = yolo_model.names[int(box.cls[0])]
            if cls != 'Ball':
                continue
            det, reason = verify_yolo_detection(frame, box, hsv)
            if det is not None:
                det['status'] = 'verified'
                verified.append(det)

    return verified


def track_balls(detections_by_frame):
    """
    Simple ball tracking across frames.
    Ball moves smoothly between frames; false positives jump around.
    Returns tracks as list of (frame, cx, cy, conf) lists.
    """
    tracks = []
    active_tracks = []

    max(max(detections_by_frame.keys()) + 1 if detections_by_frame else 0)
    all_frames = sorted(detections_by_frame.keys())

    for fn in all_frames:
        dets = detections_by_frame[fn]

        if not active_tracks:
            # Start new tracks from all detections
            for d in dets:
                active_tracks.append([(fn, d['cx'], d['cy'], d['conf'])])
            continue

        # Predicted positions from existing tracks
        used_dets = set()
        new_active = []

        for track in active_tracks:
            last_fn, last_cx, last_cy, last_conf = track[-1]
            frames_since_last = fn - last_fn

            if frames_since_last > 10:
                # Track lost, finalize
                if len(track) >= 2:
                    tracks.append(track)
                continue

            # Find best matching detection
            best_det = None
            best_dist = float('inf')

            # Max expected jump per frame (generous for fast-moving ball)
            max_jump = min(150, 30 * frames_since_last)

            for i, d in enumerate(dets):
                if i in used_dets:
                    continue
                dist = np.sqrt((d['cx'] - last_cx)**2 + (d['cy'] - last_cy)**2)
                if dist < max_jump and dist < best_dist:
                    best_dist = dist
                    best_det = i

            if best_det is not None:
                d = dets[best_det]
                track.append((fn, d['cx'], d['cy'], d['conf']))
                used_dets.add(best_det)
                new_active.append(track)
            else:
                if len(track) >= 2:
                    tracks.append(track)

        # Start new tracks from unmatched detections
        for i, d in enumerate(dets):
            if i not in used_dets:
                new_active.append([(fn, d['cx'], d['cy'], d['conf'])])

        active_tracks = new_active

    # Finalize remaining active tracks
    for track in active_tracks:
        if len(track) >= 2:
            tracks.append(track)

    return tracks


# ===== Run on full video =====
print("Loading YOLO model...")
ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')

print("Running ball detection (YOLO + color/shape verification)...")
cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

detections_by_frame = defaultdict(list)
all_detections = []
rejection_stats = defaultdict(int)
start = time.time()

fn = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    dets = detect_balls_v2(frame, ball_m, conf_threshold=0.10)
    detections_by_frame[fn] = dets

    for d in dets:
        all_detections.append({
            'frame': fn,
            'cx': round(d['cx'], 1),
            'cy': round(d['cy'], 1),
            'w': round(d['w'], 1),
            'h': round(d['h'], 1),
            'yolo_conf': round(d['yolo_conf'], 3),
            'color_match': round(d['color_match'], 3),
            'conf': round(d['conf'], 3)
        })

    fn += 1
    if fn % 500 == 0:
        elapsed = time.time() - start
        print("  %d/%d frames, %d verified detections, %.1f frames/sec" % (
            fn, total, len(all_detections), fn/elapsed if elapsed > 0 else 0))

cap.release()

print()
print("Detection complete: %d verified detections in %d frames (%.2f%%)" % (
    len(all_detections), total, len(all_detections)/total*100))
print("Avg detections per frame: %.2f" % (len(all_detections)/total))

# Save detections
import pandas as pd
df = pd.DataFrame(all_detections)
df.to_csv(OUT + '/hybrid2_ball_detections.csv', index=False)
print("Saved to hybrid2_ball_detections.csv")

# Run tracking
print()
print("Running ball tracking...")
tracks = track_balls(detections_by_frame)
print("Found %d tracks" % len(tracks))

# Track stats
track_lengths = [len(t) for t in tracks]
track_durations = [(t[-1][0] - t[0][0]) for t in tracks]
print("Track lengths: min=%d, max=%d, mean=%.1f" % (
    min(track_lengths), max(track_lengths), np.mean(track_lengths)))
print("Track durations (frames): min=%d, max=%d, mean=%.1f" % (
    min(track_durations), max(track_durations), np.mean(track_durations)))

# Save tracks
with open(OUT + '/hybrid2_tracks.pkl', 'wb') as f:
    pickle.dump(tracks, f)
print("Saved tracks to hybrid2_tracks.pkl")

# Save tracks as CSV (each detection + track_id)
track_dets = []
for track_id, track in enumerate(tracks):
    for fn, cx, cy, conf in track:
        track_dets.append({
            'track_id': track_id,
            'frame': fn,
            'cx': round(cx, 1),
            'cy': round(cy, 1),
            'conf': round(conf, 3)
        })
pd.DataFrame(track_dets).to_csv(OUT + '/hybrid2_tracks.csv', index=False)
print("Saved tracks CSV")

# Print top 20 longest tracks
print()
print("Top 20 longest tracks:")
sorted_tracks = sorted(tracks, key=lambda t: -len(t))
for i, t in enumerate(sorted_tracks[:20]):
    dur = t[-1][0] - t[0][0]
    cx_mean = np.mean([p[1] for p in t])
    cy_mean = np.mean([p[2] for p in t])
    cx_std = np.std([p[1] for p in t])
    cy_std = np.std([p[2] for p in t])
    print("  Track %d: %d frames, span=%d, center=(%.0f,%.0f), spread=(%.0f,%.0f)" % (
        tracks.index(t), len(t), dur, cx_mean, cy_mean, cx_std, cy_std))
