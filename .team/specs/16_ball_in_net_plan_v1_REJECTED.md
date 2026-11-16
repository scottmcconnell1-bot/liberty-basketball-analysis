REJECTED by Claude Code, 2026-10-29 (v1): the idea and the scope are right (existing detector, net box, 0 real misses bar, no protected file, outputs outside the repo). Three things must change. Checked by reading ai_analyzer.py:33-52 and :363, settings_store.py:13, net_detector.py:459-470.
1. Ball size (section 6 step 3). Production runs the detector on the WHOLE frame at imgsz=640 (ai_analyzer.py:363), so on the 1280x720 and 1920x1080 films it sees the ball at half or a third of its size. Upscaling a ~60 px net box to 640 makes the ball roughly ten times bigger than anything the detector is used to, so a miss or a hit would say nothing about the detector. Fix: (a) main column = a native-resolution square window centred on the net box (640x640 clamped to the frame, no resizing, imgsz=640); (b) second column = the full frame at imgsz=640, exactly as production runs it. In both, keep only detections whose box centre is inside the net box and below hoop_y. Report both columns; the 0-misses bar applies to each separately. No upscaling.
2. Confidence (sections 2, 6, 10). The plan hard-codes 0.25. settings_store.py:13 holds the default 0.25, but the program can save another value. Say where the script reads the setting (read-only), or state that the default 0.25 is used and why. Either way it is never lowered.
3. Front-of-rim risk. From this camera angle a miss that drops just in front of or behind the rim lands inside the net box in the picture. State this risk, and write a crop for EVERY real miss the check fires on (not only the 10 review misses), so Scott can see why it fired.
Everything else can stay.

PLAN - NOT BUILT OR MEASURED YET

---

# Ball In Net Plan â€” Task 1 Step 4: Existing Ball Detector on Net Box Read-Only Measurement

**Author:** Hermes (Architect)  
**Date:** 2026-10-29  
**Status:** Plan for Vetted implementation  
**Gate:** Must pass Vetter review before Cursor implements

---

## 1. Purpose

Plan 15 (net_check, colour-counting in the net box) **FAILED**: at delta_ratio â‰¥ 0.08 it caught 8/19 missed makes but fired on 22/93 real misses (10 even at 0.12), and only saw 7/28 correct makes. Scott: "yes drop color-counting."

The next idea (Scott-approved): in the review photos the ball is clearly visible inside the net on missed makes (e.g., missed_make_08, Adrian t=342800, ball in the net, no tracker point). **Run the EXISTING ball detector (`models/ball_detector.pt`, as-is) only on the net box under the rim** (`net_detector._net_box` region, or a crop around it) for the few frames after the ball reaches the rim, and ask: "is a ball detected inside the net box?"

---

## 2. Scope

- **Read-only measurement only.** No edits to `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, or any protected core file.
- **No cutoff changes.** The production `ball_confidence` (default 0.25) stays exactly as it is. The detector's confidence setting is **NOT changed** (Scott gate; no looser cutoffs). If the detector needs a crop upscaled to see the ball, say so and why; report detector confidence values as measured, but the summary uses the existing confidence setting only.
- **New code only** in `.team/shot_detectors/pixel_miss/` (one new file: `ball_in_net.py` and `README.md`).
- **Measured on the same 140 tagged shots** (Notus A1 Q1: 31, Adrian Q1â€“Q3: 109).
- **Output** written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\` (outside repo).
- **Sandbox test run** writes to `.team/shot_outputs_test/ball_in_net/` (never committed).
- **Crops for the 39 review shots** with the net box and any ball box drawn, so Scott can see what it saw.

---

## 3. How the Existing Ball Detector Is Loaded and Called

From `ai_analyzer.py:33-52` and `ai_analyzer.py:125,139`:

```python
def ball_detector_settings(ai_settings):
    class_id = int(ai_settings.get("ball_class_id", AI_DEFAULTS["ball_class_id"]))  # 0
    confidence = float(ai_settings.get("ball_confidence", AI_DEFAULTS["ball_confidence"]))  # 0.25
    return resolve_ball_detector_model(ai_settings), class_id, max(0.01, min(confidence, 0.99))

# In run_ai_analysis:
ball_model_path, ball_class_id, ball_confidence = ball_detector_settings(ai_settings)
ball_model = model if ball_model_path == person_model_path else YOLO(ball_model_path)
```

The production model is `models/ball_detector.pt` (class 0 = Ball, confidence 0.25). The detector runs on full frames during AI analysis. Here we run it **only on a crop** (the net box region).

---

## 4. Net Box Region (ROI)

From `net_detector.py:_net_box` (line 459):

```python
def _net_box(shape, hoop, rim_r: float | None) -> tuple[int, int, int, int] | None:
    h, w = int(shape[0]), int(shape[1])
    x, y = float(hoop[0]), float(hoop[1])
    r = float(rim_r or 28.0)
    x0 = int(max(0, min(w - 2, x - r * 1.1)))
    x1 = int(max(x0 + 2, min(w, x + r * 1.1)))
    y0 = int(max(0, min(h - 2, y + r * 0.25)))
    y1 = int(max(y0 + 2, min(h, y + r * 2.8)))
    if x1 - x0 < 4 or y1 - y0 < 6:
        return None
    return x0, y0, x1, y1
```

- **x-range:** `hoop_x Â± 1.1 Ã— rim_r` (width â‰ˆ `2.2 Ã— rim_r`)
- **y-range:** `hoop_y + 0.25 Ã— rim_r` to `hoop_y + 2.8 Ã— rim_r` (height â‰ˆ `2.55 Ã— rim_r`)
- `rim_r = hoop_w / 2` (from the hoop track)

**What "inside the net" means:** A ball detection whose **box centre** falls inside this net box **and** whose centre y > `hoop_y` (below the rim).

---

## 5. Frames to Sample

Let **peak_frame** = the absolute video frame where the ball *reaches the rim* (same logic as Plan 15 and `measure_net_moved.py:peak_from_track`):

- For shots **with a crossing** (from `v6_tracks.json`): the crossing frame (ball goes from above to below `hoop_y` within 0.55 Ã— `hoop_w`).
- For shots **without a crossing** (`no_valid_crossing`): the frame of the closest ball point to `(hoop_x, hoop_y)` in the saved track (same as `peak_from_track` logic).

Sample **6 frames after the peak frame**: `peak_frame + 1, +2, +3, +4, +5, +6`.

**Rationale:** The ball passes through the rim and enters the net in ~1â€“3 frames at 25 fps. Sampling 6 frames after peak captures the ball in the net before the tracker loses it or jumps away. The ball may linger in the net for a few frames on a made shot; on a miss it falls through faster.

---

## 6. Running the Ball Detector on the Net Box Crop

For each sampled frame:

1. Read the full frame from the video.
2. Crop to the net box ROI (`x0, y0, x1, y1` from `_net_box`).
3. **If the crop is smaller than the detector's training input size (640Ã—640 for YOLOv8), upscale it** to at least 640 on the short side (maintain aspect ratio). The ball in the net is small (~20â€“40 px); upscaling gives the detector enough pixels to see it. Report the upscale factor used.
4. Run `ball_model.predict(crop, conf=ball_confidence, classes=[ball_class_id], verbose=False)` â€” **using the production `ball_confidence` (0.25) and class 0**.
5. For each detection: compute the box centre in **original image coordinates** (`cx = x0 + det_x + det_w/2`, `cy = y0 + det_y + det_h/2`).
6. **Decision per frame:** "ball in net" = **any detection with centre inside the net box AND `cy > hoop_y`**.

---

## 7. Measurement Protocol

| Set | Shots | Purpose |
|-----|-------|---------|
| **Build (tagged, used for tuning)** | Notus A1 Q1 (31) + Adrian Q1â€“Q3 (109) = 140 | Measure on all 19 missed makes + 28 correct makes + 93 real misses |
| **Unseen** | **None** â€” Adrian Q4 has no tracks built | Not scored in this step; any threshold picked from these 140 shots is build-set only and is not a result until checked on unseen shots (Plan 13's open question to Scott) |

Run the check on **every shot in the build set** (140 shots). Report:

### For the 19 missed makes:
- How many have **â‰¥1 frame with "ball in net" = True** (caught)
- Per-shot: list of frames where detected, detection confidence, box centre

### For the 28 correct makes (sanity check â€” the check should catch these too):
- How many have **â‰¥1 frame with "ball in net" = True**
- Per-shot: list of frames where detected

### For the real misses (93 shots):
- How many have **â‰¥1 frame with "ball in net" = True** (**must be 0 to even consider this check**)
- Count of false fires per shot

**Success bar for even considering this check:** fires on **0 real misses**.

---

## 8. Output Files

All written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\`:

```
ball_in_net/
â”œâ”€â”€ build_results.json          # Per-shot raw measurements (140 objects)
â”œâ”€â”€ summary.md                  # Table: missed makes caught, correct makes caught, misses fired on
â”œâ”€â”€ missed_makes_detail.md      # 19 rows with frames detected, confidences
â”œâ”€â”€ correct_makes_detail.md     # 28 rows (sanity check)
â”œâ”€â”€ misses_fired_on.md          # Any misses with detections (should be empty)
â””â”€â”€ crops/                      # 39 PNGs (19 missed + 10 correct + 10 misses)
    â”œâ”€â”€ missed_make_01/
    â”‚   â””â”€â”€ ball_in_net_010.png # frame with detection (or peak+2), net box in blue, ball box in green
    â””â”€â”€ ...
```

**Crop format:** For each of the 39 review-page shots (same as `build_review_page.py` and `net_check.py`): the frame at the first detected frame (or `peak_frame + 2` if no detection), cropped to the review page's square crop (centered on hoop, size `max(hoop_w * 3, 240)`), with the net ROI box drawn in **blue** and any ball detection box drawn in **green** (with confidence text).

---

## 9. Files the Coder May Create (Only New Files)

```
.team/shot_detectors/pixel_miss/
â”œâ”€â”€ ball_in_net.py              # Main measurement script
â””â”€â”€ README.md                   # One-paragraph description + run command
```

**No config.yaml.** All constants (frame offsets, upscale min size, confidence, class_id) stay at the top of `ball_in_net.py` (no new dependency).

**No edits to existing files.** `applied_to_core` stays `false`.

---

## 10. Exact Run Command

```cmd
# Windows (Claude Code runs this with the venv)
.venv\Scripts\python.exe .team/shot_detectors/pixel_miss/ball_in_net.py --out C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net

# WSL sandbox (Cursor tests here)
python3 .team/shot_detectors/pixel_miss/ball_in_net.py --out .team/shot_outputs_test/ball_in_net
```

**WSL dependency check:** Cursor's sandbox has `python3` with `cv2` and `numpy`. **Check whether `torch` and `ultralytics` are available there** (run `python3 -c "import torch, ultralytics; print(torch.__version__, ultralytics.__version__)"`). If not available, note that the checker (Claude Code) can run the final measurement with the Windows venv which has them.

The script must:
1. Load tag files and track files (read-only).
2. For each build-set shot, compute `peak_frame` and `has_crossing` per Â§5.
3. Load the production ball detector: `YOLO('models/ball_detector.pt')` with class 0, confidence 0.25.
4. Read 6 after frames (`peak_frame + 1` through `peak_frame + 6`) from the video.
5. For each frame: crop net ROI, upscale if needed, run detector, check if any ball centre is inside net box and below `hoop_y`.
6. Write `build_results.json`, `summary.md`, `missed_makes_detail.md`, `correct_makes_detail.md`, `misses_fired_on.md`.
7. Generate crops for the 39 review-page shots.
8. Print console summary with counts.
9. **Exit. No further steps.**

---

## 11. Console Output Format

```
=== BALL IN NET SUMMARY ===
Build shots: 140
Missed makes: 19
  Caught (â‰¥1 frame with ball in net): X
  By crossing status:
    Has crossing: Y caught / 12
    No crossing:  Z caught / 7
Correct makes: 28
  Caught (â‰¥1 frame with ball in net): W   <-- sanity check
Real misses: 93
  Fired on (â‰¥1 frame with ball in net): 0   <-- MUST BE 0

Per missed make:
  missed_make_01 (notus_a1 t=64200):  detected at frames [N,N,N]  conf=[0.xx,0.xx,0.xx]  crossing=True
  ...
  missed_make_19 (adrian t=3095700):  detected at frames []  conf=[]  crossing=False

Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\build_results.json
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\summary.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\missed_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\correct_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\misses_fired_on.md
Crops: 39 PNGs in crops/
STOP â€” measurement complete, no detector changes
```

---

## 12. Verification Checklist (Coder Confirms Before Done)

- [ ] Reads `v6_tracks.json` / `v6_tracks_notus_q1.json` and tag files (read-only).
- [ ] Computes `peak_frame` per Â§5 (crossing frame or closest-ball frame).
- [ ] Samples exactly 6 after frames (`peak_frame + 1` through `peak_frame + 6`).
- [ ] Net ROI matches `net_detector.py:_net_box` (x Â± 1.1Ã—rim_r, y + 0.25Ã—rim_r to +2.8Ã—rim_r).
- [ ] Loads production ball detector: `YOLO('models/ball_detector.pt')`, class 0, confidence 0.25.
- [ ] Upscales crop to min 640 on short side if smaller; reports upscale factor.
- [ ] Runs detector on crop; maps detection centres back to image coordinates.
- [ ] "Ball in net" = detection centre inside net box AND `cy > hoop_y`.
- [ ] Outputs per-shot JSON with all frames' detection results (boxes, confidences, centres, in_net boolean).
- [ ] Reports: 19 missed makes caught count, 28 correct makes caught count, 93 misses fired-on count.
- [ ] **Asserts 0 real misses fired** (prints FAIL if not 0).
- [ ] Generates 39 crop PNGs with net ROI box (blue) and ball box (green + confidence).
- [ ] All outputs to `C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\`.
- [ ] No edits to `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, any protected file.
- [ ] `applied_to_core` stays `false`.
- [ ] No `config.yaml` created; constants at top of `ball_in_net.py`.

---

## 13. Golden Rules Compliance

| Rule | How This Plan Respects It |
|------|---------------------------|
| **No looser cutoffs** | Production `ball_confidence` (0.25) and `ball_class_id` (0) untouched. This check only measures; its threshold (â‰¥1 frame) is reported, not applied to any detector. |
| **No banned trials** | No interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter. Pure detector inference on a fixed ROI. |
| **No hard-coded results** | Measures real video frames; outputs raw detections. |
| **`applied_to_core` = false** | New file only in `.team/shot_detectors/pixel_miss/`. Core untouched. |
| **Holdouts never opened** | No unseen set in this step (Adrian Q4 has no tracks). |
| **Output outside repo** | All images/JSON to `Liberty_Shot_Outputs/`. Sandbox uses `.team/shot_outputs_test/`. |

---

## 14. Next Step (After VETTED)

This plan goes to `NEXT_TASK.md` only after the Vetter stamps it `VETTED`. The Coder (Cursor sandbox) implements `ball_in_net.py`. Results inform whether this detector can be the `net_rim_supplement.py` (Task 1 Step 4 in work order).

---

**End of Plan** â€” `.team/specs/16_ball_in_net_plan.md`
