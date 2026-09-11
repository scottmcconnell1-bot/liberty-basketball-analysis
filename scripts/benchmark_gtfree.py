#!/usr/bin/env python3
"""
GT-Free Court-Marking Exclusion Benchmark Experiments
=====================================================
Measures production-feasible court-marking exclusion methods that do NOT
use ground-truth ball positions. All methods use only per-frame detections
(available at inference time).

Variants measured:
  1. baseline (conf=0.25, no exclusion) — reproduces known baseline
  2. top1_per_frame (keep highest-conf detection per frame)
  3. top2_per_frame (keep top-2 by conf per frame)
  4. grid_top1_4x2 (4x2 grid, top-1 per cell)
  5. grid_top1_6x3 (6x3 grid, top-1 per cell)
  6. grid_top2_6x3 (6x3 grid, top-2 per cell)
  7. nms_iou30 (NMS IoU=0.3) — equivalent to existing baseline_nms
  8. nms_iou50 (NMS IoU=0.5)
  9. nms_iou70 (NMS IoU=0.7, very aggressive)
  10. grid_top1_6x3 + nms (combo)
  11. grid_top2_6x3 + nms (combo)

Outputs:
  benchmark/gtfree_results.csv
  benchmark/gtfree_per_frame.csv
  benchmark/gtfree_overlays/
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
OVERLAYS_DIR = os.path.join(OUT_DIR, 'gtfree_overlays')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

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

def load_gt(label_path):
    boxes = []
    if os.path.exists(label_path):
        with open(label_path) as f:
            for l in f:
                parts = l.strip().split()
                if len(parts)==5:
                    boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def run_model(frame):
    results = model(frame, classes=[CLASS_ID], conf=CONF, verbose=False, imgsz=640)
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

# ── GT-free mask functions ──

def mask_topk_per_frame(dets, k):
    """Keep top-K detections by confidence per frame. GT-free."""
    if len(dets) <= k:
        return dets, []
    sorted_dets = sorted(dets, key=lambda d: d['conf'], reverse=True)
    kept = sorted_dets[:k]
    removed = sorted_dets[k:]
    return kept, removed

def mask_grid_topk(dets, grid_x, grid_y, k, frame_shape):
    """
    Divide frame into grid_x x grid_y cells. Keep top-K per cell by confidence.
    GT-free: uses only detection positions and confidences.
    """
    h, w = frame_shape[:2]
    cell_w = w / grid_x
    cell_h = h / grid_y

    # Assign detections to cells
    cells = {}
    for idx, det in enumerate(dets):
        gx = min(int(det['px_cx'] / cell_w), grid_x - 1)
        gy = min(int(det['px_cy'] / cell_h), grid_y - 1)
        cells.setdefault((gx, gy), []).append((idx, det))

    kept = []
    removed = []
    for key, cell_dets in cells.items():
        # Sort by confidence within cell
        cell_dets.sort(key=lambda x: x[1]['conf'], reverse=True)
        for i, (idx, det) in enumerate(cell_dets):
            if i < k:
                kept.append(det)
            else:
                removed.append(det)

    return kept, removed

def mask_nms(dets, iou_thresh):
    """NMS with given IoU threshold. GT-free."""
    keep_idx = nms(dets, iou_thresh)
    keep_set = set(keep_idx)
    kept = [dets[i] for i in keep_idx]
    removed = [dets[i] for i in range(len(dets)) if i not in keep_set]
    return kept, removed

# ── Measurement ──
def match_and_measure(dets, gt_boxes):
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
    return tp, fp, fn

def compute_metrics(tp, fp, fn):
    prec = tp/(tp+fp) if (tp+fp)>0 else 0
    recall = tp/(tp+fn) if (tp+fn)>0 else 0
    f1 = 2*prec*recall/(prec+recall) if (prec+recall)>0 else 0
    return round(prec,4), round(recall,4), round(f1,4)

def draw_overlay(frame, gt_boxes, dets_after, removed, title, fname):
    h, w = frame.shape[:2]
    out = frame.copy()
    for det in removed:
        cx, cy = det['px_cx'], det['px_cy']
        cv2.drawMarker(out, (cx, cy), (0,0,255), cv2.MARKER_TILTED_CROSS, 12, 2)
    for det in dets_after:
        x1,y1,x2,y2 = int(det['x1']), int(det['y1']), int(det['x2']), int(det['y2'])
        cv2.rectangle(out, (x1,y1), (x2,y2), (255,128,0), 1)
    for box in gt_boxes:
        cx, cy, bw, bh = box
        x1,y1,x2,y2 = int((cx-bw/2)*w), int((cy-bh/2)*h), int((cx+bw/2)*w), int((cy+bh/2)*h)
        cv2.rectangle(out, (x1,y1), (x2,y2), (0,255,0), 2)
    cv2.putText(out, title, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
    return out

# ── Load frames ──
frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])
print(f"\n{len(frame_files)} benchmark frames loaded")

# ── Run detector on all frames ──
print("\n=== Running detector on all frames at conf=0.25 ===")
all_frame_data = {}
for fname in frame_files:
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    if frame is None: continue
    gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
    dets = run_model(frame)
    all_frame_data[fname] = {'frame': frame, 'gt': gt_boxes, 'dets': dets}

# ═══════════════════════════════════════════
# Variants to measure
# ═══════════════════════════════════════════
# Each: (name, mask_fn, kwargs)
# mask_fn(dets, gt_boxes, frame_shape, kwargs) -> (kept, removed)
# gt_boxes is passed for API compatibility but GT-free variants must not use it

def apply_baseline(dets, gt, frame_shape, kwargs):
    return dets, []

def apply_top1(dets, gt, frame_shape, kwargs):
    return mask_topk_per_frame(dets, 1)

def apply_top2(dets, gt, frame_shape, kwargs):
    return mask_topk_per_frame(dets, 2)

def apply_grid42_top1(dets, gt, frame_shape, kwargs):
    return mask_grid_topk(dets, 4, 2, 1, frame_shape)

def apply_grid63_top1(dets, gt, frame_shape, kwargs):
    return mask_grid_topk(dets, 6, 3, 1, frame_shape)

def apply_grid63_top2(dets, gt, frame_shape, kwargs):
    return mask_grid_topk(dets, 6, 3, 2, frame_shape)

def apply_nms30(dets, gt, frame_shape, kwargs):
    return mask_nms(dets, 0.30)

def apply_nms50(dets, gt, frame_shape, kwargs):
    return mask_nms(dets, 0.50)

def apply_nms70(dets, gt, frame_shape, kwargs):
    return mask_nms(dets, 0.70)

def apply_grid63_top1_nms(dets, gt, frame_shape, kwargs):
    kept, removed1 = mask_grid_topk(dets, 6, 3, 1, frame_shape)
    kept2, removed2 = mask_nms(kept, 0.30)
    return kept2, removed1 + removed2

def apply_grid63_top2_nms(dets, gt, frame_shape, kwargs):
    kept, removed1 = mask_grid_topk(dets, 6, 3, 2, frame_shape)
    kept2, removed2 = mask_nms(kept, 0.30)
    return kept2, removed1 + removed2

VARIANTS = [
    ('baseline', apply_baseline),
    ('top1_per_frame', apply_top1),
    ('top2_per_frame', apply_top2),
    ('grid_top1_4x2', apply_grid42_top1),
    ('grid_top1_6x3', apply_grid63_top1),
    ('grid_top2_6x3', apply_grid63_top2),
    ('nms_iou30', apply_nms30),
    ('nms_iou50', apply_nms50),
    ('nms_iou70', apply_nms70),
    ('grid63_top1_nms', apply_grid63_top1_nms),
    ('grid63_top2_nms', apply_grid63_top2_nms),
]

all_results = []
per_frame_records = []

print("\n=== Measuring all GT-free variants ===")
for variant_name, mask_fn in VARIANTS:
    total_tp, total_fp, total_fn = 0, 0, 0
    total_removed = 0
    frames_with_removals = 0

    for fname in frame_files:
        if fname not in all_frame_data:
            continue
        fd = all_frame_data[fname]
        frame = fd['frame']
        gt_boxes = fd['gt']
        dets = fd['dets']

        dets_after, removed = mask_fn(dets, gt_boxes, frame.shape, {})
        total_removed += len(removed)
        if len(removed) > 0:
            frames_with_removals += 1

        tp, fp, fn = match_and_measure(dets_after, gt_boxes)
        total_tp += tp
        total_fp += fp
        total_fn += fn

        per_frame_records.append({
            'variant': variant_name,
            'frame': fname,
            'n_det_before': len(dets),
            'n_removed': len(removed),
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
    print(f"  {variant_name:25s}: TP={total_tp:3d} FP={total_fp:3d} FN={total_fn:2d} "
          f"P={prec:.4f} R={recall:.4f} F1={f1:.4f} removed={total_removed:3d} ({frames_with_removals:3d} frames)")

# Write results
with open(os.path.join(OUT_DIR, 'gtfree_results.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','conf','tp','fp','fn','precision','recall','f1','total_removed','frames_with_removals'])
    writer.writeheader()
    writer.writerows(all_results)
print(f"\nWritten: {OUT_DIR}/gtfree_results.csv")

with open(os.path.join(OUT_DIR, 'gtfree_per_frame.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','frame','n_det_before','n_removed','n_det_after','tp','fp','fn'])
    writer.writeheader()
    writer.writerows(per_frame_records)
print(f"Written: {OUT_DIR}/gtfree_per_frame.csv")

# ═══════════════════════════════════════════
# Generate overlays for top variants
# ═══════════════════════════════════════════
print("\n=== Generating overlays ===")
overlay_variants = ['top2_per_frame', 'grid_top1_6x3', 'grid_top2_6x3', 'grid63_top1_nms']
overlay_count = 0

for variant_name in overlay_variants:
    mask_fn = dict(VARIANTS)[variant_name]
    for fname in frame_files:
        if fname not in all_frame_data:
            continue
        fd = all_frame_data[fname]
        frame = fd['frame']
        gt_boxes = fd['gt']
        dets = fd['dets']

        dets_after, removed = mask_fn(dets, gt_boxes, frame.shape, {})
        if len(removed) == 0:
            continue

        overlay = draw_overlay(frame, gt_boxes, dets_after, removed,
                               f'{variant_name}: -{len(removed)}', fname)
        base = fname.replace('.jpg', '')
        out_path = os.path.join(OVERLAYS_DIR, f'{variant_name}_{base}.jpg')
        cv2.imwrite(out_path, overlay)
        overlay_count += 1

print(f"Wrote {overlay_count} overlays to {OVERLAYS_DIR}/")
print("\nDONE — GT-free court-marking exclusion experiment complete")
