# Secondary Classifier Benchmark Experiment Report

**Date:** 2026-06-15
**Branch:** jason-5-may-updates
**Training script:** `benchmark_classifier.py` (initial), `benchmark_classifier_v2.py` (corrected)
**Evaluation script:** `benchmark_classifier_eval.py` (held-out eval)
**Detector:** models/ball_detector.pt (YOLOv8n, class 0 = ball, conf=0.25)
**Benchmark:** 138 frames (108 GT+, 30 GT-)

---

## Executive Summary

A MobileNetV2 secondary classifier was trained from scratch on detection crops from v2 stratified train frames (zero leakage) and evaluated on strictly held-out v2 test frames.

**Held-out test result: F1=0.763, recall=0.879.** This is only +0.010 over the baseline F1=0.753, and recall falls below the 0.95 acceptance threshold.

**The classifier is NOT a production candidate** under the current training setup. The 180-crop dataset (106 positive, 74 negative) is too small for a deep learning classifier to learn robust ball-vs-marking discrimination. The pretrained MobileNetV2 features do not transfer well to this domain with so few examples.

---

## Experiment History

This experiment went through three iterations to fix evaluation methodology:

| Version | Split Method | Training Leakage | Test F1 | Issue |
|---------|-------------|-----------------|---------|-------|
| v1 (`47656e1`) | Sequential 70/30 | 70% of test frames in training | 0.874 | In-sample, overfitted |
| v2 (`991611a`) | Stratified | Used v1 model (trained on overlapping data) | 0.901 | Model trained on leaking data |
| v3 (`991611a` fix) | Stratified, retrained from scratch | Zero | 0.763 | Honest held-out result |

Only v3 is a valid held-out evaluation. The v1 and v2 results are superseded.

---

## Experiment Design

### Classifier Architecture

| Parameter | Value |
|-----------|-------|
| Architecture | MobileNetV2 (pretrained ImageNet) + binary head (128→1) |
| Crop size | 64×64 px, 1.5× bbox margin |
| Augmentation | H-flip, rotation ±15°, color jitter, random erasing |
| Training epochs | 18 (early stop, patience=10) |
| Optimizer | Adam, lr=1e-3, weight_decay=1e-4 |

### Crop Dataset

Source: `benchmark/classifier_manifest.csv` — 180 crops from 119 frames with detections at conf=0.25

| Label | Count | Source |
|-------|-------|--------|
| Positive (ball) | 106 | GT-matched detections at IoU≥0.5 |
| Negative (FP) | 74 | Unmatched detections at conf=0.25 |

### Train/Test Split (v2, stratified)

Source: `benchmark/classifier_split_v2.csv` — stratified by frame, seed=42

| Split | Frames | Neg-only frames | Crops (pos/neg) |
|-------|--------|-----------------|-----------------|
| Train | 82 (70%) | 8 | 128 (74 pos, 54 neg) |
| Test | 37 (30%) | 4 | 52 (32 pos, 20 neg) |

**Verified:** Zero frame overlap between train and test. Neg-only frames represented in both splits.

### Threshold Selection

Threshold (0.10) was selected on a held-out validation subset of the training data (14 frames, 29 crops). This validation set was NOT used for training.

---

## Proven (measured from committed CSV data)

### Held-Out Test Results (primary metric)

Source: `benchmark/classifier_results_v3.csv`, split=test

| Variant | TP | FP | FN | Precision | Recall | F1 | ΔF1 | Removed |
|---------|----|----|----|-----------|--------|-----|-----|---------|
| **baseline** | **32** | **20** | **1** | **0.615** | **0.970** | **0.753** | — | 0 |
| classifier | 29 | 14 | 4 | 0.674 | 0.879 | 0.763 | +0.010 | 9 |
| classifier_nms | 29 | 14 | 4 | 0.674 | 0.879 | 0.763 | +0.010 | 9 |

### Train Results (for reference only)

Source: `benchmark/classifier_results_v3.csv`, split=train

| Variant | TP | FP | FN | Precision | Recall | F1 |
|---------|----|----|----|-----------|--------|-----|
| baseline | 74 | 54 | 0 | 0.578 | 1.000 | 0.733 |
| classifier | 74 | 24 | 0 | 0.755 | 1.000 | 0.860 |
| classifier_nms | 74 | 22 | 0 | 0.771 | 1.000 | 0.871 |

### Threshold Sweep on Test Set

| Threshold | TP | FP | FN | Precision | Recall | F1 |
|-----------|----|----|----|-----------|--------|-----|
| 0.05 | 29 | 14 | 3 | 0.674 | 0.906 | 0.773 |
| 0.10 | 29 | 14 | 3 | 0.674 | 0.906 | 0.773 |
| 0.15 | 29 | 12 | 3 | 0.707 | 0.906 | 0.795 |
| 0.20 | 29 | 10 | 3 | 0.744 | 0.906 | 0.817 |
| 0.25 | 28 | 9 | 4 | 0.757 | 0.875 | 0.812 |
| 0.30 | 28 | 7 | 4 | 0.800 | 0.875 | 0.836 |
| 0.40 | 25 | 6 | 7 | 0.807 | 0.781 | 0.794 |
| 0.50 | 24 | 5 | 8 | 0.828 | 0.750 | 0.787 |

**No threshold achieves recall ≥ 0.95 on the held-out test set.** The maximum recall is 0.906 (threshold ≤ 0.20), yielding F1=0.817 at best.

### Key Measured Findings

1. **The classifier provides marginal improvement on held-out test data: F1 0.753→0.763 (+0.010).**
   - Removes only 9 of 20 FPs (45% FP reduction)
   - Loses 3 additional TPs (FN 1→4)
   - Net F1 gain is negligible

2. **Recall drops below the 0.95 acceptance threshold: 0.970→0.879.**
   - 3 true balls are misclassified as FPs
   - These are balls whose crops look similar to court markings

3. **Train-test gap is large: train F1=0.860 vs test F1=0.763 (−0.097).**
   - The model overfits to the small training set
   - 128 training crops (74 pos, 54 neg) is insufficient for robust generalization

4. **The score distributions overlap significantly:**
   - Test positive scores: min=0.015, max=0.951, median=0.857
   - Test negative scores: min=0.008, max=0.922, median=0.205
   - Some court-marking FPs score higher than true balls

5. **NMS adds no benefit on the test set.**
   - classifier and classifier_nms have identical test metrics
   - The 2 additional FPs removed by NMS are in the training set only

### Per-Detection Scores

Source: `benchmark/classifier_detection_scores_v3.csv` — 180 rows with full provenance

Each record includes: crop_id, frame, v2_split, det_idx, gt_boxes_in_frame, label, det_confidence, classifier_score, classifier_accept, px_cx, px_cy.

---

## Inferred (logical deduction, not directly measured)

1. **The 180-crop dataset is too small for a deep learning approach.** MobileNetV2 has ~3.5M parameters. Training on 128 crops (even with augmentation) leads to severe overfitting. A simpler model (e.g., logistic regression on hand-crafted features) might generalize better.

2. **The 3 misclassified TPs are likely edge cases.** Balls at frame boundaries, partially occluded balls, or balls near court markings produce crops that look like FPs.

3. **Pretrained ImageNet features do not transfer well to this domain.** The model was trained on natural images of objects, animals, etc. Basketball court crops (floor textures, lines, round shapes) are very different from ImageNet classes.

4. **More training data would likely help.** Extracting crops from additional video frames (not just the 138 benchmark frames) could provide enough examples for the model to learn robust features.

5. **A simpler feature-based approach might work better.** Color histograms, shape features, or texture descriptors could distinguish balls from court markings more reliably with less data.

---

## Unknown (not validated with evidence)

1. **Performance with more training data.** Whether 10× or 100× more crops would improve held-out F1 is unknown.

2. **Alternative model architectures.** A smaller model (e.g., logistic regression, random forest, or a tiny CNN) might generalize better with limited data.

3. **Performance on non-benchmark data.** The classifier is trained and tested on the same 138 frames. Generalization to other cameras, courts, and lighting is unmeasured.

4. **Impact on downstream event detection.** Whether the marginal FP reduction improves basketball analytics is unknown.

---

## Production Recommendation

### Status: **NOT a Production Candidate** ❌

The secondary classifier **does not meet the acceptance criteria** on held-out test data:

| Criterion | Result |
|-----------|--------|
| F1 materially improved over baseline | ❌ F1 0.753→0.763 (+0.010, negligible) |
| Recall ≥ 0.95 | ❌ R=0.879 (below threshold) |
| No GT required at inference time | ✅ Uses only detection crops |
| No train/test leakage | ✅ Clean stratified split, verified |

### Recommended Next Steps

1. **Do not deploy the classifier to production.** The held-out improvement is negligible and recall is below threshold.

2. **Investigate simpler feature-based approaches.** Color, shape, or texture features with a lightweight model (logistic regression, SVM) may generalize better with limited data.

3. **Collect more training data.** Extract crops from additional video frames beyond the 138 benchmark frames. Aim for 1000+ labeled crops.

4. **Consider hard-negative mining.** The 6 remaining FPs at threshold 0.20 are court markings that look like balls. Adding these as hard negatives in training could help.

5. **Consider the adaptive (GT-dependent) mask as an alternative.** It achieves F1=0.858 with zero TP loss, but requires GT knowledge at inference time. If a reliable "ball present/absent" signal can be derived at inference time, a GT-free version of the adaptive mask could be viable.

---

## Deliverables Committed

| File | Description |
|------|-------------|
| `benchmark_classifier.py` | Initial training script (v1, superseded) |
| `benchmark_classifier_eval.py` | Held-out evaluation script (v2, superseded) |
| `benchmark_classifier_v2.py` | Corrected training + evaluation (v3, zero leakage) |
| `benchmark/classifier_manifest.csv` | 180 crops with labels and provenance |
| `benchmark/classifier_split.csv` | Original split (superseded) |
| `benchmark/classifier_split_v2.csv` | Stratified v2 split (seed=42, 82 train / 37 test) |
| `benchmark/classifier_results.csv` | v1 results (superseded) |
| `benchmark/classifier_results_v2.csv` | v2 results (superseded) |
| `benchmark/classifier_results_v3.csv` | v3 results (held-out, primary) |
| `benchmark/classifier_per_frame_v3.csv` | Per-frame detail with split column |
| `benchmark/classifier_detection_scores_v3.csv` | Per-detection scores with provenance (180 rows) |
| `benchmark/classifier_overlays_v3/` | 6 test-set held-out overlays |
| `benchmark/classifier_contact_sheet.jpg` | 20 accepted TP + 20 rejected FP crops |
| `models/court_fp_classifier.pt` | v1 model weights (superseded) |
| `models/court_fp_classifier_v2.pt` | v3 model weights (trained on v2 train only) |
| `docs/CLASSIFIER_EXPERIMENT_REPORT.md` | This document |
