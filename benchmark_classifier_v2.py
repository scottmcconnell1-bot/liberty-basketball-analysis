#!/usr/bin/env python3
"""
Secondary Classifier — Fully Corrected Held-Out Experiment
===========================================================
Retrains classifier from scratch using ONLY v2 train frames.
Evaluates on strictly held-out v2 test frames (zero leakage).

Training data:  v2 train frames only (82 frames, 128 crops)
Validation:    held-out portion of v2 train (for threshold/lr tuning)
Test data:     v2 test frames only (37 frames, 52 crops) — NEVER seen during training

All random seeds fixed for reproducibility.
"""
import os, csv, cv2, math, random, shutil
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms

# ── Config ──
CONF = 0.25
IOU_THRESHOLD = 0.5
RANDOM_SEED = 42
TRAIN_FRAC = 0.7
CROP_SIZE = 64
BATCH_SIZE = 16
MAX_EPOCHS = 50
PATIENCE = 10
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
CROPS_DIR = os.path.join(OUT_DIR, 'classifier_crops')
OVERLAYS_DIR = os.path.join(OUT_DIR, 'classifier_overlays_v3')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
device = torch.device('cpu')
torch.set_num_threads(2)

# ── Load v2 split ──
print("=== Loading v2 stratified split ===")
with open(os.path.join(OUT_DIR, 'classifier_split_v2.csv')) as f:
    reader = csv.DictReader(f)
    v2_split = {r['frame']: r['split'] for r in reader}

v2_train_fnames = set(f for f, s in v2_split.items() if s == 'train')
v2_test_fnames = set(f for f, s in v2_split.items() if s == 'test')
print(f"V2 train: {len(v2_train_fnames)} frames, V2 test: {len(v2_test_fnames)} frames")

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

# Split crops by v2 frame assignment
train_crops = [c for c in all_crops if c['frame'] in v2_train_fnames]
test_crops  = [c for c in all_crops if c['frame'] in v2_test_fnames]
print(f"Train crops: {len(train_crops)} (pos={sum(1 for c in train_crops if c['label']==1)}, neg={sum(1 for c in train_crops if c['label']==0)})")
print(f"Test crops:  {len(test_crops)} (pos={sum(1 for c in test_crops if c['label']==1)}, neg={sum(1 for c in test_crops if c['label']==0)})")

# Verify zero overlap
train_frames_in_crops = set(c['frame'] for c in train_crops)
test_frames_in_crops  = set(c['frame'] for c in test_crops)
assert len(train_frames_in_crops & test_frames_in_crops) == 0, "FRAME OVERLAP!"
print("  Zero frame overlap verified.")

# ── Further split train into train/val for threshold selection ──
# Use 80/20 of train crops (by frame) for threshold tuning
random.shuffle(train_crops)
val_frame_count = max(1, int(len(train_frames_in_crops) * 0.2))
val_frames = set(c['frame'] for c in train_crops[:val_frame_count])
trn_frames = train_frames_in_crops - val_frames

trn_crops = [c for c in train_crops if c['frame'] in trn_frames]
val_crops = [c for c in train_crops if c['frame'] in val_frames]
print(f"\n  Sub-split: {len(trn_crops)} train crops, {len(val_crops)} val crops")
print(f"  Val frames: {len(val_frames)}")

# ── Datasets ──
class CropDataset(Dataset):
    def __init__(self, crops, augment=False):
        self.crops = crops
        self.augment = augment
        self.base_t = transforms.Compose([
            transforms.ToPILImage(), transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
        ])
        self.aug_t = transforms.Compose([
            transforms.ToPILImage(),
            transforms.RandomHorizontalFlip(0.5),
            transforms.RandomRotation(15),
            transforms.ColorJitter(0.2,0.2,0.2,0.1),
            transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225]),
        ])
    def __len__(self): return len(self.crops)
    def __getitem__(self, idx):
        img = cv2.imread(self.crops[idx]['crop_path'])
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if self.augment:
            tensor = self.aug_t(img)
            if random.random() < 0.3:
                _, h, w = tensor.shape
                eh, ew = random.randint(4, 16), random.randint(4, 16)
                ex, ey = random.randint(0, w-ew), random.randint(0, h-eh)
                tensor[:, ey:ey+eh, ex:ex+ew] = torch.randn(3, eh, ew) * 0.5
        else:
            tensor = self.base_t(img)
        return tensor, self.crops[idx]['label'], self.crops[idx]['crop_id']

trn_ds = CropDataset(trn_crops, augment=True)
val_ds = CropDataset(val_crops, augment=False)
tst_ds = CropDataset(test_crops, augment=False)
trn_ld = DataLoader(trn_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
val_ld = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
tst_ld = DataLoader(tst_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

# ── Model ──
print("\n=== Training MobileNetV2 classifier (v2 train only) ===")
model = models.mobilenet_v2(pretrained=True)
model.classifier = nn.Sequential(
    nn.Dropout(0.3), nn.Linear(model.last_channel, 128), nn.ReLU(),
    nn.Dropout(0.2), nn.Linear(128, 1),
)
model = model.to(device)

n_pos = sum(1 for c in trn_crops if c['label']==1)
n_neg = sum(1 for c in trn_crops if c['label']==0)
pos_w = torch.tensor([n_neg/n_pos]).to(device)
criterion = nn.BCEWithLogitsLoss(pos_weight=pos_w)
optimizer = optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=MAX_EPOCHS)

best_val_f1 = 0
best_state = None
best_thresh = 0.5
no_improve = 0

for epoch in range(MAX_EPOCHS):
    model.train()
    trn_loss = 0
    for X, y, _ in trn_ld:
        X, y = X.to(device), y.float().to(device)
        optimizer.zero_grad()
        loss = criterion(model(X).squeeze(), y)
        loss.backward()
        optimizer.step()
        trn_loss += loss.item()
    scheduler.step()

    model.eval()
    val_preds, val_labels = [], []
    with torch.no_grad():
        for X, y, _ in val_ld:
            val_preds.extend(torch.sigmoid(model(X.to(device)).squeeze()).cpu().numpy())
            val_labels.extend(y.numpy())
    vp = np.array(val_preds); vl = np.array(val_labels)

    # Find best threshold on val
    bt, bf = 0.5, 0
    for t in np.arange(0.05, 0.95, 0.05):
        pb = (vp >= t).astype(int)
        tp = int(((pb==1)&(vl==1)).sum()); fp = int(((pb==1)&(vl==0)).sum()); fn = int(((pb==0)&(vl==1)).sum())
        p = tp/(tp+fp) if tp+fp>0 else 0; r = tp/(tp+fn) if tp+fn>0 else 0
        f = 2*p*r/(p+r) if p+r>0 else 0
        if f > bf: bf=f; bt=t

    pb = (vp>=bt).astype(int)
    tp=int(((pb==1)&(vl==1)).sum()); fp=int(((pb==1)&(vl==0)).sum()); fn=int(((pb==0)&(vl==1)).sum())
    p=tp/(tp+fp) if tp+fp>0 else 0; r=tp/(tp+fn) if tp+fn>0 else 0
    f=2*p*r/(p+r) if p+r>0 else 0

    if epoch%5==0 or f>best_val_f1:
        print(f"  Epoch {epoch:3d}: loss={trn_loss/len(trn_ld):.4f} val_F1={f:.4f} P={p:.4f} R={r:.4f} thresh={bt:.2f} TP={tp} FP={fp} FN={fn}")

    if f > best_val_f1:
        best_val_f1 = f
        best_state = {k:v.clone() for k,v in model.state_dict().items()}
        best_thresh = bt
        no_improve = 0
    else:
        no_improve += 1
        if no_improve >= PATIENCE:
            print(f"  Early stop at epoch {epoch}")
            break

model.load_state_dict(best_state)
model.eval()

# ── Score ALL crops ──
print("\n=== Scoring all crops with retrained model ===")
all_ds = CropDataset(all_crops, augment=False)
all_ld = DataLoader(all_ds, batch_size=32, shuffle=False, num_workers=0)
score_map = {}
with torch.no_grad():
    for X, _, cids in all_ld:
        out = torch.sigmoid(model(X.to(device)).squeeze())
        for i, cid in enumerate(cids.numpy()):
            score_map[int(cid)] = out[i].item()
print(f"Scored {len(score_map)} crops")

# ── Save retrained model ──
os.makedirs('models', exist_ok=True)
model_path = 'models/court_fp_classifier_v2.pt'
torch.save({
    'model_state': best_state,
    'threshold': best_thresh,
    'crop_size': CROP_SIZE,
    'val_f1': best_val_f1,
    'split': 'v2_stratified',
    'train_frames': len(trn_frames),
    'val_frames': len(val_frames),
    'test_frames': len(v2_test_fnames),
    'seed': RANDOM_SEED,
    'note': 'Retrained from scratch on v2 train only. Zero leakage.',
}, model_path)
print(f"Saved: {model_path}")

# ── Save per-detection scores ──
print("\n=== Saving per-detection scores ===")
det_records = []
for crop in all_crops:
    split = v2_split.get(crop['frame'], 'unknown')
    score = score_map.get(crop['crop_id'], 0.5)
    det_records.append({
        'crop_id': crop['crop_id'],
        'frame': crop['frame'],
        'v2_split': split,
        'det_idx': crop['det_idx'],
        'gt_boxes_in_frame': crop['gt_boxes_in_frame'],
        'label': crop['label'],
        'det_confidence': crop['conf'],
        'classifier_score': round(score, 6),
        'classifier_accept': int(score >= best_thresh),
        'px_cx': crop['px_cx'],
        'px_cy': crop['px_cy'],
    })
with open(os.path.join(OUT_DIR, 'classifier_detection_scores_v3.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=det_records[0].keys())
    writer.writeheader()
    writer.writerows(det_records)
print(f"Written: {OUT_DIR}/classifier_detection_scores_v3.csv")

# ── Benchmark measurement ──
print("\n=== Benchmark measurement ===")

def load_gt(lp):
    boxes = []
    if os.path.exists(lp):
        with open(lp) as f:
            for l in f:
                parts = l.strip().split()
                if len(parts)==5: boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def iou_yolo(b1,b2):
    cx1,cy1,w1,h1=b1; cx2,cy2,w2,h2=b2
    x1,y1,x2,y2=cx1-w1/2,cy1-h1/2,cx1+w1/2,cy1+h1/2
    x3,y3,x4,y4=cx2-w2/2,cy2-h2/2,cx2+w2/2,cy2+h2/2
    xi,yi,xj,yj=max(x1,x3),max(y1,y3),min(x2,x4),min(y2,y4)
    if xj<=xi or yj<=yi: return 0.
    return (xj-xi)*(yj-yi)/(w1*h1+w2*h2-(xj-xi)*(yj-yi))

def match_measure(dets, gt_boxes):
    matched=set()
    for gt in gt_boxes:
        best_i,best_j=0,-1
        for j,det in enumerate(dets):
            if j in matched: continue
            i=iou_yolo(gt,(det['cx'],det['cy'],det['w'],det['h']))
            if i>best_i: best_i,best_j=i,j
        if best_i>=IOU_THRESHOLD: matched.add(best_j)
    tp=len(matched); return tp, len(dets)-tp, len(gt_boxes)-tp

def metrics(tp,fp,fn):
    p=tp/(tp+fp) if tp+fp>0 else 0; r=tp/(tp+fn) if tp+fn>0 else 0
    f=2*p*r/(p+r) if p+r>0 else 0
    return round(p,4),round(r,4),round(f,4)

# Build frame->dets map
frame_dets = {}
for crop in all_crops:
    score = score_map.get(crop['crop_id'], 0.5)
    d = {'cx':float(crop['det_cx']),'cy':float(crop['det_cy']),
         'w':float(crop['det_w']),'h':float(crop['det_h']),
         'score':score,'label':crop['label'],'crop_id':crop['crop_id'],
         'px_cx':crop['px_cx'],'px_cy':crop['px_cy']}
    frame_dets.setdefault(crop['frame'], []).append(d)

VARIANTS = [('baseline',None,None), ('classifier',best_thresh,None), ('classifier_nms',best_thresh,0.3)]
SPLITS = ['train','test','all']
frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])

all_results = []
per_frame = []

for vname, vthresh, nms_iou in VARIANTS:
    for sname in SPLITS:
        ttp,tfp,tfn,trm,nf = 0,0,0,0,0
        for fname in frame_files:
            if fname not in frame_dets: continue
            if sname=='train' and fname not in v2_train_fnames: continue
            if sname=='test' and fname not in v2_test_fnames: continue
            frame = cv2.imread(os.path.join(FRAMES_DIR,fname))
            if frame is None: continue
            gt = load_gt(os.path.join(LABELS_DIR,fname.replace('.jpg','.txt')))
            dets = frame_dets[fname]; nf+=1
            if vthresh is not None:
                kept=[d for d in dets if d['score']>=vthresh]
                removed=[d for d in dets if d['score']<vthresh]
            else: kept=dets; removed=[]
            if nms_iou and len(kept)>1:
                scores=[d['score'] for d in kept]
                order=sorted(range(len(kept)),key=lambda i:scores[i],reverse=True)
                nmsk=[]
                while order:
                    i=order[0]; nmsk.append(i); rest=[]
                    for j in order[1:]:
                        io=iou_yolo((kept[i]['cx'],kept[i]['cy'],kept[i]['w'],kept[i]['h']),
                                    (kept[j]['cx'],kept[j]['cy'],kept[j]['w'],kept[j]['h']))
                        if io<nms_iou: rest.append(j)
                    order=rest
                ns=set(nmsk); removed2=[kept[i] for i in range(len(kept)) if i not in ns]
                kept=[kept[i] for i in nmsk]; removed=removed+removed2
            tp,fp,fn=match_measure(kept,gt)
            ttp+=tp; tfp+=fp; tfn+=fn; trm+=len(removed)
            per_frame.append({'variant':vname,'split':sname,'frame':fname,
                              'n_det_before':len(dets),'n_removed':len(removed),
                              'n_det_after':len(kept),'tp':tp,'fp':fp,'fn':fn})
        p,r,f=metrics(ttp,tfp,tfn)
        all_results.append({'variant':vname,'split':sname,'frames':nf,
                            'tp':ttp,'fp':tfp,'fn':tfn,
                            'precision':p,'recall':r,'f1':f,
                            'total_removed':trm,'threshold':vthresh if vthresh else 'N/A'})
        tag=f"[{sname:5s}]" if sname!='all' else "[ ALL ]"
        print(f"  {vname:25s} {tag}: TP={ttp:3d} FP={tfp:3d} FN={tfn:2d} P={p:.4f} R={r:.4f} F1={f:.4f} removed={trm:3d} ({nf} frames)")

with open(os.path.join(OUT_DIR,'classifier_results_v3.csv'),'w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['variant','split','frames','tp','fp','fn','precision','recall','f1','total_removed','threshold'])
    writer.writeheader(); writer.writerows(all_results)
print(f"\nWritten: {OUT_DIR}/classifier_results_v3.csv")

with open(os.path.join(OUT_DIR,'classifier_per_frame_v3.csv'),'w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['variant','split','frame','n_det_before','n_removed','n_det_after','tp','fp','fn'])
    writer.writeheader(); writer.writerows(per_frame)
print(f"Written: {OUT_DIR}/classifier_per_frame_v3.csv")

# ── Overlays for test frames ──
print("\n=== Generating test-set overlays ===")
ov_count=0
for fname in sorted(v2_test_fnames):
    if fname not in frame_dets: continue
    frame=cv2.imread(os.path.join(FRAMES_DIR,fname))
    if frame is None: continue
    gt=load_gt(os.path.join(LABELS_DIR,fname.replace('.jpg','.txt')))
    h,w=frame.shape[:2]
    dets=frame_dets[fname]
    kept=[d for d in dets if d['score']>=best_thresh]
    removed=[d for d in dets if d['score']<best_thresh]
    if not removed: continue
    out=frame.copy()
    for d in removed: cv2.drawMarker(out,(d['px_cx'],d['px_cy']),(0,0,255),cv2.MARKER_TILTED_CROSS,12,2)
    for d in kept: cv2.drawMarker(out,(d['px_cx'],d['px_cy']),(255,128,0),cv2.MARKER_SQUARE,8,1)
    for box in gt:
        cx,cy,bw,bh=box
        cv2.rectangle(out,(int((cx-bw/2)*w),int((cy-bh/2)*h)),(int((cx+bw/2)*w),int((cy+bh/2)*h)),(0,255,0),2)
    cv2.putText(out,f'clf_v2(th={best_thresh:.2f}): -{len(removed)}',(5,15),cv2.FONT_HERSHEY_SIMPLEX,0.4,(255,255,255),1)
    cv2.putText(out,'[TEST HELD-OUT]',(w-120,15),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,255,255),1)
    cv2.imwrite(os.path.join(OVERLAYS_DIR,f'classifier_test_{fname}'),out)
    ov_count+=1
print(f"Wrote {ov_count} test overlays to {OVERLAYS_DIR}/")
print("\nDONE — Fully corrected held-out evaluation complete")
