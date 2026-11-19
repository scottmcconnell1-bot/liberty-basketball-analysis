VETTED by Claude Code, 2026-11-04, WITH CONDITIONS (binding on the code): v1 reasons 1-7 fixed (checked: court_memory.py:165 rim_r=72 and :190 'dist <= rim_r and y <= hoop_y + 40' exist; cv2 read Adrian 1920x1080 / Notus 1280x720 both 25 fps). C1 RELEASE IS NOT A CATCH: Rule 1 as written fires on the shooter's own hands at release, so every shot would be a pass. A catch = the ball LEAVES a player box, is in flight, then ENTERS a player box, before it first reaches the rim zone in TIME (not 'ball.y < hoop.y - rim_r'). C2 PLAYERS UNDER THE RIM: player boxes overlap the hoop in 2D; a ball inside the rim zone (Rule 2 distance) is never a catch. C3 ONE UNIT: rim_contact_dist is 72 px / Adrian median hoop_w, used in hoop widths on BOTH films (v2 text mixes px on Notus). Must stay < near_hoop_dist. C4 Rule 3 drops the net_moved_after_shot check (needs video; shot_rules_measure.py is pure from JSON; a make hits the rim zone first anyway). C5 Adrian Q4 is NOT detected, read, or reported in this spec. C6 compute estimate in 4.3 is unverified (277 x 5 s = ~23 min of film total, two models, full frame); record real time. C7 the 7 numbers are Scott's before the run; code takes them as arguments with no defaults in the rule functions.

SHOT FLIGHT RULES - MEASURE SPEC v3 - not run

v3: Scott narrowed the catch check to near the hoop; folds in C1/C2.

This spec defines MEASUREMENT ONLY: apply the four agreed flight-end rules to every tagged shot and every fake shot from spec 32. No new detector, no training, no tuning, no core file edits. Questions A–D answered on Adrian Q1–Q3 (109 tags) and Notus Q1 (31 tags), plus fake shots from spec 32.

1. THE FOUR RULES (Scott agreed, v3 — catch check only near the hoop)

Rule 1 — Caught by a player near the hoop (after leaving shooter's box, before rim height) → PASS.
Rule 2 — Comes down onto the rim/backboard, untouched → SHOT (then make/miss as today).
Rule 3 — Aimed at the hoop (rises above rim height), comes down NEAR the hoop, touches nothing → AIRBALL = missed shot.
Rule 4 — Lands far from the hoop, or was headed at a teammate → BAD PASS, not a shot.
Between 3 and 4, or unclear → orange card for the coach (Scott's standing rule: program first, coach review fallback).

Decision order (checked sequentially, first match wins):
1. Where does the flight come down?
   - RIM ZONE (distance <= rim_contact_dist): Rule 2 → SHOT (never a catch, even if a player box overlaps the hoop).
   - NEAR THE HOOP but not the rim (rim_contact_dist < distance <= near_hoop_dist): check for a catch.
     - Ball, after leaving the shooter's box and being in flight, enters a player box before it drops below rim height → Rule 1 PASS.
     - Otherwise → Rule 3 AIRBALL.
   - FAR FROM THE HOOP (distance > near_hoop_dist): Rule 4 NOT A SHOT, no catch check.
2. Unclear / incomplete track (long gap, lost ball mid-flight, ambiguous landing) → ORANGE CARD (reason recorded).

An incomplete track (long gap, lost ball mid-flight) that cannot satisfy Rules 1–3 cleanly falls to Rule 4 or orange card; the reason (e.g., "gap > 3 frames during rise") is recorded.

Two distances are needed:
- "on the rim" (Rule 2): distance threshold where the ball contacts the rim/backboard.
- "near the hoop" (Rule 3): distance threshold for an airball landing near the hoop.

Each must come from EXISTING code (file + line) or be marked "Scott decides before the run" with a proposed value and why.

2. EXISTING CODE NUMBERS (read this session)

| Name | Value | Source |
|------|-------|--------|
| `rim_arc_shots` max_dist (peak) | 280 px | `event_generator.py:1071` `rim_arc_shots(..., max_dist=280.0, ...)` — peak within 280 px of hoop centre |
| `ball_through_rim` rim_r | 72.0 px | `court_memory.py:165` `rim_r: float = 72.0` (default parameter) |
| `net_detector.py` detected rim r | variable | `net_detector.py:130` `cr = max(8, int(max(bw * 0.45, bh * 0.7)))` — CV rim radius per frame |
| `net_detector.py` net_bottom | rim_y + cr * 3.2 | `net_detector.py:131` `net_bottom = min(frame_h - 1, cy + cr * 3.2)` |
| `court_memory.py` close_to_rim max_dist | 280 px | `court_memory.py:150` `close_to_rim(..., max_dist=280.0)` |
| `court_memory.py` near_basket x_scale | 1.8 | `court_memory.py:119` `half_w = abs(self.key.x1 - self.key.x0) / 2.0 * x_scale` |
| `court_memory.py` near_basket y_pad | 140 px | `court_memory.py:123` `(hoop_y - y_pad) <= y <= (hoop_y + key_h * 0.65)` |
| `ai_bridge.py` 0.55 * hoop_w | 0.55 hoop widths | `ai_bridge.py:1033` `horiz_dist <= 0.55 * hoop_w` (crossing gate) |
| `ai_bridge.py` 0.6 * hoop_w | 0.6 hoop widths | `ai_bridge.py:1082` `horiz_dist <= 0.6 * hoop_w` (column gate) |
| `ai_bridge.py` 0.85 * hoop_w | 0.85 hoop widths | `ai_bridge.py:1237` `dist_at_180 > 0.85 * hoop_w` (drift veto — through-rim "within rim opening" check) |
| `MATCH_TOLERANCE_MS` | 8000 ms | `manual_tag_teach.py:18` `MATCH_TOLERANCE_MS = 8000` (matching tolerance, NOT a detection window) |

**Numbers Scott decides before the run** (every number inside a rule gets a row):

| Name | Proposed value | Unit | Reason | Existing code line |
|------|----------------|------|--------|-------------------|
| `rim_contact_dist` ("on the rim", Rule 2) | **0.735 hoop widths** on both films | hoop widths | `rim_r` 72 px / Adrian median hoop_w 98.0 px (Claude Code, median of 111 hoop boxes in v6_tracks.json, 2026-11-04) = 0.735. Notus median hoop_w 64.5 px, so 0.735 hoop widths = 47 px there. Stays below near_hoop_dist. | `court_memory.py:165` `rim_r=72.0`; `court_memory.py:190` `dist <= rim_r and y <= hoop_y + 40` |
| `near_hoop_dist` ("near the hoop", Rule 3) | **1.833 hoop widths** - SCOTT DECIDED 2026-11-04 | hoop widths | Scott: "2 ft from the outer edge of the rim". Rim 18 in across (radius 9 in) + 24 in = 33 in from the hoop centre = 33/18 = 1.833 hoop widths. | Scott decision (no existing airball distance) |
| `gap_threshold_frames` | 3 | frames | Gap > 3 frames (120 ms at 25 fps) during flight = long gap reported, NOT filled | NOT FOUND — new threshold |
| `catch_distance_factor` | 0.5 | player box diagonal | Ball center inside player box: distance < box_diagonal * 0.5. **Used only near the hoop (rim_contact_dist < land_dist <= near_hoop_dist).** | NOT FOUND — new threshold |
| `release_trace_factor` | 0.6 | max(player_w, player_h) | Trace back: ball center inside player box: distance < max(w,h) * 0.6 | NOT FOUND — new threshold |
| `detection_window_before_ms` | **3000** | ms | MAKE tag marks ball going in; MISS tag marks ~release. Window must reach back before tag for long-shot release. Propose 3000 ms before. | `manual_tag_teach.py:18` MATCH_TOLERANCE_MS=8000 is matching tolerance, not detection window |
| `detection_window_after_ms` | **2000** | ms | Window after tag/finder time to catch late rim contact or landing | NOT FOUND — new threshold |

If Scott chooses different numbers, record them here before the run.

SCOTT APPROVED 2026-11-04 ("Lets try it and see how it goes"): near_hoop_dist 1.833 hoop widths (his number), and the proposed values for rim_contact_dist 0.735 hoop widths, detection_window_before_ms 3000, detection_window_after_ms 2000, catch_distance_factor 0.5, release_trace_factor 0.6, gap_threshold_frames 3. Fixed before the run; no tuning after results.

3. HOOP-RELATIVE UNITS (resolution-independent)

Adrian video: 1920×1080, 25 fps (confirmed by ffprobe). Notus video: 1280×720, 25 fps (confirmed by ffprobe).
Hoop width `hoop_w` varies per film and per camera zoom (Adrian ~90–105 px, Notus ~60–65 px in v6 tracks).
**All distances in rules are expressed in hoop widths (hoop_w from the hoop box at that frame).**
- `rim_contact_dist` = `rim_r` px → converted to hoop widths at runtime: `rim_r / hoop_w` (≈ 0.7–0.8 hoop widths on Adrian, ≈ 1.1–1.2 on Notus).
- `near_hoop_dist` = 1.2 * hoop_w (proposed).
- Player-box-relative distances (catch, release trace) use box diagonal or max(w,h) in pixels — these scale with player size in frame, not hoop.
- Fixed-pixel thresholds from existing code (280 px, 72 px, 140 px, 40 px) are **converted to hoop widths at runtime** using the current hoop sample's `hoop_w`. Example: 280 px / hoop_w.

If a rule needs a fixed-pixel value that has no hoop-relative equivalent, the spec says how px is scaled per film (e.g., "280 px at 1920×1080 → multiply by 1280/1920 = 0.667 for Notus").

4. DATA — WHAT EXISTS VS WHAT MUST BE PRODUCED

4.1 Existing data (read-only)

| Item | Path | Contents |
|------|------|----------|
| Adrian tags (Q1–Q3 = 109 shots) | `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` | Loader: `measure_net_moved.py:73` `load_shot_tags()` |
| Notus Q1 tags (31 shots) | `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` | Same loader |
| Adrian video | `uploads/nfhs_gam0a66d85e12.mp4` | 1920×1080, 25 fps |
| Notus video | `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` | 1280×720, 25 fps |
| Saved v6 tracks (Adrian, 111 entries) | `C:/Users/scott/AppData/Local/Temp/v6_tracks.json` | Each entry: `{t, result, hoop[x,y,w,h], ball[[frame,x,y],...], bodd[[frame,x,y],...]}`. First entry covers frames 0..35 only (~1.4 s) around the tag. |
| Saved v6 tracks (Notus Q1, 31 entries) | `C:/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json` | Same structure |
| Spec 32 fake shots (finder shots with no tag) | DB `events` table (read-only, mode=ro) | Precision + rim_arc generator rows; "tagged_gap" excluded. Adrian Q1–Q3: 106 extra. Notus Q1: 31 extra (within Q1 time span). |

4.2 What the saved tracks DO NOT have

- Full ball flight from release to rim — each saved track is a ~1.4 s window around the tag time.
- Any tracks for the fake shots (they were not tagged, so no v6 track was saved for them).

4.3 New detection run REQUIRED

To answer Questions A and D (flight coverage, release trace-back), we need full-flight ball tracks for every moment of interest (tagged shots + fake shots). This requires re-running the ball detector on the full video (or long windows around each moment).

**Script to run** (new, under `.team/shot_detectors/`): `collect_flight_tracks.py`
**Model**: existing v6 ball model (already used for v6_tracks.json) — running an existing model is not training.
**BODD model**: `C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt` (classes: basketball, hoop, player, referee) — for player boxes at release.
**Window per moment**: **detection_window_before_ms + detection_window_after_ms** (proposed 3000 + 2000 = 5000 ms total, centered on tag/finder time). Scott confirms or overrides.
**Full frame or crop**: Full frame (1920×1080 or 1280×720) — hoop position moves with camera; cropping would lose the hoop reference.
**Output dir**: `Liberty_Shot_Outputs/shot_rules/` — script MUST refuse if directory already exists.
**Output per moment**: JSON `{moment_id, tag_t_ms, ball_track[[frame,x,y,conf],...], bodd_track[[frame,x,y,conf],...], hoop_samples[{t,x,y,w,h},...], player_boxes[{frame, x,y,w,h},...]}` — **no `tracker_id`** (BODD gives boxes per frame only; ByteTrack/DeepSORT banned).
**Compute cost estimate**: ~2 min per film on GPU (v6 ball model + BODD on 25 fps video, ~5000 ms windows × ~277 moments = ~23 min video processed per film). Exact time recorded in the run log. This is an ESTIMATE.

5. HOW EACH RULE IS MEASURED (plain words → function names)

All measurements use: ball track (x,y per frame), hoop samples (x,y,w,h per sample), player boxes (x,y,w,h per frame — no tracker_id). Hoop at time t = `net_detector.hoop_at(hoop_samples, t)`.

**Rule 1 — Caught near hoop (PASS)**
- First determine where the flight comes down: find the frame where the ball is at its lowest point near the hoop (after rising above rim height). Let `land_dist = distance(ball_center, hoop_center)` at that frame.
- If `land_dist > near_hoop_dist`: Rule 1 does not apply (goes to Rule 4, no catch check).
- If `land_dist <= rim_contact_dist`: Rule 1 does not apply (rim zone → Rule 2, never a catch).
- If `rim_contact_dist < land_dist <= near_hoop_dist` (near the hoop, not the rim): check for a catch.
  - Ball must have left the shooter's box (release trace confirms it was in a player box, then exited) AND been in flight, AND then enters a player box (distance ball-to-player-center < player_box_diagonal * catch_distance_factor) before the ball drops below rim height (ball.y >= hoop.y - rim_r).
  - Function: `is_caught_near_hoop(ball_track, player_boxes, hoop_samples, near_hoop_dist_hoop_w, rim_contact_dist_hoop_w, rim_r_px, catch_distance_factor) -> bool`
  - Note: `is_caught_before_rim` is replaced; the new function is only called inside the near-hoop case.

**Rule 2 — On the rim (SHOT)**
- Ball track has a frame where distance(ball_center, hoop_center) <= `rim_contact_dist` (in hoop widths, converted to px at runtime) AND ball.y <= hoop.y + 40 (at or above rim, converted to hoop widths) AND Rule 1 false.
- Function: `hits_rim(ball_track, hoop_samples, rim_contact_dist_hoop_w, rim_r_px=72) -> (bool, frame_idx)`

**Rule 3 — Airball near hoop (MISSED SHOT)**
- Ball rises above rim height (exists frame with ball.y < hoop.y - rim_r), then falls, and at its lowest point near the hoop: distance(ball_center, hoop_center) <= `near_hoop_dist` (in hoop widths) AND Rule 1 false AND Rule 2 false AND no net motion (`net_moved_after_shot` false).
- Function: `is_airball_near_hoop(ball_track, hoop_samples, near_hoop_dist_hoop_w, rim_r_px=72) -> bool`

**Rule 4 — Bad pass (NOT a shot)**
- Ball never rises above rim height, OR lands far from hoop (distance > `near_hoop_dist` at lowest point), OR ball track points away from hoop (landing far from hoop).
- **Teammate part NOT measured in this spec** — team identity does not exist yet. Rule 4 is measured only as "comes down far from the hoop / goes out of bounds".
- Function: `is_bad_pass(ball_track, hoop_samples, near_hoop_dist_hoop_w, rim_r_px=72) -> bool`

**Orange card (unclear)**
- None of Rules 1–4 clearly apply (e.g., ball lost mid-flight, ambiguous landing, long gap during critical phase).
- Function: `is_orange_card(ball_track, hoop_samples, player_boxes, near_hoop_dist_hoop_w, rim_r_px=72, gap_threshold_frames) -> (bool, reason: str)`

**Gap reporting (banned: no interpolation, no gap filling)**
- If ball track has a gap > `gap_threshold_frames` during flight, record `longest_gap_frames` and `total_frames_seen / total_frames_in_flight_estimate`. Do NOT fill the gap.

6. WINDOW OVERLAP HANDLING

The detection window is `[tag_t_ms - detection_window_before_ms, tag_t_ms + detection_window_after_ms]` for tagged shots, and `[finder_t_ms - detection_window_before_ms, finder_t_ms + detection_window_after_ms]` for fake shots.

When two moments' windows overlap: **one run per frame range, no double detection**. The collection script merges overlapping windows into a single continuous segment per film, runs detection once on the merged segment, then slices the per-moment tracks from the combined output. This ensures each frame is processed once and no moment gets two independent detections.

7. QUESTIONS TO ANSWER (output tables)

Run on Adrian Q1–Q3 (109 tags) and Notus Q1 (31 tags), plus fake shots from spec 32 (Adrian Q1–Q3: 106 extra; Notus Q1: 31 extra). Total moments = 140 tagged + 137 fake = 277.

**A. Flight coverage per tagged shot**
For each tagged shot: `frames_seen / frames_in_flight_estimate`, `longest_gap_frames`. Split by 2PT / 3PT / FT.
- `frames_in_flight_estimate` = (tag_frame - release_frame_estimate) where release_frame_estimate is the first frame where ball rises above rim height (Rule 3 start) or first detected frame if earlier.
- Report median, min, max per kind.

**B. Rule classification per tagged shot**
For each tagged shot: which rule (1, 2, 3, 4, orange)? Expect mostly 2 or 3.
- Report counts per rule per film per kind.

**C. Rule classification per fake shot (spec 32)**
For each fake shot (finder shot with no tag, precision + rim_arc generators, excluding "tagged_gap"): which rule?
- If most land in 1 or 4 → the rules would remove them (good).
- Report counts per rule per film.

**D. Release trace-back success**
For each tagged shot where Rule 2 or 3 applies: can the arc be traced back to a player's hands?
- Trace ball track backward from rim contact / lowest point to first frame where ball is inside a player box (distance ball-center to player-box-center < max(player_w, player_h) * release_trace_factor).
- Report: success rate (%), median frames back to release, which player box (frame index + box coords) if multiple. **No tracker_id**.

8. OUTPUT

Directory: `Liberty_Shot_Outputs/shot_rules/` (refuse if exists)

Files:
- `results.json` — full per-moment detail for A–D.
- `summary.md` — short markdown tables:
  - Table A: Flight coverage (median/min/max frames_seen/frames_flight, longest_gap) × film × kind.
  - Table B: Rule counts per tagged shot × film × kind.
  - Table C: Rule counts per fake shot × film.
  - Table D: Release trace-back success rate, median frames back, per film × kind.

9. NEW CODE

Location: `.team/shot_detectors/`

Scripts:
- `collect_flight_tracks.py` — runs v6 ball + BODD on full video windows, writes per-moment JSON. Pure detection, no rules.
- `shot_rules_measure.py` — loads per-moment JSON, applies four rule functions, computes A–D, writes results + summary. Pure functions + CLI.

Rule functions (pure, tested):
- `is_caught_near_hoop(ball_track, player_boxes, hoop_samples, near_hoop_dist_hoop_w, rim_contact_dist_hoop_w, rim_r_px, catch_distance_factor) -> bool`
- `hits_rim(ball_track, hoop_samples, rim_contact_dist_hoop_w, rim_r_px) -> (bool, frame_idx)`
- `is_airball_near_hoop(ball_track, hoop_samples, near_hoop_dist_hoop_w, rim_r_px) -> bool`
- `is_bad_pass(ball_track, hoop_samples, near_hoop_dist_hoop_w, rim_r_px) -> bool`
- `is_orange_card(...) -> (bool, reason: str)`
- `trace_release(ball_track, player_boxes, start_frame, release_trace_factor) -> (success: bool, release_frame: int, player_box: dict)`

Tests (hand-made tracks, no video):
- Clean shot: ball rises, hits rim (Rule 2 true).
- Airball short: ball rises, falls near hoop, no net motion (Rule 3 true).
- Lob caught near rim: player catches ball before rim height (Rule 1 true).
- Overthrown pass past hoop: ball never rises above rim, lands far (Rule 4 true).
- Gap mid-flight: ball track missing 10 frames during rise (reports gap, no fill).
- Orange card case: ball lost mid-flight, ambiguous landing.
- Window merge: two tags 2000 ms apart → single detection run, two sliced outputs.
- Shooter's own hands at release is NOT a catch (ball starts in shooter box, leaves, no re-entry before rim).
- Ball in rim zone with overlapping player box → Rule 2 SHOT, never a pass.
- Pass caught by a player under the basket (near hoop, not rim zone) → Rule 1 PASS.
- Same flight, no catch near hoop → Rule 3 AIRBALL.
- Pass caught on the wing far from hoop (land_dist > near_hoop_dist) → Rule 4 NOT A SHOT (catch never checked).

10. ROLES & GATES

- Cursor codes `collect_flight_tracks.py` and `shot_rules_measure.py` + tests.
- Claude Code vets: no core edits, matching logic correct, window fixed before run, output dir refusal, gap reporting honest (no fill), "Scott decides" numbers recorded, hoop-relative units used, no tracker_id, teammate part excluded.
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS. A DISAGREE stops the loop for Scott.
- Scott reviews the summary tables (A–D) before any next step.
- **Stop for Scott before the run** for any "Scott decides" number (the seven numbers in Section 2 table, and the detection window in Section 4.3 if different from proposed 5000 ms).

11. FACT SOURCES

Every fact above comes from a file read this session or the lines in the prompt. Otherwise: "NOT FOUND - Claude Code to check".

Key lines read this session:
- `event_generator.py:1071-1122` (`rim_arc_shots` — peak distance 280 px, not called)
- `court_memory.py:160-195` (`ball_through_rim` rim_r=72, `close_to_rim` max_dist=280, `near_basket` x_scale=1.8, y_pad=140)
- `net_detector.py:130-132` (CV rim radius `cr`, net_bottom = cy + cr * 3.2)
- `net_detector.py:514-523` (`net_moved_after_shot` — requires peak_frame)
- `ai_bridge.py:1032-1033, 1082, 1237` (0.55/0.6/0.85 * hoop_w gates)
- `manual_tag_teach.py:18` (`MATCH_TOLERANCE_MS = 8000`)
- `measure_net_moved.py:73-97` (`load_shot_tags`)
- `.team/specs/32_find_shots_measure_spec.md` (spec 32 protocol, fake shots definition)
- `.team/shot_detectors/find_shots_measure.py` (matching, span logic)
- `v6_tracks.json` structure (first entry frames 0..35 only)
- ffprobe: Adrian 1920×1080@25fps, Notus 1280×720@25fps
- Tag counts: Adrian 127 total (Q1:44, Q2:25, Q3:40, Q4:18), Notus 31 total (Q1:31)
- Spec 32 fake counts: Adrian Q1–Q3 106 extra, Notus Q1 31 extra