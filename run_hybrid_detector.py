"""
Final hybrid ball detector for Q1 footage.
Combines YOLO abdullahtarek with color-based filtering.
Calibrated to the specific gym lighting in this footage.
"""
import cv2, numpy as np, os, time, pickle
from ultralytics import YOLO
from collections import defaultdict

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

# Basketball color ranges calibrated from actual footage
# Gym lighting shifts the orange ball significantly
# True basketball under various gym lights: H can be 5-25 in OpenCV HSV
# But false positives often have H > 100 (blue/green from LED lights) or very low saturation

# Strategy: Multiple HSV ranges to catch the ball under different lighting
BASKETBALL_HSV_RANGES = [
    # Primary: good lighting, true orange
    (np.array([5, 40, 60]), np.array([25, 255, 255])),
    # Dim/warm lighting: lower saturation and value
    (np.array([3, 25, 40]), np.array([28, 200, 200])),
    # Saturated orange-red (ball under spotlight)
    (np.array([0, 80, 80]), np.array([10, 255, 255])),
    # Brownish/worn ball
    (np.array([5, 30, 30]), np.array([18, 180, 150])),
]

# Filters to eliminate false positives
MIN_BALL_AREA = 60
MAX_BALL_AREA = 2500
MIN_CIRCULARITY = 0.4
MAX_ASPECT_RATIO = 2.5


def detect_balls_color(frame):
    """Detect basketball-colored objects using calibrated HSV ranges."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Combine all HSV ranges
    combined_mask = np.zeros((frame.shape[0], frame.shape[1]), dtype=np.uint8)
    for lower, upper in BASKETBALL_HSV_RANGES:
        mask = cv2.inRange(hsv, lower, upper)
        combined_mask = cv2.bitwise_or(combined_mask, mask)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_BALL_AREA or area > MAX_BALL_AREA:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < MIN_CIRCULARITY:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / h if h > 0 else 0
        if aspect > MAX_ASPECT_RATIO or aspect < 1.0 / MAX_ASPECT_RATIO:
            continue

        cx, cy = x + w // 2, y + h // 2

        # Verify center pixel is basketball-colored
        center_hsv = hsv[cy, cx]
        if not (3 <= center_hsv[0] <= 28 and center_hsv[1] > 25):
            continue

        # Calculate mean saturation in ROI
        roi_mask = np.zeros(combined_mask.shape, dtype=np.uint8)
        cv2.drawContours(roi_mask, [cnt], -1, 255, -1)
        mean_sat = cv2.mean(hsv, mask=roi_mask)[1]
        mean_val = cv2.mean(hsv, mask=roi_mask)[2]

        # Confidence based on circularity, saturation, and area
        conf = min(1.0, circularity * 0.4 + (mean_sat / 255) * 0.4 + min(1.0, area / 500) * 0.2)

        candidates.append({
            'cx': float(cx), 'cy': float(cy),
            'w': float(w), 'h': float(h),
            'area': float(area),
            'circularity': float(circularity),
            'mean_sat': float(mean_sat),
            'mean_val': float(mean_val),
            'conf': float(conf),
            'source': 'color'
        })

    return candidates


def detect_balls_yolo(frame, model, conf_threshold=0.1):
    """Detect balls using YOLO abdullahtarek model."""
    results = model.predict(frame, conf=conf_threshold, verbose=False)[0]
    candidates = []
    if results.boxes is not None:
        for box in results.boxes:
            cls = model.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball':
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                candidates.append({
                    'cx': (x1+x2)/2, 'cy': (y1+y2)/2,
                    'w': x2-x1, 'h': y2-y1,
                    'conf': cf, 'source': 'yolo'
                })
    return candidates


def filter_yolo_by_color(frame, yolo_dets):
    """Filter YOLO detections: keep only those with basketball-colored center pixels."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    filtered = []

    for det in yolo_dets:
        cx, cy = int(det['cx']), int(det['cy'])
        if cy < 0 or cy >= frame.shape[0] or cx < 0 or cx >= frame.shape[1]:
            continue

        pixel_hsv = hsv[cy, cx]
        h_val = pixel_hsv[0]

        # REJECT if hue is in blue/green range (H > 30) — these are false positives
        # from blue/green gym lighting on non-ball objects
        if h_val > 30:
            continue

        # REJECT if saturation is very low (gray objects)
        if pixel_hsv[1] < 20:
            continue

        filtered.append(det)

    return filtered


def merge_detections(color_dets, yolo_dets, dist_threshold=40):
    """Merge color and color-filtered YOLO detections."""
    merged = []
    used_color = set()

    for j, yd in enumerate(yolo_dets):
        best_color = None
        best_dist = float('inf')
        for i, cd in enumerate(color_dets):
            if i in used_color:
                continue
            dist = np.sqrt((cd['cx'] - yd['cx'])**2 + (cd['cy'] - yd['cy'])**2)
            if dist < dist_threshold and dist < best_dist:
                best_dist = dist
                best_color = i

        if best_color is not None:
            # Both agree
            cd = color_dets[best_color]
            merged.append({
                'cx': yd['cx'], 'cy': yd['cy'],
                'w': yd['w'], 'h': yd['h'],
                'conf': max(yd['conf'], cd['conf']),
                'source': 'both'
            })
            used_color.add(best_color)
        else:
            # YOLO only, but passed color filter
            merged.append({
                'cx': yd['cx'], 'cy': yd['cy'],
                'w': yd['w'], 'h': yd['h'],
                'conf': yd['conf'] * 0.7,  # downweight YOLO-only
                'source': 'yolo_only'
            })

    # Add unmatched color detections
    for i, cd in enumerate(color_dets):
        if i not in used_color:
            merged.append({
                'cx': cd['cx'], 'cy': cd['cy'],
                'w': cd['w'], 'h': cd['h'],
                'conf': cd['conf'] * 0.5,  # downweight color-only
                'source': 'color_only'
            })

    return merged


def detect_balls(frame, yolo_model, conf_threshold=0.15):
    """Full hybrid ball detection pipeline."""
    # Get YOLO detections
    yolo_raw = detect_balls_yolo(frame, yolo_model, conf_threshold=conf_threshold)

    # Filter YOLO by color
    yolo_filtered = filter_yolo_by_color(frame, yolo_raw)

    # Get color detections
    color_dets = detect_balls_color(frame)

    # Merge
    merged = merge_detections(color_dets, yolo_filtered)

    return merged


# ===== Run on full video =====
print("Loading YOLO model...")
ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')

print("Processing video...")
cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

all_detections = []
start = time.time()

fn = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    dets = detect_balls(frame, ball_m, conf_threshold=0.15)
    for d in dets:
        all_detections.append({
            'frame': fn,
            'cx': round(d['cx'], 1),
            'cy': round(d['cy'], 1),
            'w': round(d['w'], 1),
            'h': round(d['h'], 1),
            'conf': round(d['conf'], 3),
            'source': d['source']
        })

    fn += 1
    if fn % 500 == 0:
        elapsed = time.time() - start
        det_count = len(all_detections)
        print("  %d/%d frames, %d detections, %.1f frames/sec" % (fn, total, det_count, fn/elapsed if elapsed > 0 else 0))

cap.release()

print()
print("Total detections: %d in %d frames (%.1f%%)" % (len(all_detections), total, len(all_detections)/total*100))
print("Avg detections per frame: %.2f" % (len(all_detections)/total))

# Save
import pandas as pd
df = pd.DataFrame(all_detections)
df.to_csv(OUT + '/hybrid_ball_detections.csv', index=False)
print("Saved to hybrid_ball_detections.csv")

# Stats by source
print()
print("Detections by source:")
print(df['source'].value_counts())
print()
print("Confidence stats:")
print(df['conf'].describe())
