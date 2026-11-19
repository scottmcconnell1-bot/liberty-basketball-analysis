REJECTED by Claude Code, 2026-11-02: section 4 - (a) wrong interpreter: D1 step 1 ran on the repo venv (.team/specs/19_d1_job_spec.md line 120), not Python312; (b) step extract alone gives no makes_right - D1 step 2 arc-rule-report (spec 19 line 133) is missing; (c) step 1 stops when fewer than 90% of saved v6 ball points match the model (keep_ball_detections.py lines 43, 1080-1087) - with new weights that rate is model agreement, not mapping, and the spec does not say what happens. Also missing --tracks-dir, script names, workers.

D2 TRAIN JOB SPEC v1 - nothing built

# Stage D2 Train Job: Fine-tune Ball Detector v6 on Scott's 514 Labels

From: `.team/specs/21_d2_plan.md` §§3,4,5,6 (VETTED), `.team/specs/22_d2_label_job_spec.md` (VETTED), `AUTHORITY.md`, `AGENT_OPERATIONAL_PROTOCOL.md`, Scott's gate 2 words 2026-11-02.

---

## 1. Inputs and Exclusions

**Training labels (kept):** `C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/labels_live.json` — 514 frames total from the 7 eligible films:
- HSB_H: 73 ball / 13 no-ball
- HSB_H1: 65 ball / 15 no-ball
- RIMROCK_H: 18 ball / 56 no-ball
- GARDEN_VALLEY_A: 47 ball / 12 no-ball
- IDAHO_CITY_A: 48 ball / 18 no-ball
- NOTUS_A: 54 ball / 31 no-ball
- RIVERSTONE_A: 56 ball / 8 no-ball

Rimrock is thin on ball frames (18); noted, not resampled.

**Excluded (already removed by label job, script re-checks):**
- The 86 dropped frames (warmup, halftime, breaks, off-court balls) in `labels_all.json` / `dropped.json` — never used.
- Nothing from the 140-shot build set (Notus A1 Q1, Adrian Q1–Q3).
- Nothing from holdout (20 frames: 10 Notus A1, 10 Notus A).
- Nothing from tagged unseen check shots (Adrian Q4 18 shots, Notus A1 Q2–Q4).
- The build script refuses any crop name not from the 7 films above.

**Source frames:** JPEGs in the same folder (`d2_frames/`), native crop sizes (most 520×440, edge crops smaller e.g. 520×389). `frames.json` gives film, frame_number, time_seconds, crop_box per crop.

**Label row format:** `{"frame": "<crop jpg name>", "boxes": [[x, y, w, h]] or [], "class": "basketball"}` — box is top-left origin in crop pixels.

**Live-play note:** "in play" (not warmup, breaks, off the court) is decided *after* detection, not by this model; out of scope here, a later plan.

---

## 2. Dataset Build (YOLO format, outside repo)

**Output root:** `C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/ds/`

**Box conversion:** For each label row, read the crop JPEG to get its real width W and height H. Convert each box [x, y, w, h] (top-left, crop pixels) to YOLO normalized center format:
- `xc = (x + w/2) / W`
- `yc = (y + h/2) / H`
- `nw = w / W`
- `nh = h / H`
Write one line per box: `0 xc yc nw nh` (class 0 = basketball). No-ball frame (`boxes: []`) → empty `.txt` label file (background).

**Val split — fixed before training, by window, seed 42:**
- Window definition: crops from one film whose frame numbers are within 40 of the previous crop (Pass 2 read moment-10 .. moment+30 makes near-copies).
- Group all 514 frames by (film, window). Randomly assign ~15% of windows per film to val, rest to train, using seed 42.
- Train and val **never share a window**.
- Write `split.json` recording every frame's assigned split and its window_id.

**Stop condition:** If `d2_train/ds/` is not empty before building, stop and report — never overwrite.

---

## 3. Training Config (all numbers fixed now, never changed after seeing results)

**Start weights:** v6 at `C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt` (1 class {0: 'basketball'}, 3,011,043 params).

**Hyperparameters (copied from v6's `args.yaml` unless noted):**
- `imgsz: 640`
- `batch: 16`
- `freeze: 10` (freeze backbone)
- `single_cls: true` (class 0 only)
- `device: 0` (GPU)
- `seed: 42`
- `deterministic: true`
- `epochs: 30` (small set, modest)
- `patience: 10` (small set, modest)
- Augmentation: ultralytics defaults (no reason to change)

**Project / name (explicit, outside repo):**
- `project: Liberty_Shot_Outputs/d2_train/runs`
- `name: d2v1`
- New weights land at `Liberty_Shot_Outputs/d2_train/runs/d2v1/weights/best.pt` — **never copied to `models/`**.

**Production gate unchanged:** `models/ball_detector.pt` and `ball_confidence 0.28` stay as they are (Scott gates per `AUTHORITY.md` lines 23, 17; Golden Rule 1: No Loosening).

**Training environment:** `C:/Users/scott/AppData/Local/Programs/Python/Python312/python.exe` (torch 2.11.0+cu128, cuda True, ultralytics 8.4.99). Repo venv (`.venv`, torch 2.14.1+cpu) is NOT used for training.

---

## 4. The One Test (rerun D1 script with new weights)

**After training completes:** Run the D1 test script exactly as D1 did, only swapping the weights file.

**Command:**
```
C:/Users/scott/AppData/Local/Programs/Python/Python312/python.exe .team/shot_detectors/keep_ball_detections.py --step extract --v6-weights "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/runs/d2v1/weights/best.pt" --out-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/d2_test_results.json"
```

**Python that runs it:** D1's own GPU python at `C:/Users/scott/AppData/Local/Programs/Python/Python312/python.exe` (NOT FOUND - Claude Code to confirm this is the exact interpreter D1 used).

**Nothing else changed:** confidence 0.28, D1 crop zone, 140 shots, rule as D1 (Stage A copy all switches OFF).

**Pass criteria (hard gate):**
- `makes_right > 29` (D1 achieved 29)
- `misses_called_makes == 0` (D1 achieved 0)

**One try, then stop for Scott (gate 3).** No tuning, no retry.

---

## 5. Report to Write

After test, write `C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/d2_report.md` with:

| Metric | v6 (on same val split, measured first) | New model (d2v1) |
|--------|----------------------------------------|------------------|
| val precision | | |
| val recall | | |
| val mAP50 | | |

| D1 Test | D1 (v6) | D2 (new) |
|---------|---------|----------|
| makes_right | 29 | |
| misses_called_makes | 0 | |

Wall time: total training + test seconds.

---

## 6. Live Play Note (restated)

"In play" (actively in play during the game, not warmup/breaks/off-court) is decided **after detection**, not by this model. Out of scope here; a later plan handles it.

---

## 7. Tests the Build Script Needs (no GPU, no video)

1. Box conversion correct for standard crops (520×440) and edge crops (e.g. 520×389).
2. No-ball frame → empty label file written.
3. Split never shares a window between train and val.
4. Split reproducible: running twice with seed 42 produces identical `split.json`.
5. Refuses any crop name not from the 7 films in §1.
6. Refuses to run if output folder `d2_train/ds/` is not empty.

---

## 8. Stops

- Any check in §7 fails → stop and report.
- No training without this spec **VETTED by Claude Code** and **AGREE from Muse**.
- Gate 3 (Scott) required before new model used anywhere.