REJECTED by Claude Code, 2026-10-31: (1) section 2 names models/ball_detector.pt as BODD, but collect_q4_bodd.py line 21 uses C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt (6 MB; models/ball_detector.pt is a different 172 MB file and a Scott gate); (2) section 3 scans at stride 25 yet takes 'all consecutive frames' and 'the next 5 frames' - a stride scan cannot see those; (3) holdout distance assumes 25 fps for all films; HSB H, HSB H1 and Rimrock are 30 fps (cv2 this session); (4) hoop smoothing marked 'optional' - not fixed; (5) a file:// page cannot write labels.json into the folder; (6) crops are clamped at frame edges, so not always 520x440.

D2 LABEL JOB SPEC v1 - nothing built

# Stage D2 Label Job: Frame Picking, Labelling Page, Export

From: `.team/specs/21_d2_plan.md` (VETTED, Muse AGREE), `collect_q4_bodd.py`, `.team/shot_detectors/keep_ball_detections.py` (D1 near-hoop zone), `.team/specs/holdout_names.json`, `AUTHORITY.md`, `AGENT_OPERATIONAL_PROTOCOL.md`.

---

## 1. Source Films — exactly the 7 from 21_d2_plan.md §1

- `uploads/LIBERTY_A_v_HSB_H1_20260809_221334.mp4`
- `uploads/LIBERTY_A_v_HSB_H_20260809_221334.mp4`
- `uploads/LIBERTY_A_v_RIMROCK_H_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4` — **only frames at least 125 frames (5 seconds at 25 fps) away from any of its 10 holdout timestamps**

**Excluded entirely (no frames from these):**
- Build set: Notus A1 Q1 (`uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4`), Adrian Q1–Q3 (`uploads/nfhs_gam0a66d85e12.mp4`)
- Holdout: 10 frames each from Notus A1 and Notus A (see holdout_names.json)
- Tagged unseen check: Adrian Q4 (18 shots), Notus A1 Q2–Q4

**Notus A holdout timestamps (from holdout_names.json, ms):**
232300, 606900, 981500, 1356100, 1730700, 2105300, 2479900, 2854500, 3229100, 3603700

At 25 fps → frame numbers: 5808, 15173, 24538, 33903, 43268, 52633, 62000, 71363, 80728, 90093.
Exclusion window: ±125 frames around each.

---

## 2. Hoop Detection in Untagged, Panning Film

**Model:** BODD `models/ball_detector.pt` (path in collect_q4_bodd.py line 22: `C:\Users\scott\AppData\Local\Temp\BODD_yolov8n_0001.pt`), classes `basketball` and `hoop` (collect_q4_bodd.py lines 90–92, 172–174).

**Scan stride (fixed):** every **25 frames** (1 second at 25 fps). This keeps total decode time in hours, not days. Estimate: 7 films × ~40 min each × 25 fps = ~420k frames; stride 25 → ~16.8k BODD inferences. At ~50 ms/frame on CPU → ~14 minutes; GPU faster. Estimate.

**Per-stride step:**
1. Decode frame at stride position.
2. Run BODD at `conf=0.12, imgsz=960` (collect_q4_bodd.py line 83).
3. If any `hoop` box found: take median x,y,w,h of all hoop boxes in that frame as the hoop for that moment (collect_q4_bodd.py lines 36–46 grouping logic).
4. Record hoop (x, y, w, h) + frame number + timestamp.
5. If no hoop: skip, continue striding.

**Hoop smoothing (optional, fixed):** consecutive stride hoops within 20 px of each other are merged by median; a new hoop position starts a new segment. This handles panning without tracking.

---

## 3. Frame Pick Rule — fixed, no truth used

**Detector for picking:** v6 ball model at `C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt` (collect_q4_bodd.py line 23), class `basketball`.

**Crop:** `hoop_x ± 260`, `hoop_y - 200 .. hoop_y + 240` (collect_q4_bodd.py lines 121–124; keep_ball_detections.py lines 25–27, 195–198). `imgsz=640`, `conf=0.28` (keep_ball_detections.py line 24).

**D1 near-hoop zone (from keep_ball_detections.py lines 29–31, 166–173):**
- Horizontal: `abs(x_center - hoop_x) <= 3.0 * hoop_w`
- Vertical: `hoop_y - 4.0 * hoop_w <= y_center <= hoop_y + 300`

**Pick algorithm per film:**
1. Stride through film at the same 25-frame stride used for hoop detection.
2. At each stride where a hoop was found, run v6 on the D1 crop.
3. Collect **moments** where v6 puts a ball detection **inside the D1 near-hoop zone**.
4. From each moment, take:
   - All consecutive frames where v6 sees the ball inside the zone.
   - Plus the **next 5 frames after it loses the ball** there (where v6 fails — the "just after it loses it" frames).
5. Each such frame becomes a candidate: save the D1 crop (520×440 px JPEG) and metadata (film, frame number, time, crop box [x0,y0,x1,y1] in full-frame coords).

**Target total: 600 frames** (fixed by Scott at gate 1; 21_d2_plan.md §2 binding note).
**Split across 7 films:** 600 ÷ 7 = **85 frames per film** (85 × 7 = 595), remainder 5 → first 5 films get 86 frames each.
- If a film yields **fewer** than its quota: take all it has, distribute the shortfall evenly to the other films (recompute quotas from remaining pool).
- If a film yields **more**: take a uniform random sample (seeded) to hit its quota.

**Fixed random seed:** `42` (matches RANSAC_SEED in keep_ball_detections.py line 36).

**No ground truth used at any point.**

---

## 4. Saved Output — OUTSIDE the repo (repo is PUBLIC; film shows minors)

**Directory:** `C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/` (created by script; never committed, never uploaded, never published anywhere).

**Per-frame files:**
- `{film_stem}_fr{frame:06d}.jpg` — the D1 crop (520×440), JPEG quality 90.
- `frames.json` — array of objects:
  ```json
  {
    "film": "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4",
    "frame_number": 123456,
    "time_seconds": 4938.24,
    "crop_box": [x0, y0, x1, y1]  // full-frame pixel coordinates of the D1 crop
  }
  ```

**Exactly 600 entries in frames.json.**

---

## 5. Labelling Page — one local HTML file, no server, no internet

**Location:** `C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/label.html` (opened directly from that folder in a browser).

**Behaviour:**
- Loads `frames.json` from same folder.
- Shows **one crop at a time** (the JPEG).
- **Interaction:**
  - Drag a box on the ball → box in crop pixels (x, y, w, h).
  - Tap/click **"No ball"** button → marks frame as "no ball visible".
  - **Back** / **Next** buttons (keyboard: Left/Right arrows).
  - Progress display: `"n of 600"` (e.g. "42 of 600").
- **Labels kept in browser localStorage** (survives reload).
- **"Export labels" button** → writes `labels.json` in same folder, YOLO-ready:
  ```json
  [
    {"frame": "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4_fr001234.jpg", "boxes": [[x, y, w, h]], "class": "basketball"},
    {"frame": "LIBERTY_A_v_HSB_H1_20260809_221334.mp4_fr005678.jpg", "boxes": [], "class": "basketball"}
  ]
  ```
  - `boxes` empty = "no ball".
  - Coordinates in **crop pixels** (0..519, 0..439), top-left origin.
- **UI:** Big buttons (min 48px touch target), works on a laptop trackpad and touchscreen. No external deps (single HTML + embedded CSS/JS).

---

## 6. Tests that Prove Correctness (run as part of d2_pick_frames.py)

1. **No excluded film:** every entry's film is one of the 7 in §1.
2. **No holdout neighbours:** for every Notus A frame, `abs(frame - holdout_frame) > 125` for all 10 holdout frame numbers.
3. **Exactly 600 frames:** `len(frames.json) == 600`.
4. **Seed reproducibility:** running the picker twice with seed 42 produces identical frame lists (same film, frame_number, crop_box).
5. **Quota check:** per-film counts match the split rule in §3 (85/86 with shortfall redistribution).
6. **Zone membership:** every picked frame has at least one v6 detection inside the D1 near-hoop zone in the moment it was picked (or is within the 5-frame "just after loss" tail).

---

## 7. Stop Rule

After `d2_pick_frames.py` produces the 600 crops + `frames.json` + `label.html`, **stop for Scott to label**. No training (that is Decision 2).

---

## 8. Script to Build: `.team/shot_detectors/d2_pick_frames.py` (+ tests)

**Inputs:** the 7 film paths, BODD model path, v6 model path, holdout_names.json, output directory.
**Outputs:** 600 JPEGs, frames.json, label.html in output directory.
**Dependencies:** ultralytics, opencv-python, numpy, json, random.
**Runtime target:** hours, not days (stride 25, estimate ~30 min on CPU).

---

## 9. Values Marked Estimate / NOT FOUND

- BODD inference time per frame: **estimate** 50 ms CPU.
- Total decode+inference time for 7 films at stride 25: **estimate** 30 minutes CPU.
- Labelling time per frame: **estimate** a few seconds (21_d2_plan.md §2: "estimate about an hour at a few seconds per box").
- Frames per film if shortfall occurs: **NOT FOUND - Claude Code to check** (spec defines redistribution rule; exact numbers depend on actual yields).