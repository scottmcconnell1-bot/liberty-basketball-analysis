VETTED by Claude Code, 2026-10-31: v2 checked - BODD path matches collect_q4_bodd.py line 21; models/ball_detector.pt not read; film fps / size table matches cv2 reads this session; two-pass pick (stride 25, then moment-10..+30 sequential) with SEEN / LOST defined; quota 85/86, half SEEN half LOST, 3 frames apart, seed 42; output and page outside the repo, no publish; export to Downloads; stop before training. Binding note added in the section 1 body: holdout frames computed from holdout_names.json, not the listed numbers (two had rounding slips). Muse to check.
D2 LABEL JOB SPEC v2 - nothing built

# Stage D2 Label Job: Frame Picking, Labelling Page, Export

From: `.team/specs/21_d2_plan.md` (VETTED, Muse AGREE), `collect_q4_bodd.py`, `.team/shot_detectors/keep_ball_detections.py` (D1 near-hoop zone), `.team/specs/holdout_names.json`, `AUTHORITY.md`, `AGENT_OPERATIONAL_PROTOCOL.md`.

---

## 1. Source Films — exactly the 7 from 21_d2_plan.md §1

**Film facts (read with cv2, 2026-10-31):**

| Film | FPS | Resolution | Total Frames |
|------|-----|------------|--------------|
| HSB_H1 | 30 | 1280x720 | 102236 |
| HSB_H | 30 | 1280x720 | 111854 |
| RIMROCK_H | 30 | 1920x1080 | 162523 |
| GARDEN_VALLEY_A | 25 | 1280x720 | 196850 |
| IDAHO_CITY_A | 25 | 1280x720 | 78450 |
| RIVERSTONE_A | 25 | 1280x720 | 125750 |
| NOTUS_A | 25 | 1280x720 | 93650 |

- `uploads/LIBERTY_A_v_HSB_H1_20260809_221334.mp4`
- `uploads/LIBERTY_A_v_HSB_H_20260809_221334.mp4`
- `uploads/LIBERTY_A_v_RIMROCK_H_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4` — **only frames at least 5 seconds in that film's own fps away from any of its 10 holdout timestamps** (Notus A is 25 fps → 125 frames; keep its frame numbers)

**Excluded entirely (no frames from these):**
- Build set: Notus A1 Q1 (`uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4`), Adrian Q1–Q3 (`uploads/nfhs_gam0a66d85e12.mp4`)
- Holdout: 10 frames each from Notus A1 and Notus A (see holdout_names.json)
- Tagged unseen check: Adrian Q4 (18 shots), Notus A1 Q2–Q4

**Notus A holdout timestamps (from holdout_names.json, ms):**
232300, 606900, 981500, 1356100, 1730700, 2105300, 2479900, 2854500, 3229100, 3603700

At 25 fps → frame numbers: 5808, 15173, 24538, 33903, 43268, 52633, 62000, 71363, 80728, 90093.
Exclusion window: ±125 frames around each.

**Binding note (Claude Code, 2026-10-31):** the list above has rounding slips (round(ms x 25 / 1000) gives 5808, 15172, 24538, 33902, 43268, 52632, 61998, 71362, 80728, 90092). The script never uses the listed numbers: it reads holdout_names.json and computes each holdout frame as round(ms x fps / 1000) with the film's own fps, then keeps every training frame more than 5 x fps frames away.

---

## 2. Hoop Detection in Untagged, Panning Film

**Model:** BODD `C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt` (collect_q4_bodd.py line 21), classes `basketball` and `hoop` (collect_q4_bodd.py lines 90–92, 172–174).

**Scan stride (fixed):** every **25 frames**. This keeps total decode time in hours, not days. Estimate: 7 films × ~40 min each × 25 fps = ~420k frames; stride 25 → ~16.8k BODD inferences. At ~50 ms/frame on CPU → ~14 minutes; GPU faster. Estimate.

**Per-stride step:**
1. Decode frame at stride position.
2. Run BODD at `conf=0.12, imgsz=960` (collect_q4_bodd.py line 83).
3. If any `hoop` box found: take median x,y,w,h of all hoop boxes in that frame as the hoop for that moment (collect_q4_bodd.py lines 36–46 grouping logic).
4. Record hoop (x, y, w, h) + frame number + timestamp.
5. If no hoop: skip, continue striding.

---

## 3. Frame Pick Rule — Two Passes, Fixed

**Detector for picking:** v6 ball model at `C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt` (collect_q4_bodd.py line 23), class `basketball`.

**Crop:** `hoop_x ± 260`, `hoop_y - 200 .. hoop_y + 240` (collect_q4_bodd.py lines 121–124; keep_ball_detections.py lines 25–27, 195–198). `imgsz=640`, `conf=0.28` (keep_ball_detections.py line 24). Crops are in native pixels exactly as D1 did on the build set (Adrian is 1920x1080, Notus A1 1280x720), clamped at frame edges, saved at their real size.

**D1 near-hoop zone (from keep_ball_detections.py lines 29–31, 166–173):**
- Horizontal: `abs(x_center - hoop_x) <= 3.0 * hoop_w`
- Vertical: `hoop_y - 4.0 * hoop_w <= y_center <= hoop_y + 300`

**Pass 1 (fixed stride, find moments):**
1. Stride through film every 25 frames.
2. At each stride where a hoop was found (from §2), run v6 on the D1 crop.
3. Collect **moments** where v6 puts a ball detection **inside the D1 near-hoop zone**.
4. Record: moment frame number, hoop (x,y,w,h) for that stride.

**Pass 2 (per-moment window, sequential reads):**
For each moment from Pass 1:
1. Read frames `moment-10 .. moment+30` in order (cap.set once to moment-10, then cap.read sequentially).
2. Run v6 on the crop of each frame (same crop box as Pass 1, using the moment's hoop; no smoothing).
3. In that window a frame is **SEEN** if v6 ball is inside the D1 near-hoop zone, **LOST** if it is one of the first 8 frames after the last SEEN frame with no ball in the zone.
4. Each SEEN/LOST frame becomes a candidate: save the crop (native size, clamped at edges) and metadata (film, frame number, time, crop box [x0,y0,x1,y1] in full-frame coords).

**Target total: 600 frames** (fixed by Scott at gate 1; 21_d2_plan.md §2 binding note).

**Split across 7 films:** 600 ÷ 7 = **85 frames per film** (85 × 7 = 595), remainder 5 → first 5 films get 86 frames each.
- If a film yields **fewer** than its quota: take all it has, distribute the shortfall evenly to the other films (recompute quotas from remaining pool).
- If a film yields **more**: take a uniform random sample (seeded) to hit its quota.

**Pick from candidates, per film quota as written (85/86, shortfall rule kept):**
- Half SEEN, half LOST (if one kind runs short, fill from the other).
- At least 3 frames apart within a window.
- Seed 42.

**No ground truth used at any point.**

---

## 4. Saved Output — OUTSIDE the repo (repo is PUBLIC; film shows minors)

**Directory:** `C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/` (created by script; never committed, never uploaded, never published anywhere).

**Per-frame files:**
- `{film_stem}_fr{frame:06d}.jpg` — the D1 crop (native size, clamped at frame edges), JPEG quality 90.
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
- **"Export labels" button** → **downloads** `labels.json` to the browser's Downloads folder (file:// cannot write into the folder); the page tells Scott to move it into `d2_frames`.
  ```json
  [
    {"frame": "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4_fr001234.jpg", "boxes": [[x, y, w, h]], "class": "basketball"},
    {"frame": "LIBERTY_A_v_HSB_H1_20260809_221334.mp4_fr005678.jpg", "boxes": [], "class": "basketball"}
  ]
  ```
  - `boxes` empty = "no ball".
  - Box = `[x, y, w, h]`, top-left origin, crop pixels; `boxes` [] = no ball.
- **UI:** Big buttons (min 48px touch target), works on a laptop trackpad and touchscreen. No external deps (single HTML + embedded CSS/JS).

---

## 6. Tests that Prove Correctness (run as part of d2_pick_frames.py)

1. **No excluded film:** every entry's film is one of the 7 in §1.
2. **No holdout neighbours:** for every Notus A frame, `abs(frame - holdout_frame) > 125` for all 10 holdout frame numbers.
3. **Exactly 600 frames:** `len(frames.json) == 600`.
4. **Seed reproducibility:** running the picker twice with seed 42 produces identical frame lists (same film, frame_number, crop_box).
5. **Quota check:** per-film counts match the split rule in §3 (85/86 with shortfall redistribution).
6. **Zone membership:** every picked frame has at least one v6 detection inside the D1 near-hoop zone in the moment it was picked (or is within the 5-frame "just after loss" tail).
7. **No frame from a film not in the 7.**
8. **Every LOST frame is within 8 frames after a SEEN frame.**

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