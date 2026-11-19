VETTED by Claude Code, 2026-10-29 (v2, two binding notes): the 3 rejection points are fixed - two columns with no upscaling, A = 640x640 native window centred on the net box, B = full frame at imgsz=640 as ai_analyzer.py:363 (section 6); confidence read, never lowered (section 2); front-of-rim risk stated and a crop for every real miss that fires (sections 2 and 8). Checked by reading the revised plan against ai_analyzer.py:33-52 and :363, settings_store.py:13 and :87-102, net_detector.py:459-470. No protected file edited, no cutoff lowered, no banned trial, outputs outside the repo.
BINDING NOTE a (section 2, "reads this setting read-only"): saved settings live in the database, and settings_store.load_all_settings(db_path=...) opens it with a normal read-write sqlite3.connect (settings_store.py:95). Do NOT call it. Read the one saved value with a read-only URI connection (sqlite3.connect("file:<db>?mode=ro", uri=True)) on the repo's film_analysis.db; if there is no saved ball_confidence row, use the default 0.25 from settings_store.py:13. Print which value was used and where it came from.
BINDING NOTE b (section 6, Column A sentence "This matches ... the ball's apparent size in production"): that is not true. In Column A the ball is at full native size, two to three times larger than production sees it after the full frame is shrunk to 640 wide. Column B is the production scale. Report the two columns as measured; do not describe A as matching production.

PLAN - NOT BUILT OR MEASURED YET

---

# Ball In Net Plan — Task 1 Step 4: Existing Ball Detector on Net Box Read-Only Measurement

**Author:** Hermes (Architect)
**Date:** 2026-10-29
**Status:** Plan for Vetted implementation
**Gate:** Must pass Vetter review before Cursor implements

---

## 1. Purpose

Plan 15 (net_check, colour-counting in the net box) **FAILED**: at delta_ratio ≥ 0.08 it caught 8/19 missed makes but fired on 22/93 real misses (10 even at 0.12), and only saw 7/28 correct makes. Scott: "yes drop color-counting."

The next idea (Scott-approved): in the review photos the ball is clearly visible inside the net on missed makes (e.g., missed_make_08, Adrian t=342800, ball in the net, no tracker point). **Run the EXISTING ball detector (`models/ball_detector.pt`, as-is) only on the net box under the rim** (`net_detector._net_box` region, or a crop around it) for the few frames after the ball reaches the rim, and ask: "is a ball detected inside the net box?"

---

## 2. Scope

- **Read-only measurement only.** No edits to `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, or any protected core file.
- **No cutoff changes.** The production `ball_confidence` is stored in `settings_store.py:13` (default 0.25) and may be overridden by the user; the script **reads this setting read-only** via `ai_settings.get("ball_confidence", 0.25)` (same as `ai_analyzer.py:40-41`). The detector's confidence is **never lowered** from that value.
- **New code only** in `.team/shot_detectors/pixel_miss/` (one new file: `ball_in_net.py` and `README.md`).
- **Measured on the same 140 tagged shots** (Notus A1 Q1: 31, Adrian Q1–Q3: 109).
- **Output** written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\` (outside repo).
- **Sandbox test run** writes to `.team/shot_outputs_test/ball_in_net/` (never committed).
- **Crops for the 39 review shots** with the net box and any ball box drawn, so Scott can see what it saw.
- **Front-of-rim risk:** From this camera angle, a miss that drops just in front of or behind the rim lands inside the net box in the picture. **Write a crop for EVERY real miss the check fires on** (not only the 10 review misses), so Scott can see why it fired.

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

The production model is `models/ball_detector.pt` (class 0 = Ball, confidence 0.25). The detector runs on full frames during AI analysis. Here we run it on two columns as described in §6.

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

- **x-range:** `hoop_x ± 1.1 × rim_r` (width ≈ `2.2 × rim_r`)
- **y-range:** `hoop_y + 0.25 × rim_r` to `hoop_y + 2.8 × rim_r` (height ≈ `2.55 × rim_r`)
- `rim_r = hoop_w / 2` (from the hoop track)

**What "inside the net" means:** A ball detection whose **box centre** falls inside this net box **and** whose centre y > `hoop_y` (below the rim).

---

## 5. Frames to Sample

Let **peak_frame** = the absolute video frame where the ball *reaches the rim* (same logic as Plan 15 and `measure_net_moved.py:peak_from_track`):

- For shots **with a crossing** (from `v6_tracks.json`): the crossing frame (ball goes from above to below `hoop_y` within 0.55 × `hoop_w`).
- For shots **without a crossing** (`no_valid_crossing`): the frame of the closest ball point to `(hoop_x, hoop_y)` in the saved track (same as `peak_from_track` logic).

Sample **6 frames after the peak frame**: `peak_frame + 1, +2, +3, +4, +5, +6`.

**Rationale:** The ball passes through the rim and enters the net in ~1–3 frames at 25 fps. Sampling 6 frames after peak captures the ball in the net before the tracker loses it or jumps away. The ball may linger in the net for a few frames on a made shot; on a miss it falls through faster.

---

## 6. Running the Ball Detector on the Net Box — Two Columns, No Upscaling

Production runs the detector on the **whole frame at imgsz=640** (`ai_analyzer.py:363`). On 1280×720 and 1920×1080 films the ball appears at half or a third of its size. Upscaling a ~60 px net box to 640 makes the ball roughly ten times bigger than anything the detector is used to, so a miss or a hit would say nothing about the detector.

**Fix:** Run two columns, both at `imgsz=640`, no upscaling of the net box:

**Column A (native-resolution square window):** A 640×640 square window centred on the net box, clamped to the frame bounds, **no resizing**, run at `imgsz=640`. This matches the detector's native input size and the ball's apparent size in production.

**Column B (full frame, production path):** The full frame at `imgsz=640`, exactly as production runs it (`ai_analyzer.py:363`).

In **both columns**, keep only detections whose box centre is inside the net box and below `hoop_y`. Report both columns; the 0-misses bar applies to each separately.

For each sampled frame:

1. Read the full frame from the video.
2. Compute the net box ROI (`x0, y0, x1, y1` from `_net_box`).
3. **Column A:** Extract a 640×640 square centred on the net box centre (`cx = (x0+x1)/2`, `cy = (y0+y1)/2`), clamped to frame bounds. No resize. Run `ball_model.predict(window, conf=ball_confidence, classes=[ball_class_id], imgsz=640, verbose=False)`.
4. **Column B:** Run `ball_model.predict(full_frame, conf=ball_confidence, classes=[ball_class_id], imgsz=640, verbose=False)` — exactly as production.
5. For each detection in either column: compute the box centre in **original image coordinates**.
6. **Decision per frame per column:** "ball in net" = **any detection with centre inside the net box AND `cy > hoop_y`**.

---

## 7. Measurement Protocol

| Set | Shots | Purpose |
|-----|-------|---------|
| **Build (tagged, used for tuning)** | Notus A1 Q1 (31) + Adrian Q1–Q3 (109) = 140 | Measure on all 19 missed makes + 28 correct makes + 93 real misses |
| **Unseen** | **None** — Adrian Q4 has no tracks built | Not scored in this step; any threshold picked from these 140 shots is build-set only and is not a result until checked on unseen shots (Plan 13's open question to Scott) |

Run the check on **every shot in the build set** (140 shots). Report:

### For the 19 missed makes:
- How many have **≥1 frame with "ball in net" = True** (caught) — **per column**
- Per-shot: list of frames where detected, detection confidence, box centre, which column

### For the 28 correct makes (sanity check — the check should catch these too):
- How many have **≥1 frame with "ball in net" = True** — **per column**
- Per-shot: list of frames where detected

### For the real misses (93 shots):
- How many have **≥1 frame with "ball in net" = True** (**must be 0 to even consider this check**) — **per column**
- Count of false fires per shot

**Success bar for even considering this check:** fires on **0 real misses in each column**.

---

## 8. Output Files

All written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\`:

```
ball_in_net/
├── build_results.json          # Per-shot raw measurements (140 objects)
├── summary.md                  # Table: missed makes caught, correct makes caught, misses fired on (per column)
├── missed_makes_detail.md      # 19 rows with frames detected, confidences, column
├── correct_makes_detail.md     # 28 rows (sanity check)
├── misses_fired_on.md          # Any misses with detections (should be empty)
└── crops/                      # 39 PNGs + ANY real-miss crops that fired
    ├── missed_make_01/
    │   └── ball_in_net_010.png # frame with detection (or peak+2), net box in blue, ball box in green
    └── ...
```

**Crop format:** For each of the 39 review-page shots (same as `build_review_page.py` and `net_check.py`): the frame at the first detected frame (or `peak_frame + 2` if no detection), cropped to the review page's square crop (centered on hoop, size `max(hoop_w * 3, 240)`), with the net ROI box drawn in **blue** and any ball detection box drawn in **green** (with confidence text).

**Additional crops:** For **every real miss** where either column fires (≥1 frame with ball in net), write the same crop format so Scott can see why it fired.

---

## 9. Files the Coder May Create (Only New Files)

```
.team/shot_detectors/pixel_miss/
├── ball_in_net.py              # Main measurement script
└── README.md                   # One-paragraph description + run command
```

**No config.yaml.** All constants (frame offsets, window size, confidence, class_id) stay at the top of `ball_in_net.py` (no new dependency).

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
2. For each build-set shot, compute `peak_frame` and `has_crossing` per §5.
3. Load the production ball detector: `YOLO('models/ball_detector.pt')` with class 0, confidence read from settings (default 0.25).
4. Read 6 after frames (`peak_frame + 1` through `peak_frame + 6`) from the video.
5. For each frame: run both columns per §6, check if any ball centre is inside net box and below `hoop_y`.
6. Write `build_results.json`, `summary.md`, `missed_makes_detail.md`, `correct_makes_detail.md`, `misses_fired_on.md`.
7. Generate crops for the 39 review-page shots **plus any real-miss crops that fired**.
8. Print console summary with counts per column.
9. **Exit. No further steps.**

---

## 11. Console Output Format

```
=== BALL IN NET SUMMARY ===
Build shots: 140
Missed makes: 19
  Column A (640x640 window):
    Caught (≥1 frame with ball in net): X
    By crossing status:
      Has crossing: Y caught / 12
      No crossing:  Z caught / 7
  Column B (full frame):
    Caught (≥1 frame with ball in net): X'
    By crossing status:
      Has crossing: Y' caught / 12
      No crossing:  Z' caught / 7
Correct makes: 28
  Column A: Caught (≥1 frame with ball in net): W   <-- sanity check
  Column B: Caught (≥1 frame with ball in net): W'  <-- sanity check
Real misses: 93
  Column A: Fired on (≥1 frame with ball in net): 0   <-- MUST BE 0
  Column B: Fired on (≥1 frame with ball in net): 0   <-- MUST BE 0

Per missed make:
  missed_make_01 (notus_a1 t=64200):  detected at frames [N,N,N]  conf=[0.xx,0.xx,0.xx]  crossing=True  column=A,B
  ...
  missed_make_19 (adrian t=3095700):  detected at frames []  conf=[]  crossing=False

Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\build_results.json
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\summary.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\missed_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\correct_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\misses_fired_on.md
Crops: 39 PNGs in crops/ + any real-miss crops
STOP — measurement complete, no detector changes
```

---

## 12. Verification Checklist (Coder Confirms Before Done)

- [ ] Reads `v6_tracks.json` / `v6_tracks_notus_q1.json` and tag files (read-only).
- [ ] Computes `peak_frame` per §5 (crossing frame or closest-ball frame).
- [ ] Samples exactly 6 after frames (`peak_frame + 1` through `peak_frame + 6`).
- [ ] Net ROI matches `net_detector.py:_net_box` (x ± 1.1×rim_r, y + 0.25×rim_r to +2.8×rim_r).
- [ ] Loads production ball detector: `YOLO('models/ball_detector.pt')`, class 0, confidence read from `settings_store` (default 0.25).
- [ ] **Column A:** 640×640 square window centred on net box, clamped to frame, no resize, `imgsz=640`.
- [ ] **Column B:** Full frame at `imgsz=640` (production path).
- [ ] Runs detector on both columns; maps detection centres back to image coordinates.
- [ ] "Ball in net" = detection centre inside net box AND `cy > hoop_y`.
- [ ] Outputs per-shot JSON with all frames' detection results (boxes, confidences, centres, in_net boolean, column).
- [ ] Reports: 19 missed makes caught count per column, 28 correct makes caught count per column, 93 misses fired-on count per column.
- [ ] **Asserts 0 real misses fired in each column** (prints FAIL if not 0).
- [ ] Generates 39 review crop PNGs with net ROI box (blue) and ball box (green + confidence).
- [ ] **Generates crop PNGs for ANY real miss where either column fires.**
- [ ] All outputs to `C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net\`.
- [ ] No edits to `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, any protected file.
- [ ] `applied_to_core` stays `false`.
- [ ] No `config.yaml` created; constants at top of `ball_in_net.py`.

---

## 13. Golden Rules Compliance

| Rule | How This Plan Respects It |
|------|---------------------------|
| **No looser cutoffs** | Production `ball_confidence` read from settings (default 0.25) and `ball_class_id` (0) untouched. This check only measures; its threshold (≥1 frame) is reported, not applied to any detector. |
| **No banned trials** | No interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter. Pure detector inference on a fixed ROI. |
| **No hard-coded results** | Measures real video frames; outputs raw detections. |
| **`applied_to_core` = false** | New file only in `.team/shot_detectors/pixel_miss/`. Core untouched. |
| **Holdouts never opened** | No unseen set in this step (Adrian Q4 has no tracks). |
| **Output outside repo** | All images/JSON to `Liberty_Shot_Outputs/`. Sandbox uses `.team/shot_outputs_test/`. |

---

## 14. Next Step (After VETTED)

This plan goes to `NEXT_TASK.md` only after the Vetter stamps it `VETTED`. The Coder (Cursor sandbox) implements `ball_in_net.py`. Results inform whether this detector can be the `net_rim_supplement.py` (Task 1 Step 4 in work order).

---

**End of Plan** — `.team/specs/16_ball_in_net_plan.md`