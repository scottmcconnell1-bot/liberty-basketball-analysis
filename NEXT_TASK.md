VETTED by Claude Code (plan checker), 2026-10-28 (Task 1 step 1, v3): fixes (1)-(7) checked by reading the lines: absolute frame = round(t/1000*fps) + offset (line 43; corrected from 42 after Muse DISAGREE); original Notus tracks (20); Q4 not available, build set still runs (22, 121, 149); split by the tag "quarter" field (68), no ms boundaries left; no-crossing rule fixed before running (41); hoop_w in each video's own pixels (47). Checker note: the no-crossing rule applies to EVERY shot without a crossing, makes and misses alike, so misses are not skipped. Facts checked this session: both videos exist (25 fps; 1280x720 and 1920x1080); Adrian tags 129 shots (Q1 44, Q2 25, Q3 42, Q4 18); C:\Users\scott\AppData\Local\Temp\v6_tracks_q4.json does not exist; net_detector.py is called, not edited. Muse to check next.

# NEXT_TASK.md — Task 1, Step 1: Measure net_moved_after_shot on Tagged Shots (Read-Only)

**Source Plan:** `.team/specs/13_shot_work_order_plan.md` (v4, VETTED, Muse AGREE), Section 6, Task 1 sequence step 1.

**Goal:** Call `net_detector.net_moved_after_shot` AS-IS (imported, never edited) on the tagged shots to measure its recovery of missed makes and its false-make rate on misses. This is a BASELINE MEASUREMENT — no new detector code in this task.

---

## Films, Video Paths, and Tag Files (Found in Repo)

| Set | Film | Video Path | Tag File | Shots |
|-----|------|------------|----------|-------|
| **Build — Notus A1 Q1** | Notus A1 (Liberty H vs Notus A1) | `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` | `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` | 31 (all Q1) |
| **Build — Adrian Q1–Q3** | Adrian (Liberty A vs Adrian H) | `uploads/nfhs_gam0a66d85e12.mp4` | `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` | 111 (Q1–Q3) |
|| **Unseen — Adrian Q4** | Same Adrian film | `uploads/nfhs_gam0a66d85e12.mp4` | Same tag file | 18 (Q4) |

**Track Files (Saved v6 Tracks):**
- Notus A1 Q1: `C:\Users\scott\AppData\Local\Temp\v6_tracks_notus_q1.json` (the original, same size as the gemini-upload copy; 31 tracks, has `t`, `result`, `hoop`, `ball`, `bodd`)
- Adrian Q1–Q3: `C:\Users\scott\AppData\Local\Temp\v6_tracks.json` (111 tracks)
- Adrian Q4: does NOT exist (`v6_tracks_q4.json` was never built); unseen set will be reported as unavailable

---

## How Each Shot's Peak Frame and Hoop Position Are Found (Existing Saved Data)

**Source:** `v6_tracks.json` track rows (one per tagged shot timestamp `t`).

Each track row contains:
- `t` — tag timestamp in milliseconds (matches tag file `start` converted via `clock_ms`)
- `result` — "make" or "miss" (ground truth from tags)
- `hoop` — `[hoop_x, hoop_y, hoop_w, hoop_area]` — **grouped hoop**, `hoop_w` = width (diameter, 90–110 px)
- `ball` — list of `[frame, x, y]` — dense ball track through net (for column check and drift)
- `bodd` — list of `[frame, x, y]` — extends down to floor (for short makes continuation)

**Peak Frame (Rim Crossing Frame):**
- Computed by `run_saved_v6_rule` crossing logic: the frame index `j` where ball goes from above `hoop_y` to at/below `hoop_y` within 8 samples AND within `0.55 * hoop_w` horizontally.
- This is the `cross_idx` in `run_saved_v6_rule` (ai_bridge.py ~line 1034).
- **If no crossing found** → `detect_dynamic_entry_crossing` fallback (line 1043).
- **NO-CROSSING RULE (applied before running):** If a missed make has no rim crossing in its saved track (so no peak frame), use the ball point closest to the hoop centre as the peak frame; if the track has no ball points, use the tag frame. Report how many shots used this rule.
- The peak frame is an integer frame number (not timestamp).
- **Absolute video frame = round(t/1000 * fps) + ball-list offset.** The "frame" in each track's `ball` list is an OFFSET from the tag frame (Notus ball starts at 2, Adrian at 0). Negative offsets are allowed. Passing the offset straight to `net_moved_after_shot` would read frames from the first seconds of the video.

**Hoop Position:**
- Directly from `track['hoop']` → `hoop_x, hoop_y, hoop_w, hoop_area`.
- `hoop_w` is the grouped hoop width in each video's own pixels (Adrian 1080p ~90–110 px, Notus 720p ~64 px), NOT the CV rim radius.

**Frame Reader for `net_moved_after_shot`:**
- Must open the video file and return a frame (BGR numpy array) given a frame index.
- Use `cv2.VideoCapture` with `cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)` then `cap.read()`.

---

## Build Set and Unseen Set (Fixed Before Running)

| Set | Shots | Composition |
|-----|-------|-------------|
| **Build Set (Tagged, Used for Tuning Later)** | 142 shots | Notus A1 Q1: 31 shots (all tagged) + Adrian Q1–Q3: 111 shots (tagged) |
| **Unseen Test Set (Tagged, Held Out)** | 18 shots | Adrian Q4–end: tagged shots after Q3 |
| **Notus Unseen** | 0 | Notus A1 has NO tagged shots after Q1 in the tag file |

**Shot Selection from Tag Files:**
- Parse tag file JSON `rows`.
- Keep rows where `eventtype` in `{"2PT", "3PT", "FT"}` AND `result` in `{"Make", "Miss"}`.
- Convert `start` (e.g., `"0:21.3"`) to milliseconds: `clock_ms(start)` = `int(round((minutes*60 + seconds)*1000))`.
- Match tag timestamp to track `t` (exact match).
- **Split sets by each tag row's "quarter" field** — Q1, Q2, Q3 go to build; Q4 goes to unseen. Delete the hand-written ms quarter boundaries (no source given).

---

## What Is Reported (Per Shot, Then Summary)

**For Each Missed Make (Ground Truth = Make, `run_saved_v6_rule` Prediction = Miss):**
- Shot timestamp (ms), quarter, tag label (e.g., "2PT Make"), player
- `net_moved_after_shot` result: **True (net moved) / False (net did not move)**
- Peak frame used, hoop_x, hoop_y, hoop_w

**For Each Miss (Ground Truth = Miss):**
- Shot timestamp, quarter, tag label (e.g., "3PT Miss")
- `net_moved_after_shot` result: **True (false make) / False (correctly no net movement)**
- Count of false makes across all misses

**Summary Table:**
| Metric | Build Set (142) | Unseen Set (18) |
|--------|-----------------|-----------------|
| Missed Makes (GT=Make, Rule=Miss) | N | N |
| Of Missed Makes: Net Moved = True | N (recovery) | N |
| Of Missed Makes: Net Moved = False | N | N |
| Misses (GT=Miss) | N | N |
| Of Misses: Net Moved = True (False Makes) | N | N |
| Of Misses: Net Moved = False | N | N |

---

## Script Name and Location

**Script:** `.team/shot_detectors/pixel_miss/measure_net_moved.py`  
**Output Directory (OUTSIDE REPO):** `C:\Users\scott\Documents\Liberty_Shot_Outputs\`  
**Output Files:**
- `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_build_results.json`
- `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_unseen_results.json`
- `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_summary.md`

---

## Exact Run Command

```cmd
.\.venv\Scripts\python.exe .team/shot_detectors/pixel_miss/measure_net_moved.py
```

---

## Golden Rules (From Plan §5 and AUTHORITY.md)

- **No edits to protected files:** `net_detector.py` is NOT edited. It is imported and `net_moved_after_shot` is called read-only.
- **No looser cutoffs:** The function's internal thresholds (`min_motion=0.045`, `margin=0.02`, deltas 6/10/16) are NOT changed.
- **`applied_to_core` = false:** This measurement script lives in `.team/shot_detectors/pixel_miss/` and does not touch `ai_bridge.py`, `event_generator.py`, or any core file.
- **Tag files read-only:** `data/film_tags/*.json` are read-only for scoring.
- **STOP conditions:** If Adrian Q4 track file (`v6_tracks_q4.json`) does not exist, the script runs the build set and reports the unseen set as "not available: Adrian Q4 tracks were never built". Building Q4 tracks is a separate task for Scott to approve.

---

## What the Coder Must Implement

1. **Load tag files** → extract shot timestamps, labels, quarters, ground truth (make/miss).
2. **Load track files** → match by timestamp `t`, get `hoop`, `ball`, `bodd` for each shot.
3. **Compute peak frame** for each shot using the EXACT crossing logic from `run_saved_v6_rule` (lines 1014–1043 in `ai_bridge.py`). Reuse that logic (copy the crossing detection code) — do NOT call `run_saved_v6_rule` (it returns make/miss, not peak frame).
4. **Create frame reader** for each video: `cv2.VideoCapture` + `cap.set(cv2.CAP_PROP_POS_FRAMES, frame)`.
5. **Call `net_detector.net_moved_after_shot(frame_reader, peak_frame, hoop, rim_r=None)`** for each shot.
   - `hoop` = `(hoop_x, hoop_y)` tuple or list `[hoop_x, hoop_y]` (function expects `hoop` as sequence with x, y at indices 0, 1).
   - `rim_r` = `hoop_w / 2.0` (grouped hoop radius).
6. **Aggregate results** by build/unseen set, missed makes vs misses.
7. **Write JSON and Markdown outputs** to `C:\Users\scott\Documents\Liberty_Shot_Outputs\`.
8. **Print summary to console** and **STOP** — no new detector code, no threshold tuning, no gate logic.

---

## STOP After Reporting

This task ends after the measurement is reported. The decision to write `net_rim_supplement.py` (Step 2 in Plan §6) comes AFTER Scott reviews these numbers. Do not proceed to Step 2 in this task.

---

## Verification Checklist (Coder Confirms Before Done)

- [ ] All 142 build-set shots processed (31 Notus A1 Q1 + 111 Adrian Q1–Q3)
- [ ] Unseen set reported as "not available: Adrian Q4 tracks were never built" (Adrian Q4 track file does not exist)
- [ ] Peak frame computed from saved tracks using exact `run_saved_v6_rule` crossing logic with absolute video frame = round(t/1000 * fps) + ball-list offset
- [ ] `net_moved_after_shot` called with correct `hoop` (x, y) and `rim_r = hoop_w/2`
- [ ] Results written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\` (outside repo)
- [ ] No edits to `net_detector.py`, `ai_bridge.py`, or any core file
- [ ] Summary printed with recovery % and false-make count for build set