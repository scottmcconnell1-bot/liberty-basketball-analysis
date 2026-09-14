#!/usr/bin/env python3
"""
Secondary Classifier — Corrected Held-Out Evaluation
=====================================================
Re-evaluates the trained classifier with proper stratified train/test split.
Reports metrics on train / test / ALL frames separately.

Key corrections vs previous version:
- Stratified 70/30 frame split (neg-only frames represented in both)
- Metrics broken down by split
- Per-detection scores saved with full provenance
- Test-only held-out metrics are the primary result
"""
import os, csv, cv2, math, random, json
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms
from torch.utils.data import Dataset, DataLoader

# ── Config ──
CONF = 0.25
IOU_THRESHOLD = 0.5
RANDOM_SEED = 42
TRAIN_FRAC = 0.7
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
CROPS_DIR = os.path.join(OUT_DIR, 'classifier_crops')
OVERLAYS_DIR = os.path.join(OUT_DIR, 'classifier_overlays')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
device = torch.device('cpu')

# ── Load manifest ──
all_crops = []
with open(os.path.join(OUT_DIR, 'classifier_manifest.csv')) as f:
    reader = csv.DictReader(f)
    for row in reader:
        row['label'] = int(row['label'])
        row['crop_id'] = int(row['crop_id'])
        row['gt_boxes_in_frame'] = int(row['gt_boxes_in_frame'])
        row['px_cx'] = int(row['px_cx'])
        row['px_cy'] = int(row['px_cy'])
        all_crops.append(row)

# Load existing model
checkpoint = torch.load('models/court_fp_classifier.pt', map_location=device, weights_only=False)
thresh = checkpoint['threshold']
crop_size = checkpoint['crop_size']
val_f1_train = checkpoint['val_f1']  # from original training

print(f"Loaded classifier: threshold={thresh:.2f}, training val_F1={val_f1_train:.4f}")

model = models.mobilenet_v2()
model.classifier = nn.Sequential(
    nn.Dropout(0.3), nn.Linear(model.last_channel, 128), nn.ReLU(),
    nn.Dropout(0.2), nn.Linear(128, 1),
)
model.load_state_dict(checkpoint['model_state'])
model.eval()

# ── Step 1: Stratified train/test split ──
print("\n=== Step 1: Stratified train/test split ===")

frame_crops = {}
for crop in all_crops:
    frame_crops.setdefault(crop['frame'], []).append(crop)

frames = []
for fname, crops in sorted(frame_crops.items()):
    has_gt = any(c['gt_boxes_in_frame'] > 0 for c in crops)
    frames.append({'frame': fname, 'is_neg_frame': not has_gt})

neg_only = [f for f in frames if f['is_neg_frame']]
pos_frames = [f for f in frames if not f['is_neg_frame']]
random.shuffle(neg_only)
random.shuffle(pos_frames)

split_idx_neg = int(len(neg_only) * TRAIN_FRAC)
split_idx_pos = int(len(pos_frames) * TRAIN_FRAC)

train_fnames = set(f['frame'] for f in neg_only[:split_idx_neg] + pos_frames[:split_idx_pos])
test_fnames = set(f['frame'] for f in neg_only[split_idx_neg:] + pos_frames[split_idx_pos:])

print(f"Train: {len(train_fnames)} frames (neg-only={split_idx_neg}, pos={split_idx_pos})")
print(f"Test:  {len(test_fnames)} frames (neg-only={len(neg_only)-split_idx_neg}, pos={len(pos_frames)-split_idx_pos})")

assert len(train_fnames & test_fnames) == 0, "Overlap!"

# ── Step 2: Score all crops ──
print("\n=== Step 2: Scoring all crops ===")

transform = transforms.Compose([
    transforms.ToPILImage(), transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

class SimpleDataset(Dataset):
    def __init__(self, crops): self.crops = crops
    def __len__(self): return len(self.crops)
    def __getitem__(self, idx):
        img = cv2.imread(self.crops[idx]['crop_path'])
        return transform(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), self.crops[idx]['crop_id']

loader = DataLoader(SimpleDataset(all_crops), batch_size=32, shuffle=False, num_workers=0)
score_map = {}
with torch.no_grad():
    for X, ids in loader:
        out = torch.sigmoid(model(X.to(device)).squeeze())
        for i, cid in enumerate(ids.numpy()):
            score_map[int(cid)] = out[i].item()

print(f"Scored {len(score_map)} crops")

# ── Step 3: Save per-detection scores with provenance ──
print("\n=== Step 3: Saving per-detection scores ===")

det_records = []
for crop in all_crops:
    split = 'train' if crop['frame'] in train_fnames else 'test'
    det_records.append({
        'crop_id': crop['crop_id'],
        'frame': crop['frame'],
        'split': split,
        'det_idx': crop['det_idx'],
        'gt_boxes_in_frame': crop['gt_boxes_in_frame'],
        'label': crop['label'],
        'det_confidence': crop['conf'],
        'classifier_score': round(score_map.get(crop['crop_id'], 0.5), 6),
        'classifier_accept': int(score_map.get(crop['crop_id'], 0.5) >= thresh),
        'px_cx': crop['px_cx'],
        'px_cy': crop['px_cy'],
    })

with open(os.path.join(OUT_DIR, 'classifier_detection_scores.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=det_records[0].keys())
    writer.writeheader()
    writer.writerows(det_records)
print(f"Written: {OUT_DIR}/classifier_detection_scores.csv ({len(det_records)} rows)")

# ── Step 4: Benchmark measurement by split ──
print("\n=== Step 4: Benchmark measurement by split ===")

def load_gt(label_path):
    boxes = []
    if os.path.exists(label_path):
        with open(label_path) as f:
            for l in f:
                parts = l.strip().split()
                if len(parts) == 5:
                    boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def iou_yolo(b1, b2):
    cx1,cy1,w1,h1 = b1; cx2,cy2,w2,h2 = b2
    x1,y1,x2,y2 = cx1-w1/2, cy1-h1/2, cx1+w1/2, cy1+h1/2
    x3,y3,x4,y4 = cx2-w2/2, cy2-h2/2, cx2+w2/2, cy2+h2/2
    xi,yi,xj,yj = max(x1,x3),max(y1,y3),min(x2,x4),min(y2,y4)
    if xj<=xi or yj<=yi: return 0.
    return (xj-xi)*(yj-yi)/(w1*h1+w2*h2-(xj-xi)*(yj-yi))

def match_and_measure(dets, gt_boxes):
    matched = set()
    for gt in gt_boxes:
        best_i, best_j = 0, -1
        for j, det in enumerate(dets):
            if j in matched: continue
            i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
            if i > best_i: best_i, best_j = i, j
        if best_i >= IOU_THRESHOLD:
            matched.add(best_j)
    tp = len(matched)
    return tp, len(dets) - tp, len(gt_boxes) - tp

def compute_metrics(tp, fp, fn):
    prec = tp/(tp+fp) if (tp+fp)>0 else 0
    recall = tp/(tp+fn) if (tp+fn)>0 else 0
    f1 = 2*prec*recall/(prec+recall) if (prec+recall)>0 else 0
    return round(prec,4), round(recall,4), round(f1,4)

# Group by frame
frame_data_map = {}
for crop in all_crops:
    score = score_map.get(crop['crop_id'], 0.5)
    det = {
        'cx': float(crop['det_cx']), 'cy': float(crop['det_cy']),
        'w': float(crop['det_w']), 'h': float(crop['det_h']),
        'score': score, 'label': crop['label'], 'crop_id': crop['crop_id'],
        'px_cx': crop['px_cx'], 'px_cy': crop['px_cy'],
    }
    frame_data_map.setdefault(crop['frame'], []).append(det)

VARIANTS = [
    ('baseline', None, None),
    ('classifier', thresh, None),
    ('classifier_nms', thresh, 0.3),
]

SPLITS = ['all', 'train', 'test']

frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])

# Collect results: variant x split
all_results = []
per_frame_records = []

for variant_name, v_thresh, nms_iou in VARIANTS:
    for split_name in SPLITS:
        total_tp, total_fp, total_fn = 0, 0, 0
        total_removed = 0
        n_frames = 0

        for fname in frame_files:
            if fname not in frame_data_map:
                continue
            # Filter by split
            if split_name == 'train' and fname not in train_fnames:
                continue
            if split_name == 'test' and fname not in test_fnames:
                continue
            if split_name == 'all' and fname not in train_fnames and fname not in test_fnames:
                continue  # frames with no detections

            frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
            if frame is None:
                continue
            gt = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
            dets = frame_data_map[fname]
            n_frames += 1

            # Filter
            if v_thresh is not None:
                kept = [d for d in dets if d['score'] >= v_thresh]
                removed = [d for d in dets if d['score'] < v_thresh]
            else:
                kept = dets
                removed = []

            if nms_iou is not None and len(kept) > 1:
                scores = [d['score'] for d in kept]
                order = sorted(range(len(kept)), key=lambda i: scores[i], reverse=True)
                nms_keep = []
                while order:
                    i = order[0]
                    nms_keep.append(i)
                    rest = []
                    for j in order[1:]:
                        iou = iou_yolo(
                            (kept[i]['cx'], kept[i]['cy'], kept[i]['w'], kept[i]['h']),
                            (kept[j]['cx'], kept[j]['cy'], kept[j]['w'], kept[j]['h']))
                        if iou < nms_iou:
                            rest.append(j)
                    order = rest
                nms_set = set(nms_keep)
                removed2 = [kept[i] for i in range(len(kept)) if i not in nms_set]
                kept = [kept[i] for i in nms_keep]
                removed = removed + removed2

            tp, fp, fn = match_and_measure(kept, gt)
            total_tp += tp; total_fp += fp; total_fn += fn
            total_removed += len(removed)

            per_frame_records.append({
                'variant': variant_name,
                'split': split_name,
                'frame': fname,
                'n_det_before': len(dets),
                'n_removed': len(removed),
                'n_det_after': len(kept),
                'tp': tp, 'fp': fp, 'fn': fn,
            })

        prec, recall, f1 = compute_metrics(total_tp, total_fp, total_fn)
        all_results.append({
            'variant': variant_name,
            'split': split_name,
            'frames': n_frames,
            'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
            'precision': prec, 'recall': recall, 'f1': f1,
            'total_removed': total_removed,
            'threshold': v_thresh if v_thresh else 'N/A',
        })
        tag = f"[{split_name:5s}]" if split_name != 'all' else "[ ALL ]"
        print(f"  {variant_name:25s} {tag}: TP={total_tp:3d} FP={total_fp:3d} FN={total_fn:2d} "
              f"P={prec:.4f} R={recall:.4f} F1={f1:.4f} removed={total_removed:3d} ({n_frames} frames)")

# Write results
with open(os.path.join(OUT_DIR, 'classifier_results_v2.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','split','frames','tp','fp','fn','precision','recall','f1','total_removed','threshold'])
    writer.writeheader()
    writer.writerows(all_results)
print(f"\nWritten: {OUT_DIR}/classifier_results_v2.csv")

with open(os.path.join(OUT_DIR, 'classifier_per_frame_v2.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','split','frame','n_det_before','n_removed','n_det_after','tp','fp','fn'])
    writer.writeheader()
    writer.writerows(per_frame_records)
print(f"Written: {OUT_DIR}/classifier_per_frame_v2.csv")

# Write new split file
with open(os.path.join(OUT_DIR, 'classifier_split_v2.csv'), 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['frame', 'split', 'seed', 'stratified'])
    for fname in sorted(train_fnames):
        writer.writerow([fname, 'train', RANDOM_SEED, True])
    for fname in sorted(test_fnames):
        writer.writerow([fname, 'test', RANDOM_SEED, True])
print(f"Written: {OUT_DIR}/classifier_split_v2.csv")

# ── Step 5: Generate overlaid for test frames only ──
print("\n=== Step 5: Generating test-set overlays ===")
overlay_count = 0
for fname in sorted(test_fnames):
    if fname not in frame_data_map:
        continue
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    if frame is None:
        continue
    gt = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
    h, w = frame.shape[:2]

    dets = frame_data_map[fname]
    kept = [d for d in dets if d['score'] >= thresh]
    removed = [d for d in dets if d['score'] < thresh]

    if not removed:
        continue

    out = frame.copy()
    for d in removed:
        cv2.drawMarker(out, (d['px_cx'], d['px_cy']), (0,0,255), cv2.MARKER_TILTED_CROSS, 12, 2)
    for d in kept:
        cv2.drawMarker(out, (d['px_cx'], d['px_cy']), (255,128,0), cv2.MARKER_SQUARE, 8, 1)
    for box in gt:
        cx,cy,bw,bh = box
        cv2.rectangle(out,(int((cx-bw/2)*w),int((cy-bh/2)*h)),(int((cx+bw/2)*w),int((cy+bh/2)*h)),(0,255,0),2)
    cv2.putText(out, f'clf(th={thresh:.2f}): -{len(removed)}', (5,15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
    cv2.putText(out, '[TEST]', (w-50, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,255), 1)

    cv2.imwrite(os.path.join(OVERLAYS_DIR, f'classifier_test_{fname}'), out)
    overlay_count += 1

print(f"Wrote {overlay_count} test-set overlays to {OVERLAYS_DIR}/")
print("\nDONE — Corrected held-out evaluation complete")
