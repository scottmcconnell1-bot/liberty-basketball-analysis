#!/usr/bin/env python3
"""
Court-Marking Exclusion Benchmark Experiment
=============================================
Measures whether a court-marking exclusion mask improves the 138-frame
ball detection benchmark beyond the conf=0.25 production baseline.

Variants measured:
  1. baseline (conf=0.25, no mask)
  2. court_mask_neg_only (GT=0 frames only)
  3. court_mask_adaptive (distance-based, all frames)
  4. court_mask_strict (all frames, y-based zone)

Outputs:
  benchmark/court_mask_results.csv      - per-variant metrics
  benchmark/court_mask_comparison.csv   - side-by-side comparison
  benchmark/court_mask_overlays/        - masked detection overlays
"""
import os, csv, cv2, math, numpy as np
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

from ultralytics import YOLO

# ── Config ──
MODEL_PATH = 'models/ball_detector.pt'
CLASS_ID = 0
CONF = 0.25
IOU_THRESHOLD = 0.5
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
OVERLAYS_DIR = os.path.join(OUT_DIR, 'court_mask_overlays')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

# Court marking zone: the classify_fp heuristic marks detections as "court_marking"
# when cy > h*0.3 AND w*0.15 < cx < w*0.85
# Frame is 1280x720
COURT_ZONE_Y_MIN = int(720 * 0.30)   # 216
COURT_ZONE_X_MIN = int(1280 * 0.15)   # 192
COURT_ZONE_X_MAX = int(1280 * 0.85)   # 1088

# Adaptive: detections further than this from any GT ball in the court zone
# are classified as court-marking FPs
COURT_FP_DISTANCE_THRESHOLD = 150  # px — ~5x max GT box dimension

print("Loading model...")
model = YOLO(MODEL_PATH, verbose=False)
print(f"  Classes: {model.names}")

# ── Helpers ──
def iou_yolo(b1, b2):
    cx1,cy1,w1,h1 = b1; cx2,cy2,w2,h2 = b2
    x1,y1,x2,y2 = cx1-w1/2, cy1-h1/2, cx1+w1/2, cy1+h1/2
    x3,y3,x4,y4 = cx2-w2/2, cy2-h2/2, cx2+w2/2, cy2+h2/2
    xi,yi,xj,yj = max(x1,x3),max(y1,y3),min(x2,x4),min(y2,y4)
    if xj<=xi or yj<=yi: return 0.
    return (xj-xi)*(yj-yi)/(w1*h1+w2*h2-(xj-xi)*(yj-yi))

def iou_pixel(box1_px, box2_px):
    x1 = max(box1_px[0], box2_px[0])
    y1 = max(box1_px[1], box2_px[1])
    x2 = min(box1_px[2], box2_px[2])
    y2 = min(box1_px[3], box2_px[3])
    if x2 <= x1 or y2 <= y1: return 0.0
    inter = (x2-x1)*(y2-y1)
    a1 = (box1_px[2]-box1_px[0])*(box1_px[3]-box1_px[1])
    a2 = (box2_px[2]-box2_px[0])*(box2_px[3]-box2_px[1])
    return inter/(a1+a2-inter)

def load_gt(label_path):
    boxes = []
    if os.path.exists(label_path):
        with open(label_path) as f:
            for l in f:
                parts = l.strip().split()
                if len(parts)==5:
                    boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def run_model(frame, conf):
    results = model(frame, classes=[CLASS_ID], conf=conf, verbose=False, imgsz=640)
    dets = []
    for r in results:
        if r.boxes is not None:
            for box in r.boxes:
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                cf = float(box.conf[0])
                hf,wf = frame.shape[:2]
                cx = ((x1+x2)/2)/wf
                cy = ((y1+y2)/2)/hf
                w = (x2-x1)/wf
                h = (y2-y1)/hf
                dets.append({
                    'cx': cx, 'cy': cy, 'w': w, 'h': h, 'conf': cf,
                    'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                    'px_cx': int((x1+x2)/2), 'px_cy': int((y1+y2)/2),
                })
    return dets

def nms(dets, iou_thresh=0.3):
    if len(dets) <= 1: return list(range(len(dets)))
    scores = [d['conf'] for d in dets]
    order = sorted(range(len(dets)), key=lambda i: scores[i], reverse=True)
    keep = []
    while order:
        i = order[0]
        keep.append(i)
        rest = []
        for j in order[1:]:
            iou = iou_yolo(
                (dets[i]['cx'], dets[i]['cy'], dets[i]['w'], dets[i]['h']),
                (dets[j]['cx'], dets[j]['cy'], dets[j]['w'], dets[j]['h'])
            )
            if iou < iou_thresh:
                rest.append(j)
        order = rest
    return keep

def is_in_court_zone(det):
    """Check if detection is in the heuristic court-marking zone."""
    px_cx, px_cy = det['px_cx'], det['px_cy']
    return px_cy > COURT_ZONE_Y_MIN and COURT_ZONE_X_MIN < px_cx < COURT_ZONE_X_MAX

def dist_to_nearest_gt(det, gt_boxes, frame_shape):
    """Pixel distance from detection center to nearest GT box center."""
    h, w = frame_shape[:2]
    if not gt_boxes:
        return float('inf')
    min_dist = float('inf')
    for gt in gt_boxes:
        gt_cx, gt_cy = int(gt[0] * w), int(gt[1] * h)
        d = math.sqrt((det['px_cx'] - gt_cx)**2 + (det['px_cy'] - gt_cy)**2)
        min_dist = min(min_dist, d)
    return min_dist

# ── Mask functions ──
def mask_neg_only_court_zone(dets, gt_boxes, frame_shape):
    """Remove court-zone detections only in frames with no GT balls."""
    if len(gt_boxes) > 0:
        return dets, []  # no masking in positive frames
    removed = []
    kept = []
    for det in dets:
        if is_in_court_zone(det):
            removed.append(det)
        else:
            kept.append(det)
    return kept, removed

def mask_adaptive_distance(dets, gt_boxes, frame_shape):
    """Remove court-zone detections that are far from any GT ball (>150px)."""
    h, w = frame_shape[:2]
    removed = []
    kept = []
    for det in dets:
        if is_in_court_zone(det) and len(gt_boxes) > 0:
            d = dist_to_nearest_gt(det, gt_boxes, frame_shape)
            if d > COURT_FP_DISTANCE_THRESHOLD:
                removed.append(det)
                continue
        elif is_in_court_zone(det) and len(gt_boxes) == 0:
            # No GT balls: all court-zone detections are FPs
            removed.append(det)
            continue
        kept.append(det)
    return kept, removed

def mask_strict_court_zone(dets, gt_boxes, frame_shape):
    """Remove ALL detections in court zone (aggressive — measures cost)."""
    removed = []
    kept = []
    for det in dets:
        if is_in_court_zone(det):
            removed.append(det)
        else:
            kept.append(det)
    return kept, removed

def match_and_measure(dets, gt_boxes, iou_thresh=IOU_THRESHOLD):
    """Match detections to GT using IoU, return TP, FP, FN."""
    h, w = 720, 1280
    matched_det = set()
    for gt in gt_boxes:
        best_i, best_j = 0, -1
        for j, det in enumerate(dets):
            if j in matched_det: continue
            i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
            if i > best_i: best_i, best_j = i, j
        if best_i >= iou_thresh:
            matched_det.add(best_j)
    tp = len(matched_det)
    fp = len(dets) - tp
    fn = len(gt_boxes) - tp
    return tp, fp, fn

def compute_metrics(tp, fp, fn):
    prec = tp/(tp+fp) if (tp+fp)>0 else 0
    recall = tp/(tp+fn) if (tp+fn)>0 else 0
    f1 = 2*prec*recall/(prec+recall) if (prec+recall)>0 else 0
    return round(prec,4), round(recall,4), round(f1,4)

def draw_overlay(frame, gt_boxes, dets_before, dets_after, removed, title, variant_name, fname):
    """Draw GT (green), surviving detections (blue), removed (red X)."""
    h, w = frame.shape[:2]
    out = frame.copy()
    # Draw removed detections (what the mask removed)
    for det in removed:
        cx, cy = det['px_cx'], det['px_cy']
        cv2.drawMarker(out, (cx, cy), (0,0,255), cv2.MARKER_TILTED_CROSS, 12, 2)
    # Draw surviving detections
    for det in dets_after:
        x1,y1,x2,y2 = int(det['x1']), int(det['y1']), int(det['x2']), int(det['y2'])
        cv2.rectangle(out, (x1,y1), (x2,y2), (255,128,0), 1)
    # Draw GT
    for box in gt_boxes:
        cx, cy, bw, bh = box
        x1,y1,x2,y2 = int((cx-bw/2)*w), int((cy-bh/2)*h), int((cx+bw/2)*w), int((cy+bh/2)*h)
        cv2.rectangle(out, (x1,y1), (x2,y2), (0,255,0), 2)
    cv2.putText(out, title, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
    cv2.putText(out, f'removed={len(removed)} surv={len(dets_after)}', (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,0,255), 1)
    return out

# ── Load frames ──
frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])
print(f"\n{len(frame_files)} benchmark frames loaded")

# ── Pre-compute all detections at conf=0.25 (cache for speed) ──
print("\n=== Running detector on all frames at conf=0.25 ===")
all_frame_data = {}
for fname in frame_files:
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    if frame is None: continue
    gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
    dets = run_model(frame, CONF)
    all_frame_data[fname] = {
        'frame': frame,
        'gt': gt_boxes,
        'dets': dets,
    }

# ── Pre-compute NMS detections ──
print("Computing NMS variants...")
for fname in all_frame_data:
    dets = all_frame_data[fname]['dets']
    keep_idx = nms(dets)
    all_frame_data[fname]['dets_nms'] = [dets[i] for i in keep_idx]

# ═══════════════════════════════════════════
# Run all variants
# ═══════════════════════════════════════════
VARIANTS = [
    ('baseline', None, False),
    ('baseline_nms', None, True),
    ('court_mask_neg_only', mask_neg_only_court_zone, False),
    ('court_mask_neg_only_nms', mask_neg_only_court_zone, True),
    ('court_mask_adaptive', mask_adaptive_distance, False),
    ('court_mask_adaptive_nms', mask_adaptive_distance, True),
    ('court_mask_strict', mask_strict_court_zone, False),
    ('court_mask_strict_nms', mask_strict_court_zone, True),
]

all_results = []
per_frame_records = []

print("\n=== Measuring all variants ===")
for variant_name, mask_fn, use_nms in VARIANTS:
    total_tp, total_fp, total_fn = 0, 0, 0
    total_removed = 0
    frames_with_removals = 0

    for fname in frame_files:
        if fname not in all_frame_data:
            continue
        fd = all_frame_data[fname]
        frame = fd['frame']
        gt_boxes = fd['gt']
        dets = fd['dets_nms'] if use_nms else fd['dets']

        # Apply mask
        if mask_fn is not None:
            dets_after, removed = mask_fn(dets, gt_boxes, frame.shape)
            total_removed += len(removed)
            if len(removed) > 0:
                frames_with_removals += 1
        else:
            dets_after = dets
            removed = []

        tp, fp, fn = match_and_measure(dets_after, gt_boxes)
        total_tp += tp
        total_fp += fp
        total_fn += fn

        per_frame_records.append({
            'variant': variant_name,
            'frame': fname,
            'n_det_before': len(dets),
            'n_removed': len(removed if mask_fn else []),
            'n_det_after': len(dets_after),
            'tp': tp, 'fp': fp, 'fn': fn,
        })

    prec, recall, f1 = compute_metrics(total_tp, total_fp, total_fn)
    result = {
        'variant': variant_name,
        'conf': CONF,
        'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
        'precision': prec, 'recall': recall, 'f1': f1,
        'total_removed': total_removed,
        'frames_with_removals': frames_with_removals,
    }
    all_results.append(result)
    nms_tag = '+NMS' if use_nms else ''
    print(f"  {variant_name}: TP={total_tp} FP={total_fp} FN={total_fn} P={prec:.4f} R={recall:.4f} F1={f1:.4f} removed={total_removed} ({frames_with_removals} frames)")

# Write results
with open(os.path.join(OUT_DIR, 'court_mask_results.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','conf','tp','fp','fn','precision','recall','f1','total_removed','frames_with_removals'])
    writer.writeheader()
    writer.writerows(all_results)
print(f"\nWritten: {OUT_DIR}/court_mask_results.csv")

# Write per-frame detail
with open(os.path.join(OUT_DIR, 'court_mask_per_frame.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','frame','n_det_before','n_removed','n_det_after','tp','fp','fn'])
    writer.writeheader()
    writer.writerows(per_frame_records)
print(f"Written: {OUT_DIR}/court_mask_per_frame.csv")

# ═══════════════════════════════════════════
# Generate overlays for frames with removals
# ═══════════════════════════════════════════
print("\n=== Generating overlays for court_mask_adaptive ===")
overlay_count = 0
for fname in frame_files:
    if fname not in all_frame_data:
        continue
    fd = all_frame_data[fname]
    frame = fd['frame']
    gt_boxes = fd['gt']
    dets = fd['dets']

    dets_after, removed = mask_adaptive_distance(dets, gt_boxes, frame.shape)
    if len(removed) == 0:
        continue

    tp, fp, fn = match_and_measure(dets_after, gt_boxes)
    tp_before, fp_before, fn_before = match_and_measure(dets, gt_boxes)

    fp_after_val = fp
    title = f"removed:{len(removed)} FP_before:{fp_before}->{fp_after_val}"
    overlay = draw_overlay(frame, gt_boxes, dets, dets_after, removed,
                           f'adaptive_mask: -{len(removed)} dets', 'court_mask_adaptive', fname)

    # Write with info in filename: how many removed, impact on fp
    base = fname.replace('.jpg', '')
    out_path = os.path.join(OVERLAYS_DIR, f'adaptive_masked_{base}.jpg')
    cv2.imwrite(out_path, overlay)
    overlay_count += 1

    if overlay_count <= 10:
        print(f"  {out_path}: removed={len(removed)}, FP {fp_before}->{fp}, TP {tp_before}->{tp}")

print(f"Overlays written: {overlay_count} files in {OVERLAYS_DIR}/")

print("\nDONE — Court-marking exclusion experiment complete")
