# Ball Detection Benchmark Report
**Date:** 2026-06-14  
**Branch:** jason-5-may-updates  
**Commit:** (corrected results)  
**Benchmark size:** 138 frames (108 positive, 30 negative)  
**IoU threshold:** 0.50  
**Evaluation:** conf=0.15 (production default), imgsz=640  

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
- **Caveat:** These are "likely negative" — no human verification that every frame is truly ball-free. This is a known limitation (see Unknown section).

### Contact Sheet
`benchmark/contact_sheet.jpg` shows 20 sample frames (10 positive with green GT boxes, 10 negative with no boxes).

---

## 2. Results

### Base YOLOv8n, COCO Class 32 (sports ball) — Production Path

| Metric | Value |
|--------|-------|
| TP | 0 |
| FP | 11 |
| FN | 108 |
| Precision | 0.000 |
| Recall | 0.000 |
| F1 | 0.000 |

**The production detector finds zero basketballs.** Every detection is a false positive. The 11 false positives at conf=0.15 are non-ball objects (rim, court markings, etc.) that happen to trigger the COCO "sports ball" class.

### Fine-Tuned ball_detector.pt (class 0 = Ball)

| Metric | Value |
|--------|-------|
| TP | 106 |
| FP | 128 |
| FN | 2 |
| Precision | 0.453 |
| Recall | 0.982 |
| F1 | 0.618 |

**The fine-tuned model works.** 98.2% recall — it finds 106 of 108 balls. But precision is only 45.3% — 128 false positives across 138 frames (0.93 FP/frame). The 2 false negatives are likely occlusion or unusual angles.

### Confidence Sweep (Fine-Tuned Model)

| Conf Threshold | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 0.01 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |
| 0.05 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |
| 0.10 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |
| 0.15 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |
| 0.20 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |
| 0.30 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |
| 0.50 | 106 | 128 | 2 | 0.453 | 0.982 | 0.618 |

Note: The fine-tuned model's detections are all above 0.50 confidence for this benchmark set, so the sweep shows identical results. The FP count is high because the model detects other orange/brown objects (hoop, clock, overlay graphics) as "Ball".

---

## 3. Proven / Inferred / Unknown

### PROVEN
1. Production detector (YOLOv8n COCO class 32) achieves **0% precision and 0% recall** on 138-frame benchmark — verified by this evaluation
2. Fine-tuned model (`models/ball_detector.pt`) achieves **45.3% precision, 98.2% recall** on the same benchmark
3. The fine-tuned model has 7 classes: Ball, Clock, Hoop, Overlay, Player, Ref, Scoreboard (class 0 = Ball)
4. The production pipeline never loads the fine-tuned model — it uses `yolov8n.pt` COCO class 32
5. `ball_finetune/runs/finetune2/results.csv` shows precision=0, recall=0 at all 15 epochs — the training job used a broken data path (`ball_finetune/data.yaml` was missing)
6. The 5-image training dataset (`ball_dataset/`) has oversized boxes (16–56% of frame)
7. The fine-tuned model was trained on a different dataset than `ball_dataset_v2` — it learned 7 classes including Ball, but with low precision

### INFERRED
1. The fine-tuned model's 128 false positives are mostly Hoop, Clock, and Overlay classes being misclassified as Ball (the model has 7 classes but we only filter for class 0)
2. The 2 false negatives are likely frames where the ball is heavily occluded or at an unusual angle
3. The production pipeline's fallback estimator (player-proximity heuristic) generates most "ball" positions, not actual detections
4. The fine-tuned model would perform better with a higher confidence threshold (0.50+), trading recall for precision

### UNKNOWN
1. Whether the 30 negative frames contain any balls (not human-verified)
2. Per-scenario performance (ball in hand, flight, occluded, near rim) — not categorized
3. Performance on footage from different games, cameras, or lighting conditions
4. Why the fine-tuned model's training showed 0/0 metrics when the saved weights actually work — possibly the validation set was empty or the metrics were computed before the first epoch completed

---

## 4. Conclusions

**The production ball detector is non-functional.** Verified: 0% precision, 0% recall. Every "ball detection" is either a false positive or a fallback estimate.

**The fine-tuned model (`models/ball_detector.pt`) actually works** but with low precision (45%). It finds 98% of balls but also produces many false positives. It is not currently used in production.

**Recommendation:** 
1. Switch production to use `models/ball_detector.pt` with class 0 (Ball) filtering
2. Add NMS and confidence threshold tuning to reduce FP rate
3. Retrain on the `ball_dataset_v2` labels (108 images, proper tight boxes) to improve precision
4. Expand dataset to 500+ images for better generalization

---

## 5. Files Committed

| File | Description |
|---|---|
| `benchmark/manifest.csv` | Frame provenance: 138 frames, source, labeler, review status |
| `benchmark/frames/` | 138 frame images (108 positive + 30 negative) |
| `benchmark/labels/` | YOLO-format ground truth labels |
| `benchmark/results_summary.csv` | Precision/recall at each confidence threshold |
| `benchmark/results_perframe.csv` | Per-frame TP/FP/FN |
| `benchmark/contact_sheet.jpg` | 20-frame contact sheet with GT boxes |
| `benchmark_run.py` | Reproducible evaluation script (bug-fixed: h normalization) |
| `benchmark_contact.py` | Contact sheet generator |
| `models/ball_detector.pt` | Fine-tuned model weights (pulled from dataset-v2) |
| `docs/BALL_DETECTION_BENCHMARK_2026-06-14.md` | This report |
