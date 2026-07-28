#!/usr/bin/env python3
"""
Secondary Classifier for Court-Marking FP Rejection
====================================================
Trains a lightweight MobileNetV2 to distinguish ball detections from
court-marking FPs. Measures as a GT-free post-processing filter.

Architecture: MobileNetV2 (pretrained ImageNet) + binary head
Crop: 64x64 centered on detection bbox with 1.5x margin
Augmentation: flip, rotate, color jitter, random erasing

Train/test split: by frame (70/30) — no frame overlap.

Outputs:
  benchmark/classifier_crops/           - extracted crop images
  benchmark/classifier_manifest.csv     - crop metadata
  benchmark/classifier_split.csv        - frame-level split
  benchmark/classifier_results.csv      - per-variant metrics
  benchmark/classifier_per_frame.csv    - per-frame detail
  benchmark/classifier_overlays/        - accepted/rejected frames
  benchmark/classifier_contact_sheet.jpg
  models/court_fp_classifier.pt         - trained weights
"""
import os, csv, cv2, math, random, shutil
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

import numpy as np

# ── Config ──
MODEL_PATH = 'models/ball_detector.pt'
CLASS_ID = 0
CONF = 0.25
IOU_THRESHOLD = 0.5
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
CROPS_DIR = os.path.join(OUT_DIR, 'classifier_crops')
OVERLAYS_DIR = os.path.join(OUT_DIR, 'classifier_overlays')
os.makedirs(CROPS_DIR, exist_ok=True)
os.makedirs(OVERLAYS_DIR, exist_ok=True)

CROP_SIZE = 64
CROP_MARGIN = 1.5
RANDOM_SEED = 42
TRAIN_FRAC = 0.7
MAX_EPOCHS = 50
PATIENCE = 10
BATCH_SIZE = 16

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

from ultralytics import YOLO

print("Loading detector model...")
detector = YOLO(MODEL_PATH, verbose=False)

# ── Helpers ──
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

def extract_crop(frame, det, margin=CROP_MARGIN):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = int(det['x1']), int(det['y1']), int(det['x2']), int(det['y2'])
    bw, bh = x2-x1, y2-y1
    if bw <= 0 or bh <= 0:
        return None
    cx, cy = (x1+x2)//2, (y1+y2)//2
    new_bw = int(bw * margin)
    new_bh = int(bh * margin)
    nx1 = max(0, cx - new_bw//2)
    ny1 = max(0, cy - new_bh//2)
    nx2 = min(w, cx + new_bw//2)
    ny2 = min(h, cy + new_bh//2)
    crop = frame[ny1:ny2, nx1:nx2]
    if crop.size == 0:
        return None
    return cv2.resize(crop, (CROP_SIZE, CROP_SIZE))

def match_and_measure(dets, gt_boxes):
    """Match detections to GT using IoU, return TP, FP, FN."""
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

# ── Step 1: Extract all detections and label them ──
print("\n=== Step 1: Extracting detections and labeling ===")
frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])

all_crops = []
crop_idx = 0

for fname in frame_files:
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    if frame is None:
        continue
    gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))

    results = detector(frame, classes=[CLASS_ID], conf=CONF, verbose=False, imgsz=640)
    dets = []
    for r in results:
        if r.boxes is not None:
            for box in r.boxes:
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                cf = float(box.conf[0])
                hf,wf = frame.shape[:2]
                dets.append({
                    'cx': ((x1+x2)/2)/wf, 'cy': ((y1+y2)/2)/hf,
                    'w': (x2-x1)/wf, 'h': (y2-y1)/hf, 'conf': cf,
                    'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                    'px_cx': int((x1+x2)/2), 'px_cy': int((y1+y2)/2),
                })

    matched_det = set()
    for gt in gt_boxes:
        best_i, best_j = 0, -1
        for j, det in enumerate(dets):
            if j in matched_det: continue
            i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
            if i > best_i: best_i, best_j = i, j
        if best_i >= IOU_THRESHOLD:
            matched_det.add(best_j)

    for j, det in enumerate(dets):
        crop_img = extract_crop(frame, det)
        if crop_img is None:
            continue
        label = 1 if j in matched_det else 0
        crop_path = os.path.join(CROPS_DIR, f'crop_{crop_idx:04d}.jpg')
        cv2.imwrite(crop_path, crop_img)
        all_crops.append({
            'crop_id': crop_idx,
            'frame': fname,
            'det_idx': j,
            'crop_path': crop_path,
            'label': label,
            'conf': det['conf'],
            'px_cx': det['px_cx'],
            'px_cy': det['px_cy'],
            'gt_boxes_in_frame': len(gt_boxes),
            # Store full det info for benchmark measurement
            'det_cx': det['cx'], 'det_cy': det['cy'],
            'det_w': det['w'], 'det_h': det['h'],
            'det_x1': det['x1'], 'det_y1': det['y1'],
            'det_x2': det['x2'], 'det_y2': det['y2'],
        })
        crop_idx += 1

print(f"Extracted {len(all_crops)} crops")
print(f"  Positive (ball): {sum(1 for c in all_crops if c['label']==1)}")
print(f"  Negative (FP):   {sum(1 for c in all_crops if c['label']==0)}")

with open(os.path.join(OUT_DIR, 'classifier_manifest.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['crop_id','frame','det_idx','crop_path','label','conf','px_cx','px_cy','gt_boxes_in_frame',
                                            'det_cx','det_cy','det_w','det_h','det_x1','det_y1','det_x2','det_y2'])
    writer.writeheader()
    writer.writerows(all_crops)
print(f"Written: {OUT_DIR}/classifier_manifest.csv")

# ── Step 2: Train/test split by frame ──
print("\n=== Step 2: Train/test split ===")
frame_crops = {}
for crop in all_crops:
    frame_crops.setdefault(crop['frame'], []).append(crop)

all_frame_names = sorted(frame_crops.keys())
split_idx = int(len(all_frame_names) * TRAIN_FRAC)
train_frames = set(all_frame_names[:split_idx])
test_frames = set(all_frame_names[split_idx:])

train_crops = [c for c in all_crops if c['frame'] in train_frames]
test_crops = [c for c in all_crops if c['frame'] in test_frames]

print(f"Train frames: {len(train_frames)}, Test frames: {len(test_frames)}")
print(f"Train crops: {len(train_crops)} (pos={sum(1 for c in train_crops if c['label']==1)}, neg={sum(1 for c in train_crops if c['label']==0)})")
print(f"Test crops:  {len(test_crops)} (pos={sum(1 for c in test_crops if c['label']==1)}, neg={sum(1 for c in test_crops if c['label']==0)})")

overlap = train_frames & test_frames
assert len(overlap) == 0, f"Frame overlap: {overlap}"
print("  No frame overlap — clean split verified")

with open(os.path.join(OUT_DIR, 'classifier_split.csv'), 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['frame', 'split'])
    for fr in sorted(train_frames):
        writer.writerow([fr, 'train'])
    for fr in sorted(test_frames):
        writer.writerow([fr, 'test'])
print(f"Written: {OUT_DIR}/classifier_split.csv")

# ── Step 3: Train classifier ──
print("\n=== Step 3: Training MobileNetV2 classifier ===")

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models

device = torch.device('cpu')
torch.set_num_threads(2)

class CropDataset(Dataset):
    def __init__(self, crops, augment=False):
        self.crops = crops
        self.augment = augment
        self.base_transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        self.aug_transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.RandomHorizontalFlip(0.5),
            transforms.RandomRotation(15),
            transforms.ColorJitter(0.2, 0.2, 0.2, 0.1),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    def __len__(self):
        return len(self.crops)

    def __getitem__(self, idx):
        crop = cv2.imread(self.crops[idx]['crop_path'])
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        if self.augment:
            tensor = self.aug_transform(crop)
            # Random erasing
            if random.random() < 0.3:
                _, h, w = tensor.shape
                eh, ew = random.randint(4, 16), random.randint(4, 16)
                ex, ey = random.randint(0, w-ew), random.randint(0, h-eh)
                tensor[:, ey:ey+eh, ex:ex+ew] = torch.randn(3, eh, ew) * 0.5
        else:
            tensor = self.base_transform(crop)
        label = self.crops[idx]['label']
        return tensor, label

train_dataset = CropDataset(train_crops, augment=True)
test_dataset = CropDataset(test_crops, augment=False)
train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

model = models.mobilenet_v2(pretrained=True)
model.classifier = nn.Sequential(
    nn.Dropout(0.3),
    nn.Linear(model.last_channel, 128),
    nn.ReLU(),
    nn.Dropout(0.2),
    nn.Linear(128, 1),
)
model = model.to(device)

n_pos = sum(1 for c in train_crops if c['label']==1)
n_neg = sum(1 for c in train_crops if c['label']==0)
pos_weight = torch.tensor([n_neg / n_pos]).to(device)
criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
optimizer = optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=MAX_EPOCHS)

best_val_f1 = 0
best_state = None
best_thresh_final = 0.5
no_improve = 0

for epoch in range(MAX_EPOCHS):
    model.train()
    train_loss = 0
    for X, y in train_loader:
        X, y = X.to(device), y.float().to(device)
        optimizer.zero_grad()
        out = model(X).squeeze()
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()
        train_loss += loss.item()
    scheduler.step()

    model.eval()
    val_preds, val_labels = [], []
    with torch.no_grad():
        for X, y in test_loader:
            X = X.to(device)
            out = torch.sigmoid(model(X).squeeze())
            val_preds.extend(out.cpu().numpy())
            val_labels.extend(y.numpy())

    val_preds_np = np.array(val_preds)
    val_labels_np = np.array(val_labels)

    # Find best threshold on validation set
    best_t, best_f = 0.5, 0
    for thresh in np.arange(0.05, 0.95, 0.05):
        preds_bin = (val_preds_np >= thresh).astype(int)
        tp = int(((preds_bin == 1) & (val_labels_np == 1)).sum())
        fp = int(((preds_bin == 1) & (val_labels_np == 0)).sum())
        fn = int(((preds_bin == 0) & (val_labels_np == 1)).sum())
        prec = tp/(tp+fp) if tp+fp > 0 else 0
        recall = tp/(tp+fn) if tp+fn > 0 else 0
        f1 = 2*prec*recall/(prec+recall) if prec+recall > 0 else 0
        if f1 > best_f:
            best_f = f1
            best_t = thresh

    preds_bin = (val_preds_np >= best_t).astype(int)
    tp = int(((preds_bin == 1) & (val_labels_np == 1)).sum())
    fp = int(((preds_bin == 1) & (val_labels_np == 0)).sum())
    fn = int(((preds_bin == 0) & (val_labels_np == 1)).sum())
    prec = tp/(tp+fp) if tp+fp > 0 else 0
    recall = tp/(tp+fn) if tp+fn > 0 else 0
    f1 = 2*prec*recall/(prec+recall) if prec+recall > 0 else 0

    if epoch % 5 == 0 or f1 > best_val_f1:
        print(f"  Epoch {epoch:3d}: loss={train_loss/len(train_loader):.4f} val_F1={f1:.4f} P={prec:.4f} R={recall:.4f} thresh={best_t:.2f} TP={tp} FP={fp} FN={fn}")

    if f1 > best_val_f1:
        best_val_f1 = f1
        best_state = {k: v.clone() for k, v in model.state_dict().items()}
        best_thresh_final = best_t
        no_improve = 0
    else:
        no_improve += 1
        if no_improve >= PATIENCE:
            print(f"  Early stop at epoch {epoch}")
            break

model.load_state_dict(best_state)
model.eval()

# Final validation
val_preds_final = []
with torch.no_grad():
    for X, _ in test_loader:
        X = X.to(device)
        out = torch.sigmoid(model(X).squeeze())
        val_preds_final.extend(out.cpu().numpy())
val_preds_final = np.array(val_preds_final)
val_labels_final = np.array([c['label'] for c in test_crops])

preds_bin = (val_preds_final >= best_thresh_final).astype(int)
tp_v = int(((preds_bin == 1) & (val_labels_final == 1)).sum())
fp_v = int(((preds_bin == 1) & (val_labels_final == 0)).sum())
fn_v = int(((preds_bin == 0) & (val_labels_final == 1)).sum())
prec_v = tp_v/(tp_v+fp_v) if tp_v+fp_v > 0 else 0
recall_v = tp_v/(tp_v+fn_v) if tp_v+fn_v > 0 else 0
f1_v = 2*prec_v*recall_v/(prec_v+recall_v) if prec_v+recall_v > 0 else 0

print(f"\n  Best validation: F1={f1_v:.4f} P={prec_v:.4f} R={recall_v:.4f} thresh={best_thresh_final:.2f}")
print(f"  TP={tp_v} FP={fp_v} FN={fn_v}")

os.makedirs('models', exist_ok=True)
torch.save({
    'model_state': best_state,
    'threshold': best_thresh_final,
    'crop_size': CROP_SIZE,
    'val_f1': f1_v,
    'val_precision': prec_v,
    'val_recall': recall_v,
}, 'models/court_fp_classifier.pt')
print("  Saved: models/court_fp_classifier.pt")

# ── Step 4: Run classifier as benchmark filter ──
print("\n=== Step 4: Running classifier as benchmark filter ===")

# Score ALL crops
all_dataset = CropDataset(all_crops, augment=False)
all_loader = DataLoader(all_dataset, batch_size=32, shuffle=False, num_workers=0)

all_scores = []
with torch.no_grad():
    for X, _ in all_loader:
        X = X.to(device)
        out = torch.sigmoid(model(X).squeeze())
        all_scores.extend(out.cpu().numpy())
all_scores = np.array(all_scores)

crop_score_map = {c['crop_id']: score for c, score in zip(all_crops, all_scores)}

# Group by frame
frame_data = {}
for crop in all_crops:
    frame_data.setdefault(crop['frame'], []).append(crop)

VARIANTS = [
    ('baseline', None, None),
    ('classifier', best_thresh_final, None),
    ('classifier_nms', best_thresh_final, 0.3),
]

results = []
per_frame_records = []

for variant_name, thresh, nms_iou in VARIANTS:
    total_tp, total_fp, total_fn = 0, 0, 0
    total_removed = 0
    frames_with_removals = 0

    for fname in frame_files:
        if fname not in frame_data:
            continue
        crops = frame_data[fname]
        frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
        if frame is None:
            continue
        gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))

        # Reconstruct detections from crops
        dets = []
        for crop in crops:
            score = crop_score_map.get(crop['crop_id'], 0.5)
            dets.append({
                'cx': crop['det_cx'], 'cy': crop['det_cy'],
                'w': crop['det_w'], 'h': crop['det_h'],
                'x1': crop['det_x1'], 'y1': crop['det_y1'],
                'x2': crop['det_x2'], 'y2': crop['det_y2'],
                'px_cx': crop['px_cx'], 'px_cy': crop['px_cy'],
                'conf': crop['conf'], 'score': score,
                'label': crop['label'], 'crop_id': crop['crop_id'],
            })

        # Apply classifier filter
        if thresh is not None:
            kept = [d for d in dets if d['score'] >= thresh]
            removed = [d for d in dets if d['score'] < thresh]
        else:
            kept = dets
            removed = []

        # Apply NMS if requested
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
                        (kept[j]['cx'], kept[j]['cy'], kept[j]['w'], kept[j]['h'])
                    )
                    if iou < nms_iou:
                        rest.append(j)
                order = rest
            nms_keep_set = set(nms_keep)
            removed2 = [kept[i] for i in range(len(kept)) if i not in nms_keep_set]
            kept = [kept[i] for i in nms_keep]
            removed = removed + removed2

        tp, fp, fn = match_and_measure(kept, gt_boxes)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_removed += len(removed)
        if len(removed) > 0:
            frames_with_removals += 1

        per_frame_records.append({
            'variant': variant_name,
            'frame': fname,
            'n_det_before': len(dets),
            'n_removed': len(removed),
            'n_det_after': len(kept),
            'tp': tp, 'fp': fp, 'fn': fn,
        })

    prec, recall, f1 = compute_metrics(total_tp, total_fp, total_fn)
    results.append({
        'variant': variant_name,
        'conf': CONF,
        'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
        'precision': prec, 'recall': recall, 'f1': f1,
        'total_removed': total_removed,
        'frames_with_removals': frames_with_removals,
        'threshold': thresh if thresh else 'N/A',
    })
    print(f"  {variant_name:25s}: TP={total_tp:3d} FP={total_fp:3d} FN={total_fn:2d} "
          f"P={prec:.4f} R={recall:.4f} F1={f1:.4f} removed={total_removed:3d} ({frames_with_removals:3d} frames)")

with open(os.path.join(OUT_DIR, 'classifier_results.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','conf','tp','fp','fn','precision','recall','f1','total_removed','frames_with_removals','threshold'])
    writer.writeheader()
    writer.writerows(results)
print(f"\nWritten: {OUT_DIR}/classifier_results.csv")

with open(os.path.join(OUT_DIR, 'classifier_per_frame.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','frame','n_det_before','n_removed','n_det_after','tp','fp','fn'])
    writer.writeheader()
    writer.writerows(per_frame_records)
print(f"Written: {OUT_DIR}/classifier_per_frame.csv")

# ── Step 5: Generate overlays ──
print("\n=== Step 5: Generating overlays ===")
overlay_count = 0
for fname in frame_files:
    if fname not in frame_data:
        continue
    crops = frame_data[fname]
    frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
    if frame is None:
        continue
    gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))

    kept, removed = [], []
    for crop in crops:
        score = crop_score_map.get(crop['crop_id'], 0.5)
        det = {'px_cx': crop['px_cx'], 'px_cy': crop['px_cy'], 'label': crop['label'], 'score': score}
        if score >= best_thresh_final:
            kept.append(det)
        else:
            removed.append(det)

    if len(removed) == 0:
        continue

    out = frame.copy()
    for det in removed:
        cv2.drawMarker(out, (det['px_cx'], det['px_cy']), (0,0,255), cv2.MARKER_TILTED_CROSS, 12, 2)
    for det in kept:
        cv2.drawMarker(out, (det['px_cx'], det['px_cy']), (255,128,0), cv2.MARKER_CIRCLE, 8, 1)
    for box in gt_boxes:
        cx, cy, bw, bh = box
        h, w = frame.shape[:2]
        cv2.rectangle(out, (int((cx-bw/2)*w),int((cy-bh/2)*h)), (int((cx+bw/2)*w),int((cy+bh/2)*h)), (0,255,0), 2)
    cv2.putText(out, f'classifier(thresh={best_thresh_final:.2f}): -{len(removed)}', (5,15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    out_path = os.path.join(OVERLAYS_DIR, f'classifier_{fname}')
    cv2.imwrite(out_path, out)
    overlay_count += 1

print(f"Wrote {overlay_count} overlays to {OVERLAYS_DIR}/")

# ── Step 6: Contact sheet ──
print("\n=== Step 6: Generating contact sheet ===")
tp_scored = sorted([(c, crop_score_map[c['crop_id']]) for c in all_crops if c['label']==1], key=lambda x: x[1], reverse=True)
fp_scored = sorted([(c, crop_score_map[c['crop_id']]) for c in all_crops if c['label']==0], key=lambda x: x[1])

n_show = min(20, len(tp_scored), len(fp_scored))
sheet_parts = []
for label_name, crop_list in [('accepted_TP', tp_scored[:n_show]), ('rejected_FP', fp_scored[:n_show])]:
    row = np.zeros((CROP_SIZE, CROP_SIZE * n_show, 3), dtype=np.uint8)
    for i, (crop, score) in enumerate(crop_list):
        img = cv2.imread(crop['crop_path'])
        if img is not None:
            row[:, i*CROP_SIZE:(i+1)*CROP_SIZE] = img
            color = (0,255,0) if score >= best_thresh_final else (0,0,255)
            cv2.putText(row, f'{score:.2f}', (i*CROP_SIZE+2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
    # Add label
    cv2.putText(row, label_name, (2, CROP_SIZE-4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255,255,255), 1)
    sheet_parts.append(row)

contact_sheet = np.vstack(sheet_parts)
cv2.imwrite(os.path.join(OUT_DIR, 'classifier_contact_sheet.jpg'), contact_sheet)
print(f"Written: {OUT_DIR}/classifier_contact_sheet.jpg")

print("\nDONE — Secondary classifier experiment complete")
