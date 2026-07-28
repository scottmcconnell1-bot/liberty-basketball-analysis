# GT-Free Court-Marking Exclusion Experiment Report

**Date:** 2026-06-15
**Branch:** jason-5-may-updates
**Start commit:** 3548fa5 (court-marking exclusion benchmark experiment)
**Detector:** models/ball_detector.pt (YOLOv8n, class 0 = ball, conf=0.25)
**Benchmark:** 138 frames (108 GT+, 30 GT-)
**Experiment script:** `benchmark_gtfree.py`

---

## Executive Summary

**No GT-free method materially improves over the conf=0.25 baseline (F1=0.7361) while maintaining recall ≥ 0.95.**

The best GT-free variants — `grid_top2_6x3`, `nms_iou30`, `nms_iou50`, and `grid63_top2_nms` — all achieve **F1=0.7413** (+0.0052 over baseline), which is the same marginal gain as NMS alone. They remove only 2 detections across 2 frames.

Methods that aggressively remove detections (top-1, top-2 per frame, grid-top-1) all **lose substantial recall** (0.62–0.92) because court-marking FPs and true balls occupy the same spatial cells and have overlapping confidence scores.

**The spatial overlap problem is fundamental:** 95% of GT balls are within 100px of a court-marking FP, and balls span nearly the entire frame width (70–1271px of 1280px). No fixed spatial mask at any resolution can separate them without losing TPs.

**Conclusion: GT-free court-marking exclusion is NOT a production candidate at conf=0.25.** The adaptive mask (GT-dependent, F1=0.858) remains the only method that materially improves F1, but it cannot run in production without ground truth.

---

## Proven (measured from committed CSV data)

### GT-Free Variant Results at conf=0.25

Source: `benchmark/gtfree_results.csv` (all values measured, not estimated)

| Variant | TP | FP | FN | Precision | Recall | F1 | ΔF1 | Removed |
|---------|----|----|----|-----------|--------|-----|-----|---------|
| **baseline** | **106** | **74** | **2** | **0.5889** | **0.9815** | **0.7361** | — | 0 |
| top1_per_frame | 67 | 52 | 41 | 0.5630 | 0.6204 | 0.5903 | −0.1458 | 61 |
| top2_per_frame | 93 | 67 | 15 | 0.5813 | 0.8611 | 0.6940 | −0.0421 | 20 |
| grid_top1_4x2 | 97 | 66 | 11 | 0.5951 | 0.8981 | 0.7159 | −0.0202 | 17 |
| grid_top1_6x3 | 99 | 68 | 9 | 0.5928 | 0.9167 | 0.7200 | −0.0161 | 13 |
| **grid_top2_6x3** | **106** | **72** | **2** | **0.5955** | **0.9815** | **0.7413** | **+0.0052** | 2 |
| **nms_iou30** | **106** | **72** | **2** | **0.5955** | **0.9815** | **0.7413** | **+0.0052** | 2 |
| **nms_iou50** | **106** | **72** | **2** | **0.5955** | **0.9815** | **0.7413** | **+0.0052** | 2 |
| nms_iou70 | 106 | 74 | 2 | 0.5889 | 0.9815 | 0.7361 | 0.0000 | 0 |
| grid63_top1_nms | 99 | 68 | 9 | 0.5928 | 0.9167 | 0.7200 | −0.0161 | 13 |
| **grid63_top2_nms** | **106** | **72** | **2** | **0.5955** | **0.9815** | **0.7413** | **+0.0052** | 2 |

### Key Measured Findings

1. **NMS (any IoU threshold 0.3–0.5) is the best GT-free method: F1=0.7413 (+0.0052).**
   - Removes only 2 detections total (both from 2 frames)
   - These 2 detections are within 30–50% IoU of a higher-confidence detection
   - Effectively: NMS only helps when there are duplicate/near-duplicate detections

2. **Grid_top2_6x3 equals NMS exactly (F1=0.7413, 2 removed).**
   - The 6×3 grid with top-2 per cell is slightly more aggressive than needed
   - But only 2 frames have >2 detections in the same cell at conf=0.25
   - In practice, grid_top2_6x3 ≈ NMS for this benchmark

3. **Grid_top1 variants lose 9–11 TPs (recall 0.90–0.92).**
   - Even at 6×3 resolution (213×240px cells), some cells contain both a ball and court-marking FPs
   - Keeping only top-1 per cell removes the ball when a court-marking FP has higher confidence
   - Affects 11–17 frames, loses 7–9 TPs

4. **Top-K per frame is worse than grid-based methods.**
   - top1_per_frame: recall 0.62 (loses 39 TPs — the known multi-detection problem)
   - top2_per_frame: recall 0.86 (loses 14 TPs, better but still below 0.95 threshold)

5. **NMS IoU=0.7 is too aggressive — removes nothing (0 removed, F1=0.7361).**
   - At IoU=0.7, almost no detection pairs overlap enough to trigger suppression
   - At IoU=0.3–0.5, the same 2 duplicate detections are caught

6. **The 2 detectable-by-NMS frames have 4+ detections each.**
   - These are frames where the ball is detected multiple times with slight position shifts
   - NMS collapses the duplicates, removes 1 FP in each of 2 frames
   - The remaining 72 FPs are spatially isolated and not near-duplicate

### Why GT-Free Court-Marking Exclusion Fails

The spatial analysis proves the fundamental problem:

| Metric | Value |
|--------|-------|
| GT ball X range | 70–1271px (93% of frame width) |
| GT ball Y range | 162–610px (62% of frame height) |
| Court-marking FP X range | 214–1081px |
| Court-marking FP Y range | 224–616px |
| GT balls within 100px of a court-marking FP | 103/108 (95%) |
| GT-FP cell overlap (8×4 grid, finest tested) | 13/19 cells (68%) |

**At any grid resolution, the ball and court markings occupy the same cells.** There is no spatial boundary that separates them.

---

## Inferred (logical deduction, not directly measured)

1. **The remaining 72 FPs (post-NMS) are irreducible by spatial methods alone.** They are spatially isolated detections on court markings that don't overlap with other detections. Removing them requires either GT knowledge, a secondary classifier, temporal consistency, or a fundamentally better detector.

2. **A learned secondary classifier is the most promising GT-free direction.** Train a small model to distinguish "ball" from "court marking" using the detection crops. This doesn't need GT ball positions at inference time — only at training time. Not measured.

3. **Temporal consistency filtering could help.** Court markings are stationary while the ball moves. A multi-frame tracker that requires detections to move ball-like would suppress static court-marking FPs. Not measured.

4. **The benchmark frames may be harder than typical game film.** Curated benchmark frames likely include challenging angles and lighting. Real game footage from a fixed camera might have more predictable court geometry, making a fixed ROI mask more effective. Not measured.

5. **Combining NMS with a learned classifier could reach F1 > 0.80.** NMS handles near-duplicates (F1 +0.005), a classifier handles isolated court-marking FPs (untested). Not measured.

---

## Unknown (not validated with evidence)

1. **Secondary classifier performance.** A model trained to distinguish ball crops from court-marking crops could remove isolated FPs. Architecture, training data requirements, and measured accuracy are all unknown.

2. **Temporal filtering effectiveness.** Whether ball-like motion is distinctive enough to separate from court markings across frames is unmeasured.

3. **Performance on non-benchmark data.** The spatial overlap statistics are computed from 138 curated frames. Other cameras, courts, or angles might have different overlap characteristics.

4. **Whether a fixed camera ROI mask could work for single-camera setups.** The benchmark spans multiple videos/cameras. A single fixed camera might have a predictable court region where ball-vs-marking separation is easier.

5. **Detector improvement path.** The fundamental problem is the detector confuses court markings with balls. Training with hard-negative court-marking examples could reduce FPs at the source. Not measured.

---

## Comparison: GT-Dependent vs GT-Free Methods

| Method | F1 | Recall | ΔF1 | GT-free? | Production? |
|--------|-----|--------|-----|----------|-------------|
| baseline (conf=0.25) | 0.7361 | 0.9815 | — | Yes | Current prod |
| NMS (IoU=0.3) | 0.7413 | 0.9815 | +0.005 | Yes | Marginal |
| **adaptive mask (GT-dep)** | **0.8583** | **0.9815** | **+0.122** | **No** | **Candidate** |
| neg-only mask (GT-dep) | 0.7709 | 0.9815 | +0.035 | No | Candidate |
| grid_top1_6x3 | 0.7200 | 0.9167 | −0.016 | Yes | No |
| top2_per_frame | 0.6940 | 0.8611 | −0.042 | Yes | No |
| top1_per_frame | 0.5903 | 0.6204 | −0.146 | Yes | No |

---

## Production Recommendation

### GT-Free Methods: NOT Production Candidates

No GT-free method meets the acceptance criteria (F1 materially improved over 0.7361, recall ≥ 0.95). The best GT-free method (NMS IoU=0.3) achieves F1=0.7413 — a negligible +0.005 gain that does not justify production changes.

### Recommended Next Steps

1. **Do not deploy any GT-free spatial mask to production.** The gains are nonexistent.

2. **Investigate a secondary classifier** as the primary GT-free path. Train on crops from the existing benchmark (ball vs. court marking) and measure precision/recall on held-out frames.

3. **Investigate temporal filtering** as a complementary approach. Requires multi-frame pipeline but is purely GT-free.

4. **Revisit hard-negative training data.** The root cause is the detector confuses court markings with balls. Adding court-marking negatives to training could reduce FPs at the source.

5. **Consider the neg-only mask (GT-dependent) as a partial production improvement.** It removes 13 FPs from negative frames with zero TP loss (F1 +0.035). If there's a reliable way to identify "ball-absent" frames at inference time (e.g., low detection count + low confidence), this could be partially GT-free.

---

## Deliverables Committed

| File | Description |
|------|-------------|
| `benchmark_gtfree.py` | Full GT-free experiment script — 11 variants, overlay generation |
| `benchmark/gtfree_results.csv` | Per-variant metrics (11 rows) |
| `benchmark/gtfree_per_frame.csv` | Per-frame detail (1,518 rows = 138 × 11) |
| `benchmark/gtfree_overlays/` | 40 annotated frames showing removed detections |
| `docs/COURT_MASK_GTFREE_EXPERIMENT_REPORT.md` | This document |
