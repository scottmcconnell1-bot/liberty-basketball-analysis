VETTED by Claude Code, 2026-11-02: v3 checked - gate 2 at keep_ball_detections.py 1109-1118 read this session; agreement 3279/3800 = 0.8629 from d2_train/test2/candidates.json; best_basketball.pt tensors torch.equal to best.pt, names only; flag default = today; step 1 not rerun; step 0 rerun with flag must be 29/0; pass unchanged; one valid try then gate 3. Claude Code restored the title/From lines Hermes dropped and removed the stale no-code-change words. Muse to check.
D2 TRAIN JOB SPEC v3 - trained, test run once: FAIL (29 right, 5 misses called makes) - stopped for Scott

# Stage D2 Train Job: Fine-tune Ball Detector v6 on Scott's 514 Labels

From: `.team/specs/21_d2_plan.md` sections 3-6 (VETTED), `.team/specs/22_d2_label_job_spec.md` (VETTED), `AUTHORITY.md`, `AGENT_OPERATIONAL_PROTOCOL.md`, Scott 2026-11-02 "Go" (gate 2) and "Fix name, rerun test".

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
- `workers: 2` (as v6)
- Augmentation: ultralytics defaults (no reason to change)

**Project / name (explicit, outside repo):**
- `project: Liberty_Shot_Outputs/d2_train/runs`
- `name: d2v1`
- New weights land at `Liberty_Shot_Outputs/d2_train/runs/d2v1/weights/best.pt` — **never copied to `models/`**.

**Training command (Python312):**
```bash
C:/Users/scott/AppData/Local/Programs/Python/Python312/python.exe -c "
from ultralytics import YOLO
model = YOLO('C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt')
model.train(
    data='C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/ds/data.yaml',
    imgsz=640, batch=16, freeze=10, single_cls=True,
    device=0, seed=42, deterministic=True,
    epochs=30, patience=10, workers=2,
    project='C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/runs',
    name='d2v1', exist_ok=False
)"
```
`data.yaml` written by the build script with absolute paths, names {0: basketball}.

**Production gate unchanged:** `models/ball_detector.pt` and `ball_confidence 0.28` stay as they are (Scott gates per `AUTHORITY.md` lines 23, 17; Golden Rule 1: No Loosening).

**Training environment:** `C:/Users/scott/AppData/Local/Programs/Python/Python312/python.exe` (torch 2.11.0+cu128, cuda True, ultralytics 8.4.99). Repo venv (`.venv`, torch 2.14.1+cpu) is NOT used for training.

**Class-name fact (recorded for future runs):** With `single_cls: true`, ultralytics names the class `'item'` instead of `'basketball'`. The test run used `best_basketball.pt` (the d2v1 `best.pt` with `names` dict changed to `{0: 'basketball'}` only; every weight tensor identical by `torch.equal` on all `state_dict` keys). **Future runs: use `single_cls: false` (data is already one class) to avoid the rename.**

---

## 4. The One Test (rerun D1 script with new weights)

**Interpreter:** D1 step 1 (extract) ran on the repo venv at `C:/Users/scott/Documents/liberty-basketball-analysis/.venv/Scripts/python.exe` (spec 19 line 120). The D2 test uses the SAME venv for both steps, so only the weights change. Python312 is for training and val metrics only.

**Step 0 — proof the test path is unchanged (before training):**
Run step 2 with the venv on D1's own `C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json`, writing to `d2_train/test/d1_repeat_results.json` and `d1_repeat_report.md`. It must give `makes_right 29` and `misses_called_makes 0`; if not, stop for Scott.

**Two steps (Windows paths, both run with the repo venv):**

Step 1 — extract with new weights:
```bash
C:/Users/scott/Documents/liberty-basketball-analysis/.venv/Scripts/python.exe .team/shot_detectors/keep_ball_detections.py --step extract --v6-weights "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/runs/d2v1/weights/best.pt" --tracks-dir "C:/Users/scott/AppData/Local/Temp" --out-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test/candidates.json"
```

Step 2 — arc-rule-report (produces makes_right and misses_called_makes):
```bash
C:/Users/scott/Documents/liberty-basketball-analysis/.venv/Scripts/python.exe .team/shot_detectors/keep_ball_detections.py --step arc-rule-report --candidates-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test/candidates.json" --tracks-dir "C:/Users/scott/AppData/Local/Temp" --out-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test/d2_results.json" --out-md "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test/d2_test_report.md"
```

**Nothing else changed:** confidence 0.28, D1 crop zone, 140 shots, rule as D1 (Stage A copy all switches OFF).

**Mapping check (keep_ball_detections.py lines 43, 1080-1087, 1109-1118):** Step 1 compares every saved v6 ball point with the model's raw detections and exits (SystemExit) when fewer than 90% match (MAPPING_MIN_MATCH_RATE 0.90). It writes `candidates.json` BEFORE that exit (line 1078 area). The frame mapping itself was proven with v6 on this same unchanged code: D1 `candidates.json` mapping_check = 3798/3800 = 0.9995. With new weights the rate measures agreement with v6, not mapping. Rule: record the rate in the report as "agreement with v6 ball points"; if step 1 exits only because of that gate and `candidates.json` was written, go on to step 2 (with the small fix below); any other error stops for Scott.

**Small fix (the only code change; default behaviour unchanged):**
Add an optional argument `--mapping-proof-json` to `--step arc-rule-report` in `keep_ball_detections.py`. When it is NOT given, behaviour is exactly today's (lines 1109-1118 gate reads the rate from the candidates file and requires >= 0.90). When given (D1's own `C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json`):
- The gate reads the rate from THAT file and must be >= 0.90 (it is 3798/3800).
- The proof file and the new candidates.json must have identical `constants` and identical `n_shots` and the same set of `(film, t)` shots, else stop.
- The new file's rate is printed and written to the results JSON as `"agreement_with_v6"` (not a gate).
Nothing else in the file changes: no cutoff, zone, confidence, cap, arc or rule number.

**Pass criteria (hard gate):**
- `makes_right > 29` (D1 achieved 29)
- `misses_called_makes == 0` (D1 achieved 0)

`makes_right` and `misses_called_makes` come from step 2's `d2_results.json`.

**One try, then stop for Scott (gate 3).** No tuning, no retry.

---

## 5. Tests for the Fix (in keep_ball_detections test file)

1. Without the flag, a candidates.json with mapping_check.rate < 0.90 still stops at the gate (lines 1109-1118).
2. With a good proof file (rate >= 0.90, identical constants, n_shots, shot set), a candidates.json with rate < 0.90 goes on and `agreement_with_v6` is written to the results JSON.
3. With a proof file whose rate is below 0.90, the gate stops (proof file must pass its own gate).
4. With a proof file that has different constants, or different n_shots, or different (film, t) set, the step stops.

---

## 6. Test Commands

**Step 1 is NOT rerun** (test2/candidates.json from best_basketball.pt is used as is).

**Step 2:**
```bash
C:/Users/scott/Documents/liberty-basketball-analysis/.venv/Scripts/python.exe .team/shot_detectors/keep_ball_detections.py --step arc-rule-report --candidates-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test2/candidates.json" --mapping-proof-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json" --tracks-dir "C:/Users/scott/AppData/Local/Temp" --out-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test2/d2_results.json" --out-md "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test2/d2_test_report.md"
```

**Also rerun step 0 with the flag** (D1 candidates as both files) and it must still give 29 / 0:
```bash
C:/Users/scott/Documents/liberty-basketball-analysis/.venv/Scripts/python.exe .team/shot_detectors/keep_ball_detections.py --step arc-rule-report --candidates-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json" --mapping-proof-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json" --tracks-dir "C:/Users/scott/AppData/Local/Temp" --out-json "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test2/d1_repeat_results.json" --out-md "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/test2/d1_repeat_report.md"
```

**Pass unchanged:** `makes_right > 29` AND `misses_called_makes == 0`. This is the one valid try; then Scott (gate 3).

---

## 7. Report to Write

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

**Val metrics (both by Python312):**
```bash
C:/Users/scott/AppData/Local/Programs/Python/Python312/python.exe -c "
from ultralytics import YOLO
model = YOLO('C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt')
metrics = model.val(data='C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train/ds/data.yaml', split='val', imgsz=640, batch=16, device=0)
print('v6 val:', metrics.box.mp, metrics.box.mr, metrics.box.map50)
"
```
Then same with d2v1 weights.

**Additional rows in report:**
- Step 0 result: `makes_right`, `misses_called_makes` from `d1_repeat_results.json` (must be 29 / 0).
- Step 1 agreement rate: from `candidates.json` mapping_check.rate, labeled "agreement with v6 ball points".
- Step 2 `agreement_with_v6` from results JSON.

Wall time: total training + test seconds.

---

## 8. Live Play Note (restated)

"In play" (actively in play during the game, not warmup/breaks/off-court) is decided **after detection**, not by this model. Out of scope here; a later plan handles it.

---

## 9. Tests the Build Script Needs (no GPU, no video)

1. Box conversion correct for standard crops (520×440) and edge crops (e.g. 520×389).
2. No-ball frame → empty label file written.
3. Split never shares a window between train and val.
4. Split reproducible: running twice with seed 42 produces identical `split.json`.
5. Refuses any crop name not from the 7 films in §1.
6. Refuses to run if output folder `d2_train/ds/` is not empty.

---

## 10. Stops

- Any check in §9 fails → stop and report.
- No training without this spec **VETTED by Claude Code** and **AGREE from Muse**.
- Gate 3 (Scott) required before new model used anywhere.

---

## 11. Files

- Build script: `.team/shot_detectors/d2_build_dataset.py`
- Build script test: `.team/shot_detectors/test_d2_build_dataset.py`
- Train/val runner: `.team/shot_detectors/d2_train.py` (writes the report)
- `keep_ball_detections.py` (the `--mapping-proof-json` flag only)
- `test_keep_ball_detections.py` (tests for the fix)

Written by Claude Code, checked by Hermes and Muse before anything runs. No other repo file changes.