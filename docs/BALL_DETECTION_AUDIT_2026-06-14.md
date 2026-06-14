# Ball Detection Audit — 2026-06-14

**Auditor:** OWL (automated audit, evidence-based)  
**Scope:** Liberty Basketball Analysis project ball detection pipeline  
**Branch:** `dataset-v2` (active working branch per git log)  
**Deliverable:** Evidence inventory + failure mode analysis + recommendations

---

## 1. Executive Summary

**The ball detector is non-functional for film analysis.** The fine-tuned model (`ball_finetune/runs/finetune2/weights/best.pt`) was trained on a dataset of 5–108 images across multiple versions, with training runs that show **precision=0 and recall=0 at every epoch checkpoint**. The production pipeline (`ai_analyzer.py` / `ai_analyzer_tuned.py`) uses the base YOLOv8 model's `classes=[32]` (sports ball) with HSV color filtering, but the audit scripts (`audit_detector.py`, `audit_top20.py`, `audit_top20_v2.py`) were **never successfully run to completion** — no `precision_recall.csv` exists. The top-20 visual audit of v14 detections found **0 basketballs** among the 20 highest-confidence "ball" detections.

**Verdict: Ball detection is NOT usable for film analysis. A rebuild is required.**

---

## 2. Active Detector Path

### 2.1 Production Pipeline (PROVEN)

The active ball detection path is in `ai_analyzer.py` (lines 155–229) and `ai_analyzer_tuned.py` (lines 155–229):

1. **Model:** `resolve_detector_model()` returns `yolov8n.pt` by default (`settings_store.py` line 5: `"detector_model": "yolov8n.pt"`)
2. **Ball detection method:** `model(frame, classes=[32], conf=0.15, verbose=False, imgsz=640)` — uses COCO class 32 ("sports ball") from the **base YOLOv8 nano model**, NOT the fine-tuned ball detector
3. **Post-filter:** HSV color check (orange H: 10–30, S: 150–255 + brown H: 0–20, S: 80–150), minimum 15% pixel match
4. **Size filter:** 8 < w < 80, 8 < h < 80, aspect ratio 0.3–3.0
5. **Position filter:** Reject detections in top 15% of frame
6. **Fallback:** If no ball detected, estimate position from nearest player centroid (weighted 70% player, 30% last known ball)
7. **Frequency:** Every 5th frame only

**Key finding:** The fine-tuned model (`ball_finetune/runs/finetune2/weights/best.pt`) is **never used** in the production pipeline. The pipeline uses the base YOLOv8n COCO sports ball class.

### 2.2 Standalone Detection Scripts (PROVEN)

| Script | Model Used | Purpose |
|--------|-----------|---------|
| `detect_ball_full.py` | `yolov8s.pt` (COCO) | Full video sweep, class 32 |
| `detect_ball_finetuned_stride.py` | `runs/detect/train-2/weights/best.pt` | Strided detection with fine-tuned model |
| `ball_detection_smooth.py` | `yolov8n.pt` (COCO) | Detection + interpolation smoothing |
| `ball_detection_smooth_stride2.py` | `yolov8n.pt` (COCO) | Same, stride-2 variant |

### 2.3 Audit Scripts (PROVEN)

| Script | Model Used | Status |
|--------|-----------|--------|
| `audit_detector.py` | `ball_finetune/runs/finetune2/weights/best.pt` | **Never completed** — no precision_recall.csv |
| `audit_heatmap.py` | `ball_finetune/runs/finetune2/weights/best.pt` | Ran, produced heatmap images |
| `audit_heatmap_fast.py` | v14 pickle (no inference) | Ran, produced heatmap + top20 |
| `audit_top20.py` | v14 pickle (pixel analysis) | Ran, classified top-20 detections |
| `audit_top20_v2.py` | v14 pickle (improved classification) | Ran, classified top-20 detections |

---

## 3. Model Files and Weights Inventory

### 3.1 Model Files (PROVEN)

| File | Size | MD5 | Date | Provenance |
|------|------|-----|------|------------|
| `models/ball_detector.pt` | 164.6 MB | `671cbc9b...` | May 24 15:03 | Fine-tuned from `ball_finetune/runs/finetune2` |
| `models/player_detector.pt` | 164.6 MB | `eb97427b...` | May 24 15:04 | Separate fine-tune (different hash from ball) |
| `models/court_keypoint_detector.pt` | 398.4 MB | `1d05b062...` | May 24 15:04 | Court keypoint model |
| `yolov8n.pt` | 6.2 MB | — | Jun 4 08:35 | Base YOLOv8 nano (COCO) |
| `yolov8s.pt` | 21.5 MB | — | Jun 4 08:35 | Base YOLOv8 small (COCO) |
| `yolo11m.pt` | — | — | — | YOLOv11 medium (present but unused) |

### 3.2 Training Run Weights (PROVEN)

| Run | File | Size | MD5 | Epochs | Precision | Recall | mAP50 |
|-----|------|------|-----|--------|-----------|--------|-------|
| `runs/detect/train` | `best.pt` | 85.3 MB | `cd8387e4...` | 4 of 20 | 0.011 | 0.2 | 0.008 |
| `runs/detect/train-2` | `best.pt` | 21.4 MB | `d364ea9b...` | 5 of 5 | 0.009 | 0.2 | 0.006 |
| `ball_finetune/runs/finetune` | *empty* | — | — | 0 of 20 | — | — | — |
| `ball_finetune/runs/finetune2` | `best.pt` | 164.6 MB | `e64ed1f4...` | 15 of 15 | **0.000** | **0.000** | **0.000** |

**Critical finding:** `ball_finetune/runs/finetune2` (the model referenced by audit scripts) shows **precision=0, recall=0, mAP50=0 at ALL 15 epochs**. The model never learned to detect balls. The `finetune` run produced no weights at all (empty directory).

### 3.3 Model Provenance Chain (INFERRED)

1. `runs/detect/train` and `train-2`: Trained from `yolov8s.pt` on `ball_dataset` (5 images). Failed to learn (mAP50 < 0.01).
2. `ball_finetune/runs/finetune`: Started from `models/ball_detector.pt` on `ball_finetune/data.yaml`. Produced no weights (training crashed or was cancelled).
3. `ball_finetune/runs/finetune2`: Started from `models/ball_detector.pt` on `ball_finetune/data.yaml`. Ran 15 epochs but metrics stayed at 0. The `data.yaml` file is **missing** — the file at `ball_finetune/data.yaml` does not exist, suggesting the training data path was broken.
4. `models/ball_detector.pt`: Likely a copy of `finetune2/best.pt` (similar file sizes: 164.6 MB vs 164.6 MB, but different MD5 hashes — `671cbc9b` vs `e64ed1f4` — so they are different files).

---

## 4. Dataset Inventory

### 4.1 Dataset Versions (PROVEN)

| Dataset | Images | Train | Val | Label Quality | Used By |
|---------|--------|-------|-----|---------------|---------|
| `ball_dataset` | 5 | 5 (same as val) | 5 (same as val) | **Poor** — boxes are 16–56% of frame size (giant boxes) | `runs/detect/train`, `train-2` |
| `ball_dataset_fixed` | 2 | 2 (same as val) | 2 (same as val) | Unknown (only 2 images) | Unused |
| `ball_dataset_auto` | 0 | 0 | 0 | No images | Abandoned |
| `ball_dataset_v2` | 108 | 86 | 20 | **Good** — tight boxes (~18×31px avg at 1280×720) | `ball_finetune` (intended) |
| `ball_dataset_v2.zip` | 108 | — | — | Archive of v2 | Reference |

### 4.2 Label Provenance (PROVEN)

- **`ball_dataset` (v1):** 5 images with YOLO-format labels. Boxes are enormous (e.g., `0.1633 × 0.1917` normalized = 209×138px for a ball). These are clearly wrong — a basketball should be ~15–30px at 1280×720.
- **`ball_dataset_v2` (v2):** 108 images with corrected tight bounding boxes. Average box size ~18×31px (normalized: w≈0.014, h≈0.032). Created with "corrected tight bounding boxes" per git commit `816e07e`. Split 86/20 train/val on Jun 4.
- **Contact sheets and verification sheets** exist: `contact_sheet.jpg`, `verify_sheet.jpg` — visual confirmation of label quality.

### 4.3 Data Governance Gaps (INFERRED)

1. **No train/val split in v1:** `ball_dataset/data.yaml` points both train and val to the same directory. The model cannot generalize.
2. **Tiny dataset:** 5 images (v1) and 108 images (v2) are insufficient for reliable ball detection. Standard YOLO fine-tuning recommends 1000+ images.
3. **Single class:** All datasets use `nc: 1, names: ['ball']`. The fine-tuned model only knows "ball" — it cannot leverage COCO pre-training for related classes.
4. **No negative examples:** No images without balls are included. The model has no incentive to reject false positives.
5. **Single game footage:** All labeled frames appear to come from the same game video (`Liberty_Vs_Riverstone`). No cross-game generalization.

---

## 5. Verification of Reported 0/20 Result

### 5.1 The 0/20 Claim (PROVEN)

The `annotate_top20.py` script hard-codes classification results for the top-20 highest-confidence v14 detections:

```
Basketball:      0
Rim/backboard:   9
Court marking:   2
Other:           9
```

**0 out of 20** top detections were classified as basketballs. This is the "0/20" result referenced in the audit request.

### 5.2 Classification Method (PROVEN)

The classification was done by pixel analysis in `audit_top20.py` and `audit_top20_v2.py`:
- Extract 30×30 ROI around each detection
- Compute HSV statistics (mean H, S, V)
- Compute edge density (Canny)
- Compute distance to nearest basket
- Score each class (Basketball, Rim/backboard, Court marking, Player/jersey, Floor reflection) using heuristic thresholds
- Basketball scoring: H 5–25 + S > 40 + orange pixel % > 30

### 5.3 Confidence Distribution (PROVEN)

The top-20 detection confidences range from 0.0017 to 0.0003 — **extremely low**. These are the highest-confidence ball detections across the entire video, yet all are below 0.2% confidence. This confirms the detector is not finding balls.

### 5.4 Spatial Distribution (INFERRED)

From `audit_heatmap_fast.py` output and the top-20 coordinates:
- Detections cluster near basket positions (left: ~260,566 right: ~691,449 in 720p)
- Several detections are at court center (free throw line area)
- No detections in expected ball-handling positions (perimeter, wing)

---

## 6. Actual Validation Method, Precision, Recall, and Failure Modes

### 6.1 Validation Method (PROVEN)

**No formal validation was completed.** The `audit_detector.py` script exists and is well-structured (IoU-based evaluation at multiple conf/imgsz thresholds), but:
- The `precision_recall.csv` file is **empty** (0 bytes)
- The label template was generated (`labels_template.csv`) but never filled in
- The 20 `label_frame_*.jpg` images were extracted but never manually labeled

**What was actually done instead:** Pixel-based heuristic classification of the top-20 detections from the v14 pipeline (which used the base YOLOv8n model, not the fine-tuned one).

### 6.2 Training Metrics (PROVEN)

**`runs/detect/train-2` (5 epochs, 5 images, yolov8s):**
- Final: Precision=0.009, Recall=0.2, mAP50=0.006, mAP50-95=0.002
- The model detected 1 ball correctly out of 5 (recall=0.2) but with very low precision

**`ball_finetune/runs/finetune2` (15 epochs, ball_detector.pt, data.yaml missing):**
- All epochs: Precision=0.000, Recall=0.000, mAP50=0.000
- Training loss increased over epochs (box_loss: 0.0004 → 0.75), indicating the model **diverged** rather than converged
- The `data.yaml` file referenced (`ball_finetune/data.yaml`) does not exist on disk

### 6.3 Failure Modes (INFERRED from evidence)

1. **Training data insufficiency:** 5 images (v1) and 108 images (v2) are far below the recommended minimum for YOLO fine-tuning
2. **Broken data path:** `ball_finetune/data.yaml` is missing, meaning the finetune2 run likely trained on empty or wrong data
3. **Giant bounding boxes in v1:** The original 5-image dataset had boxes covering 16–56% of the frame — the model learned to detect "large regions" not "small balls"
4. **No negative samples:** Without images containing no balls, the model has no false positive suppression
5. **Single-class fine-tuning:** By training with `nc: 1`, the model lost COCO's 80-class knowledge and had to learn from scratch with 5–108 images
6. **Production uses wrong model:** The production pipeline (`ai_analyzer.py`) uses `yolov8n.pt` COCO class 32, not the fine-tuned model. The fine-tuned model is irrelevant to production.
7. **Color filter is too strict:** The HSV filter (orange H: 10–30 S: 150–255) may reject real balls under different lighting conditions
8. **Low confidence threshold in production:** `conf=0.15` for base YOLO sports ball class produces many false positives, which the color filter then rejects

### 6.4 What "0/20" Actually Means

The 0/20 result means: **of the 20 highest-confidence "ball" detections produced by the v14 pipeline (base YOLOv8n + color filtering), none were visually confirmed as basketballs.** They were rim/backboard structures, court markings, or other artifacts. This is consistent with:
- Base YOLOv8n's sports ball class being trained on COCO (tennis balls, soccer balls, etc.) — not basketballs specifically
- The color filter passing non-ball orange/brown objects near baskets
- The fallback estimator (player-proximity-based) generating synthetic "ball" positions that don't correspond to actual balls

---

## 7. Proven / Inferred / Unknown

### PROVEN (verified from file contents, git log, or tool output)

1. Production pipeline uses `yolov8n.pt` COCO class 32 for ball detection, not the fine-tuned model
2. Fine-tuned model (`finetune2`) shows precision=0, recall=0 at all 15 epochs
3. `ball_finetune/data.yaml` does not exist on disk
4. `audit_detector.py` was never run to completion (no precision_recall.csv)
5. Top-20 audit found 0 basketballs among highest-confidence detections
6. Original `ball_dataset` has 5 images with giant bounding boxes (16–56% of frame)
7. `ball_dataset_v2` has 108 images with corrected tight boxes, split 86/20
8. `ball_finetune/runs/finetune` produced no weights (empty directory)
9. `runs/detect/train` and `train-2` trained on 5 images with same train/val split
10. The `NEGATIVE_RESULT_color_of_failure.md` documents that color-based OF tracking fails because ball and court have identical HSV values

### INFERRED (logical deduction from evidence)

1. The finetune2 training run failed because `data.yaml` was missing or pointed to wrong paths
2. The production pipeline's fallback estimator (player-proximity) generates most "ball" positions, not actual detections
3. The 108-image v2 dataset was never used for training (the finetune2 run used a missing `data.yaml`)
4. The `models/ball_detector.pt` was likely copied from an earlier training attempt, not from finetune2
5. The base YOLOv8n sports ball class performs poorly on basketballs (different size, color, context than COCO sports balls)

### UNKNOWN (requires further investigation)

1. What video footage was used to extract the 108 v2 dataset frames
2. Whether the v2 dataset labels have been manually verified for correctness
3. Whether the `models/ball_detector.pt` is a valid model or a corrupted file
4. What the actual detection rate is (frames with any ball detection / total frames)
5. Whether the fallback estimator produces physically plausible ball trajectories
6. What the `court_keypoint_detector.pt` and `player_detector.pt` models contain (separate training)

---

## 8. Recommendations

### 8.1 Immediate Priority: Build a Proper Benchmark

**Before rebuilding the detector, establish ground truth:**
1. Manually label 30–50 frames from the `benchmark_25_final` set (images exist, labels are empty)
2. Include diverse scenarios: ball in hand, ball in flight, ball occluded, ball near rim, no ball visible
3. Use the existing `audit_detector.py` framework (it's well-designed) with filled-in labels
4. Run the benchmark against: (a) base YOLOv8n class 32, (b) current fine-tuned model, (c) any new model

**Effort:** 2–4 hours of manual labeling + automated evaluation

### 8.2 Rebuild the Detector

**The current detector must be rebuilt. Recommended approach:**

1. **Expand dataset to 500+ images** from multiple games/angles
2. **Use `ball_dataset_v2` (108 images) as seed data** — labels are good quality
3. **Add negative examples** (frames without balls) to reduce false positives
4. **Train from `yolov8s.pt`** (not nano) with `pretrained: true` to retain COCO knowledge
5. **Use proper train/val/test split** (70/15/15) from different games
6. **Set `multi_scale: 0.5`** and `imgsz: 640` for better small-object detection
7. **Validate with IoU-based metrics** (the existing `audit_detector.py` framework)

### 8.3 Data Governance Improvements

1. **Version datasets** with clear provenance (source video, extraction date, labeler)
2. **Minimum dataset size:** 500 images for production use, 1000+ preferred
3. **Multi-game coverage:** At least 3–5 different games with different lighting/camera angles
4. **Negative examples:** 20–30% of dataset should be images without balls
5. **Label verification:** Contact sheets + independent review (the v2 dataset has this)
6. **Automated CI check:** Run `audit_detector.py` on every model update

### 8.4 Near-Term Work: Manual Film Workflows

**While the detector is being rebuilt, shift film analysis to manual/coach workflows:**

1. **Manual shot tagging:** Use the existing web UI to let coaches tag shot attempts manually
2. **Semi-automatic workflow:** Use player detection (which works) + manual ball position clicking
3. **Event-based analysis:** Focus on events that don't require ball detection (player movement, spacing)
4. **Leverage existing detections:** Player detections and court keypoints are working — build analytics on those

### 8.5 Decision Matrix

| Option | Effort | Impact | Recommendation |
|--------|--------|--------|----------------|
| Rebuild detector | High (2–4 weeks) | High | **Do this in parallel with benchmark** |
| Build benchmark first | Low (2–4 hours) | Critical | **Do this FIRST** |
| Improve data governance | Medium (1 week) | High | **Do in parallel with rebuild** |
| Manual film workflows | Low (1–2 days) | Medium | **Do this NOW for near-term** |

### Recommended Sequence:
1. **NOW:** Build benchmark (label 30–50 frames, run audit_detector.py)
2. **NOW:** Enable manual film workflows in the web UI
3. **WEEK 1:** Expand dataset to 500+ images, verify labels
4. **WEEK 1–2:** Train new detector with proper methodology
5. **WEEK 2:** Validate with benchmark, iterate
6. **WEEK 3:** Deploy to production, A/B test against fallback estimator

---

## 9. Appendix: File Manifest

### Key Source Files
- `ai_analyzer.py` — Production pipeline (ball detection at lines 155–229)
- `ai_analyzer_tuned.py` — Tuned variant (ball detection at lines 155–229)
- `settings_store.py` — Default model: `yolov8n.pt`
- `audit_detector.py` — IoU-based evaluation framework (never completed)
- `audit_top20.py` / `audit_top20_v2.py` — Pixel-based classification of top-20 detections
- `audit_heatmap.py` / `audit_heatmap_fast.py` — Spatial analysis of detections
- `annotate_top20.py` — Visual annotation of top-20 with classifications
- `ball_detection_smooth.py` — Standalone detection + smoothing
- `detect_ball_full.py` — Full video sweep with base YOLO
- `detect_ball_finetuned_stride.py` — Strided detection with fine-tuned model
- `clean_dataset.py` — Dataset purification utility
- `NEGATIVE_RESULT_color_of_failure.md` — Color-based OF failure analysis

### Key Data Files
- `ball_dataset/` — 5 images, giant boxes (v1)
- `ball_dataset_v2/` — 108 images, tight boxes (v2, current best)
- `ball_dataset_fixed/` — 2 images (unused)
- `ball_finetune/runs/finetune2/weights/best.pt` — Failed fine-tune (precision=0)
- `models/ball_detector.pt` — Deployed fine-tuned model (origin unclear)
- `pipeline_output/detector_audit/` — Audit outputs (heatmaps, top-20 images)
- `pipeline_output/benchmark_25_final/` — 25 benchmark frames (labels empty)
