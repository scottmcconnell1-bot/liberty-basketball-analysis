# Ball Detection Precision Cleanup Plan

Date: 2026-06-14
Branch: jason-5-may-updates
Owner: Codex
Verification lead: Hermes/OWL

## Purpose

Improve ball detector precision without losing the recall gain from switching production ball detection to models/ball_detector.pt.

This task is not a new detector rebuild. It is a measurement-first cleanup pass on the verified production path.

## Proven Inputs

- Commit 2c31954 switches production ball detection to models/ball_detector.pt, class 0, confidence 0.15.
- Hermes/OWL verified commit 2c31954 on Linux with 186/186 tests passing.
- Hermes/OWL verified the production path loads models/ball_detector.pt class 0 at conf=0.15.
- benchmark/results_summary.csv reports models/ball_detector.pt at conf=0.15: TP=106, FP=128, FN=2, precision=0.453, recall=0.9815.
- Hermes/OWL smoke test found detections in 4 of 5 positive frames and false positives in 4 of 5 likely negative frames.

## Questions To Answer

1. Are multi-detection positive frames duplicate detections of the same ball?
2. Are false positives mostly specific classes or objects such as hoop, clock, scoreboard, hands, or court markings?
3. How much can confidence increase before recall drops materially?
4. Are any likely negative frames actually positive frames with a visible ball?
5. Does production-path output match the committed benchmark evaluator on the full 138-frame benchmark?

## Proposed Work

1. Run the full 138-frame benchmark through the current production path.
2. Generate per-frame detection overlays for the highest-confidence false positives and the two false negatives.
3. Classify false positives by source: duplicate, hoop/rim, scoreboard/clock, player body/hand, court marking, or uncertain.
4. Run a confidence sweep at minimum: 0.15, 0.20, 0.25, 0.30, 0.40.
5. Evaluate whether simple per-frame non-max suppression or top-1 ball selection improves precision without reducing recall.
6. Document results before any production post-processing change.

## Acceptance Criteria

- Full 138-frame production-path benchmark results are committed or documented.
- False positives are categorized with examples.
- Confidence sweep includes precision, recall, TP, FP, FN, and F1.
- Any proposed post-processing change has before/after benchmark evidence.
- Report distinguishes Proven, Inferred, and Unknown.

## Non-Goals

- Do not retrain the model in this task.
- Do not replace models/ball_detector.pt in this task.
- Do not build downstream event or possession features until ball precision cleanup is measured.
