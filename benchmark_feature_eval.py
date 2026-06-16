#!/usr/bin/env3
"""
Feature-Based FP Filter — Complete Evaluation
===============================================
Extracts features, trains LR + RF filters, evaluates on v2 stratified split.
Primary metric: held-out v2 test F1 with recall >= 0.95.
"""
import os, csv, cv2, math, random
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# ── Config ──
CONF = 0.25
IOU_THRESHOLD = 0.5
RANDOM_SEED = 42
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
OVERLAYS_DIR = os.path.join(OUT_DIR, 'feature_filter_overlays')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# ── Load data ──
print("=== Loading data ===")
all_crops = []
with open(os.path.join(OUT_DIR, 'classifier_manifest.csv')) as f:
    for row in csv.DictReader(f):
        row['label'] = int(row['label'])
        row['crop_id'] = int(row['crop_id'])
        row['gt_boxes_in_frame'] = int(row['gt_boxes_in_frame'])
        row['px_cx'] = int(row['px_cx'])
        row['px_cy'] = int(row['px_cy'])
        row['det_cx'] = float(row['det_cx'])
        row['det_cy'] = float(row['det_cy'])
        row['det_w'] = float(row['det_w'])
        row['det_h'] = float(row['det_h'])
        row['conf'] = float(row['conf'])
        all_crops.append(row)

with open(os.path.join(OUT_DIR, 'classifier_split_v2.csv')) as f:
    v2_split = {r['frame']: r['split'] for r in csv.DictReader(f)}

train_fnames = set(f for f, s in v2_split.items() if s == 'train')
test_fnames = set(f for f, s in v2_split.items() if s == 'test')

train_crops = [c for c in all_crops if c['frame'] in train_fnames]
test_crops = [c for c in all_crops if c['frame'] in test_fnames]
assert len(set(c['frame'] for c in train_crops) & set(c['frame'] for c in test_crops)) == 0

# ── Load pre-extracted features ──
print("=== Loading features ===")
feature_rows = []
with open(os.path.join(OUT_DIR, 'feature_manifest.csv')) as f:
    for row in csv.DictReader(f):
        row['label'] = int(row['label'])
        row['crop_id'] = int(row['crop_id'])
        feature_rows.append(row)

feat_keys = [k for k in feature_rows[0].keys()
             if k not in ['crop_id','frame','split','label','px_cx','px_cy','v2_split']]

# Build arrays
trn_rows = [r for r in feature_rows if r['split'] == 'train']
tst_rows = [r for r in feature_rows if r['split'] == 'test']

X_trn = np.array([[r[k] for k in feat_keys] for r in trn_rows])
y_trn = np.array([r['label'] for r in trn_rows])
X_tst = np.array([[r[k] for k in feat_keys] for r in tst_rows])
y_tst = np.array([r['label'] for r in tst_rows])

scaler = StandardScaler()
X_trn_sc = scaler.fit_transform(X_trn)
X_tst_sc = scaler.transform(X_tst)

print(f"Train: {X_trn.shape}, Test: {X_tst.shape}")
print(f"Features: {feat_keys}")

# ── Train classifiers ──
print("\n=== Training classifiers ===")

# Logistic Regression
lr = LogisticRegression(C=1.0, class_weight='balanced', random_state=RANDOM_SEED, max_iter=1000)
lr.fit(X_trn_sc, y_trn)
lr_probs = lr.predict_proba(X_tst_sc)[:, 1]

# Random Forest
rf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=RANDOM_SEED, max_depth=5)
rf.fit(X_trn_sc, y_trn)
rf_probs = rf.predict_proba(X_tst_sc)[:, 1]

# ── Find optimal thresholds on TRAIN, apply to TEST ──
print("\n=== Threshold optimization on TRAIN ===")

def sweep_threshold(probs, y_true, name):
    """Find best threshold on train data."""
    best_f1, best_thresh = 0, 0.5
    best_r = 0
    results = []
    for thresh in np.arange(0.05, 0.95, 0.05):
        preds = (probs >= thresh).astype(int)
        tp = int(((preds==1)&(y_true==1)).sum())
        fp = int(((preds==1)&(y_true==0)).sum())
        fn = int(((preds==0)&(y_true==1)).sum())
        r = tp/(tp+fn) if tp+fn>0 else 0
        p = tp/(tp+fp) if tp+fp>0 else 0
        f = 2*p*r/(p+r) if p+r>0 else 0
        results.append({'thresh': thresh, 'tp': tp, 'fp': fp, 'fn': fn,
                        'precision': round(p,4), 'recall': round(r,4), 'f1': round(f,4)})
        if f > best_f1:
            best_f1, best_thresh = f, thresh
            best_r = r
    return results, best_thresh, best_f1

lr_train_results, lr_best_thresh, lr_best_f1 = sweep_threshold(
    lr.predict_proba(X_trn_sc)[:, 1], y_trn, "LR")
rf_train_results, rf_best_thresh, rf_best_f1 = sweep_threshold(
    rf.predict_proba(X_trn_sc)[:, 1], y_trn, "RF")

print(f"LR best train: thresh={lr_best_thresh:.2f}, F1={lr_best_f1:.4f}")
print(f"RF best train: thresh={rf_best_thresh:.2f}, F1={rf_best_f1:.4f}")

# Also find recall>=0.95 thresholds on train
def find_recall_threshold(probs, y_true, min_recall=0.95):
    """Find threshold that achieves min_recall with best F1."""
    best_f1, best_thresh = 0, 0.5
    for thresh in np.arange(0.05, 0.95, 0.01):
        preds = (probs >= thresh).astype(int)
        tp = int(((preds==1)&(y_true==1)).sum())
        fp = int(((preds==1)&(y_true==0)).sum())
        fn = int(((preds==0)&(y_true==1)).sum())
        r = tp/(tp+fn) if tp+fn>0 else 0
        p = tp/(tp+fp) if tp+fp>0 else 0
        f = 2*p*r/(p+r) if p+r>0 else 0
        if r >= min_recall and f > best_f1:
            best_f1, best_thresh = f, thresh
    return best_thresh, best_f1

lr_r95_thresh, lr_r95_f1 = find_recall_threshold(lr.predict_proba(X_trn_sc)[:, 1], y_trn)
rf_r95_thresh, rf_r95_f1 = find_recall_threshold(rf.predict_proba(X_trn_sc)[:, 1], y_trn)
print(f"LR R>=0.95: thresh={lr_r95_thresh:.2f}, F1={lr_r95_f1:.4f}")
print(f"RF R>=0.95: thresh={rf_r95_thresh:.2f}, F1={rf_r95_f1:.4f}")

# ── Apply to TEST ──
print("\n=== Test set evaluation ===")

def evaluate_filter(probs, y_true, thresh, name):
    preds = (probs >= thresh).astype(int)
    tp = int(((preds==1)&(y_true==1)).sum())
    fp = int(((preds==1)&(y_true==0)).sum())
    fn = int(((preds==0)&(y_true==1)).sum())
    tn = int(((preds==0)&(y_true==0)).sum())
    r = tp/(tp+fn) if tp+fn>0 else 0
    p = tp/(tp+fp) if tp+fp>0 else 0
    f = 2*p*r/(p+r) if p+r>0 else 0
    print(f"  {name}: TP={tp} FP={fp} FN={fn} TN={tn} P={p:.4f} R={r:.4f} F1={f:.4f}")
    return {'name': name, 'thresh': thresh, 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(p,4), 'recall': round(r,4), 'f1': round(f,4)}

# Baseline
baseline_test = evaluate_filter(np.ones(len(y_tst)), y_tst, 0.0, "baseline")

# LR with best train threshold
lr_test = evaluate_filter(lr_probs, y_tst, lr_best_thresh, f"LR_best({lr_best_thresh:.2f})")

# LR with R>=0.95 threshold
lr_r95_test = evaluate_filter(lr_probs, y_tst, lr_r95_thresh, f"LR_R95({lr_r95_thresh:.2f})")

# RF with best train threshold
rf_test = evaluate_filter(rf_probs, y_tst, rf_best_thresh, f"RF_best({rf_best_thresh:.2f})")

# RF with R>=0.95 threshold
rf_r95_test = evaluate_filter(rf_probs, y_tst, rf_r95_thresh, f"RF_R95({rf_r95_thresh:.2f})")

# ── Save per-detection scores ──
print("\n=== Saving per-detection scores ===")
score_rows = []
for i, row in enumerate(tst_rows):
    score_rows.append({
        'crop_id': row['crop_id'],
        'frame': row['frame'],
        'label': row['label'],
        'px_cx': row['px_cx'],
        'px_cy': row['px_cy'],
        'lr_prob': round(float(lr_probs[i]), 6),
        'rf_prob': round(float(rf_probs[i]), 6),
        'lr_accept_best': int(lr_probs[i] >= lr_best_thresh),
        'lr_accept_r95': int(lr_probs[i] >= lr_r95_thresh),
        'rf_accept_best': int(rf_probs[i] >= rf_best_thresh),
        'rf_accept_r95': int(rf_probs[i] >= rf_r95_thresh),
    })

with open(os.path.join(OUT_DIR, 'feature_filter_scores.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=score_rows[0].keys())
    writer.writeheader()
    writer.writerows(score_rows)
print(f"Written: {OUT_DIR}/feature_filter_scores.csv")

# ── Per-frame benchmark measurement ──
print("\n=== Per-frame benchmark measurement ===")

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

# Build frame->dets map with scores
frame_dets = {}
for crop in all_crops:
    # Find matching feature row
    feat = next((r for r in feature_rows if r['crop_id'] == crop['crop_id']), None)
    if feat is None: continue
    
    # Find matching score row (test only)
    score = next((r for r in score_rows if r['crop_id'] == crop['crop_id']), None)
    
    d = {
        'cx': crop['det_cx'], 'cy': crop['det_cy'],
        'w': crop['det_w'], 'h': crop['det_h'],
        'px_cx': crop['px_cx'], 'px_cy': crop['px_cy'],
        'label': crop['label'], 'crop_id': crop['crop_id'],
        'lr_prob': score['lr_prob'] if score else 0.5,
        'rf_prob': score['rf_prob'] if score else 0.5,
    }
    frame_dets.setdefault(crop['frame'], []).append(d)

frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])

VARIANTS = [
    ('baseline', 'none', 0, None),
    ('lr_best', 'lr', lr_best_thresh, None),
    ('lr_r95', 'lr', lr_r95_thresh, None),
    ('rf_best', 'rf', rf_best_thresh, None),
    ('rf_r95', 'rf', rf_r95_thresh, None),
]

all_results = []
per_frame = []

for vname, vtype, vthresh, _ in VARIANTS:
    for sname in ['train', 'test', 'all']:
        ttp, tfp, tfn, trm, nf = 0, 0, 0, 0, 0
        for fname in frame_files:
            if fname not in frame_dets: continue
            if sname == 'train' and fname not in train_fnames: continue
            if sname == 'test' and fname not in test_fnames: continue
            
            frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
            if frame is None: continue
            gt = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
            dets = frame_dets[fname]; nf += 1
            
            if vtype == 'none':
                kept = dets; removed = []
            elif vtype == 'lr':
                kept = [d for d in dets if d['lr_prob'] >= vthresh]
                removed = [d for d in dets if d['lr_prob'] < vthresh]
            elif vtype == 'rf':
                kept = [d for d in dets if d['rf_prob'] >= vthresh]
                removed = [d for d in dets if d['rf_prob'] < vthresh]
            
            tp, fp, fn = match_measure(kept, gt)
            ttp += tp; tfp += fp; tfn += fn; trm += len(removed)
            
            per_frame.append({
                'variant': vname, 'split': sname, 'frame': fname,
                'n_det_before': len(dets), 'n_removed': len(removed),
                'n_det_after': len(kept), 'tp': tp, 'fp': fp, 'fn': fn,
            })
        
        p, r, f = metrics(ttp, tfp, tfn)
        all_results.append({
            'variant': vname, 'split': sname, 'frames': nf,
            'tp': ttp, 'fp': tfp, 'fn': tfn,
            'precision': p, 'recall': r, 'f1': f,
            'total_removed': trm, 'threshold': vthresh if vthresh else 'N/A',
        })
        tag = f"[{sname:5s}]" if sname != 'all' else "[ ALL ]"
        print(f"  {vname:15s} {tag}: TP={ttp:3d} FP={tfp:3d} FN={tfn:2d} "
              f"P={p:.4f} R={r:.4f} F1={f:.4f} removed={trm:3d} ({nf} frames)")

with open(os.path.join(OUT_DIR, 'feature_filter_results.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','split','frames','tp','fp','fn','precision','recall','f1','total_removed','threshold'])
    writer.writeheader(); writer.writerows(all_results)
print(f"\nWritten: {OUT_DIR}/feature_filter_results.csv")

with open(os.path.join(OUT_DIR, 'feature_filter_per_frame.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['variant','split','frame','n_det_before','n_removed','n_det_after','tp','fp','fn'])
    writer.writeheader(); writer.writerows(per_frame)
print(f"Written: {OUT_DIR}/feature_filter_per_frame.csv")

# ── Overlays for test frames ──
print("\n=== Generating test-set overlays ===")
for vname, vtype, vthresh, _ in VARIANTS[1:]:  # skip baseline
    ov_count = 0
    for fname in sorted(test_fnames):
        if fname not in frame_dets: continue
        frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
        if frame is None: continue
        gt = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))
        h, w = frame.shape[:2]
        dets = frame_dets[fname]
        
        if vtype == 'lr':
            kept = [d for d in dets if d['lr_prob'] >= vthresh]
            removed = [d for d in dets if d['lr_prob'] < vthresh]
        elif vtype == 'rf':
            kept = [d for d in dets if d['rf_prob'] >= vthresh]
            removed = [d for d in dets if d['rf_prob'] < vthresh]
        
        if not removed: continue
        
        out = frame.copy()
        for d in removed:
            cv2.drawMarker(out, (d['px_cx'], d['px_cy']), (0,0,255), cv2.MARKER_TILTED_CROSS, 12, 2)
        for d in kept:
            cv2.drawMarker(out, (d['px_cx'], d['px_cy']), (255,128,0), cv2.MARKER_SQUARE, 8, 1)
        for box in gt:
            cx,cy,bw,bh = box
            cv2.rectangle(out,(int((cx-bw/2)*w),int((cy-bh/2)*h)),(int((cx+bw/2)*w),int((cy+bh/2)*h)),(0,255,0),2)
        cv2.putText(out, f'{vname}(th={vthresh:.2f}): -{len(removed)}', (5,15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
        cv2.putText(out, '[TEST HELD-OUT]', (w-120, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,255), 1)
        cv2.imwrite(os.path.join(OVERLAYS_DIR, f'{vname}_{fname}'), out)
        ov_count += 1
    print(f"  {vname}: {ov_count} overlays")

print("\nDONE — Feature filter evaluation complete")
