# Ball Detection Precision Cleanup Report
**Date:** 2026-06-14  
**Branch:** jason-5-may-updates  
**Detector:** models/ball_detector.pt (YOLOv8n, 7-class → class 0 = ball)  
**Benchmark:** 138 frames (108 GT+, 30 GT-)

---

## Executive Summary

The detector is **highly sensitive but imprecise**. At the default conf=0.15, it finds 106/108 balls (98.2% recall) but generates 128 spurious detections (45.3% precision). The dominant failure mode is false positives on court markings (69.5% of all FPs).

**Recommended near-term path:** Apply post-processing (exclude court markings + top-1 per frame) to reach ~80% precision at ~98% recall, while planning detector retraining with improved court-marking negatives.

---

## Proven (evidence from benchmark data)

### Confidence Sweep Results

| Conf | TP | FP | FN | Precision | Recall | F1 |
|------|----|----|----|-----------|--------|-----|
| 0.15 | 106 | 128 | 2 | 0.453 | 0.981 | 0.620 |
| 0.20 | 106 | 97 | 2 | 0.522 | 0.981 | 0.682 |
| **0.25** | **106** | **74** | **2** | **0.589** | **0.981** | **0.736** |
| 0.30 | 86 | 67 | 22 | 0.562 | 0.796 | 0.659 |
| 0.40 | 60 | 46 | 48 | 0.566 | 0.556 | 0.561 |
| 0.50 | 45 | 36 | 63 | 0.556 | 0.417 | 0.476 |

**Best single-threshold F1: conf=0.25 (F1=0.736)**

### FP Classification Breakdown (conf=0.15, 128 total FPs)

| Category | Count | % of FPs | GT=0 | GT=1 |
|----------|-------|----------|------|------|
| court_marking | 89 | 69.5% | 20 | 69 |
| uncertain | 28 | 21.9% | 3 | 25 |
| hoop_rim | 8 | 6.3% | 0 | 8 |
| duplicate_near_ball | 3 | 2.3% | 0 | 3 |

### Post-Processing Impact on FP Count (conf=0.15)

| Variant | FP Removed | FP Remaining | FP Reduction |
|---------|-----------|-------------|--------------|
| baseline | 0 | 128 | — |
| top1_per_frame | 58 | 70 | 45.3% |
| exclude_court_markings | 89 | 39 | 69.5% |
| top1 + exclude_court | 98 | 30 | 76.6% |

### Estimated Metrics with Post-Processing (conf=0.15, TP=106/FN=2 assumed constant)

| Variant | FP | Precision | Recall | F1 |
|---------|-----|-----------|--------|-----|
| baseline | 128 | 0.453 | 0.982 | 0.620 |
| top1_per_frame | 70 | 0.602 | 0.982 | 0.747 |
| exclude_court_markings | 39 | 0.731 | 0.982 | 0.838 |
| **top1 + exclude_court** | **30** | **0.779** | **0.982** | **0.869** |

At conf=0.20 with the same variant: **Precision≈0.803, Recall≈0.982, F1≈0.883**

### Overlay Evidence
Generated images in `benchmark/precision_overlays/`:
- `fp_top01_*.jpg` through `fp_top10_*.jpg` — highest-confidence false positives
- `fn_01_*.jpg`, `fn_02_*.jpg` — the 2 missed balls
- `multi_01_*.jpg` through `multi_05_*.jpg` — frames with multiple spurious detections

Visual inspection confirms: top FPs are court lines/features misclassified as balls, plus ambiguous detections on player bodies and rim areas.

---

## Inferred (logical deduction, not directly measured)

1. **`exclude_court_markings` classification is imperfect.** The classification was done by a heuristic in benchmark_precision.py, not by the detector itself. The 89 "court_marking" FPs likely include some near-ball court markings that could also remove true positive detections. **Actual TP loss from this filter is unmeasured but estimated at 2-5 TPs** (ball near free-throw line, etc.).

2. **The court_marking classifier is a post-hoc spatial/texture heuristic.** It was applied by the analysis script, not the YOLO model. The model itself has no concept of "court marking" — it just outputs class 0 (ball) with high confidence for these features.

3. **Top-1 per frame is safe for shot detection.** Shot detection needs ball presence, not precise location. Taking the highest-confidence detection per frame should retain the TP in most cases, since the actual ball typically gets the highest confidence.

4. **The 2 FN frames are likely edge cases.** The ball is very small, occluded, or in an unusual position.

5. **NMS provides minimal benefit** (126 vs 128 FPs at conf=0.15) because most FPs are in different spatial regions of the frame, not clustered.

6. **The model confuses court features with balls.** Lines, circles, and high-contrast court features (free-throw circles, lane edges) are the primary confusion source. This is a training data gap — the model lacks hard negative examples of court markings.

---

## Unknown (not validated with evidence)

1. **Actual TP reduction from post-processing.** We assumed TP stays constant, but `exclude_court_markings` likely removes 2-5 TPs. Need frame-by-frame TP overlay analysis to verify.

2. **Detector performance on game film vs. benchmark.** The benchmark uses curated frames. Real game film may have different lighting, camera angles, and occlusion patterns.

3. **Temporal consistency.** Frame-by-frame detection without temporal smoothing. The benchmark evaluates single frames; real-world usage might benefit from temporal filtering (e.g., Kalman filter, track-based smoothing).

4. **Model performance by court region.** FPs may cluster in specific court regions. Spatial analysis not yet done.

5. **Impact of input resolution.** The benchmark uses whatever resolution the detector expects (likely 640x640). Higher court-resolution footage might change the FP/FN balance.

6. **Training data composition for court markings.** Unknown how many court-marking negatives were in training. The dominant FP mode suggests insufficient hard negatives.

---

## Recommendation

### Near-term (this sprint): Apply post-processing, hold on rebuild

**Apply `conf=0.25` + `exclude_court_markings_spatial` + `top1_per_frame`:**

```python
# Recommended production config
BALL_DETECTION_CONF = 0.25
BALL_DETECTION_TOP1_PER_FRAME = True
BALL_DETECTION_EXCLUDE_COURT_MASK = True  # ROI mask: exclude far court beyond 3pt line
```

**Expected production metrics (estimated):**
- Precision: ~0.73-0.78 (up from 0.45)
- Recall: ~0.96-0.98 (may drop slightly from 0.98)
- F1: ~0.83-0.86 (up from 0.62)

**Caveats:**
- The court marking exclusion needs a spatial mask (ROI), not the post-hoc classification from the benchmark
- Must verify on the 2 FN frames that the mask doesn't remove those detections
- ~56/108 GT+ frames have spurious extra detections — top-1 cleans these up

### Medium-term (next 2-3 sprints): Retrain with hard negatives

1. Extract high-confidence FP frames from game film (especially court markings)
2. Add as hard negative training examples
3. Consider adding a "not-ball" class or background augmentation
4. Re-run the full benchmark to validate improvement

### Detector rebuild decision: DEFER

**Do not rebuild yet.** The post-processing path gets us to usable precision (~75-80%) for near-term film analysis workflows. Rebuild only if:
- Post-processing drops recall below 95%
- Film analysis workflows require >85% precision (unlikely for near-term)
- Hard negative retraining (cheaper than full rebuild) doesn't achieve >80% precision

---

## Deliverables committed

| File | Description |
|------|-------------|
| `benchmark_precision.py` | Full benchmark + FP classification + confidence sweep + overlay generation |
| `benchmark/precision_analysis.csv` | Per-detection FP classifications (128 rows) |
| `benchmark/confidence_sweep.csv` | 6-threshold metrics |
| `benchmark/postprocess_results.csv` | Post-processing variant comparison |
| `benchmark/precision_overlays/` | 15 overlay images (FP, FN, multi-detection) |
| `docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md` | This document |
