# Ball Detection Precision Cleanup Plan

**Date:** 2026-06-14
**Branch:** jason-5-may-updates
**Detector:** `models/ball_detector.pt`, class 0, conf=0.15
**Current benchmark:** TP=106, FP=128, FN=2, P=0.453, R=0.982 (138 frames, IoU=0.50)

## Purpose

The fine-tuned detector finds 98% of balls but has 45% precision — 128 false positives per 138 frames. This plan measures the FP sources and evaluates threshold-based and post-processing fixes before any retraining.

## Proven Inputs

- `models/ball_detector.pt` has 7 classes: Ball(0), Clock(1), Hoop(2), Overlay(3), Player(4), Ref(5), Scoreboard(6)
- Production path now loads this model at class 0, conf=0.15 (verified at HEAD 2c31954)
- 186/186 tests pass
- 138-frame benchmark committed with results_summary.csv and results_perframe.csv

## Sequence

### Phase 1: FP Classification

Run the full 138-frame benchmark through the **current production path** (not standalone script). For every FP detection:

1. Classify into one of:
   - **duplicate**: IoU > 0.3 with another detection in the same frame (same ball detected multiple times)
   - **hoop/rim**: detection center within 60px of known basket positions
   - **scoreboard/clock**: detection in top 20% of frame where scoreboard graphics are
   - **player/body**: detection overlaps a person bounding box
   - **court marking**: detection on court floor area, no player overlap
   - **uncertain**: none of the above

2. Generate overlay images for:
   - Top 10 highest-confidence FP detections
   - The 2 FN frames (missed balls)
   - Frames with multi-detections (3+ detections of class 0)

### Phase 2: Confidence Sweep

Evaluate at conf = 0.15, 0.20, 0.25, 0.30, 0.40, 0.50:
- TP, FP, FN at each threshold
- TP/FP ratio to find the "knee" where FP drops fast with minimal recall loss
- Identify the threshold that maximizes F1

### Phase 3: Post-Processing Evaluation

At the best confidence threshold from Phase 2, evaluate:

1. **Top-1 per frame**: keep only the highest-confidence ball detection per frame
2. **NMS (IoU=0.3)**: suppress overlapping detections
3. **Scoreboard mask**: reject detections in the scoreboard region (top ~15% of frame, right side)
4. **Combined**: NMS + mask + threshold

Measure TP/FP/FN for each variant.

### Phase 4: Decision

Based on evidence, recommend one of:
- Raise confidence threshold only (simplest)
- NMS + threshold (moderate complexity)
- Scoreboard mask + NMS + threshold (addresses known FP source)
- Retrain with negative examples (high effort, defer)

## Deliverables

- `benchmark/precision_analysis.csv`: per-FP classification
- `benchmark/precision_overlays/`: overlay images for FP/FN/multi-detection frames
- `benchmark/confidence_sweep.csv`: TP/FP/FN at each threshold
- `benchmark/postprocess_results.csv`: TP/FP/FN for each post-processing variant
- `docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md`: evidence + recommendation

## Non-Goals

- Do not change production code yet
- Do not retrain the model yet
- Do not modify the benchmark frames or labels
