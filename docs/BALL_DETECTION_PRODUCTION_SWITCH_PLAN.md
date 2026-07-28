# Ball Detection Production Switch Plan

Date: 2026-06-14
Branch: jason-5-may-updates
Owner: Codex
Approval required: Scott McConnell

## Purpose

Replace the current production basketball detection path with the benchmarked fine-tuned model in the smallest safe step.

This is not a detector rebuild. It is a controlled production path correction based on the benchmark evidence.

## Proven Inputs

- ai_analyzer.py currently loads the configured detector model through resolve_detector_model(ai_settings).
- settings_store.py defaults ai.detector_model to yolov8n.pt.
- ai_analyzer.py currently detects players with classes=[0] and detects balls with the same model using classes=[32], conf=0.15.
- docs/BALL_DETECTION_BENCHMARK_2026-06-14.md reports production YOLOv8n COCO class 32 at conf=0.15: TP=0, FP=11, FN=108, precision=0.0, recall=0.0.
- docs/BALL_DETECTION_BENCHMARK_2026-06-14.md reports models/ball_detector.pt class 0 at conf=0.15: TP=106, FP=128, FN=2, precision=0.453, recall=0.9815.
- benchmark/results_summary.csv and benchmark/results_perframe.csv are committed and internally consistent.
- models/ball_detector.pt is Git LFS tracked and was fetchable by Codex on 2026-06-14.

## Proposed Implementation

1. Keep the existing configured detector model for person detection.
2. Add a separate ball detector configuration so player detection and ball detection are no longer forced to use the same model.
3. Default ball detector path to models/ball_detector.pt.
4. Default ball detector class id to 0.
5. Keep the initial ball confidence threshold at 0.15 to match the benchmark.
6. Preserve the existing fallback estimator, but tag or document fallback-generated ball rows so measured detections and estimates are not confused in future audits.
7. Add tests for model resolution and class selection without running YOLO inference in unit tests.

## Files Expected To Change

- ai_analyzer.py
- settings_store.py
- helpers.py, if the settings UI/catalog should expose the separate ball model setting
- tests/test_event_pipeline.py or a new focused test file for detector settings
- PROJECT_STATUS.md, WORKLOG.md, and DECISION_LOG.md after implementation and verification

## Verification Plan

Codex local verification:

- Compile changed Python files.
- Run focused tests for detector settings/model resolution if local dependencies allow.
- Run git diff --check.

Hermes/OWL Linux verification:

- Confirm jason-5-may-updates branch.
- Run the full test suite.
- Confirm models/ball_detector.pt is available through Git LFS.
- Run the benchmark or a focused benchmark smoke against models/ball_detector.pt.
- Report Proven / Inferred / Unknown evidence.

## Risks

- Precision is only 45.3% at conf=0.15 on the benchmark, so false positives remain likely.
- The benchmark comes from one game source, so cross-game generalization is unknown.
- The 30 negative frames are likely negative but not fully human-reviewed.
- If production and benchmark preprocessing differ, live results may differ.

## Approval Gate

Scott approval is required before production detector behavior changes.
