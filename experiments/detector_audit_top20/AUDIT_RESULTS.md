# v14 Ball Detector — Top-20 Audit Results

**Date:** 2026-05-29  
**Detector:** v14 YOLO (fine-tuned on 5 frames, mAP=0 across all 15 epochs)  
**Source:** Liberty vs Riverstone Q1, 720p, 2701 frames  
**Method:** Human inspection of the 20 highest-confidence detections across all frames.

## Audit Table

| # | Frame | Conf | X | Y | Object | Certainty |
|---|-------|------|--------|--------|---------------------|-----------|
| 1 | 808 | 0.0017 | 977.7 | 630.8 | Floor (nothing) | High |
| 2 | 120 | 0.0016 | 1106.1 | 473.5 | Player (Riverstone foot) | High |
| 3 | 467 | 0.0016 | 273.2 | 440.4 | Floor (nothing) | High |
| 4 | 724 | 0.0013 | 466.8 | 308.0 | Player (Liberty) | High |
| 5 | 2174 | 0.0012 | 915.1 | 474.6 | Court marking (key block) | High |
| 6 | 2051 | 0.0011 | 304.6 | 439.4 | Floor (nothing) | High |
| 7 | 990 | 0.0010 | 1043.1 | 537.0 | Floor (nothing) | High |
| 8 | 1072 | 0.0010 | 433.8 | 407.2 | Floor (nothing) | High |
| 9 | 1290 | 0.0008 | 693.3 | 439.3 | Player (Liberty #11 foot) | High |
| 10 | 2318 | 0.0008 | 785.0 | 472.8 | Player (Liberty #5 foot) | High |
| 11 | 2435 | 0.0007 | 948.7 | 440.5 | Court marking (volleyball line) | High |
| 12 | 2591 | 0.0007 | 785.3 | 506.6 | Floor (half circle) | High |
| 13 | 1413 | 0.0006 | 853.5 | 502.0 | Player (Riverstone calf) | High |
| 14 | 2505 | 0.0005 | 756.6 | 440.7 | Other (between players) | Medium |
| 15 | 33 | 0.0004 | 597.2 | 342.4 | Other (mascot at half court) | High |
| 16 | 68 | 0.0004 | 212.3 | 378.1 | Player (Liberty foot) | High |
| 17 | 259 | 0.0004 | 241.1 | 280.5 | Player (Liberty foot) | High |
| 18 | 2642 | 0.0004 | 467.4 | 507.5 | Floor (nothing) | High |
| 19 | 236 | 0.0003 | 241.4 | 507.1 | Floor reflection (gym light) | High |
| 20 | 617 | 0.0003 | 276.8 | 429.3 | Player (Riverstone knee) | High |

## Summary

| Object | Count | Pct |
|--------|-------|-----|
| Player/jersey (feet/calf/knee) | 7 | 35% |
| Floor (nothing visible) | 6 | 30% |
| Court marking/logo | 2 | 10% |
| Other (mascot, between players) | 2 | 10% |
| Floor reflection | 1 | 5% |
| **Basketball** | **0** | **0%** |
| **Rim/backboard** | **0** | **0%** |

## Conclusion

**The v14 detector has zero basketball detections in its top 20 results.** It is not a weak detector — it is detecting the wrong objects entirely. The detector locked onto:
- Player feet and calves (35%)
- Empty floor patches (30%)
- Court markings (10%)
- Miscellaneous artifacts (mascot, reflections, etc.) (25%)

Every pipeline built on top of v14 (v15–v40, shot classification, clustering, all of it) is built on garbage detections and must be discarded.

## Implications

- Do NOT fine-tune this model — it is fundamentally broken
- Do NOT build shot-classification until a working detector exists
- Start from scratch with pretrained models (abdullahtarek)
- A ground-truth benchmark is required before evaluating ANY detector

## Annotated Frames

All 20 annotated frames (green cross at detection point) are saved in:
`docs/detector_audit_top20/` on branch `jason-5-may-updates`.
