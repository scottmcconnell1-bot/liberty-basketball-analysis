# Ball Detection Precision Cleanup Report
**Date:** 2026-06-14
**Branch:** jason-5-may-updates
**Detector:** models/ball_detector.pt (YOLOv8n, 7-class → class 0 = ball)
**Benchmark:** 138 frames (108 GT+, 30 GT-)

---

## Executive Summary

The detector is **highly sensitive but imprecise**. At conf=0.15, it finds 106/108 balls (98.2% recall) but generates 128 spurious detections (45.3% precision). The dominant failure mode is false positives on court markings (69.5% of all FPs).

**Measured best F1: 0.741** at conf=0.25 with NMS (50px). This is only +0.005 over threshold-only (F1=0.736). Post-processing variants measured so far provide minimal improvement.

**Near-term recommendation:** Raise threshold to conf=0.25 for F1=0.736. Court-marking exclusion is a promising but **unmeasured** hypothesis — needs implementation and benchmark before claiming benefit.

---

## Proven (measured from committed CSV data)

### Confidence Sweep Results
Source: `benchmark/confidence_sweep.csv`

| Conf | TP | FP | FN | Precision | Recall | F1 |
|------|----|----|----|-----------|--------|-----|
| 0.15 | 106 | 128 | 2 | 0.453 | 0.981 | 0.620 |
| 0.20 | 106 | 97 | 2 | 0.522 | 0.981 | 0.682 |
| **0.25** | **106** | **74** | **2** | **0.589** | **0.981** | **0.736** |
| 0.30 | 86 | 67 | 22 | 0.562 | 0.796 | 0.659 |
| 0.40 | 60 | 46 | 48 | 0.566 | 0.556 | 0.561 |
| 0.50 | 45 | 36 | 63 | 0.556 | 0.417 | 0.476 |

**Best single-threshold F1: conf=0.25 (F1=0.736)**

### Post-Processing Variants at conf=0.25
Source: `benchmark/postprocess_results.csv` (all values measured, not estimated)

| Variant | TP | FP | FN | Precision | Recall | F1 |
|---------|----|----|----|-----------|--------|-----|
| threshold_only (baseline) | 106 | 74 | 2 | 0.589 | 0.981 | 0.736 |
| threshold_nms | 106 | 72 | 2 | 0.596 | 0.981 | 0.741 |
| threshold_mask | 106 | 74 | 2 | 0.589 | 0.981 | 0.736 |
| threshold_nms_mask | 106 | 72 | 2 | 0.596 | 0.981 | 0.741 |
| threshold_top1 | 67 | 52 | 41 | 0.563 | 0.620 | 0.590 |
| threshold_nms_mask_top1 | 67 | 52 | 41 | 0.563 | 0.620 | 0.590 |

**Key measured findings:**
- **NMS (50px) gives minor gain:** F1 0.736 → 0.741 (+0.005). Only 2 FP removed.
- **Scoreboard mask does nothing:** F1 identical to baseline (0.736). Zero FPs in scoreboard region.
- **Top-1 per frame hurts significantly:** F1 drops to 0.590. Top-1 removes 39 TP detections in frames where the ball is detected multiple times (41 FN vs 2 FN baseline). This is because many GT+ frames have multiple valid ball detections, and top-1 arbitrarily keeps only one.
- **NMS + mask = NMS alone:** No additional benefit from combining mask with NMS.

### FP Classification Breakdown (conf=0.15)
Source: `benchmark/precision_analysis.csv` (128 FP detections classified by heuristic)

| Category | Count | % of FPs | In GT=0 frames | In GT=1 frames |
|----------|-------|----------|----------------|----------------|
| court_marking | 89 | 69.5% | 20 | 69 |
| uncertain | 28 | 21.9% | 3 | 25 |
| hoop_rim | 8 | 6.3% | 0 | 8 |
| duplicate_near_ball | 3 | 2.3% | 0 | 3 |

### Overlay Evidence
Generated images in `benchmark/precision_overlays/`:
- `fp_top01_*.jpg` through `fp_top10_*.jpg` — highest-confidence false positives
- `fn_01_*.jpg`, `fn_02_*.jpg` — the 2 missed balls
- `multi_01_*.jpg` through `multi_05_*.jpg` — frames with multiple spurious detections

---

## Inferred (logical deduction, not directly measured)

1. **Court-marking exclusion is promising but unmeasured.** 69.5% of FPs are heuristically classified as court markings. A spatial ROI mask excluding court regions (e.g., beyond the 3-point line) could substantially reduce FPs. However, this has NOT been implemented or measured. The benchmark's `threshold_mask` variant tested a scoreboard mask (top-right corner), not a court-marking mask — and it found zero FPs in that region.

2. **Top-1 per frame is harmful for this detector.** The measured data contradicts the assumption that top-1 is safe. 56/108 GT+ frames have multiple detections, and top-1 removes 39 true positives. The detector produces multiple overlapping detections of the same ball, and top-1's arbitrary selection (highest conf) doesn't always pick the correct one.

3. **NMS provides minimal benefit** because FPs are spatially distributed across the frame, not clustered. Only 2 FPs are within 50px of another detection.

4. **The model confuses court features with balls.** Lines, circles, and high-contrast court features are the primary confusion source. This is a training data gap — the model likely lacks hard negative examples of court markings.

5. **The 2 FN frames are edge cases.** The ball is very small, occluded, or in an unusual position.

---

## Unknown (not validated with evidence)

1. **Impact of a true court-marking ROI mask.** The scoreboard mask was tested and found nothing. A mask excluding court regions (where 69.5% of FPs occur) has not been implemented or measured.

2. **Actual TP loss from court-marking exclusion.** Any spatial mask that excludes court regions will also exclude balls near those regions (free-throw line, paint area). Unmeasured.

3. **Detector performance on game film vs. benchmark.** The benchmark uses curated frames. Real game film may have different lighting, camera angles, and occlusion patterns.

4. **Temporal consistency.** Frame-by-frame detection without temporal smoothing. The benchmark evaluates single frames; real-world usage might benefit from temporal filtering.

5. **Model performance by court region.** Spatial FP distribution analysis not yet done.

6. **Training data composition for court markings.** Unknown how many court-marking negatives were in training.

---

## Recommendation

### Near-term (this sprint): Raise threshold, hold on post-processing

**Apply conf=0.25 as the production default.**

```python
# Recommended production config (proven)
BALL_DETECTION_CONF = 0.25
```

**Measured result:** F1=0.736 (P=0.589, R=0.981). This is the best measured configuration.

**Do NOT apply top-1 or NMS yet:**
- Top-1 drops F1 to 0.590 (measured)
- NMS gains only +0.005 F1 (measured) — not worth the complexity

### Medium-term: Implement and measure court-marking exclusion

1. Design a spatial ROI mask that excludes far-court regions (beyond 3-point line)
2. Add it as a variant in `benchmark_precision.py`
3. Run the full 138-frame benchmark to measure actual FP reduction and TP loss
4. Only deploy if measured F1 improves meaningfully (>0.80) with recall staying above 95%

### Detector rebuild decision: DEFER

**Do not rebuild yet.** The measured post-processing gains are minimal. The promising path is court-marking exclusion, which is a targeted intervention, not a full rebuild. Rebuild only if:
- Court-marking ROI mask doesn't achieve F1 > 0.80
- Hard negative retraining (cheaper than full rebuild) doesn't achieve F1 > 0.80

---

## Deliverables committed

| File | Description |
|------|-------------|
| `benchmark_precision.py` | Full benchmark + FP classification + confidence sweep + overlay generation |
| `benchmark/precision_analysis.csv` | Per-detection FP classifications (128 rows) |
| `benchmark/confidence_sweep.csv` | 6-threshold metrics |
| `benchmark/postprocess_results.csv` | 6 post-processing variants at conf=0.25 (all measured) |
| `benchmark/precision_overlays/` | 15 overlay images (FP, FN, multi-detection) |
| `docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md` | This document |
| `docs/BALL_DETECTION_PRECISION_CLEANUP_PLAN.md` | Original plan doc |
