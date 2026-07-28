# Feature-Based False-Positive Filter Benchmark Report

**Date:** 2026-06-16
**Branch:** jason-5-may-updates
**Scripts:** `benchmark_feature_filters.py` (feature extraction + training), `benchmark_feature_eval.py` (evaluation)
**Detector:** models/ball_detector.pt (YOLOv8n, class 0 = ball, conf=0.25)
**Benchmark:** 138 frames (108 GT+, 30 GT-)
**Split:** v2 stratified (82 train frames / 37 test frames, 0 overlap, seed=42)

---

## Executive Summary

Simple, auditable features (geometry, location, color, shape/texture) were extracted from 180 detection crops and used to train Logistic Regression and Random Forest filters. **No feature-based filter materially improves held-out test F1 while maintaining recall >= 0.95.**

**No TRAIN-SELECTED feature-filter configuration meets the recall >= 0.95 threshold on held-out test data.** The best held-out test recall is 0.906 (LR), well below the 0.95 requirement.

**No feature-based filter is a production candidate.** The feature distributions for balls and court-marking FPs overlap too much for simple classifiers to separate them reliably.

---

## Feature Set

17 features extracted per detection crop:

| Family | Features |
|--------|----------|
| Geometry | bbox_area, aspect_ratio |
| Location | norm_cx, norm_cy (normalized 0-1) |
| Color (HSV) | h_mean, h_std, s_mean, s_std, v_mean, v_std |
| Color (semantic) | orange_ratio (H 5-25), white_ratio (V>200,S<50), dark_ratio (V<80) |
| Shape/Texture | edge_density (Canny), circularity (contour), hough_line_density |
| Detector | det_confidence |

---

## Feature Analysis (Train Set)

Key discriminating features (train set, 74 pos / 54 neg):

| Feature | POS mean | NEG mean | Diff |
|---------|----------|----------|------|
| h_mean | 65.6 | 57.1 | +8.5 |
| s_mean | 60.7 | 51.1 | +9.6 |
| orange_ratio | 0.472 | 0.478 | -0.006 |
| edge_density | 0.028 | 0.036 | -0.008 |
| hough_line_density | 0.478 | 0.547 | -0.069 |
| circularity | 0.332 | 0.347 | -0.015 |

**Key observation:** The feature distributions overlap heavily. Orange ratio (the most intuitive "ball color" feature) is nearly identical between balls and FPs (0.472 vs 0.478). Hue and saturation show some separation but with substantial overlap. No single feature cleanly separates the classes.

---

## Results (measured from committed CSV data)

All 180 detections (train + test) were scored by both classifiers. Train/test/all metrics below are computed from real model outputs — no default probability placeholders were used.

### Held-Out Test Results (primary metric)

Source: `benchmark/feature_filter_results.csv`, split=test

| Variant | TP | FP | FN | Precision | Recall | F1 | DeltaF1 | Removed |
|---------|----|----|----|-----------|--------|-----|---------|---------|
| **baseline** | **32** | **20** | **1** | **0.615** | **0.970** | **0.753** | — | 0 |
| lr_best(0.30) | 29 | 16 | 4 | 0.644 | 0.879 | 0.744 | −0.009 | 7 |
| lr_r95(0.27) | 29 | 16 | 4 | 0.644 | 0.879 | 0.744 | −0.009 | 7 |
| rf_best(0.50) | 25 | 11 | 8 | 0.694 | 0.758 | 0.725 | −0.028 | 16 |
| rf_r95(0.47) | 28 | 13 | 5 | 0.683 | 0.849 | 0.757 | +0.004 | 11 |

**No configuration achieves recall >= 0.95 on held-out test data.** The best recall is 0.879 (LR).

### Train Results (reference only — classifiers trained on this data)

Source: `benchmark/feature_filter_results.csv`, split=train

| Variant | TP | FP | FN | Precision | Recall | F1 | Removed |
|---------|----|----|-----------|--------|-----|---------|
| baseline | 74 | 54 | 0 | 0.578 | 1.000 | 0.733 | 0 |
| lr_best(0.30) | 70 | 40 | 4 | 0.636 | 0.946 | 0.761 | 18 |
| lr_r95(0.27) | 71 | 43 | 3 | 0.623 | 0.960 | 0.755 | 14 |
| rf_best(0.50) | 74 | 0 | 0 | 1.000 | 1.000 | 1.000 | 54 |
| rf_r95(0.47) | 74 | 0 | 0 | 1.000 | 1.000 | 1.000 | 54 |

**Note:** RF achieves perfect train recall and precision because it overfits the small training set (128 crops). This does not generalize to held-out test data.

### All Results (train + test combined)

Source: `benchmark/feature_filter_results.csv`, split=all

| Variant | TP | FP | FN | Precision | Recall | F1 | Removed |
|---------|----|----|----|-----------|--------|-----|---------|
| baseline | 106 | 74 | 1 | 0.589 | 0.991 | 0.739 | 0 |
| lr_best | 99 | 56 | 8 | 0.639 | 0.925 | 0.756 | 25 |
| lr_r95 | 100 | 59 | 7 | 0.629 | 0.935 | 0.752 | 21 |
| rf_best | 99 | 11 | 8 | 0.900 | 0.925 | 0.912 | 70 |
| rf_r95 | 102 | 13 | 5 | 0.887 | 0.953 | 0.919 | 65 |

### Key Measured Findings

1. **No TRAIN-SELECTED feature-filter configuration achieves recall >= 0.95 on held-out test data.** The best recall is 0.879 (LR_r95), well below the 0.95 threshold.

2. **The best held-out F1 improvement is +0.004 (rf_r95), which is negligible.** All other configurations perform worse than baseline.

3. **Feature distributions overlap too much.** The most intuitive discriminating feature (orange_ratio) is nearly identical between balls and FPs. Hue shows some separation but with substantial overlap.

4. **The RF train-test gap is extreme: train F1=1.000 vs test F1=0.725-0.757.** This confirms severe overfitting to the small training set (128 crops).

5. **LR is more stable but weaker.** Train F1=0.761 vs test F1=0.744 — smaller gap but lower absolute performance, and still below the recall threshold.

6. **The features that matter most differ between LR and RF:**
   - LR: edge_density (negative), hough_line_density (positive), h_mean (positive)
   - RF: edge_density, s_mean, s_std, h_mean (all similar importance)

7. **Orange ratio is not discriminative.** Despite balls being orange-brown, the orange pixel ratio is nearly identical between balls (0.472) and court-marking FPs (0.478). This is likely because court floor pixels also fall in the orange-brown HSV range.

### Per-Detection Scores

Source: `benchmark/feature_filter_scores.csv` — 180 detections (128 train + 52 test) with lr_prob, rf_prob, and accept/reject decisions. All scores are real model outputs, not placeholders.

---

## Exploratory Observation (NOT a production recommendation)

A post-hoc threshold sweep on the **test set** (not used for training) shows that RF threshold 0.35 achieves R=1.000 and F1=0.831 on test. However, this threshold was selected by looking at test data — it is exploratory and overfit. It cannot be selected in production without access to ground truth labels. The train-optimized thresholds (selected without looking at test data) fail to meet recall >= 0.95, which is the primary conclusion.

---

## Inferred (logical deduction, not directly measured)

1. **The 180-crop dataset is too small and not discriminative enough for any classifier.** The feature distributions overlap fundamentally — balls and court markings share similar colors, shapes, and textures in 64x64 crops.

2. **Larger crops or full-frame context might help.** The 64x64 crop may not capture enough context to distinguish a ball on a court from a court marking. A larger crop showing the surrounding floor pattern could be more informative.

3. **Temporal features could be more discriminative.** The ball moves between frames while court markings are static. A multi-frame consistency check could separate them more reliably than single-frame features.

4. **The detector itself may be the limiting factor.** If the YOLO detector confuses court markings with balls at the feature level, a post-processing filter using similar features (color, shape, texture) is unlikely to do better.

5. **A fundamentally different approach may be needed.** Options include: (a) retrain the detector with hard-negative court-marking examples, (b) use temporal consistency across frames, (c) use a court-region mask calibrated per-camera.

---

## Unknown (not validated with evidence)

1. **Whether larger crops would improve discrimination.** 128x128 or full-frame context might capture more informative features.

2. **Whether temporal filtering would help.** Ball motion vs static court markings could be a strong signal.

3. **Whether more training data would help.** The 180-crop dataset may be fundamentally insufficient, or 1000+ crops might enable better separation.

4. **Performance on non-benchmark data.** The feature distributions may differ for other cameras, courts, and lighting conditions.

5. **Whether a per-camera court mask could work.** A fixed ROI per camera might exclude court-marking FPs more reliably than learned features.

---

## Production Recommendation

### Status: **NOT a Production Candidate** ❌

No TRAIN-SELECTED feature-based filter meets the acceptance criteria on held-out test data:

| Criterion | Best Result | Status |
|-----------|-------------|--------|
| F1 materially improved over 0.753 | +0.004 (rf_r95) | ❌ Negligible |
| Recall >= 0.95 (train-selected threshold) | 0.879 (LR) | ❌ Below threshold |
| No GT at inference | ✅ | ✅ |
| No train/test leakage | ✅ | ✅ |
| Auditable | ✅ Simple features | ✅ |

### Comparison to Other Methods

| Method | Test F1 | Test R | DeltaF1 | GT-free? | Production? |
|--------|---------|--------|---------|----------|-------------|
| baseline (conf=0.25) | 0.753 | 0.970 | — | Yes | Current |
| NMS alone | 0.741 | 0.982 | +0.005 | Yes | Marginal |
| MobileNet classifier v3 | 0.763 | 0.879 | +0.010 | Yes | No |
| **RF feature filter** | **0.757** | **0.849** | **+0.004** | **Yes** | **No** |
| LR feature filter | 0.744 | 0.879 | −0.009 | Yes | No |
| adaptive mask (GT-dep) | 0.858 | 0.982 | +0.122 | No | Requires GT |

### Recommended Next Steps

1. **Do not deploy any feature-based filter to production.** The held-out improvement is negligible and recall is below threshold.

2. **Investigate temporal consistency filtering.** The ball moves between frames while court markings are static. This could be a much stronger signal than single-frame features.

3. **Consider per-camera court masks.** A fixed ROI per camera, calibrated once, could exclude far-court FPs without learned features.

4. **Consider detector retraining with hard negatives.** Adding court-marking examples as negative training data could reduce FPs at the source.

---

## Deliverables Committed

| File | Description |
|------|-------------|
| `benchmark_feature_filters.py` | Feature extraction + classifier training |
| `benchmark_feature_eval.py` | Held-out evaluation script |
| `benchmark/feature_manifest.csv` | 180 crops x 17 features |
| `benchmark/feature_filter_results.csv` | Per-variant metrics by split (train/test/all) |
| `benchmark/feature_filter_per_frame.csv` | Per-frame detail |
| `benchmark/feature_filter_scores.csv` | Per-detection scores (180 detections, all scored) |
| `benchmark/feature_filter_overlays/` | Test-set overlays per variant |
| `docs/FEATURE_FILTER_EXPERIMENT_REPORT.md` | This document |
