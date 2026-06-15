# Ball Detection Benchmark Report
**Date:** 2026-06-14  
**Branch:** jason-5-may-updates  
**Benchmark size:** 138 frames (108 positive, 30 negative)  
**IoU threshold:** 0.50  
**Evaluation:** conf=0.05 and 0.15, imgsz=640  

---

## 1. Benchmark Construction

### Positive Frames (108)
- **Source:** `ball_dataset_v2/images/` + `ball_dataset_v2/labels/` (human-verified labels)
- **Split:** 86 train / 20 val (preserved from original dataset)
- **Video source:** `Liberty_Vs_Riverstone_20260519_103815.webm`
- **Box characteristics:** Tight boxes, average ~18×31px at 1280×720
- **Label provenance:** Human-labeled, verified via contact sheets (git commit 816e07e)

### Negative Frames (30)
- **Source:** Evenly sampled from `Liberty_Vs_Riverstone_20260519_103815.webm`
- **Distribution:** 10 from 0–3min, 10 from 17–29min, 10 from 31–60min
- **Selection:** Frame numbers do not overlap with ball_dataset_v2 frame range
- **Limitation:** These are "likely negative" — no human verification that every frame is truly ball-free. FP count may be slightly overstated if any negative frame contains a ball.

### Contact Sheet
`benchmark/contact_sheet.jpg` shows 20 sample frames (10 positive with green GT boxes, 10 negative with no boxes).

---

## 2. Results

### Base YOLOv8n, COCO Class 32 (sports ball) — Production Path

| Conf | TP | FP | FN | Precision | Recall | F1 |
|------|----|----|----|-----------|--------|-----|
| 0.05 | 3 | 25 | 105 | 0.107 | 0.028 | 0.044 |
| 0.15 | 0 | 11 | 108 | 0.000 | 0.000 | 0.000 |

**The production detector is non-functional.** At the production threshold (conf=0.15): 0 true positives, 11 false positives, 108 false negatives. The 3 "hits" at conf=0.05 are marginal and disappear at any reasonable threshold.

### Fine-Tuned ball_detector.pt (class 0 = Ball)

| Conf | TP | FP | FN | Precision | Recall | F1 |
|------|----|----|----|-----------|--------|-----|
| 0.05 | 106 | 249 | 2 | 0.299 | 0.982 | 0.458 |
| 0.15 | 106 | 128 | 2 | 0.453 | 0.982 | 0.620 |

**The fine-tuned model works.** 98.2% recall at both thresholds — it finds 106 of 108 balls. Precision is 45.3% at conf=0.15 (128 false positives = 0.93 FP/frame). The 2 false negatives are consistent across thresholds, suggesting genuinely difficult frames (occlusion, unusual angle).

Key insight: raising conf from 0.05 to 0.15 drops FP from 249 to 128 (49% reduction) with zero recall loss. Further confidence tuning could improve precision further.

---

## 3. Proven / Inferred / Unknown

### PROVEN
1. Production detector (YOLOv8n COCO class 32) achieves **0% precision, 0% recall** at conf=0.15 on 138-frame benchmark
2. Fine-tuned model (`models/ball_detector.pt`) achieves **45.3% precision, 98.2% recall** at conf=0.15
3. The fine-tuned model has 7 classes: Ball(0), Clock(1), Hoop(2), Overlay(3), Player(4), Ref(5), Scoreboard(6)
4. The production pipeline never loads the fine-tuned model — it uses `yolov8n.pt` COCO class 32
5. `ball_finetune/runs/finetune2/results.csv` shows precision=0, recall=0 at all 15 epochs — training used broken data path
6. The 5-image training dataset (`ball_dataset/`) has oversized boxes (16–56% of frame)
7. Detection box height normalization bug was fixed (was dividing by w_frame, now h_frame) — results in this report use the corrected code

### INFERRED
1. The fine-tuned model's 128 FP at conf=0.15 are mostly non-ball objects (hoop, clock, court markings) that share similar visual features with basketballs
2. The 2 FN are likely frames with heavy occlusion or unusual ball angles
3. The production pipeline's fallback estimator (player-proximity heuristic) generates most "ball" positions, not actual detections
4. The fine-tuned model was trained on a different dataset than `ball_dataset_v2` — it learned 7 classes, not just "ball"
5. Precision could be improved by training on `ball_dataset_v2` labels (tight boxes, single class) and adding negative examples

### UNKNOWN
1. Whether the 30 negative frames contain any balls (not human-verified)
2. Per-scenario performance (ball in hand, flight, occluded, near rim) — not categorized in this benchmark
3. Performance on footage from different games, cameras, or lighting conditions (all frames from one game)
4. Why training metrics showed 0/0 when the saved weights actually work — possibly validation set was empty or metrics computed before first epoch

---

## 4. Conclusions

**The production ball detector is non-functional.** Verified: 0% precision, 0% recall at conf=0.15. Every "ball detection" is either a false positive or a fallback estimate.

**The fine-tuned model (`models/ball_detector.pt`) works** with 98% recall but 45% precision. It is not currently used in production.

**Recommendation:**
1. Switch production to use `models/ball_detector.pt` with class 0 (Ball) filtering — immediate 98% recall improvement
2. Add confidence threshold tuning (0.15–0.30 range) to balance precision vs recall
3. Retrain on `ball_dataset_v2` labels (108 images, tight boxes, single class) to improve precision
4. Expand dataset to 500+ images with negative examples for better generalization

---

## 5. Files Committed

| File | Description |
|---|---|
| `benchmark/manifest.csv` | Frame provenance: 138 frames, source, labeler, review status |
| `benchmark/frames/` | 138 frame images (108 positive + 30 negative) |
| `benchmark/labels/` | YOLO-format ground truth labels |
| `benchmark/results_summary.csv` | Precision/recall at each confidence threshold (4 rows) |
| `benchmark/results_perframe.csv` | Per-frame TP/FP/FN (552 rows) |
| `benchmark/contact_sheet.jpg` | 20-frame contact sheet with GT boxes |
| `benchmark_run.py` | Reproducible evaluation script (bug-fixed) |
| `benchmark_gen_csvs.py` | Standalone CSV generator |
| `benchmark_contact.py` | Contact sheet generator |
| `models/ball_detector.pt` | Fine-tuned model weights (pulled from dataset-v2) |
| `models/court_keypoint_detector.pt` | Court keypoint model |
| `models/player_detector.pt` | Player detector model |
| `docs/BALL_DETECTION_BENCHMARK_2026-06-14.md` | This report |
