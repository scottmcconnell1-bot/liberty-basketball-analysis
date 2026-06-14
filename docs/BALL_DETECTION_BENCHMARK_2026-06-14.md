# Ball Detection Benchmark Report
**Date:** 2026-06-14  
**Branch:** jason-5-may-updates  
**Benchmark size:** 138 frames (108 positive, 30 negative)  
**IoU threshold:** 0.50  

---

## 1. Benchmark Construction

### Positive Frames (108)
- **Source:** `ball_dataset_v2/images/` + `ball_dataset_v2/labels/`
- **Provenance:** Human-labeled bounding boxes created June 4 2026, verified via contact sheets and zoom verification images
- **Split:** 86 train / 20 val (per original dataset split, kept separate in benchmark)
- **Video source:** Same game footage (`Liberty_Vs_Riverstone_20260519_103815.webm`)
- **Box characteristics:** Tight boxes, average ~18×31px at 1280×720
- **Scenarios covered:** Ball in various court positions — perimeter, center court, near basket area

### Negative Frames (30)
- **Source:** Evenly sampled from `Liberty_Vs_Riverstone_20260519_103815.webm`
- **Distribution:** 10 from 0–3min, 10 from 17–29min, 10 from 31–60min
- **Selection:** Frame numbers do not overlap with ball_dataset_v2 frame range (which clusters around frames 2000–5000)
- **Caveat:** These are "likely negative" — no human verification that every frame is truly ball-free. A ball could be present but outside the labeled dataset's frame range. This is a known limitation (see Unknown section).

### Provenance Gap
- The ball_dataset_v2 labels were created by a human labeler (per git history: tight boxes corrected from original v1 dataset), but the **labeler identity and review process are not documented in the repo**. The git commits reference "contact sheet" and "verification sheet" creation, suggesting a review step existed, but no review record survives.
- Negative frame labeling is **automated** (no human verification).

---

## 2. Results — Base YOLOv8n, COCO Class 32 (sports ball)

### Confidence Sweep

| Conf Threshold | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 0.01 | 0 | 102 | 143 | 0.000 | 0.000 | 0.000 |
| 0.05 | 0 | 32 | 143 | 0.000 | 0.000 | 0.000 |
| 0.10 | 0 | 16 | 143 | 0.000 | 0.000 | 0.000 |
| 0.15 | 0 | 12 | 143 | 0.000 | 0.000 | 0.000 |
| 0.20 | 0 | 10 | 143 | 0.000 | 0.000 | 0.000 |
| 0.30 | 0 | 3 | 143 | 0.000 | 0.000 | 0.000 |
| 0.50 | 0 | 2 | 143 | 0.000 | 0.000 | 0.000 |

**PRODUCTION MODEL: Precision=0.000, Recall=0.000, F1=0.000**

The base YOLOv8n COCO "sports ball" class produces **zero true positives** across all confidence thresholds on a 138-frame benchmark with 143 ground truth balls.

### False Positive Analysis (conf=0.01)
- 102 false positive detections across 138 frames
- Average of 0.74 FP per frame
- At the production threshold (conf=0.15): 12 FP remain
- False positives decrease as confidence increases, indicating the model is finding *something* but always below production confidence

---

## 3. Results — Fine-Tuned Model

**NOT EVALUATED.** The fine-tuned model weights (`ball_finetune/runs/finetune2/weights/best.pt`) are **not present on the jason-5-may-updates branch**. They exist only on `dataset-v2`.

Alternative fine-tuned artifacts on this branch:
- `runs/detect/train/weights/best.pt` (85MB, 4 epochs, mAP50=0.008 on 5-image dataset)
- `runs/detect/train-2/weights/best.pt` (21MB, 5 epochs, mAP50=0.006 on 5-image dataset)

Both were trained on the broken 5-image dataset with oversized bounding boxes. Evaluation skipped — training metrics already proved these don't work.

**Recommendation:** Pull `ball_finetune/runs/finetune2/weights/best.pt` from `dataset-v2` and re-run evaluation. Training metrics show precision=0 at all 15 epochs, so we expect TP=0 here too.

---

## 4. Proven / Inferred / Unknown

### PROVEN
1. Production detector (YOLOv8n COCO class 32) achieves **0% precision and 0% recall** on a 138-frame benchmark — verified by this evaluation
2. The production false positive rate is 0.74 FP/frame at conf=0.01, 0.09 FP/frame at conf=0.15
3. `ball_finetune/runs/finetune2/weights/best.pt` does not exist on jason-5-may-updates
4. The fine-tuned model trained to precision=0, recall=0 at all 15 epochs (from `finetune2/results.csv` on dataset-v2)
5. The 5-image training dataset (`ball_dataset/`) has oversized boxes (16–56% of frame)

### INFERRED
1. The fine-tuned model (`finetune2`) also achieves TP=0 on this benchmark — it learned nothing from training (broken data path, see audit)
2. The 30 negative frames are likely ball-free but **not human-verified** — FP count may be slightly overstated if a ball is present in a "negative" frame
3. The 108 positive frames all come from the same game and same ~5-minute window — performance on other games/lighting is unknown

### UNKNOWN
1. Fine-tuned model performance (weights not available on this branch)
2. Whether any negative frames contain a ball (not human-verified)
3. How the detector performs on footage from different games, cameras, or lighting conditions
4. Performance on the specific "hard cases" requested (ball in hand, in flight, occluded, near rim) — the dataset doesn't label scenarios, so per-scenario breakdown isn't possible without manual categorization

---

## 5. Conclusions

**The production ball detector is non-functional.** Verified on 138 frames: 0 true positives, 0% precision, 0% recall. Every "ball detection" the production pipeline outputs is either a false positive or a fallback estimate from the player-proximity heuristic.

The benchmark is committed to `jason-5-may-updates` and can be used to evaluate any future detector.

---

## 6. Files Committed

| File | Description |
|---|---|
| `benchmark/manifest.csv` | Frame provenance: 138 frames, source, labeler, review status |
| `benchmark/frames/` | 138 frame images (108 positive + 30 negative) |
| `benchmark/labels/` | YOLO-format ground truth labels |
| `benchmark/results_summary.csv` | Precision/recall at each confidence threshold |
| `benchmark/results_perframe.csv` | Per-frame TP/FP/FN |
| `benchmark_run.py` | Reproducible evaluation script |
| `docs/BALL_DETECTION_BENCHMARK_2026-06-14.md` | This report |
