VETTED WITH CONDITIONS by Claude Code, 2026-11-05: read spec v2 against collect_q4_bodd.py:49-146 (is_make, v6_ball), shot_rules_measure.py:251-284 (rises_above_rim, release_estimate_frame), collect_flight_tracks.py:59-60 (3000/2000), find_shots_measure.match_shots. Conditions E1-E9 OVERRIDE the text below where they differ.
E1 Hoop every frame: the v6 crop needs a hoop each frame, so BODD full frame runs on EVERY frame of the span (hoop + ball + players, saved for the trace). Section 4 cost is wrong ("BODD trace negligible"): cost = BODD on every frame + v6 crop on every frame. Mark ESTIMATE; record real time.
E2 Two hoops in view: run one v6 crop per BODD hoop detected in that frame (each end separately); a moment records which hoop. No new number.
E3 v6 per frame = a new function that does exactly what collect_q4_bodd.v6_ball does per frame (crop 260/200/240, conf 0.28, imgsz 640, pick within 220 px, prev*0.35 - lines 110-146, not line 49), run over the span instead of 80 frames from a tag. Test: on a recorded frame list it returns the same series as v6_ball. collect_q4_bodd.py is imported, never edited (it has a __main__ guard, line 248).
E4 Miss trigger, no new numbers: "above earlier" = is_make's own test, y < hoop_y - 6 within the last 8 v6 frames (is_make gap 8) and |x - hx| <= 2.2 hoop_w; then the ball inside 0.735 hoop widths and y <= hoop_y + 40*hoop_w/98.
E5 Merge: drop merge_window_ms. One moment per v6 run; a run ends when v6 loses the ball for more than 8 frames (is_make gap). If Scott wants a time window instead, he decides it before the run.
E6 Trace: reuse shot_rules_measure.release_estimate_frame and ball_inside_player(mode='release', 0.6) on the BODD ball over 3000 ms before the trigger (spec 33 Scott-approved window, collect_flight_tracks.py:59). Miss moments trace from the trigger frame (there is no crossing). Floor spot = bottom-centre of the shooter box in picture px (no court map). Trace fails -> ORANGE with reason.
E7 Span with no tags: finder CLI takes --video --start-ms --end-ms --out-dir (+ model paths). Adrian end = Q4_MS 55:17.1 (collect_q4_bodd.py:28); start and Notus Q1 end supplied by Claude Code from an existing source, recorded in the run log - never from tags. The finder imports nothing that reads tags or the DB (test greps its imports).
E8 Measure: drop "+ fakes" from section 7 (rim_first_measure.py reads finder output + tags only). Report found / missed / extra per kind, timing, trace rate, orange count. Extras listed with time so Scott can view them.
E9 One try. No change to any number after results; Q4 untouched until Scott sees the numbers.

RIM-FIRST SHOT FINDER SPEC v2 - not run

1. SCOPE RULE (Scott)

I do not want to manually tag video then you check my tags. Tags are ONLY the answer key while we build and measure, on film Scott already tagged (Adrian Q1-Q3, Notus Q1). The finder itself must read NO tags, NO scoreboard, NO DB shot rows — video in, shot moments out. The code must make that provable: the finder script takes only video path(s) + model paths + out dir; only the separate measure script reads tags.

2. ARCHITECT OPINION

v6 on the hoop crop is proven reliable for make/miss (coach page 41/42 shots correct, 0 differ from tags; collect_q4_bodd.py v6_ball). Using "ball comes DOWN INTO the rim area from above" as the shot trigger leverages this proven reliability and avoids BODD full-frame false positives (spare balls, referee, lights, crowd) that caused spec 33's low SHOT/AIRBALL rates (Adrian 33/109, Notus 5/31).

3. EXACT DETECTION

3.1 Models, crops, confidence, imgsz (from existing code)

Component | Model | Crop | Conf | Imgsz | Source
--- | --- | --- | --- | --- | ---
BODD full-frame (trace only) | `BODD_yolov8n_0001.pt` | Full frame (1920×1080 Adrian, 1280×720 Notus) | 0.12 | 960 | collect_flight_tracks.py:311–312, 340–342
BODD classes kept | basketball, hoop, player | — | — | — | collect_flight_tracks.py:348–350
v6 ball (trigger + confirm) | `ball_net_runs/v6/weights/best.pt` | Hoop crop: hx±260, hy-200..hy+240 | 0.28 | 640 | collect_q4_bodd.py:121–125, v6_ball()
v6 crop center | Hoop position per frame: same frame BODD hoop, else most recent earlier, else next later (shot_rules_measure.hoop_at) — no time-limit number | — | — | — | shot_rules_measure.hoop_at

3.2 Two triggers, both from v6 over the hoop crop (NOT BODD full frame)

Run v6_ball crop (conf 0.28, imgsz 640, hx±260, hy-200..hy+240, prev*0.35 continuity from collect_q4_bodd.py line 49) over the whole span. No rise/peak/arc-top requirement (the arc left the top of the picture in 5 of 20 hand-checked failures).

(a) MAKE trigger: reuse collect_q4_bodd.py is_make (line 49) unchanged — half 0.55, drop 180, gap 8, its own 2.2/0.9/1.3 widths. Import it, do not copy-edit. Proven on the coach page; do not rescale it.

(b) MISS / rim trigger: v6 ball inside the rim zone (<= 0.735 hoop widths of hoop centre, spec 33 Scott-approved; court_memory.py:165 rim_r=72 / Adrian median hoop_w=98 = 0.735) AND at or above rim height (y <= hoop_y + 40*hoop_w/98, court_memory.py:190 scaled), having been above hoop_y in an earlier v6 frame of the same run (coming down).

Merging two triggers within one moment: one moment per descent. Any merge number is "Scott decides before the run" with proposed value: merge_window_ms = 300 (≈ 8 frames at 25 fps). If two triggers fall within this window of the same descent, keep the earlier one.

3.3 Trace back to shooter (release trace)

BODD full frame ONLY for the trace back to the shooter from the confirmed crossing frame. Release trace as spec 33: release_trace_factor 0.6 (spec 33 Scott-approved) — first frame where ball center inside a player box (distance < max(w,h) × 0.6). Output: shooter box + floor spot.

3.4 All distances in hoop widths

Adrian 1920×1080, Notus 1280×720, both 25 fps. Pixels only where reused unchanged from proven code (is_make).

4. COST ESTIMATE (ESTIMATE)

Film | Duration (Q1–Q3) | Frames (25 fps) | v6 over every frame
--- | --- | --- | ---
Adrian | ~32 min (1920 s) | ~48,000 | 48,000 frames
Notus Q1 | ~8 min (480 s) | ~12,000 | 12,000 frames
**Total** | **~40 min** | **~60,000** | **~60,000 v6 frames**

v6 on hoop crop: ~60,000 frames × 2 films. BODD full-frame only for trace (tiny fraction). **Estimated GPU time: ~20–30 minutes total** (v6 ~20–25 ms/frame on GPU, BODD trace negligible). Marked ESTIMATE — real time recorded in run log.

v6_confirm_window_ms from v1 goes away: v6 runs over the whole span continuously, so no separate confirm window is needed.

5. MEASURE

Finder times vs tags over the same Q1-Q3 / Notus Q1 span with find_shots_measure.match_shots, 8000 ms window: found / missed / extra, per kind (2PT/3PT/FT), timing error (median/max per kind); release trace + shooter box rate. Drop the "277 moments incl. fakes" measure. Adrian Q4 never read; blind run only after Scott sees the numbers.

Output dir: `Liberty_Shot_Outputs/rim_first/` (script refuses if exists).

6. MAKE/MISS SAFETY

Files and outputs the make/miss path uses (this spec touches NONE):
- `.team/shot_detectors/make_review_queue_page.py` — builds coach review page
- `collect_q4_bodd.py` — collects Q4 v6 tracks (v6_ball function)
- `C:/Users/scott/AppData/Local/Temp/v6_tracks.json` — Adrian Q1–Q3 v6 tracks (111 entries)
- `C:/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json` — Notus Q1 v6 tracks (31 entries)
- `Liberty_Shot_Outputs/q4_guard/v6_tracks_q4.json` — Adrian Q4 v6 tracks
- `Liberty_Shot_Outputs/ball_arc/d1_results.json` — D1 results for Adrian Q1–Q3
- `Liberty_Shot_Outputs/d2_train/test2/d2_results.json` — d2v1 results for Adrian Q1–Q3
- `Liberty_Shot_Outputs/review_queue/q4/v6/results.json` — v6 Q4 results
- `Liberty_Shot_Outputs/review_queue/q4/d2v1/results.json` — d2v1 Q4 results
- V6 weights: `C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt`
- BODD weights: `C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt` (used only for hoop samples in collect_q4_bodd.py)

Check before and after this spec's run:
```
.venv/Scripts/python.exe .team/shot_detectors/make_review_queue_page.py --wide-combined --out-dir <NEW>
```

Verify output:
- `gray=30 orange=9` for Adrian + Notus (42 shots shown on page)
- Combined groups match page_v6 (printed "combined groups (film, times, first, last, length)")

There is no "v6 mapping check" print — remove it. Make/miss files untouched.

If any check differs → STOP, Scott decides.

7. CODE

New scripts under `.team/shot_detectors/` (pure functions + tests):

- `rim_first_finder.py` — v6 crop over whole span, two triggers, merge, emit shot moments JSON. Takes only video path(s) + model paths + out dir. Reads NO tags, NO scoreboard, NO DB.
- `rim_first_trace.py` — BODD full-frame trace back from confirmed crossing to shooter box + floor spot.
- `rim_first_measure.py` — Load finder moments + tags + fakes, run matching (8000 ms), compute measure tables. ONLY script that reads tags.

Rules:
- No core edits (event_generator.py, ai_bridge.py, court_memory.py, net_detector.py untouched)
- No training (uses existing v6 and BODD weights)
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter (as defined: shifting saved hoop position inside MAKE rule)
- No tuning after results — all numbers fixed before run (section 8 table)
- DB read-only (mode=ro for fake shots)
- Images local only (minors to `Liberty_Shot_Outputs/rim_first/debug/`)
- Output dir `Liberty_Shot_Outputs/rim_first/` — script refuses if exists
- Finder separate from measure (provable: finder takes only video+model+out)

8. NUMBERS TABLE (only numbers this plan uses)

Number | Value | Source / Decision
--- | --- | ---
v6 crop hx± | 260 px | collect_q4_bodd.py:121–125
v6 crop hy- | 200 px | collect_q4_bodd.py:121–125
v6 crop hy+ | 240 px | collect_q4_bodd.py:121–125
v6 conf | 0.28 | collect_q4_bodd.py:121–125
v6 imgsz | 640 | collect_q4_bodd.py:121–125
v6 continuity prev* | 0.35 | collect_q4_bodd.py:49
MAKE half | 0.55 hoop_w | collect_q4_bodd.py is_make (line 49), ai_bridge.py:1033
MAKE drop | 180 px | collect_q4_bodd.py is_make (line 49)
MAKE gap | 8 frames | collect_q4_bodd.py is_make (line 49)
MAKE widths | 2.2/0.9/1.3 hoop_w | collect_q4_bodd.py is_make (line 49)
MISS rim zone | 0.735 hoop_w | spec 33 Scott-approved; court_memory.py:165 (rim_r=72 / 98)
MISS at/above rim | y <= hoop_y + 40*hoop_w/98 | court_memory.py:190 scaled
MISS coming down | was above hoop_y earlier in same v6 run | this spec
merge_window_ms | 300 ms (proposed) | Scott decides before the run
release_trace_factor | 0.6 | spec 33 Scott-approved
match_window_ms | 8000 ms | manual_tag_teach.py:18, spec 33
BODD trace conf | 0.12 | collect_flight_tracks.py:311–312
BODD trace imgsz | 960 | collect_flight_tracks.py:311–312
Hoop per frame | same frame, else most recent earlier, else next later | shot_rules_measure.hoop_at

9. ROLES & GATES

- Cursor codes the three scripts + tests (pure functions, hand-made tracks).
- Claude Code vets: no core edits, matching logic correct (8000 ms window, find_shots_measure.match_shots), window fixed before run, output dir refusal, no gap filling, "Scott decides" numbers recorded, hoop-relative units used, no tracker_id, teammate part excluded, make/miss safety check before/after, finder takes ONLY video+model+out.
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS. A DISAGREE stops the loop for Scott.
- Stop for Scott with the table of "Scott decides" numbers (section 8: merge_window_ms proposed 300 ms).

10. FACT SOURCES

Every fact above comes from a file read this session or the prompt. Otherwise: "NOT FOUND - Claude Code to check".

Key lines read this session:
- collect_q4_bodd.py:49 (is_make), 110–146 (v6_ball crop, conf 0.28, imgsz 640, prev*0.35)
- collect_flight_tracks.py:311–314, 340–382 (BODD full-frame, v6 crop)
- court_memory.py:165 (rim_r=72.0), :190 (dist <= rim_r and y <= hoop_y + 40), :150 (close_to_rim max_dist=280)
- ai_bridge.py:1033 (0.55*hoop_w crossing)
- manual_tag_teach.py:18 (MATCH_TOLERANCE_MS=8000)
- .team/specs/33_shot_flight_rules_measure_spec.md (spec 33 full, Scott-approved numbers, results)
- shot_rules_measure.hoop_at (hoop position per frame logic)
- OLLAMA.md / DETECTOR_PROPOSAL_REJECTION.md / AGENT_OPERATIONAL_PROTOCOL.md (banned trials)
- .team/shot_detectors/make_review_queue_page.py (coach page, gray/orange logic, wide-combined output)
- ffprobe: Adrian 1920×1080@25fps, Notus 1280×720@25fps
- Tag counts: Adrian 127 total (Q1:44, Q2:25, Q3:40, Q4:18), Notus 31 total (Q1:31)
- Spec 33 results: SHOT/AIRBALL only Adrian 33/109, Notus 5/31; fakes removed well; release trace-back 36/38