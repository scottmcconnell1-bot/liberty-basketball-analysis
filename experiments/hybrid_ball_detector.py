"""
Hybrid basketball detector: YOLO abdullahtarek + precise color filtering.
Uses the official basketball color (HEX #ee6730, HSV ~9,204,238) to filter
YOLO detections and eliminate false positives.
"""
import cv2, numpy as np, os, time, pickle
from ultralytics import YOLO
from collections import defaultdict

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

# Official basketball color: HEX #ee6730, RGB(238,103,48), HSL(17,85%,56%)
# In OpenCV HSV: approximately H=9, S=204, V=238
# We use a range to account for lighting variations

# Primary orange range (bright basketball in good light)
LOWER_ORANGE1 = np.array([5, 100, 100])
UPPER_ORANGE1 = np.array([20, 255, 255])

# Secondary range for darker/indoor lighting
LOWER_ORANGE2 = np.array([3, 60, 60])
UPPER_ORANGE2 = np.array([22, 255, 240])

# Brown range for worn/dirty basketballs
LOWER_BROWN = np.array([5, 40, 30])
UPPER_BROWN = np.array([18, 200, 180])

# Basketball physical size: 9.4in diameter = 23.9cm
# At typical gym camera distance, ball is roughly 15-40 pixels in diameter
MIN_BALL_AREA = 80    # ~10px diameter minimum
MAX_BALL_AREA = 2000  # ~50px diameter maximum
MIN_CIRCULARITY = 0.5  # ball should be somewhat circular


def get_basketball_mask(hsv_frame):
    """Create a mask for basketball-colored pixels."""
    mask1 = cv2.inRange(hsv_frame, LOWER_ORANGE1, UPPER_ORANGE1)
    mask2 = cv2.inRange(hsv_frame, LOWER_ORANGE2, UPPER_ORANGE2)
    mask3 = cv2.inRange(hsv_frame, LOWER_BROWN, UPPER_BROWN)
    mask = cv2.bitwise_or(mask1, mask2)
    mask = cv2.bitwise_or(mask, mask3)
    # Clean up with morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def detect_ball_color(frame):
    """Detect basketball using color segmentation + shape filtering."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = get_basketball_mask(hsv)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_BALL_AREA or area > MAX_BALL_AREA:
            continue

        # Check circularity
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < MIN_CIRCULARITY:
            continue

        # Get bounding box and center
        x, y, w, h = cv2.boundingRect(cnt)
        cx, cy = x + w // 2, y + h // 2
        aspect = w / h if h > 0 else 0
        if aspect < 0.5 or aspect > 2.0:
            continue

        # Check that the center pixel is actually basketball-colored
        center_hsv = hsv[cy, cx]
        if not (5 <= center_hsv[0] <= 22 and center_hsv[1] > 60):
            continue

        # Calculate average saturation in the region (higher = more likely ball)
        roi_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(roi_mask, [cnt], -1, 255, -1)
        mean_sat = cv2.mean(hsv, mask=roi_mask)[1]

        candidates.append({
            'cx': cx, 'cy': cy, 'w': w, 'h': h,
            'area': area, 'circularity': circularity,
            'mean_saturation': mean_sat,
            'aspect': aspect,
            'conf': min(1.0, circularity * mean_sat / 128)  # heuristic confidence
        })

    return candidates


def detect_ball_yolo(frame, model, conf=0.1):
    """Detect basketball using YOLO model."""
    results = model.predict(frame, conf=conf, verbose=False)[0]
    candidates = []
    if results.boxes is not None:
        for box in results.boxes:
            cls = model.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball':
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                w, h = x2 - x1, y2 - y1
                candidates.append({
                    'cx': cx, 'cy': cy, 'w': w, 'h': h,
                    'conf': cf, 'source': 'yolo'
                })
    return candidates


def merge_detections(color_dets, yolo_dets, iou_threshold=0.3):
    """Merge color and YOLO detections. Prefer YOLO when both agree."""
    merged = []
    used_yolo = set()

    for cd in color_dets:
        best_yolo = None
        best_dist = float('inf')
        for j, yd in enumerate(yolo_dets):
            if j in used_yolo:
                continue
            dist = np.sqrt((cd['cx'] - yd['cx'])**2 + (cd['cy'] - yd['cy'])**2)
            if dist < 50 and dist < best_dist:
                best_dist = dist
                best_yolo = j

        if best_yolo is not None:
            # Both agree — use YOLO position with combined confidence
            yd = yolo_dets[best_yolo]
            merged.append({
                'cx': yd['cx'], 'cy': yd['cy'],
                'w': yd['w'], 'h': yd['h'],
                'conf': max(yd['conf'], cd.get('conf', 0)),
                'source': 'both'
            })
            used_yolo.add(best_yolo)
        else:
            # Only color detection
            merged.append({
                'cx': cd['cx'], 'cy': cd['cy'],
                'w': cd['w'], 'h': cd['h'],
                'conf': cd.get('conf', 0.3),
                'source': 'color'
            })

    # Add unmatched YOLO detections
    for j, yd in enumerate(yolo_dets):
        if j not in used_yolo:
            merged.append({
                'cx': yd['cx'], 'cy': yd['cy'],
                'w': yd['w'], 'h': yd['h'],
                'conf': yd['conf'],
                'source': 'yolo_only'
            })

    return merged


# ===== Test on sample frames =====
print("Loading models...")
ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# Test on frames around known shots
test_frames = [260, 685, 1462, 1469, 2489]

for fn in test_frames:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue

    color_dets = detect_ball_color(frame)
    yolo_dets = detect_ball_yolo(frame, ball_m, conf=0.1)
    merged = merge_detections(color_dets, yolo_dets)

    print(f"\nF{fn}:")
    print(f"  Color detections: {len(color_dets)}")
    for cd in color_dets:
        print(f"    ({cd['cx']:.0f},{cd['cy']:.0f}) area={cd['area']:.0f} circ={cd['circularity']:.2f} sat={cd['mean_saturation']:.0f} conf={cd['conf']:.3f}")
    print(f"  YOLO detections: {len(yolo_dets)}")
    for yd in yolo_dets:
        print(f"    ({yd['cx']:.0f},{yd['cy']:.0f}) conf={yd['conf']:.3f}")
    print(f"  Merged: {len(merged)}")
    for m in merged:
        print(f"    ({m['cx']:.0f},{m['cy']:.0f}) conf={m['conf']:.3f} src={m['source']}")

cap.release()
print("\nDone.")
