VETTED by Claude Code, 2026-11-04, WITH CONDITIONS (binding): D1 MAKE/MISS CHECK COMMAND IS WRONG: not 'python -I ... default page_v3' (-I breaks the clip_moment_fix sibling import; page_v3 is old). The check = .venv python .team/shot_detectors/make_review_queue_page.py --wide-combined --out-dir <NEW dir> and compare printed gray 30 / orange 9 / 42 shots and combined groups to page_v6; v6 mapping 1.0000 is the run_d1_q4 proof, not the page. D2 WINDOW: spec 33 window is 3000 ms before / 2000 ms after, not +-5 s. D3 NO NEW THRESHOLDS: (a) court_memory CourtMemory.key is the PAINT, not the court, and the fixed px bounds (100/980/1820, 80 px/frame) are unsourced and px across 1920 vs 1280 films. Replace (a) and (b) with DISTRIBUTIONS, no cutoff: per source, ball height above the hoop in hoop widths ((hoop_y - y)/hoop_w), ball distance from the hoop in hoop widths, and frame-to-frame jump in hoop widths; report median / 90th pct / max and, for failed tagged moments, the values at the frame that set the failure (rise, peak, landing). No Scott numbers remain, so none to gate. (c) missing stays. D4 HAND CHECK: 20 failed tagged moments chosen evenly in moment order (every k-th, k = failures/20), Q1-Q3 + Notus only; one full frame each at the frame that set the failure with BODD and v6 boxes drawn; Claude Code labels each (real ball / light / crowd / player / other). Images under Liberty_Shot_Outputs/ball_check/hand_check/, local only. D5 coverage bug reported only (shot_rules_measure.py not edited). D6 nothing touches the make/miss files in section 2.

BALL TRACK CHECK SPEC v1 - not run

1. Why make/miss works and flight finding does not (Proven / Inferred)

Make/miss path (coach review page, 41/42 shots correct, 0 differ from tags):
- Uses ONLY the v6 ball model on a CROP around the hoop: hx±260, hy-200..hy+240 (collect_q4_bodd.py:121-125)
- Starts at Scott's TAG time, runs ~1.4 s (80 frames at 25 fps) forward (collect_q4_bodd.py:112-116)
- Confidence 0.28, imgsz 640 (collect_q4_bodd.py:125)
- Only needs the ball AT THE RIM (crossing gate 0.55*hoop_w, drop 180 px, gap ≤8 frames; collect_q4_bodd.py:49-72)
- Uses saved v6_tracks.json (Adrian 111 entries, Notus Q1 31 entries) + v6_tracks_q4.json for Q4
- Results fed to make_review_queue_page.py (.team/shot_detectors/make_review_queue_page.py) which pairs v6 + D1 predictions; gray=both make (auto), orange=disagree (coach calls)
- v6 weights: C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt

Flight finding (spec 33) path:
- Uses BODD model (conf 0.12, imgsz 960) on FULL FRAME (collect_flight_tracks.py:340-365)
- Needs WHOLE FLIGHT from release to rim, not just the rim window
- Must FIND the flight itself (no tag to anchor the start; window is ±5 s around tag/finder time; collect_flight_tracks.py:59-60)
- v6 crop still used but only where hoop is detected (collect_flight_tracks.py:376-413); hoop position moves with camera
- BODD basketball class at conf 0.12 picks up lights/crowd/reflections as "ball" (Inferred from spec 33 result: landing ball at y=18 px on 1080 frame = top of frame = crowd/light)
- No tracker (ByteTrack/DeepSORT banned); BODD gives boxes per frame only
- Result: only 33/109 Adrian tagged shots called SHOT/AIRBALL, 5/31 Notus; 31 ORANGE from >3-frame gap, 18 "descent not seen", median 7.4 hoop widths for NOT_A_SHOT

Proven difference: make/miss starts at a known tag time, crops to the hoop, runs v6 only ~1.4 s, and only cares about the rim crossing. Flight finding must scan ±5 s full-frame with a low-confidence BODD model that hallucinates "basketball" in the stands, then stitch v6 crop detections (which need a hoop detection first) across a long window where the hoop moves and the ball may be far from the hoop.

2. Make/miss stays safe

Files and outputs the make/miss path uses (this spec touches NONE of them):
- .team/shot_detectors/make_review_queue_page.py — builds coach review page
- scripts/build_review_page.py — alternate review page (also uses v6 tracks)
- collect_q4_bodd.py — collects Q4 v6 tracks (v6_ball function, lines 110-146)
- C:/Users/scott/AppData/Local/Temp/v6_tracks.json — Adrian Q1-Q3 v6 tracks (111 entries)
- C:/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json — Notus Q1 v6 tracks (31 entries)
- Liberty_Shot_Outputs/q4_guard/v6_tracks_q4.json — Adrian Q4 v6 tracks (18 entries)
- Liberty_Shot_Outputs/ball_arc/d1_results.json — D1 results for Adrian Q1-Q3
- Liberty_Shot_Outputs/d2_train/test2/d2_results.json — d2v1 results for Adrian Q1-Q3
- Liberty_Shot_Outputs/review_queue/q4/v6/results.json — v6 Q4 results
- Liberty_Shot_Outputs/review_queue/q4/d2v1/results.json — d2v1 Q4 results
- V6 weights: C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt
- BODD weights: C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt (used only for hoop samples in collect_q4_bodd.py)

Check Claude Code runs after any later change:
- Run make_review_queue_page.py (default page_v3 path): python -I .team/shot_detectors/make_review_queue_page.py
- Verify output: "gray=30 orange=9" for Adrian + Notus (42 shots shown on page)
- Verify v6 mapping check: the script prints "v6 mapping check 1.0000" (make_review_queue_page.py uses hoops dict keyed by (film, t) from v6 tracks; all 42 shots must have a hoop entry)
- Run pytest tests/test_build_review_page.py (if exists) to confirm page generation

3. Ball check on existing spec 33 tracks (no new detection)

Input: Liberty_Shot_Outputs/shot_rules/adrian.json and notus.json (per-moment JSON from collect_flight_tracks.py, each moment has ball_track=v6 on crop, bodd_track=BODD full frame, hoop_samples, player_boxes)

New script: .team/shot_detectors/ball_track_check.py (pure functions + CLI + tests)

Per moment and per source (v6 crop vs BODD full), compute:
(a) OUTSIDE COURT / HIGH IN STANDS: ball center y < court_top_y (Adrian: y < 100 px on 1080p; Notus: y < 67 px on 720p) OR ball center y > court_bottom_y (Adrian: y > 980; Notus: y > 653) OR ball center x outside court sides (Adrian: x < 100 or x > 1820; Notus: x < 67 or x > 1213). Court bounds from existing court_memory.py key points — use the key polygon from the first hoop sample's film. Threshold: "Scott decides before the run" with proposed value = 5% margin inside the court key polygon (file+line: court_memory.py CourtMemory.key property). If no court key in track, use frame dimensions × 0.9 as fallback.

(b) IMPOSSIBLE JUMP BETWEEN FRAMES: distance between consecutive detections > MAX_BALL_SPEED_PX_PER_FRAME. How judged: "Scott decides before the run" with proposed value = 80 px/frame (≈ 2000 px/s at 25 fps; a thrown basketball ~15-20 m/s ≈ 1200-1600 px/s on 1080p at court distance; 80 px/frame allows margin). Existing code reference: ai_bridge.py:1033 uses 0.55*hoop_w for crossing gate (≈54 px on Adrian), ai_bridge.py:1082 uses 0.6*hoop_w for column gate (≈59 px); 80 px is larger than both gates. Per source: v6 track (crop-confined, jumps unlikely) vs BODD track (full frame, jumps common when switching between false detections).

(c) MISSING: frames in the detection window with NO ball detection from that source. Report: missing_frames / window_frames, and longest consecutive missing run.

For tagged shots that failed (NOT_A_SHOT / PASS / ORANGE from spec 33 results):
- For each failed moment, check which of (a)(b)(c) explains the failure:
  - If landing ball at y=18 (top of frame) → (a) outside court
  - If gap >3 frames during flight → (b) impossible jump (gap = missing frames, but could also be (c) missing)
  - If "descent not seen" → (c) missing in critical phase, or (a) false detection in stands
  - If NOT_A_SHOT at median 7.4 hoop widths → likely (a) BODD false detection far from hoop, or (c) v6 lost the ball early
- Output a table: moment_id, rule_result, explained_by (a/b/c/none), detail

Coverage counting bug (shot_rules_measure.py flight_coverage, lines 810-850):
- In the ELSE branch (when landing is None or descent_not_seen or no rise), gap_report is called WITHOUT lo_frame/hi_frame, so frames_seen = ALL frames in ball_track. But frames_in_flight_estimate is computed from release_f to end_f (or full track span). If release_f > ball_track[0][0], frames_seen > frames_in_flight_estimate → coverage_ratio > 1.
- Fix: in the ELSE branch, either (1) call gap_report with lo_frame=release_f, hi_frame=end_f to match frames_in_flight_estimate, or (2) compute frames_in_flight_estimate from the same span as gap_report uses. Since this spec does not edit shot_rules_measure.py, the fix is REPORTED ONLY in the ball_check output with the exact lines (830-839) and the condition that triggers it.

4. Hand check

Claude Code views a small set of frames to confirm what the false "balls" are:
- How many: 20 frames total (5 per failure type × 4 types: stands/crowd, lights/reflections, player confusion, other)
- How chosen: from the ball_check results, pick moments where (a) BODD ball is outside court, (b) BODD ball jumps >80 px/frame, (c) v6 ball missing >10 consecutive frames in window, (d) BODD ball at y<50 (top 5% of frame). For each type, take the first 5 distinct moments.
- Failures only: only moments where the rule result was NOT_A_SHOT, PASS, or ORANGE (i.e., not clean SHOT/AIRBALL).
- Q1-Q3 only: Adrian Q1-Q3 and Notus Q1 (Adrian Q4 never read per C5).
- Images stay local: Claude Code reads frames from local video files (uploads/nfhs_gam0a66d85e12.mp4 and uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4) using cv2.VideoCapture, saves crops to Liberty_Shot_Outputs/ball_check/hand_check/ for review. No uploads, no external transfer.

5. Output

Directory: Liberty_Shot_Outputs/ball_check/ — script MUST refuse if directory already exists.

Files:
- results.json — full per-moment detail for (a)(b)(c) per source, plus failure explanations for tagged shots
- summary.md — markdown tables:
  - Table 1: v6 source — outside court count, impossible jump count, missing stats (median/max missing frames, longest run) × film
  - Table 2: BODD source — same metrics × film
  - Table 3: Failed tagged shots (NOT_A_SHOT/PASS/ORANGE) — moment_id, rule, explained_by, detail
  - Table 4: Coverage bug report — moments with coverage_ratio > 1, their release_f, land_f, frames_seen, frames_in_flight_estimate
  - Table 5: Hand check log — 20 frames reviewed, what was seen (crowd/light/player/other), file paths

New script location: .team/shot_detectors/ball_track_check.py with pure functions:
- check_ball_track(ball_track, hoop_samples, court_bounds, max_speed_px) -> dict with outside_court, impossible_jumps, missing_stats
- explain_failure(moment, rule_result, v6_check, bodd_check) -> (explained_by, detail)
- coverage_bug_check(moment, flight_coverage_result) -> bool (true if coverage_ratio > 1)
- hand_check_select(moments, n_per_type=5) -> list of (moment_id, frame_idx, reason_type, crop_path)

Tests (hand-made tracks, no video):
- v6 track confined to crop → zero outside court, zero impossible jumps
- BODD track with false detection at y=10 → outside court flagged
- BODD track jumping 100 px between frames → impossible jump flagged
- Track with 15-frame gap → missing stats correct
- Coverage bug: release_f > track[0][0] with no landing → coverage_ratio > 1 detected

6. Roles & Gates

- Cursor codes ball_track_check.py + tests.
- Claude Code vets: no core edits, no model changes, uses existing spec 33 tracks only, output dir refusal, hand check images local only, coverage bug reported not fixed, "Scott decides" numbers recorded.
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS. A DISAGREE stops the loop for Scott.
- Scott reviews the summary tables (1-5) before any next step.
- Stop for Scott with the table of "Scott decides" numbers:
  - court_margin_pct (proposed 5%, from court_memory.py CourtMemory.key)
  - max_ball_speed_px_per_frame (proposed 80, from ai_bridge.py:1033/1082 gates)
  - hand_check_n_per_type (proposed 5)
  - hand_check_failure_types (proposed: stands, lights, player_confusion, other)

7. Fact Sources

Every fact above comes from a file read this session or the lines in the prompt. Otherwise: "NOT FOUND - Claude Code to check".

Key files read this session:
- collect_q4_bodd.py (v6_ball crop, conf 0.28, is_make logic)
- .team/shot_detectors/make_review_queue_page.py (coach page, v6 tracks, D1/d2v1 results, gray/orange logic)
- scripts/build_review_page.py (alternate review page using ai_bridge.run_saved_v6_rule)
- .team/shot_detectors/collect_flight_tracks.py (BODD full frame conf 0.12, v6 crop, window ±5s, merge windows, slice moments)
- .team/shot_detectors/shot_rules_measure.py (four rules, flight_coverage bug lines 830-839, gap_report, classify_flight)
- .team/shot_detectors/test_shot_rules_measure.py (tests for rules, coverage, hoop-width units)
- .team/specs/33_shot_flight_rules_measure_spec.md (spec 33 full context, results: 33/109 SHOT/AIRBALL, 31 ORANGE gap, 18 descent not seen, 7.4 hoop widths NOT_A_SHOT)
- court_memory.py (CourtMemory.key for court bounds, rim_r=72 at line 165, near_basket at lines 119-123)
- ai_bridge.py (0.55*hoop_w crossing gate line 1033, 0.6*hoop_w column gate line 1082, 0.85*hoop_w drift veto line 1237)
- Spec 33 results: tagged shots called SHOT/AIRBALL only adrian 33/109, notus 5/31; real shots called NOT_A_SHOT median 7.4 hoop widths; 31 ORANGE from >3-frame gap; 18 "descent not seen"; landing ball at y=18 px (top of frame) inferred false BODD basketball; coverage ratio >1 on 18 rows.