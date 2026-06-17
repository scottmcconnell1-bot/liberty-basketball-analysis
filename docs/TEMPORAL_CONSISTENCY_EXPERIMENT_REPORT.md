# Temporal Consistency Filter Benchmark Report

**Date:** 2026-06-16
**Branch:** jason-5-may-updates
**Commit:** benchmark_temporal.py + artifacts (see Deliverables)
**Detector:** models/ball_detector.pt (YOLOv8n, class 0 = ball, conf=0.25)
**Benchmark corpus:** 138 frames (108 GT+, 30 GT-)
**Metric rows:** 120 evaluated frames for the `all` split because `benchmark_temporal.py` skips frames with neither ground truth nor detector output.
**Split:** v2 stratified labels (82 train frames / 37 test frames, 0 frame overlap, seed=42)
**Temporal context caveat:** Tracks are built across full video sequences before split-level scoring. Codex verified 17 tracks span train/test frame labels. No supervised model is trained, but held-out metrics use cross-split temporal context and should not be described as a leakage-free trained-model evaluation.

---

## Executive Summary

Temporal consistency filtering was tested as a court-marking FP rejection strategy. Detections were linked across consecutive frames into tracks using greedy nearest-neighbor matching (max normalized centroid distance = 0.05). Tracks were then filtered by lifespan and motion.

**Result: No temporal consistency filter configuration achieves recall >= 0.95 on held-out test data.** The best recall is 0.545 (temporal_len2), far below threshold.

**Root cause:** The ball detector fires inconsistently — 70% of pos frames have only 1 detection, and 39% of those single-detection frames have their detection in a track of length 1 (no temporal neighbor). Temporal filtering disproportionately removes true positives because the detector itself doesn't provide consistent temporal coverage.

**Temporal consistency is NOT a production candidate with the current detector.**

---

## Method

1. **Detector run**: ball_detector.pt at conf=0.25 on all 138 benchmark frames → 180 detections (165 on pos frames, 15 on neg frames).
2. **Track building**: Greedy nearest-neighbor matching within video sequences, max centroid distance 0.05 (normalized). 133 tracks built.
3. **Filter variants**:
   - `baseline`: no temporal filtering (all conf>=0.25 detections kept)
   - `temporal_len2`: keep only detections in tracks of length >= 2
   - `temporal_len3`: keep only detections in tracks of length >= 3
   - `temporal_mov2`: keep only detections in tracks with >= 2 frames AND non-zero total motion
4. **Primary metric**: v2 test recall (must be >= 0.95), F1. Test rows should be read with the temporal-context caveat above.

---

## Proven (measured from committed CSV data)

### Detections and Tracks

Source: `benchmark/temporal_detection_scores.csv` (180 detections), `benchmark/temporal_tracks.csv` (133 tracks)

| Metric | Value |
|--------|-------|
| Total detections (conf>=0.25) | 180 |
| Detections on pos frames | 165 |
| Detections on neg frames | 15 |
| Total tracks | 133 |
| Tracks of length 1 | 99 (74%) |
| Tracks of length 2 | 27 (20%) |
| Tracks of length >= 3 | 7 (5%) |
| Max track length | 6 |

### Evaluation Frame Accounting

Source: Codex verification of `benchmark/frames`, `benchmark/labels`, `benchmark/temporal_detection_scores.csv`, and `benchmark_temporal.py`

| Metric | Value |
|--------|-------|
| Benchmark image files | 138 |
| GT-positive frames | 108 |
| Frames with detector output | 119 |
| Frames with GT or detector output | 120 |
| Frames skipped from metric aggregation because they have neither GT nor detections | 18 |
| Tracks spanning both train and test frame labels | 17 |

The `temporal_results.csv` `all` rows therefore cover 120 evaluated frames, not all 138 benchmark image files.

### Track Length by Detection Source

| Track Length | Total Dets | Pos Dets | Neg Dets |
|-------------|-----------|----------|----------|
| >= 1 (all) | 180 | 165 | 15 |
| >= 2 | 81 | 79 | 2 |
| >= 3 | 27 | 27 | **0** |
| >= 4 | 12 | 12 | 0 |
| >= 5 | 12 | 12 | 0 |
| >= 6 | 12 | 12 | 0 |

**Key observation:** Neg detections (court-marking FPs) almost never persist across frames. Only 2 of 15 neg detections appear in tracks of length >= 2, and zero appear in tracks of length >= 3. This confirms the hypothesis that temporal continuity distinguishes balls from static FPs.

### Held-Out Test Results (primary metric)

Source: `benchmark/temporal_results.csv`, split=test

| Variant | TP | FP | FN | Precision | Recall | F1 | DeltaF1 | Removed |
|---------|----|----|----|-----------|--------|-----|---------|---------|
| **baseline** | **32** | **20** | **1** | **0.615** | **0.970** | **0.753** | — | 0 |
| temporal_len2 | 18 | 6 | 15 | 0.750 | 0.545 | 0.632 | −0.121 | 28 |
| temporal_len3 | 8 | 2 | 25 | 0.800 | 0.242 | 0.372 | −0.381 | 42 |
| temporal_mov2 | 9 | 3 | 24 | 0.750 | 0.273 | 0.400 | −0.353 | 40 |

### Train Results (reference only)

| Variant | TP | FP | FN | Precision | Recall | F1 | Removed |
|---------|----|----|----|-----------|--------|-----|---------|
| baseline | 74 | 54 | 0 | 0.578 | 1.000 | 0.733 | 0 |
| temporal_len2 | 37 | 20 | 37 | 0.649 | 0.500 | 0.565 | 71 |
| temporal_len3 | 13 | 4 | 61 | 0.765 | 0.176 | 0.286 | 111 |
| temporal_mov2 | 20 | 7 | 54 | 0.741 | 0.270 | 0.396 | 101 |

### Per-Frame Analysis (Test Set)

| Metric | Value |
|--------|-------|
| Pos test frames with detections | 33 |
| Pos frames with 1 detection (baseline) | 23 (70%) |
| Pos frames with 2+ detections (baseline) | 10 (30%) |
| Single-det pos frames losing only det to len2 | 9/23 (39%) |
| Neg frames with detections removed by len2 | 4/15 |

---

## Inferred (reasonable conclusions from evidence)

1. **The detector's per-frame inconsistency is the primary blocker.** 70% of pos frames have exactly 1 detection. When that single detection has no temporal neighbor (track length 1), temporal_len2 filtering removes it regardless of confidence. This is a detector limitation, not a filtering limitation.

2. **Temporal consistency works directionally correctly.** Neg detections rarely persist (only 2 of 15 in tracks >= 2 frames), while pos detections often do (79 of 165). The signal exists but is too sparse with this detector to achieve high recall.

3. **A more consistent detector could make temporal filtering viable.** If the detector fired on the ball in >= 2 consecutive frames for most GT balls, temporal_len2 could potentially reject most FPs while preserving recall. The max track length of 6 suggests some sequences have consistent detection.

4. **Track length threshold is a precision-recall knob.** len2 gives R=0.545 (precision=0.75), len3 gives R=0.242 (precision=0.80). Even at len3 where all neg detections are eliminated, the recall cost is catastrophic.

5. **Motion filtering (mov2) underperforms length filtering.** The ball is often nearly static between consecutive frames (especially when far from camera), so requiring non-zero motion adds noise without meaningfully improving FP rejection.

6. **The benchmark frame sampling exacerbates the problem.** Frames are sampled at 200-frame intervals (neg_NNN_fYYYYY), meaning consecutive benchmark frames are 200 frames apart in the original video. Detections at these intervals won't spatially overlap enough to form temporal tracks.

---

## Unknown (not yet validated)

1. **Would temporal filtering work with denser frame sampling?** The current benchmark samples frames ~200 apart in the source video. With consecutive or near-consecutive frames, tracks would likely be longer and recall loss smaller.

2. **Would a lower confidence threshold help?** Running at conf=0.15 instead of 0.25 would produce more detections per frame, potentially creating longer tracks. The tradeoff is more FPs entering the system.

3. **Would a better tracker help?** Greedy nearest-neighbor with a fixed distance threshold is simple. A Kalman filter or Hungarian algorithm approach might build longer, more accurate tracks.

4. **Would temporal filtering work on the pos track sequence?** The pos frames (train 003-096, val 097-108) are sequential and show max track length of 6. If the detector were more consistent on these, temporal filtering might preserve more recall.

5. **What recall could be achieved on denser sampling?** Unknown — would require running the detector on consecutive video frames rather than the benchmark's sampled frames.

---

## Production Recommendation

### Status: **NOT a Production Candidate** ❌

No temporal consistency filter meets the acceptance criteria:

| Criterion | Best Result | Status |
|-----------|-------------|--------|
| F1 materially improved over 0.753 | −0.009 (temporal_len2) | ❌ Worse |
| Recall >= 0.95 | 0.545 (temporal_len2) | ❌ Far below threshold |
| No GT at inference | Yes | Pass |
| No supervised train/test fitting | Yes | Pass |
| Cross-split temporal context disclosed | 17 mixed tracks | Caveat |

### Comparison to Other Methods

| Method | Test F1 | Test R | DeltaF1 | GT-free? | Production? |
|--------|---------|--------|---------|----------|-------------|
| baseline (conf=0.25) | 0.753 | 0.970 | — | Yes | Current |
| NMS alone | 0.741 | 0.982 | +0.005 | Yes | Marginal |
| MobileNet classifier v3 | 0.763 | 0.879 | +0.010 | Yes | No |
| RF feature filter | 0.757 | 0.849 | +0.004 | Yes | No |
| LR feature filter | 0.744 | 0.879 | −0.009 | Yes | No |
| **Temporal len2** | **0.632** | **0.545** | **−0.121** | **Yes** | **No** |
| Temporal len3 | 0.372 | 0.242 | −0.381 | Yes | No |
| Temporal mov2 | 0.400 | 0.273 | −0.353 | Yes | No |
| adaptive mask (GT-dep) | 0.858 | 0.982 | +0.122 | No | Requires GT |

### Recommended Next Steps

1. **Do not deploy temporal consistency filtering.** Recall is catastrophic with the current detector.

2. **The fundamental problem is detector consistency, not the filter.** Improving per-frame ball detection consistency (e.g., lower confidence threshold, better training data, temporal smoothing in the detector itself) is a prerequisite for temporal filtering to work.

3. **If detector consistency improves, re-evaluate.** A detector that fires on the ball in >= 2 consecutive frames for most GT balls would change the equation entirely. The fact that zero neg detections appear in tracks >= 3 confirms the signal is real.

4. **Consider test-time temporal approaches that don't require consistent detection.** E.g., track the ball with a dedicated tracker (e.g., DeepSORT, ByteTrack) initialized from high-confidence detections rather than filtering all detections by track length.

---

## Deliverables Committed

| File | Description |
|------|-------------|
| `benchmark_temporal.py` | Full experiment script |
| `benchmark/temporal_results.csv` | Per-variant metrics by split |
| `benchmark/temporal_per_frame.csv` | Per-frame detail |
| `benchmark/temporal_tracks.csv` | 133 tracks with lifespan, motion, pass/fail |
| `benchmark/temporal_detection_scores.csv` | 180 detections with track assignments |
| `benchmark/temporal_overlays/` | 78 test-set overlays across 3 variants |
| `benchmark/temporal_contact_sheet.jpg` | Contact sheet of all overlays |
| `docs/TEMPORAL_CONSISTENCY_EXPERIMENT_REPORT.md` | This document |
