VETTED by Claude Code (plan checker), 2026-10-28 (v2): fixes (1)-(3) checked by reading the lines: peak frames come from net_moved_build_results.json (absolute, rerun by the checker; lines 117-119, 307) and drawn ball points use absolute frame = round(t/1000*fps) + offset (line 127); counts updated to 127 shots / 109 in Q1-Q3 (line 28) and the duplicate times corrected to 2738600 and 2747200 (lines 286, 306); hoop box centred (line 126). BINDING CHECKER NOTES: (a) fix (4) is not in the plan text, so it goes in the coder's job prompt: the script takes --out (default C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review); Cursor tests with python3 and --out .team/shot_outputs_test/missed_makes_review; the checker runs the final build with the Windows venv. (b) Section 9 is already done (Scott removed the duplicates 2026-10-28). (c) The step-1 results file still lists the 2 duplicate rows twice; select each t once. Muse to check next. Rejection kept in 14_missed_makes_diagnosis_plan_v1_REJECTED.md.

---

# Missed Makes Diagnosis Plan — Step 2: Build Review Page (Read-Only)

**Author:** Hermes (Architect)  
**Date:** 2026-10-28  
**Status:** Plan for Coder (Cursor sandbox)  
**Gate:** Vetter review before implementation

---

## 1. Purpose

Scott's directive (2026-10-28): "we have to get to 100%" on makes and misses. A DIAGNOSIS step is required before any new fix. This task builds a static HTML review page so Scott and the checker can **look at the 19 missed makes** and assign each a cause from a fixed list. No detector changes, no threshold tuning, no code guessing.

**Measured facts (2026-10-28):**
- Current rule misses 19 makes (Notus A1 Q1: 7, Adrian Q1–Q3: 12) and calls 0 misses makes.
- 50 of 142 build shots have no rim crossing in the saved ball path.
- `net_moved_after_shot` as-is catches 6 of 19 missed makes but fires on 38 of 93 misses (Adrian tag file no longer has the 2 duplicate miss rows at 45:38.6 and 45:47.2 — 127 shots, 109 in Q1-Q3; v6_tracks.json and the step-1 results file still list t=2738600 and t=2747200 twice, so each t is selected once; true Adrian Q1–Q3 baseline is 97 of 109; whole film 111 of 127).

---

## 2. Scope

**Read-only inputs:**
- Tag files: `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` (31 shots), `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` (127 shots, 109 Q1–Q3) — duplicates removed (backup in `data/film_tags/_history/`)
- Saved v6 tracks: `C:\\Users\\scott\\AppData\\Local\\Temp\\v6_tracks_notus_q1.json` (31 tracks), `C:\\Users\\scott\\AppData\\Local\\Temp\\v6_tracks.json` (111 tracks, includes 2 duplicates) — look tracks up by `t` from the deduped tags
- Videos: `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` (25 fps, 1280×720), `uploads/nfhs_gam0a66d85e12.mp4` (25 fps, 1920×1080)

**No edits to:** `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, any core file.  
**No detector changes in this step.** STOP after the page is built.

---

## 3. Shot Selection (Fixed Before Looking)

### A. The 19 Missed Makes (Ground Truth = Make, `run_saved_v6_rule` Prediction = Miss)

From `net_moved_build_results.json` (build set, `missed_make=true`):

| # | Film | t (ms) | Time | Quarter | Label | Player | Peak Frame | Peak Reason | Net Moved |
|---|------|--------|------|---------|-------|--------|------------|-------------|-----------|
| 1 | notus_a1 | 64200 | 1:04.2 | Q1 | And-1 | 0 - Camden Linkhart | 1605 | no_crossing_closest_ball | False |
| 2 | notus_a1 | 142600 | 2:22.6 | Q1 | FT Make | 0 - Camden Linkhart | 3629 | crossing | False |
| 3 | notus_a1 | 159300 | 2:39.3 | Q1 | FT Make | 0 - Camden Linkhart | 3983 | no_crossing_closest_ball | False |
| 4 | notus_a1 | 212300 | 3:32.3 | Q1 | 2PT Make | 11 - Flores | 5333 | crossing | False |
| 5 | notus_a1 | 357500 | 5:57.5 | Q1 | FT Make | 0 - Camden Linkhart | 8983 | crossing | False |
| 6 | notus_a1 | 483400 | 8:03.4 | Q1 | 2PT Make | 2 - Carson Linkhart | 12085 | no_crossing_closest_ball | False |
| 7 | notus_a1 | 774600 | 12:54.6 | Q1 | FT Make | 53 - Price | 19398 | crossing | False |
| 8 | adrian | 342800 | 5:42.8 | Q1 | 2PT Make | 51 - Peterson | 8573 | crossing | False |
| 9 | adrian | 638300 | 10:38.3 | Q1 | And-1 | 21 - Colman | 15992 | crossing | False |
| 10 | adrian | 717000 | 11:57.0 | Q1 | 2PT Make | 21 - Colman | 17953 | no_crossing_closest_ball | False |
| 11 | adrian | 801800 | 13:21.8 | Q1 | 2PT Make | 40 - Dayley | 20045 | no_crossing_tag_frame | True |
| 12 | adrian | 1231400 | 20:31.4 | Q2 | FT Make | 25 - Alvarez | 30785 | crossing | True |
| 13 | adrian | 1792900 | 29:52.9 | Q2 | 2PT Make | 40 - Dayley | 44822 | crossing | False |
| 14 | adrian | 1836700 | 30:36.7 | Q2 | 3PT Make | 21 - Colman | 45959 | crossing | False |
| 15 | adrian | 2479100 | 41:19.1 | Q3 | 2PT Make | 23 - Rodus | 62031 | no_crossing_closest_ball | True |
| 16 | adrian | 2870400 | 47:50.4 | Q3 | 3PT Make | 21 - Colman | 71803 | crossing | False |
| 17 | adrian | 2962500 | 49:22.5 | Q3 | 2PT Make | 21 - Colman | 74062 | crossing | True |
| 18 | adrian | 3045900 | 50:45.9 | Q3 | FT Make | 25 - Alvarez | 76169 | crossing | True |
| 19 | adrian | 3095700 | 51:35.7 | Q3 | FT Make | 13 - Mendoza | 77401 | no_crossing_closest_ball | True |

### B. 10 Correctly-Called Makes (Ground Truth = Make, Rule Prediction = Make)

**Selection rule (fixed before looking):** From the build set shots where `gt_make=true` and `rule_pred_make=true`, take the first 10 by timestamp (ascending `t`). If fewer than 10, take all.

### C. 10 Misses (Ground Truth = Miss, Rule Prediction = Miss)

**Selection rule (fixed before looking):** From the build set shots where `gt_make=false` and `rule_pred_make=false`, take the first 10 by timestamp (ascending `t`) **excluding the 2 Adrian rows that appear twice in v6_tracks.json and the step-1 results** (t=2738600 "45:38.6 2PT Miss" and t=2747200 "45:47.2 3PT Miss" — the tag file no longer has these duplicates, but tracks/results still list each t twice, so select each t once). If fewer than 10 after deduplication, take all unique.

---

## 4. Fixed Cause List (Decided in This Plan, Before Looking)

Each of the 19 missed makes will be assigned **exactly one** cause from this list by Scott or the checker looking at the review page. The coder does **not** assign causes.

1. **ball_never_detected_near_rim** — no ball points in the saved track within ~150 px of the hoop center during the shot window
2. **ball_detected_crossing_outside_055** — ball crosses hoop_y but horizontal distance > 0.55 × hoop_w at the crossing frame
3. **hoop_box_wrong_or_moved** — the saved hoop box (hoop_x, hoop_y, hoop_w) is visibly not on the orange rim in the frames around the shot
4. **camera_panned_zoomed_during_shot** — the camera moves noticeably (background shifts) during the 10-before to 25-after frame window, so the fixed hoop box no longer aligns
5. **ball_hidden_by_players_backboard** — the ball is occluded by a player, the backboard, or the net cords at the critical crossing frames
6. **crossing_seen_but_column_drift_test_rejected** — a valid crossing exists (ball above → below within 0.55 hoop_w) but the column check (0.6 hoop_w from 80–180 px below) or drift veto (>0.40 hoop_w) fails
7. **other** — none of the above; write a one-sentence description

---

## 5. Review Page Specification

### Output Location (OUTSIDE REPO)

```
C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review\
├── index.html                    # Main review page
├── shots/
│   ├── missed_make_01/           # One subdir per missed make (19 total)
│   │   ├── frames/               # Cropped frame strips (PNG)
│   │   │   ├── frame_000.png     # 10 frames before peak
│   │   │   ├── ...
│   │   │   ├── frame_010.png     # Peak frame (crossing or closest-approach)
│   │   │   ├── ...
│   │   │   └── frame_035.png     # 25 frames after peak (36 frames total)
│   │   ├── overlay_data.json     # Ball points, hoop box, peak frame, rule reason
│   │   └── shot_meta.json        # Timestamp, label, player, film, quarter, etc.
│   ├── correct_make_01/          # 10 correctly-called makes (same structure)
│   └── miss_01/                  # 10 misses (same structure)
├── cause_template.json           # Empty template for Scott/checker to fill
└── cause_counts.md               # Summary table written after causes assigned
```

### Frame Strip Generation (Per Shot)

For each of the 39 shots (19 missed makes + 10 correct makes + 10 misses):

1. **Peak frame determination** (reuse logic from `run_saved_v6_rule` and step-1 script):
   - **Absolute peak frame from `net_moved_build_results.json`:** Use the `peak_frame` value already computed and stored there — it is already an absolute video frame number, validated by the step-1 checker rerun.
   - Do NOT recompute from track ball/bodd offsets; the saved `peak_frame` is the correct absolute frame.
   - **This peak frame is an absolute video frame number.**

2. **Frame window:** `[peak_frame - 10, peak_frame + 25]` inclusive (36 frames). Clamp to `[0, total_frames-1]`.

3. **Crop region:** Square crop centered on `(hoop_x, hoop_y)` with side length `max(hoop_w * 3, 240)` pixels. Clamp to video bounds. This captures the hoop, net, and ~1.5 hoop widths around it.

4. **Draw on each cropped frame:**
   - Saved hoop box: rectangle **centered on (hoop_x, hoop_y)** — top-left = `(hoop_x - hoop_w/2 - crop_x, hoop_y - hoop_w/2 - crop_y)` with width `hoop_w`, height `hoop_w` (green, 2 px).
   - All ball points from the track that fall in this frame: draw as red circles (radius 4 px) at `(ball_x - crop_x, ball_y - crop_y)`. **Use absolute frame = round(t/1000*fps) + offset** when looking up ball points by frame.
   - Peak frame marker: draw a yellow crosshair (10 px) at the hoop center on the peak frame only.
   - Frame number text: top-left corner of crop.

5. **Save each cropped frame as PNG** in `shots/<shot_id>/frames/frame_<000-035>.png`.

### Overlay Data (per shot, `overlay_data.json`)

```json
{
  "peak_frame": 1605,
  "peak_frame_type": "crossing" | "closest_ball" | "tag_frame",
  "hoop": {"x": 440.6, "y": 145.3, "w": 59.9},
  "rim_r": 29.95,
  "crop": {"cx": 440.6, "cy": 145.3, "size": 240},
  "ball_points_by_frame": {
    "1595": [[442.1, 140.2], [443.5, 142.8]],
    "1596": [[441.8, 144.1]],
    ...
  },
  "rule_details": {
    "reason": "no_valid_crossing",
    "cross_idx": null,
    "column_ratio": 0.0,
    "drift": null,
    "short_net_depth": true,
    "ball_went_up": false,
    "short_combined_track": false
  }
}
```

`rule_details` comes from the `details` dict produced by `run_saved_v6_rule` for that shot (the `reason` field and any extra fields). For shots where `run_saved_v6_rule` returned early (e.g., `short_combined_track`), include whatever fields exist.

### Shot Metadata (per shot, `shot_meta.json`)

```json
{
  "film": "notus_a1",
  "t": 64200,
  "time_str": "1:04.2",
  "quarter": "Q1",
  "label": "And-1",
  "player": "0 - Camden Linkhart",
  "gt_make": true,
  "rule_pred_make": false,
  "missed_make": true,
  "net_moved": false,
  "video_path": "C:\\Users\\scott\\Documents\\liberty-basketball-analysis\\uploads\\LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
  "tracks_path": "C:\\Users\\scott\\AppData\\Local\\Temp\\v6_tracks_notus_q1.json",
  "fps": 25.0
}
```

### Main Page (`index.html`)

Static HTML (no JS frameworks, no server). Structure:

- Header: "Missed Makes Diagnosis Review — 2026-10-28"
- Three sections: **Missed Makes (19)**, **Correct Makes (10)**, **Misses (10)**
- Each section: grid of shot cards (responsive, ~3 per row on desktop)
- Each card shows:
  - Film, time, quarter, label, player
  - **Peak frame crop** (frame_010.png) as the thumbnail
  - Rule reason badge (e.g., "no_valid_crossing", "column_ratio_low: 0.33", "short_net_depth")
  - `net_moved_after_shot` result (True/False)
  - Link to detail view (opens `shots/<shot_id>/detail.html`)
- Detail view (`detail.html` in each shot subdir):
  - Horizontal strip of all 36 frame thumbnails (click to enlarge)
  - Full-size view on click (lightbox or new tab)
  - Metadata table
  - **Cause dropdown** (for missed makes only): the 7 fixed causes + free-text for "other"
  - "Save cause" button → writes to `shots/<shot_id>/cause.json` (local file via File System Access API or download link; simplest: generate a `causes.json` download with all assignments)

**Simplest implementation:** The HTML page is fully self-contained. Cause assignment is done by Scott/checker opening the page in a browser, selecting causes, and clicking "Export Causes" which downloads `causes.json`. They save it to `C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review\causes.json`. The coder's script does **not** write causes.

---

## 6. Script Name and Location

**Script (inside repo):**
```
.team/shot_detectors/pixel_miss/build_review_page.py
```

**Output directory (outside repo):**
```
C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review\
```

**Test output directory (sandbox only, never committed):**
```
.team/shot_outputs_test/missed_makes_review/
```

---

## 7. Exact Run Command

```cmd
.\\.venv\\Scripts\\python.exe .team/shot_detectors/pixel_miss/build_review_page.py
```

The script must:
1. Load tag files and track files (read-only).
2. Compute the 19 missed makes, 10 correct makes, 10 misses per the fixed selection rules.
3. For each shot, compute peak frame, extract 36-frame crop strip, draw overlays, save PNGs.
4. Write `overlay_data.json`, `shot_meta.json` per shot.
5. Generate `index.html` and per-shot `detail.html`.
6. Write `cause_template.json` (empty causes for the 19 missed makes).
7. Print summary to console: counts, output path, "STOP — page built, causes assigned by human".
8. **Exit. No further steps.**

---

## 8. What Is Reported (Console + Files)

### Console Output

```
Built review page at C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review\
Shots processed: 39 (19 missed makes, 10 correct makes, 10 misses)
Frames extracted: 39 × 36 = 1404 PNGs
Cause template written: causes.json (19 entries, all null)
Open index.html in a browser to assign causes.
```

### File: `cause_template.json` (for Scott/checker to fill)

```json
[
  {"shot_id": "missed_make_01", "t": 64200, "film": "notus_a1", "cause": null},
  {"shot_id": "missed_make_02", "t": 142600, "film": "notus_a1", "cause": null},
  ...
  {"shot_id": "missed_make_19", "t": 3095700, "film": "adrian", "cause": null}
]
```

### File: `cause_counts.md` (written AFTER Scott/checker fills causes and saves `causes.json`; the script can include a helper to regenerate this from a filled `causes.json`, or it can be done manually)

```
# Cause Counts (filled after review)

| Cause | Count |
|-------|-------|
| ball_never_detected_near_rim | N |
| ball_detected_crossing_outside_055 | N |
| hoop_box_wrong_or_moved | N |
| camera_panned_zoomed_during_shot | N |
| ball_hidden_by_players_backboard | N |
| crossing_seen_but_column_drift_test_rejected | N |
| other | N |
| **Total** | **19** |
```

---

## 9. Duplicate Tag Rows — Done

Scott removed the 2 duplicate Adrian tag rows on 2026-10-28 (backup in `data/film_tags/_history/`). The tag file now has 127 shots, 109 in Q1-Q3. v6_tracks.json and the step-1 results file still list t=2738600 and t=2747200 twice; each t is selected once.

---

## 10. Golden Rules (From Plan §5 and AUTHORITY.md)

- **No edits to protected files:** `net_detector.py`, `ai_bridge.py`, `models/ball_detector.pt`, `ball_confidence`, `schema.sql` — none are touched.
- **No looser cutoffs:** This task only visualizes; it does not change any threshold.
- **`applied_to_core` = false:** The script lives in `.team/shot_detectors/pixel_miss/` and does not touch core.
- **Tag files read-only:** `data/film_tags/*.json` are read-only for scoring.
- **Output outside repo:** All images and HTML go to `C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review\`.
- **Sandbox test run** may write under `.team/shot_outputs_test/` (never committed).
- **STOP after the page is built.** No detector code, no gate logic, no tuning.

---

## 11. Verification Checklist (Coder Confirms Before Done)

- [ ] All 19 missed makes from `net_moved_build_results.json` (`missed_make=true`) are included.
- [ ] 10 correct makes selected by fixed rule (first 10 by `t` where `gt_make=true` and `rule_pred_make=true`).
- [ ] 10 misses selected by fixed rule (first 10 unique by `t` where `gt_make=false` and `rule_pred_make=false`, excluding the 2 Adrian rows that appear twice in v6_tracks.json and the step-1 results at t=2738600 and t=2747200 — the tag file no longer has these duplicates, but tracks/results still list each t twice, so select each t once).
- [ ] Peak frame taken from `net_moved_build_results.json` (absolute, already validated) for all 39 shots.
- [ ] 36-frame crop strips (10 before, peak, 25 after) saved as PNG with hoop box **centered on (hoop_x, hoop_y)**, ball points drawn at absolute frames, peak marker.
- [ ] `overlay_data.json` and `shot_meta.json` written per shot with all required fields.
- [ ] `index.html` and per-shot `detail.html` generated, openable in browser.
- [ ] `cause_template.json` written with 19 null causes.
- [ ] Output directory is `C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review\` (outside repo).
- [ ] No edits to any protected file; no detector changes; script exits after page generation.
- [ ] Console prints summary with counts and output path.

---

## 12. Next Step (After This Plan Is VETTED)

This plan goes to `NEXT_TASK.md` only after the Vetter stamps it `VETTED`. The Coder (Cursor sandbox) implements `build_review_page.py`. After the page is built and Scott/checker assign causes, the cause counts inform the supplement detector design (Task 1 Step 2 in the work order plan: `net_rim_supplement.py`).

---

**End of Plan** — `.team/specs/14_missed_makes_diagnosis_plan.md`