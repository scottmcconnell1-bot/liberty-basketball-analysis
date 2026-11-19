REJECTED by Claude Code, 2026-11-04: (1) hidden new numbers with no source and no Scott gate: player_box_diagonal*0.5 (Rule 1), hoop.y+40 (Rule 2), gap >3 frames, max(player_w,player_h)*0.6 (D). (2) 'near the hoop' = 0.85*hoop_w is ai_bridge.py:1237 'within rim opening' (through-rim veto) - about the same ring as rim_r, so Rule 3 would be almost empty; it is not an airball distance. (3) Fixed px (72, 280) assume 1920x1080 but Notus is 1280x720 (cv2 read this session) - distances must be hoop-relative or per film. (4) player tracker_id needs a tracker (ByteTrack/DeepSORT banned) - BODD gives boxes only. (5) 'headed at a teammate' needs team identity that does not exist - say so. (6) moment count wrong: 140 tags + 106+31 fakes = 277, cost estimate unverified. (7) MATCH_TOLERANCE_MS is a matching tolerance, reused as detection window without saying where the window sits vs the tag.

SHOT FLIGHT RULES - MEASURE SPEC v1 - not run

This spec defines MEASUREMENT ONLY: apply the four agreed flight-end rules to every tagged shot and every fake shot from spec 32. No new detector, no training, no tuning, no core file edits. Questions A–D answered on Adrian Q1–Q3 (109 tags) and Notus Q1 (31 tags).

1. THE FOUR RULES (Scott agreed, not yet coded)

Rule 1 — Caught by a player before reaching the hoop → PASS.
Rule 2 — Comes down onto the rim/backboard, untouched → SHOT (then make/miss as today).
Rule 3 — Aimed at the hoop (rises above rim height), comes down NEAR the hoop, touches nothing → AIRBALL = missed shot.
Rule 4 — Lands far from the hoop, or was headed at a teammate → BAD PASS, not a shot.
Between 3 and 4, or unclear → orange card for the coach (Scott's standing rule: program first, coach review fallback).

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
| `ai_bridge.py` 0.55 * hoop_w | 0.55 hoop widths | `ai_bridge.py:1032-1033` `horiz_dist <= 0.55 * hoop_w` (crossing gate) |
| `ai_bridge.py` 0.6 * hoop_w | 0.6 hoop widths | `ai_bridge.py:1082` `horiz_dist <= 0.6 * hoop_w` (column gate) |
| `ai_bridge.py` 0.85 * hoop_w | 0.85 hoop widths | `ai_bridge.py:1237` `dist_at_180 > 0.85 * hoop_w` (drift veto) |
| `MATCH_TOLERANCE_MS` | 8000 ms | `manual_tag_teach.py:18` `MATCH_TOLERANCE_MS = 8000` |

Proposed defaults for the two new distances (Scott confirms/overrides before run):

- **"on the rim" (Rule 2)**: `rim_r` from `ball_through_rim` default = **72 px**. Reason: existing make/miss code already uses this as the iron radius; a ball whose center passes within `rim_r` of the hoop centre at rim height is "on the rim".
- **"near the hoop" (Rule 3)**: `0.85 * hoop_w` = **0.85 hoop widths** (≈ `rim_r * 1.7`). Reason: `ai_bridge.py:1237` already uses 0.85 * hoop_w as the outer bound for a ball that went through the rim; an airball landing inside this ring is "near". Alternative from existing code: `court_memory.py close_to_rim max_dist=280` px (peak distance, not landing).

If Scott chooses different numbers, record them here before the run.

3. DATA — WHAT EXISTS VS WHAT MUST BE PRODUCED

3.1 Existing data (read-only)

| Item | Path | Contents |
|------|------|----------|
| Adrian tags (Q1–Q3 = 109 shots) | `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` | Loader: `measure_net_moved.py:73` `load_shot_tags()` |
| Notus Q1 tags (31 shots) | `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` | Same loader |
| Adrian video | `uploads/nfhs_gam0a66d85e12.mp4` | 25 fps |
| Notus video | `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` | 25 fps (assumed) |
| Saved v6 tracks (Adrian, 111 entries) | `C:/Users/scott/AppData/Local/Temp/v6_tracks.json` | Each entry: `{t, result, hoop[x,y,w,h], ball[[frame,x,y],...], bodd[[frame,x,y],...]}`. First entry covers frames 0..35 only (~1.4 s) around the tag. |
| Saved v6 tracks (Notus Q1, 31 entries) | `C:/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json` | Same structure |
| Spec 32 fake shots (finder shots with no tag) | `Liberty_Shot_Outputs/find_shots/results.json` | Precision + rim_arc generator rows; "tagged_gap" generator excluded. |

3.2 What the saved tracks DO NOT have

- Full ball flight from release to rim — each saved track is a ~1.4 s window around the tag time.
- Any tracks for the fake shots (they were not tagged, so no v6 track was saved for them).

3.3 New detection run REQUIRED

To answer Questions A and D (flight coverage, release trace-back), we need full-flight ball tracks for every moment of interest (tagged shots + fake shots). This requires re-running the ball detector on the full video (or long windows around each moment).

**Script to run** (new, under `.team/shot_detectors/`): `collect_flight_tracks.py`
**Model**: existing v6 ball model (already used for v6_tracks.json) — running an existing model is not training.
**BODD model**: `C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt` (classes: basketball, hoop, player, referee) — for player boxes at release.
**Window per moment**: **8000 ms** (from `MATCH_TOLERANCE_MS` in `manual_tag_teach.py:18`, same window used in spec 32 matching). Scott confirms or overrides.
**Full frame or crop**: Full frame (1920×1080) — hoop position moves with camera; cropping would lose the hoop reference.
**Output dir**: `Liberty_Shot_Outputs/shot_rules/` — script MUST refuse if directory already exists.
**Output per moment**: JSON `{moment_id, tag_t_ms, ball_track[[frame,x,y,conf],...], bodd_track[[frame,x,y,conf],...], hoop_samples[{t,x,y,w,h},...], player_boxes[{frame, track_id, x,y,w,h},...]}`
**Compute cost estimate**: ~2 min per film on GPU (v6 ball model + BODD on 25 fps video, 8000 ms windows × ~140 moments = ~190 s video processed per film). Exact time recorded in the run log.

4. HOW EACH RULE IS MEASURED (plain words → function names)

All measurements use: ball track (x,y per frame), hoop samples (x,y,w,h per sample), player boxes (x,y,w,h per frame, tracker_id). Hoop at time t = `net_detector.hoop_at(hoop_samples, t)`.

**Rule 1 — Caught before hoop (PASS)**
- Ball track has a frame where a player box contains the ball center (distance ball-to-player-center < player_box_diagonal * 0.5) AND that frame is before the ball reaches rim height (ball.y < hoop.y - rim_r).
- Function: `is_caught_before_rim(ball_track, player_boxes, hoop_samples) -> bool`

**Rule 2 — On the rim (SHOT)**
- Ball track has a frame where distance(ball_center, hoop_center) <= `rim_r` (72 px) AND ball.y <= hoop.y + 40 (at or above rim) AND no player caught it first (Rule 1 false).
- Function: `hits_rim(ball_track, hoop_samples, rim_r=72) -> (bool, frame_idx)`

**Rule 3 — Airball near hoop (MISSED SHOT)**
- Ball rises above rim height (exists frame with ball.y < hoop.y - rim_r), then falls, and at its lowest point near the hoop: distance(ball_center, hoop_center) <= `near_hoop_dist` (0.85 * hoop_w) AND Rule 1 false AND Rule 2 false AND no net motion (`net_moved_after_shot` false).
- Function: `is_airball_near_hoop(ball_track, hoop_samples, near_hoop_dist, rim_r=72) -> bool`

**Rule 4 — Bad pass (NOT a shot)**
- Ball never rises above rim height, OR lands far from hoop (distance > `near_hoop_dist` at lowest point), OR ball track points toward a teammate (vector from release to landing points to a player box not at the hoop).
- Function: `is_bad_pass(ball_track, hoop_samples, player_boxes, near_hoop_dist, rim_r=72) -> bool`

**Orange card (unclear)**
- None of Rules 1–4 clearly apply (e.g., ball lost mid-flight, ambiguous landing).
- Function: `is_orange_card(ball_track, hoop_samples, player_boxes, near_hoop_dist, rim_r=72) -> bool`

**Gap reporting (banned: no interpolation, no gap filling)**
- If ball track has a gap > 3 frames (120 ms at 25 fps) during flight, record `longest_gap_frames` and `total_frames_seen / total_frames_in_flight_estimate`. Do NOT fill the gap.

5. QUESTIONS TO ANSWER (output tables)

Run on Adrian Q1–Q3 (109 tags) and Notus Q1 (31 tags), plus fake shots from spec 32.

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
- Trace ball track backward from rim contact / lowest point to first frame where ball is inside a player box (distance ball-center to player-box-center < max(player_w, player_h) * 0.6).
- Report: success rate (%), median frames back to release, which player box (tracker_id) if multiple.

6. OUTPUT

Directory: `Liberty_Shot_Outputs/shot_rules/` (refuse if exists)

Files:
- `results.json` — full per-moment detail for A–D.
- `summary.md` — short markdown tables:
  - Table A: Flight coverage (median/min/max frames_seen/frames_flight, longest_gap) × film × kind.
  - Table B: Rule counts per tagged shot × film × kind.
  - Table C: Rule counts per fake shot × film.
  - Table D: Release trace-back success rate, median frames back, per film × kind.

7. NEW CODE

Location: `.team/shot_detectors/`

Scripts:
- `collect_flight_tracks.py` — runs v6 ball + BODD on full video windows, writes per-moment JSON. Pure detection, no rules.
- `shot_rules_measure.py` — loads per-moment JSON, applies four rule functions, computes A–D, writes results + summary. Pure functions + CLI.

Rule functions (pure, tested):
- `is_caught_before_rim(ball_track, player_boxes, hoop_samples) -> bool`
- `hits_rim(ball_track, hoop_samples, rim_r) -> (bool, frame_idx)`
- `is_airball_near_hoop(ball_track, hoop_samples, near_hoop_dist, rim_r) -> bool`
- `is_bad_pass(ball_track, hoop_samples, player_boxes, near_hoop_dist, rim_r) -> bool`
- `is_orange_card(...) -> bool`
- `trace_release(ball_track, player_boxes, start_frame) -> (success: bool, release_frame: int, player_tracker_id: int)`

Tests (hand-made tracks, no video):
- Clean shot: ball rises, hits rim (Rule 2 true).
- Airball short: ball rises, falls near hoop, no net motion (Rule 3 true).
- Lob caught near rim: player catches ball before rim height (Rule 1 true).
- Overthrown pass past hoop: ball never rises above rim, lands far (Rule 4 true).
- Gap mid-flight: ball track missing 10 frames during rise (reports gap, no fill).
- Orange card case: ball lost mid-flight, ambiguous landing.

8. ROLES & GATES

- Cursor codes `collect_flight_tracks.py` and `shot_rules_measure.py` + tests.
- Claude Code vets: no core edits, matching logic correct, window fixed before run, output dir refusal, gap reporting honest (no fill), "Scott decides" numbers recorded.
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS. A DISAGREE stops the loop for Scott.
- Scott reviews the summary tables (A–D) before any next step.
- **Stop for Scott before the run** for any "Scott decides" number (the two distances in Section 2, and the window per moment in Section 3.3 if different from 8000 ms).

9. FACT SOURCES

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