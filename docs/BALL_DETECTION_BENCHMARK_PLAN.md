# Ball Detection Benchmark Plan

Date: 2026-06-14
Branch: jason-5-may-updates
Decision maker: Scott McConnell

## Purpose

Create a small, verified ground-truth benchmark before rebuilding or retraining the basketball detector.

The current audit reports that ball detection is not usable for film analysis, but it also reports that formal precision/recall validation was not completed. This benchmark becomes the repeatable measurement gate for the current detector, existing model artifacts, and any future rebuilt detector.

## Proven Inputs

- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports the production detector path uses base YOLOv8 COCO sports-ball class 32, not the fine-tuned ball detector.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports the top-20 v14 audit found 0 basketballs among the 20 highest-confidence detections.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports formal precision/recall validation was not completed because precision_recall.csv was empty.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md identifies audit_detector.py as the intended IoU-based evaluation framework.
- Scott approved building the benchmark first on 2026-06-14.

## Benchmark Scope

Create a benchmark set of 30-50 frames.

The frame set should include:

- Ball in hand.
- Ball in flight.
- Ball near rim/backboard.
- Ball partially occluded.
- Ball near court markings.
- Ball absent from frame.
- Multiple lighting/background conditions if available.
- Multiple game sources if available.

Target mix:

- 70-80% positive frames with one visible basketball.
- 20-30% negative frames with no visible basketball.

## Label Requirements

Each benchmark frame must have explicit provenance:

- Source video or source frame path.
- Frame number or timestamp.
- Labeler.
- Review status.
- Whether the frame is positive or negative.
- For positive frames: basketball bounding box coordinates.
- For hard cases: short note explaining ambiguity.

Label format should be compatible with audit_detector.py or converted into that format before evaluation.

## Models To Evaluate

Run the benchmark against:

1. Current production path: base YOLOv8 sports-ball class 32 as used by ai_analyzer.py.
2. Existing fine-tuned artifact: models/ball_detector.pt, if loadable.
3. Any candidate rebuilt detector before it is considered for production use.

## Metrics

Report at minimum:

- Precision.
- Recall.
- False positives.
- False negatives.
- True positives.
- Detection confidence distribution.
- IoU threshold used for scoring.
- Per-scenario notes for the hardest failures.

Preferred thresholds:

- IoU >= 0.50 for a correct detection.
- Confidence sweep across several thresholds rather than a single confidence value.

## Deliverables

Hermes/OWL should produce or update:

- Benchmark frame directory.
- Benchmark labels file or label directory.
- Contact sheet showing labels.
- Machine-readable benchmark result file.
- Written report with Proven / Inferred / Unknown sections.

Codex should then import the report into jason-5-may-updates and update:

- PROJECT_STATUS.md.
- ROADMAP.md.
- DATASET_INVENTORY.md or equivalent dataset governance file.
- DECISION_LOG.md if a detector rebuild decision is made.

## Acceptance Criteria

The benchmark is complete when:

1. 30-50 frames are selected.
2. Every frame has provenance.
3. Every positive frame has a human-reviewed basketball box.
4. Negative frames are explicitly labeled as no-ball.
5. audit_detector.py or an equivalent documented evaluator runs successfully.
6. Results include precision, recall, false positives, and false negatives.
7. The report distinguishes Proven, Inferred, and Unknown.
8. The benchmark result is stored or referenced from jason-5-may-updates.

## Non-Goals

- Do not retrain a model as part of this benchmark task.
- Do not replace the production detector yet.
- Do not merge dataset-v2 wholesale into jason-5-may-updates.
- Do not treat heuristic top-20 classification as a substitute for formal labeled-frame validation.

## Recommended Next Step

Ask Hermes/OWL to build the benchmark on the Linux machine, because the relevant videos, model artifacts, and dataset directories are Linux-local.
