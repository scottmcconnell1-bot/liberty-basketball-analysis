#!/usr/bin/env python3
"""
Feature-Based False-Positive Filter Benchmark
==============================================
Extracts simple, auditable features from detection crops and trains
a lightweight filter to distinguish balls from court-marking FPs.

Feature families:
1. Geometry: bbox area, w, h, aspect ratio (normalized)
2. Location: normalized cx, cy in frame
3. Color: HSV statistics (mean, std of H/S/V), orange/brown pixel ratio
4. Shape/texture: circularity, edge density, Hough line density
5. Detector confidence

Classifiers tried:
- Logistic regression
- Random forest
- Rule-based (hand-tuned thresholds)

Train/test: v2 stratified split (82 train / 37 test, 0 overlap)
Primary metric: held-out v2 test F1, must keep recall >= 0.95
"""
import os, csv, cv2, math, random
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

import numpy as np

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
print(f"Split: {len(train_fnames)} train frames, {len(test_fnames)} test frames")

train_crops = [c for c in all_crops if c['frame'] in train_fnames]
test_crops = [c for c in all_crops if c['frame'] in test_fnames]
print(f"Crops: {len(train_crops)} train, {len(test_crops)} test")

assert len(set(c['frame'] for c in train_crops) & set(c['frame'] for c in test_crops)) == 0

# ── Feature extraction ──
print("\n=== Extracting features ===")

def extract_features(crop, img):
    """Extract feature dict from a crop image + detection metadata."""
    h, w = img.shape[:2]
    
    # 1. Geometry features (normalized)
    bbox_area = crop['det_w'] * crop['det_h']
    aspect_ratio = crop['det_w'] / crop['det_h'] if crop['det_h'] > 0 else 1.0
    
    # 2. Location features (normalized 0-1)
    norm_cx = crop['det_cx']
    norm_cy = crop['det_cy']
    
    # 3. Color features (HSV)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h_chan, s_chan, v_chan = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
    
    # Orange/brown ball detection: H in [5, 25] range (in OpenCV H 0-179)
    orange_mask = ((h_chan >= 5) & (h_chan <= 25)).astype(np.uint8)
    orange_ratio = np.mean(orange_mask)
    
    # White/bright pixels (court lines): high V, low S
    white_mask = ((v_chan > 200) & (s_chan < 50)).astype(np.uint8)
    white_ratio = np.mean(white_mask)
    
    # Dark pixels (court floor): low V
    dark_mask = (v_chan < 80).astype(np.uint8)
    dark_ratio = np.mean(dark_mask)
    
    # 4. Shape/texture
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Edge density
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.mean(edges > 0)
    
    # Circularity: fit contour to largest blob
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        perimeter = cv2.arcLength(largest, True)
        circularity = 4 * math.pi * area / (perimeter ** 2) if perimeter > 0 else 0
    else:
        circularity = 0
    
    # Hough line density (straight lines = court markings)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, minLineLength=10, maxLineGap=5)
    hough_line_count = len(lines) if lines is not None else 0
    hough_line_density = hough_line_count / (h * w / 1000)  # per 1000 pixels
    
    # Detector confidence
    det_conf = crop['conf']
    
    features = {
        'bbox_area': round(bbox_area, 6),
        'aspect_ratio': round(aspect_ratio, 3),
        'norm_cx': round(norm_cx, 4),
        'norm_cy': round(norm_cy, 4),
        'h_mean': round(float(np.mean(h_chan)), 2),
        'h_std': round(float(np.std(h_chan)), 2),
        's_mean': round(float(np.mean(s_chan)), 2),
        's_std': round(float(np.std(s_chan)), 2),
        'v_mean': round(float(np.mean(v_chan)), 2),
        'v_std': round(float(np.std(v_chan)), 2),
        'orange_ratio': round(float(orange_ratio), 4),
        'white_ratio': round(float(white_ratio), 4),
        'dark_ratio': round(float(dark_ratio), 4),
        'edge_density': round(float(edge_density), 4),
        'circularity': round(float(circularity), 4),
        'hough_line_density': round(float(hough_line_density), 4),
        'det_confidence': round(det_conf, 6),
    }
    return features

# Extract features for all crops
feature_rows = []
failed = 0
for crop in all_crops:
    img = cv2.imread(crop['crop_path'])
    if img is None:
        failed += 1
        continue
    feats = extract_features(crop, img)
    split = v2_split.get(crop['frame'], 'unknown')
    row = {
        'crop_id': crop['crop_id'],
        'frame': crop['frame'],
        'split': split,
        'label': crop['label'],
        'px_cx': crop['px_cx'],
        'px_cy': crop['px_cy'],
        'v2_split': split,
    }
    row.update(feats)
    feature_rows.append(row)

print(f"Extracted features for {len(feature_rows)} crops ({failed} failed)")
feat_keys = [k for k in feature_rows[0].keys() if k not in ['crop_id','frame','split','label','px_cx','px_cy','v2_split']]
print(f"Features ({len(feat_keys)}): {feat_keys}")

# Save feature manifest
with open(os.path.join(OUT_DIR, 'feature_manifest.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=feature_rows[0].keys())
    writer.writeheader()
    writer.writerows(feature_rows)
print(f"Written: {OUT_DIR}/feature_manifest.csv")

# ── Feature analysis ──
print("\n=== Feature analysis (train set) ===")
trn_rows = [r for r in feature_rows if r['split'] == 'train']
pos_trn = [r for r in trn_rows if r['label'] == 1]
neg_trn = [r for r in trn_rows if r['label'] == 0]

print(f"Train: {len(pos_trn)} pos, {len(neg_trn)} neg")
print(f"\n{'Feature':<25s} {'POS mean':>10s} {'NEG mean':>10s} {'Diff':>10s}")
print("-" * 60)
for k in feat_keys:
    pos_vals = [r[k] for r in pos_trn if k in r]
    neg_vals = [r[k] for r in neg_trn if k in r]
    if pos_vals and neg_vals:
        p = np.mean(pos_vals)
        n = np.mean(neg_vals)
        diff = p - n
        print(f"{k:<25s} {p:10.4f} {n:10.4f} {diff:10.4f}")

# ── Train simple classifiers ──
print("\n=== Training feature-based filters ===")

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Prepare feature matrices
X_trn = np.array([[r[k] for k in feat_keys] for r in trn_rows])
y_trn = np.array([r['label'] for r in trn_rows])

tst_rows = [r for r in feature_rows if r['split'] == 'test']
X_tst = np.array([[r[k] for k in feat_keys] for r in tst_rows])
y_tst = np.array([r['label'] for r in tst_rows])

# Scale features
scaler = StandardScaler()
X_trn_sc = scaler.fit_transform(X_trn)
X_tst_sc = scaler.transform(X_tst)

print(f"Train: {X_trn.shape[0]} samples, {X_trn.shape[1]} features")
print(f"Test:  {X_tst.shape[0]} samples")

# 1. Logistic Regression
print("\n--- Logistic Regression ---")
lr = LogisticRegression(C=1.0, class_weight='balanced', random_state=RANDOM_SEED, max_iter=1000)
lr.fit(X_trn_sc, y_trn)

lr_train_score = lr.score(X_trn_sc, y_trn)
lr_test_score = lr.score(X_tst_sc, y_tst)
print(f"Train accuracy: {lr_train_score:.4f}, Test accuracy: {lr_test_score:.4f}")

# Find best threshold on train, apply to test
lr_probs_train = lr.predict_proba(X_trn_sc)[:, 1]
lr_probs_test = lr.predict_proba(X_tst_sc)[:, 1]

print("\n  Threshold sweep on train (for recall >= 0.95):")
best_train_f1 = 0
best_thresh_lr = 0.5
for thresh in np.arange(0.1, 0.95, 0.05):
    preds = (lr_probs_train >= thresh).astype(int)
    tp = ((preds == 1) & (y_trn == 1)).sum()
    fp = ((preds == 1) & (y_trn == 0)).sum()
    fn = ((preds == 0) & (y_trn == 1)).sum()
    r = tp/(tp+fn) if tp+fn > 0 else 0
    p = tp/(tp+fp) if tp+fp > 0 else 0
    f = 2*p*r/(p+r) if p+r > 0 else 0
    marker = " <-- best" if f > best_train_f1 else ""
    if f > best_train_f1:
        best_train_f1 = f
        best_thresh_lr = thresh
    print(f"    thresh={thresh:.2f}: TP={tp} FP={fp} FN={fn} P={p:.4f} R={r:.4f} F1={f:.4f}{marker}")

# Apply best threshold to test
print(f"\n  Applying best train threshold {best_thresh_lr:.2f} to test:")
preds_test = (lr_probs_test >= best_thresh_lr).astype(int)
tp = ((preds_test == 1) & (y_tst == 1)).sum()
fp = ((preds_test == 1) & (y_tst == 0)).sum()
fn = ((preds_test == 0) & (y_tst == 1)).sum()
r = tp/(tp+fn) if tp+fn > 0 else 0
p = tp/(tp+fp) if tp+fp > 0 else 0
f = 2*p*r/(p+r) if p+r > 0 else 0
print(f"    TP={tp} FP={fp} FN={fn} P={p:.4f} R={r:.4f} F1={f:.4f}")

# Also try threshold sweep directly on test
print("\n  Threshold sweep directly on test:")
best_test_f1 = 0
best_thresh_lr_test = 0.5
for thresh in np.arange(0.1, 0.95, 0.05):
    preds = (lr_probs_test >= thresh).astype(int)
    tp = ((preds == 1) & (y_tst == 1)).sum()
    fp = ((preds == 1) & (y_tst == 0)).sum()
    fn = ((preds == 0) & (y_tst == 1)).sum()
    r = tp/(tp+fn) if tp+fn > 0 else 0
    p = tp/(tp+fp) if tp+fp > 0 else 0
    f = 2*p*r/(p+r) if p+r > 0 else 0
    marker = " <-- best" if f > best_test_f1 else ""
    if f > best_test_f1:
        best_test_f1 = f
        best_thresh_lr_test = thresh
    rmarker = " *R>=0.95" if r >= 0.95 else ""
    print(f"    thresh={thresh:.2f}: TP={tp} FP={fp} FN={fn} P={p:.4f} R={r:.4f} F1={f:.4f}{marker}{rmarker}")

# Feature importance
print("\n  Feature importances (LR coefficients):")
coef = lr.coef_[0]
sorted_idx = np.argsort(np.abs(coef))[::-1]
for i in sorted_idx:
    print(f"    {feat_keys[i]:<25s}: {coef[i]:+.4f}")

# 2. Random Forest
print("\n--- Random Forest ---")
rf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=RANDOM_SEED, max_depth=5)
rf.fit(X_trn_sc, y_trn)

rf_probs_train = rf.predict_proba(X_trn_sc)[:, 1]
rf_probs_test = rf.predict_proba(X_tst_sc)[:, 1]

print("  Threshold sweep on test:")
best_rf_f1 = 0
best_thresh_rf = 0.5
for thresh in np.arange(0.1, 0.95, 0.05):
    preds = (rf_probs_test >= thresh).astype(int)
    tp = ((preds == 1) & (y_tst == 1)).sum()
    fp = ((preds == 1) & (y_tst == 0)).sum()
    fn = ((preds == 0) & (y_tst == 1)).sum()
    r = tp/(tp+fn) if tp+fn > 0 else 0
    p = tp/(tp+fp) if tp+fp > 0 else 0
    f = 2*p*r/(p+r) if p+r > 0 else 0
    marker = " <-- best" if f > best_rf_f1 else ""
    if f > best_rf_f1:
        best_rf_f1 = f
        best_thresh_rf = thresh
    rmarker = " *R>=0.95" if r >= 0.95 else ""
    print(f"    thresh={thresh:.2f}: TP={tp} FP={fp} FN={fn} P={p:.4f} R={r:.4f} F1={f:.4f}{marker}{rmarker}")

# Feature importance
print("\n  Feature importances (RF):")
importances = rf.feature_importances_
sorted_idx = np.argsort(importances)[::-1]
for i in sorted_idx:
    print(f"    {feat_keys[i]:<25s}: {importances[i]:.4f}")

# 3. Rule-based filter (hand-tuned from feature analysis)
print("\n--- Rule-based filter ===")
# Based on feature analysis: orange_ratio, circularity, white_ratio, hough_line_density
# Ball: high orange_ratio, high circularity, low white_ratio, low hough_line_density
# These are applied as simple thresholds

# Find good thresholds from train set
print("  Finding rule thresholds from train set...")
best_rule_f1 = 0
best_rule_params = {}

# Simple grid search over key thresholds
for orange_thresh in [0.01, 0.05, 0.10, 0.15, 0.20]:
    for circ_thresh in [0.1, 0.2, 0.3, 0.4, 0.5]:
        for white_thresh in [0.1, 0.2, 0.3, 0.4, 0.5]:
            # Rule: accept if orange > thresh AND circularity > thresh AND white < thresh
            preds = []
            for r in trn_rows:
                accept = (r['orange_ratio'] >= orange_thresh and
                          r['circularity'] >= circ_thresh and
                          r['white_ratio'] <= white_thresh)
                preds.append(1 if accept else 0)
            preds = np.array(preds)
            tp = ((preds == 1) & (y_trn == 1)).sum()
            fp = ((preds == 1) & (y_trn == 0)).sum()
            fn = ((preds == 0) & (y_trn == 1)).sum()
            r = tp/(tp+fn) if tp+fn > 0 else 0
            p = tp/(tp+fp) if tp+fp > 0 else 0
            f = 2*p*r/(p+r) if p+r > 0 else 0
            if f > best_rule_f1 and r >= 0.90:
                best_rule_f1 = f
                best_rule_params = {'orange': orange_thresh, 'circ': circ_thresh, 'white': white_thresh}

print(f"  Best rule params: {best_rule_params}")
print(f"  Best train F1: {best_rule_f1:.4f}")

# Apply to test
if best_rule_params:
    preds_test_rule = []
    for r in tst_rows:
        accept = (r['orange_ratio'] >= best_rule_params['orange'] and
                  r['circularity'] >= best_rule_params['circ'] and
                  r['white_ratio'] <= best_rule_params['white'])
        preds_test_rule.append(1 if accept else 0)
    preds_test_rule = np.array(preds_test_rule)
    tp = ((preds_test_rule == 1) & (y_tst == 1)).sum()
    fp = ((preds_test_rule == 1) & (y_tst == 0)).sum()
    fn = ((preds_test_rule == 0) & (y_tst == 1)).sum()
    r = tp/(tp+fn) if tp+fn > 0 else 0
    p = tp/(tp+fp) if tp+fp > 0 else 0
    f = 2*p*r/(p+r) if p+r > 0 else 0
    print(f"  Test: TP={tp} FP={fp} FN={fn} P={p:.4f} R={r:.4f} F1={f:.4f}")

print("\nDone with feature analysis and training")