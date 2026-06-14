#!/usr/bin/env python3
"""
Ball Detection Benchmark
========================
Uses ball_dataset_v2 (human-verified labels) as positive set.
Adds negative frames from video.
Evaluates:
  1. Base YOLOv8n COCO sports-ball class 32 (production path)
  2. Fine-tuned ball_detector.pt (ball_finetune/runs/finetune2/weights/best.pt)

Outputs to benchmark/:
  frames/           - all benchmark frame images
  labels/           - YOLO-format ground truth labels
  detections_base.csv
  detections_ft.csv
  results_perframe.csv
  results_summary.csv
  report.md
"""

import os, sys, csv, time, shutil
import cv2
import numpy as np

os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

from ultralytics import YOLO

# ── Paths ──
VIDEO = 'uploads/Liberty_Vs_Riverstone_20260519_103815.webm'
V2_IMAGES = 'ball_dataset_v2/images'
V2_LABELS = 'ball_dataset_v2/labels'
FT_MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
OUT = 'benchmark'
FRAMES_DIR = os.path.join(OUT, 'frames')
LABELS_DIR = os.path.join(OUT, 'labels')

os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(LABELS_DIR, exist_ok=True)

IOU_THRESHOLD = 0.5
CONF_SWEEP = [0.01, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]

# ── Step 1: Build positive set from ball_dataset_v2 ──
print("=== Building positive set from ball_dataset_v2 ===")

positive_frames = []  # (dest_fname, src_img, src_label, scenario)

for split in ['train', 'val']:
    img_dir = os.path.join(V2_IMAGES, split)
    lbl_dir = os.path.join(V2_LABELS, split)
    if not os.path.exists(img_dir):
        continue
    
    for img_file in sorted(os.listdir(img_dir)):
        if not img_file.endswith('.jpg'):
            continue
        base = img_file.replace('.jpg', '')
        lbl_file = base + '.txt'
        lbl_path = os.path.join(lbl_dir, lbl_file)
        img_path = os.path.join(img_dir, img_file)
        
        if not os.path.exists(lbl_path):
            continue
        
        # Read label to verify it has a ball
        with open(lbl_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        
        if not lines:
            continue
        
        # Determine scenario from label characteristics
        scenarios = []
        for line in lines:
            parts = line.split()
            if len(parts) == 5:
                _, cx, cy, w, h = [float(x) for x in parts]
                # Classify scenario
                if cy > 0.85:
                    scenarios.append('near_bottom')
                if cx < 0.2 or cx > 0.8:
                    scenarios.append('perimeter')
                if 0.4 < cx < 0.6 and 0.3 < cy < 0.6:
                    scenarios.append('center_court')
                px_w = w * 1280
                px_h = h * 720
                if px_w > 40 or px_h > 40:
                    scenarios.append('large_box')
        
        scenario = ','.join(set(scenarios)) if scenarios else 'standard'
        
        dest_fname = f'pos_{split}_{img_file}'
        shutil.copy2(img_path, os.path.join(FRAMES_DIR, dest_fname))
        shutil.copy2(lbl_path, os.path.join(LABELS_DIR, dest_fname.replace('.jpg', '.txt')))
        
        positive_frames.append({
            'fname': dest_fname,
            'split': split,
            'scenario': scenario,
            'n_boxes': len(lines),
        })

print(f"Positive frames: {len(positive_frames)}")
for p in positive_frames[:5]:
    print(f"  {p['fname']}: {p['scenario']} ({p['n_boxes']} boxes)")

# ── Step 2: Build negative set from video ──
print("\n=== Building negative set from video ===")

# Select frames from the video that are NOT in ball_dataset_v2
# ball_dataset_v2 frames are numbered frame_003 to frame_110
# Pick frames from the video at intervals that don't overlap
cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)

# Select 30 negative frames spread across the video
# Avoid frames 2000-5000 which is where most v2 frames come from
neg_indices = []
# First part of video (0-2000): 10 frames
neg_indices.extend(np.linspace(0, 1800, 10, dtype=int))
# Middle part (5000-9000): 10 frames  
neg_indices.extend(np.linspace(5200, 8800, 10, dtype=int))
# End part (9000-end): 10 frames
neg_indices.extend(np.linspace(9200, total-1, 10, dtype=int))

negative_frames = []
for i, fi in enumerate(neg_indices):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    if not ret:
        continue
    
    fname = f'neg_{i:03d}_f{fi:05d}.jpg'
    cv2.imwrite(os.path.join(FRAMES_DIR, fname), frame)
    
    # Create empty label file (no ball)
    with open(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')), 'w') as f:
        pass
    
    negative_frames.append({
        'fname': fname,
        'video_frame': fi,
        'time_sec': fi / fps,
    })

cap.release()
print(f"Negative frames: {len(negative_frames)}")

# ── Step 3: Write manifest ──
print("\n=== Writing manifest ===")

all_frames = positive_frames + [{'fname': n['fname'], 'split': 'negative', 'scenario': 'no_ball', 'n_boxes': 0} for n in negative_frames]

with open(os.path.join(OUT, 'manifest.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['fname', 'split', 'scenario', 'n_boxes', 'labeler', 'review_status', 'source'])
    writer.writeheader()
    for frame in all_frames:
        writer.writerow({
            'fname': frame['fname'],
            'split': frame.get('split', 'negative'),
            'scenario': frame.get('scenario', 'no_ball'),
            'n_boxes': frame.get('n_boxes', 0),
            'labeler': 'ball_dataset_v2_human_labeler' if frame.get('n_boxes', 0) > 0 else 'video_extraction',
            'review_status': 'verified' if frame.get('n_boxes', 0) > 0 else 'auto_negative',
            'source': 'ball_dataset_v2' if frame.get('n_boxes', 0) > 0 else VIDEO,
        })

print(f"Total benchmark: {len(all_frames)} frames ({len(positive_frames)} positive, {len(negative_frames)} negative)")

# ── Step 4: IoU computation ──
def iou_yolo(box1, box2):
    """IoU between two boxes in YOLO normalized format (cx, cy, w, h)."""
    cx1, cy1, w1, h1 = box1
    cx2, cy2, w2, h2 = box2
    x1_min, y1_min = cx1 - w1/2, cy1 - h1/2
    x1_max, y1_max = cx1 + w1/2, cy1 + h1/2
    x2_min, y2_min = cx2 - w2/2, cy2 - h2/2
    x2_max, y2_max = cx2 + w2/2, cy2 + h2/2
    xi1, yi1 = max(x1_min, x2_min), max(y1_min, y2_min)
    xi2, yi2 = min(x1_max, x2_max), min(y1_max, y2_max)
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    inter = (xi2 - xi1) * (yi2 - yi1)
    return inter / (w1*h1 + w2*h2 - inter)

def load_gt(label_path):
    """Load ground truth boxes from YOLO label file."""
    boxes = []
    if not os.path.exists(label_path):
        return boxes
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 5:
                boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def run_detector(model, frame, imgsz=640, conf=0.15, classes=None):
    """Run YOLO model, return list of (cx, cy, w, h, conf) in normalized coords."""
    kwargs = dict(imgsz=imgsz, conf=conf, verbose=False)
    if classes is not None:
        kwargs['classes'] = classes
    results = model(frame, **kwargs)
    detections = []
    for r in results:
        if r.boxes is not None:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cf = float(box.conf[0])
                h_frame, w_frame = frame.shape[:2]
                cx = ((x1 + x2) / 2) / w_frame
                cy = ((y1 + y2) / 2) / h_frame
                w = (x2 - x1) / w_frame
                h = (y2 - y1) / w_frame
                detections.append((cx, cy, w, h, cf))
    return detections

def evaluate_frame(gt_boxes, det_boxes, iou_thresh=IOU_THRESHOLD):
    """Returns (tp, fp, fn) for one frame."""
    if len(gt_boxes) == 0:
        return 0, len(det_boxes), 0
    if len(det_boxes) == 0:
        return 0, 0, len(gt_boxes)
    matched_det = set()
    tp = 0
    for gt_box in gt_boxes:
        best_iou, best_det = 0, -1
        for j, det in enumerate(det_boxes):
            if j in matched_det:
                continue
            i = iou_yolo(gt_box, det[:4])
            if i > best_iou:
                best_iou, best_det = i, j
        if best_iou >= iou_thresh:
            tp += 1
            matched_det.add(best_det)
    fp = len(det_boxes) - len(matched_det)
    fn = len(gt_boxes) - tp
    return tp, fp, fn

# ── Step 5: Load models ──
print("\n=== Loading models ===")

print("Loading yolov8n.pt (base)...")
model_base = YOLO('yolov8n.pt', verbose=False)
print("  Done")

ft_loaded = False
model_ft = None
if os.path.exists(FT_MODEL):
    print(f"Loading {FT_MODEL} (fine-tuned)...")
    try:
        model_ft = YOLO(FT_MODEL, verbose=False)
        ft_loaded = True
        print("  Done")
    except Exception as e:
        print(f"  FAILED: {e}")
else:
    print(f"  SKIPPED: {FT_MODEL} not found")

# ── Step 6: Run evaluation ──
print(f"\n=== Evaluating {len(all_frames)} frames ===")

frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])

model_configs = [('base_yolov8n_class32', model_base, [32])]
if ft_loaded:
    model_configs.append(('finetuned_ball_detector', model_ft, None))

all_results = []
summary_results = []

for model_name, model, classes in model_configs:
    print(f"\n--- {model_name} ---")
    
    for conf_thresh in CONF_SWEEP:
        total_tp, total_fp, total_fn = 0, 0, 0
        per_frame = []
        
        for fname in frame_files:
            fpath = os.path.join(FRAMES_DIR, fname)
            frame = cv2.imread(fpath)
            if frame is None:
                continue
            
            gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
            dets = run_detector(model, frame, imgsz=640, conf=conf_thresh, classes=classes)
            tp, fp, fn = evaluate_frame(gt_boxes, dets)
            
            total_tp += tp
            total_fp += fp
            total_fn += fn
            
            per_frame.append({
                'frame': fname,
                'model': model_name,
                'conf_thresh': conf_thresh,
                'gt_boxes': len(gt_boxes),
                'n_dets': len(dets),
                'tp': tp, 'fp': fp, 'fn': fn,
                'best_conf': max([d[4] for d in dets], default=0),
            })
        
        prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * prec * recall / (prec + recall) if (prec + recall) > 0 else 0
        
        summary_results.append({
            'model': model_name,
            'conf_thresh': conf_thresh,
            'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
            'precision': round(prec, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
        })
        
        all_results.extend(per_frame)
        
        print(f"  conf={conf_thresh:.2f}: TP={total_tp} FP={total_fp} FN={total_fn} P={prec:.4f} R={recall:.4f} F1={f1:.4f}")

# ── Step 7: Write results ──
print("\n=== Writing results ===")

with open(os.path.join(OUT, 'results_summary.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['model', 'conf_thresh', 'tp', 'fp', 'fn', 'precision', 'recall', 'f1'])
    writer.writeheader()
    writer.writerows(summary_results)

with open(os.path.join(OUT, 'results_perframe.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['frame', 'model', 'conf_thresh', 'gt_boxes', 'n_dets', 'tp', 'fp', 'fn', 'best_conf'])
    writer.writeheader()
    writer.writerows(all_results)

print(f"Results written to {OUT}/")
print("DONE")
