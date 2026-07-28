#!/usr/bin/env python3
"""
Ball Detection Precision Cleanup
=================================
Phase 1: FP classification — run production path on 138 frames, classify every FP
Phase 2: Confidence sweep — TP/FP/FN at 0.15, 0.20, 0.25, 0.30, 0.40, 0.50
Phase 3: Post-processing — NMS, top-1, scoreboard mask at best threshold

Outputs:
  benchmark/precision_analysis.csv     — per-FP classification
  benchmark/confidence_sweep.csv       — TP/FP/FN per threshold
  benchmark/postprocess_results.csv    — post-processing comparison
  benchmark/precision_overlays/        — annotated FP/FN/multi-detection frames
"""
import os, csv, cv2, numpy as np
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

from ultralytics import YOLO

# ── Config ──
MODEL_PATH = 'models/ball_detector.pt'
CLASS_ID = 0
CONF_DEFAULT = 0.15
IOU_THRESHOLD = 0.5
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
OVERLAYS_DIR = os.path.join(OUT_DIR, 'precision_overlays')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

# Basket positions in 720p (from prior analysis)
BASKET_LEFT = (260, 566)
BASKET_RIGHT = (691, 449)
BASKET_RADIUS_PX = 80  # FP within this distance of basket = "hoop/rim"

# Scoreboard region: top 15% of frame, right half
SCOREBOARD_Y_MAX = int(720 * 0.15)
SCOREBOARD_X_MIN = int(1280 * 0.5)

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
    """IoU between two boxes in pixel coords (x1,y1,x2,y2)."""
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

def run_production_path(frame, conf):
    """Run the production ball detection path: model.classes=[0], given conf."""
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

def classify_fp(det, gt_boxes, frame_shape):
    """Classify a false positive detection."""
    h, w = frame_shape[:2]
    px_cx, px_cy = det['px_cx'], det['px_cy']
    det_box_px = (int(det['x1']), int(det['y1']), int(det['x2']), int(det['y2']))
    
    # Check if it's a duplicate (IoU > 0.3 with a GT ball — but it's FP so it didn't match at 0.5)
    # Check IoU with GT at lower threshold
    for gt in gt_boxes:
        gt_cx, gt_cy, gt_w, gt_h = gt
        gt_box_px = (int((gt_cx-gt_w/2)*w), int((gt_cy-gt_h/2)*h),
                     int((gt_cx+gt_w/2)*w), int((gt_cy+gt_h/2)*h))
        if iou_pixel(det_box_px, gt_box_px) > 0.3:
            return 'duplicate_near_ball'
    
    # Check basket proximity
    dist_left = np.sqrt((px_cx - BASKET_LEFT[0])**2 + (px_cy - BASKET_LEFT[1])**2)
    dist_right = np.sqrt((px_cx - BASKET_RIGHT[0])**2 + (px_cy - BASKET_RIGHT[1])**2)
    if min(dist_left, dist_right) < BASKET_RADIUS_PX:
        return 'hoop_rim'
    
    # Check scoreboard region
    if px_cy < SCOREBOARD_Y_MAX and px_cx > SCOREBOARD_X_MIN:
        return 'scoreboard_clock'
    
    # Check if in top 15% of frame (general)
    if px_cy < h * 0.15:
        return 'top_of_frame'
    
    # Check if on court floor (bottom 70% of frame, center x range)
    if px_cy > h * 0.3 and w * 0.15 < px_cx < w * 0.85:
        return 'court_marking'
    
    return 'uncertain'

def draw_overlay(frame, gt_boxes, dets, title, labels=None):
    """Draw GT (green), detections (red), labels."""
    h, w = frame.shape[:2]
    out = frame.copy()
    for box in gt_boxes:
        cx, cy, bw, bh = box
        x1,y1,x2,y2 = int((cx-bw/2)*w), int((cy-bh/2)*h), int((cx+bw/2)*w), int((cy+bh/2)*h)
        cv2.rectangle(out, (x1,y1), (x2,y2), (0,255,0), 2)
        cv2.putText(out, 'GT', (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
    for i, det in enumerate(dets):
        x1,y1,x2,y2 = int(det['x1']), int(det['y1']), int(det['x2']), int(det['y2'])
        cv2.rectangle(out, (x1,y1), (x2,y2), (0,0,255), 1)
        label = labels[i] if labels else f'{det["conf"]:.3f}'
        cv2.putText(out, label, (x1, y2+12), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0,0,255), 1)
    cv2.putText(out, title, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
    return out

# ── Load frame list ──
frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])
print(f"\n{len(frame_files)} benchmark frames loaded")

# ═══════════════════════════════════════════
# Phase 1: FP Classification at conf=0.15
# ═══════════════════════════════════════════
print("\n=== Phase 1: FP Classification (conf=0.15) ===")

fp_classifications = []  # per-FP records
fn_frames = []           # frames with false negatives
multi_det_frames = []    # frames with 3+ detections
top10_fp = []            # highest-confidence FPs for overlay

for fname in frame_files:
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    if frame is None: continue
    gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
    dets = run_production_path(frame, CONF_DEFAULT)
    
    # Match detections to GT
    matched_det = set()
    for gt in gt_boxes:
        best_i, best_j = 0, -1
        for j, det in enumerate(dets):
            if j in matched_det: continue
            i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
            if i > best_i: best_i, best_j = i, j
        if best_i >= IOU_THRESHOLD:
            matched_det.add(best_j)
    
    # Classify unmatched detections (FPs)
    fp_dets = [d for j, d in enumerate(dets) if j not in matched_det]
    for det in fp_dets:
        fp_class = classify_fp(det, gt_boxes, frame.shape)
        fp_classifications.append({
            'frame': fname,
            'conf': det['conf'],
            'px_cx': det['px_cx'],
            'px_cy': det['px_cy'],
            'classification': fp_class,
            'gt_boxes_in_frame': len(gt_boxes),
        })
        top10_fp.append((det['conf'], fname, det, fp_class, gt_boxes, frame.shape))
    
    # Track FN frames
    fn_count = len(gt_boxes) - len(matched_det)
    if fn_count > 0:
        fn_frames.append((fname, fn_count, len(gt_boxes), dets, gt_boxes))
    
    # Track multi-detection frames
    if len(dets) >= 3:
        multi_det_frames.append((fname, len(dets), len(gt_boxes), dets, gt_boxes))

# Sort FPs by confidence for top-10 overlay
top10_fp.sort(key=lambda x: x[0], reverse=True)

# Print FP classification summary
from collections import Counter
fp_counts = Counter(fc['classification'] for fc in fp_classifications)
print(f"\nFP Classification ({len(fp_classifications)} total FPs):")
for cls, count in fp_counts.most_common():
    print(f"  {cls}: {count} ({count/len(fp_classifications)*100:.1f}%)")

print(f"\nFN frames: {len(fn_frames)}")
print(f"Multi-detection frames (3+ dets): {len(multi_det_frames)}")

# Write precision_analysis.csv
with open(os.path.join(OUT_DIR, 'precision_analysis.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['frame','conf','px_cx','px_cy','classification','gt_boxes_in_frame'])
    writer.writeheader()
    writer.writerows(fp_classifications)
print(f"Written: {OUT_DIR}/precision_analysis.csv")

# ═══════════════════════════════════════════
# Phase 1b: Generate Overlays
# ═══════════════════════════════════════════
print("\n=== Phase 1b: Generating Overlays ===")

# Top 10 highest-confidence FPs
for i, (conf, fname, det, fp_class, gt_boxes, shape) in enumerate(top10_fp[:10]):
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    all_dets = run_production_path(frame, CONF_DEFAULT)
    labels = [f'{d["conf"]:.3f}' for d in all_dets]
    overlay = draw_overlay(frame, gt_boxes, all_dets,
                           f'FP #{i+1} conf={conf:.3f} [{fp_class}]', labels)
    out_path = os.path.join(OVERLAYS_DIR, f'fp_top{i+1:02d}_{fname}')
    cv2.imwrite(out_path, overlay)
    print(f'  {out_path}')

# FN frames
for i, (fname, fn_count, gt_count, dets, gt_boxes) in enumerate(fn_frames):
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    overlay = draw_overlay(frame, gt_boxes, dets,
                           f'FN #{i+1}: {fn_count}/{gt_count} missed')
    out_path = os.path.join(OVERLAYS_DIR, f'fn_{i+1:02d}_{fname}')
    cv2.imwrite(out_path, overlay)
    print(f'  {out_path}')

# Multi-detection frames (top 5 by detection count)
multi_det_frames.sort(key=lambda x: x[1], reverse=True)
for i, (fname, n_dets, n_gt, dets, gt_boxes) in enumerate(multi_det_frames[:5]):
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    overlay = draw_overlay(frame, gt_boxes, dets,
                           f'Multi: {n_dets} dets, {n_gt} GT')
    out_path = os.path.join(OVERLAYS_DIR, f'multi_{i+1:02d}_{fname}')
    cv2.imwrite(out_path, overlay)
    print(f'  {out_path}')

print(f"Overlays written to {OVERLAYS_DIR}/")

# ═══════════════════════════════════════════
# Phase 2: Confidence Sweep
# ═══════════════════════════════════════════
print("\n=== Phase 2: Confidence Sweep ===")

CONF_SWEEP = [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
sweep_results = []

for conf in CONF_SWEEP:
    total_tp, total_fp, total_fn = 0, 0, 0
    for fname in frame_files:
        frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
        if frame is None: continue
        gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
        dets = run_production_path(frame, conf)
        
        matched_det = set()
        for gt in gt_boxes:
            best_i, best_j = 0, -1
            for j, det in enumerate(dets):
                if j in matched_det: continue
                i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
                if i > best_i: best_i, best_j = i, j
            if best_i >= IOU_THRESHOLD:
                matched_det.add(best_j)
        
        tp = len(matched_det)
        fp = len(dets) - tp
        fn = len(gt_boxes) - tp
        total_tp += tp; total_fp += fp; total_fn += fn
    
    prec = total_tp/(total_tp+total_fp) if (total_tp+total_fp)>0 else 0
    recall = total_tp/(total_tp+total_fn) if (total_tp+total_fn)>0 else 0
    f1 = 2*prec*recall/(prec+recall) if (prec+recall)>0 else 0
    sweep_results.append({
        'conf': conf, 'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
        'precision': round(prec,4), 'recall': round(recall,4), 'f1': round(f1,4),
    })
    print(f"  conf={conf:.2f}: TP={total_tp} FP={total_fp} FN={total_fn} P={prec:.4f} R={recall:.4f} F1={f1:.4f}")

with open(os.path.join(OUT_DIR, 'confidence_sweep.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['conf','tp','fp','fn','precision','recall','f1'])
    writer.writeheader()
    writer.writerows(sweep_results)
print(f"Written: {OUT_DIR}/confidence_sweep.csv")

# Find best F1 threshold
best = max(sweep_results, key=lambda x: x['f1'])
print(f"\nBest F1: conf={best['conf']:.2f} P={best['precision']:.4f} R={best['recall']:.4f} F1={best['f1']:.4f}")

# ═══════════════════════════════════════════
# Phase 3: Post-Processing at best threshold
# ═══════════════════════════════════════════
print(f"\n=== Phase 3: Post-Processing (conf={best['conf']:.2f}) ===")

def nms(dets, iou_thresh=0.3):
    """Non-maximum suppression. Returns indices to keep."""
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

def scoreboard_mask(dets):
    """Remove detections in scoreboard region."""
    return [d for d in dets
            if not (d['px_cy'] < SCOREBOARD_Y_MAX and d['px_cx'] > SCOREBOARD_X_MIN)]

postprocess_results = []

for variant_name, apply_nms, apply_mask, top1 in [
    ('threshold_only', False, False, False),
    ('threshold_top1', False, False, True),
    ('threshold_nms', True, False, False),
    ('threshold_mask', False, True, False),
    ('threshold_nms_mask', True, True, False),
    ('threshold_nms_mask_top1', True, True, True),
]:
    total_tp, total_fp, total_fn = 0, 0, 0
    for fname in frame_files:
        frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
        if frame is None: continue
        gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
        dets = run_production_path(frame, best['conf'])
        
        if apply_mask:
            dets = scoreboard_mask(dets)
        if apply_nms:
            keep_idx = nms(dets)
            dets = [dets[i] for i in keep_idx]
        if top1 and dets:
            dets = [max(dets, key=lambda d: d['conf'])]
        
        matched_det = set()
        for gt in gt_boxes:
            best_i, best_j = 0, -1
            for j, det in enumerate(dets):
                if j in matched_det: continue
                i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
                if i > best_i: best_i, best_j = i, j
            if best_i >= IOU_THRESHOLD:
                matched_det.add(best_j)
        
        tp = len(matched_det)
        total_tp += tp
        total_fp += len(dets) - tp
        total_fn += len(gt_boxes) - tp
    
    prec = total_tp/(total_tp+total_fp) if (total_tp+total_fp)>0 else 0
    recall = total_tp/(total_tp+total_fn) if (total_tp+total_fn)>0 else 0
    f1 = 2*prec*recall/(prec+recall) if (prec+recall)>0 else 0
    postprocess_results.append({
        'variant': variant_name,
        'conf': best['conf'],
        'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
        'precision': round(prec,4), 'recall': round(recall,4), 'f1': round(f1,4),
    })
    print(f"  {variant_name}: TP={total_tp} FP={total_fp} FN={total_fn} P={prec:.4f} R={recall:.4f} F1={f1:.4f}")

with open(os.path.join(OUT_DIR, 'postprocess_results.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','conf','tp','fp','fn','precision','recall','f1'])
    writer.writeheader()
    writer.writerows(postprocess_results)
print(f"Written: {OUT_DIR}/postprocess_results.csv")

print("\nDONE — All phases complete")
