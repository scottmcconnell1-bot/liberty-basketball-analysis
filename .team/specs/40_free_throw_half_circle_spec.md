VETTED WITH CONDITIONS by Claude Code, 2026-11-06: v1 read against Scott's FT rule (memory free-throw-rule), stage1b_court_lines.py build_paint_mask :118 and yaml, rim_first_finder.py retrace, run39 facts. Q1-Q9 OVERRIDE the text below. Settings fixed by Claude Code before code and run (Scott: Claude Code picks settings).
Q1 Stillness: window [trigger-3000 ms, trigger-1000 ms] (the measured 1-3 s); still when the MEDIAN over players of per-player move per second (nearest-box match, frames 25 apart, every 5 frames) <= STILL_MOVE_MAX 0.15 player heights. Not "every player" (a walking referee or a player taking his lane spot would break it).
Q2 Region is NOT guessed from the hoop (the camera is side-on; "toward mid-court" is a diagonal). Candidates = players the ball was inside (release 0.6) at least once in [trigger-3000, trigger], after spec-39 merge and referee drop. For each candidate, on the still frame nearest trigger-1000 ms: region = square centred on the candidate's feet (box bottom-centre), half-size REGION_HALF 2.0 x that player's box height.
Q3 Paint: build_paint_mask from stage1b_court_lines.py with its yaml, imported read-only; gym name per film from CLI --gym (adrian | liberty); one setting per gym, no tuning.
Q4 Fit: remove straight segments (HoughLinesP with the yaml parameters, erase segments longer than 1.0 player height), then RANSAC ellipse on the remaining paint pixels: 300 tries, random.Random(40), 5-point cv2.fitEllipse, inlier if |ellipse distance| <= 3 px x (frame width / 1280); accept when inliers >= 40, major axis between 1.2 and 4.0 player heights, minor/major >= 0.15. No homography, no whole-court fit.
Q5 FT decision: still AND ellipse accepted AND exactly one player's feet (all players on that frame after merge + referee drop) inside the ellipse AND that player is a candidate (ball was in his hold circle) -> free_throw true, shooter = that player (override). Still but no ellipse for any candidate -> orange "ft_circle_not_found". Ellipse but 0 or 2+ feet inside -> no flag, trace unchanged.
Q6 Retrace gets --video and --gym; the video is opened only for still moments (one frame each). Live run uses the same function.
Q7 Mask check BEFORE the measured run: Cursor's code writes local debug images (paint mask + accepted ellipse) for 6 calibration FT moments from the spec-38 sample (3 per film; Claude Code names them). Claude Code looks; if the arc is not in the mask on 2 of 3 per gym, STOP for Scott - no tuning.
Q8 Measure (rim_first_measure.py may add an ft section): free_throw flags vs FT tags (found / missed / false), non-FT moments flagged free_throw (target 0), orange ft_circle_not_found count. Hand-check seed 40: up to 10 flagged FT moments per film NOT in the spec-38/39 samples, verdicts written before reading numbers.
Q9 NFHS facts used: FT circle radius 6 ft, FT line 15 ft from backboard (stage1b yaml: ft_circle_radius_ft 6.0, ft_line_y_ft 13.75 from hoop). Player height as the ruler; no ft-per-pixel needed.

FREE THROW HALF CIRCLE SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto.
File: .team/specs/40_free_throw_half_circle_spec.md (new file only; nothing else edited).
Cursor edits rim_first_finder.py / test_rim_first.py and one new file .team/shot_detectors/ft_half_circle.py, plus its tests (test_rim_first.py or test_ft_half_circle.py). No other file touched.

1. GOAL (Scott 2026-11-06, binding)
Scott: "The FT line ... is actually a half circle. The FT shooter will always be in that half circle by him or herself when shooting freethrows."
Scott: "I wouldn't go with player space ... I would use the half circle. If there is no player movement and one is in the half circle, then players are preparing for a free throw."
Add a video-only FT detector: stillness plus exactly one player's feet inside a detected FT half circle flags the moment free_throw and sets shooter = that player. It overrides the trace shooter only for free_throw moments; everything else untouched. Claude Code chooses every number before the run (Scott: aim for higher results); no tuning after results.

2. FACTS (each from a file read this session or the prompt; otherwise NOT FOUND - Claude Code to check)
- Stillness 1-3 s before the rim trigger, median per-player move per second in player heights (nearest-box match, frames 1 s apart): FT 0.11 (n 38, Q3 0.13, max 0.55), 2PT 0.42 (n 56, Q1 0.32), 3PT 0.38 (n 30, Q1 0.28) (.team/drift_log.md:179).
- Hand-checked FTs from both samples, 21 FTs: current trace right 8/21; a lane player is picked or the card goes orange (.team/drift_log.md:177).
- "Most isolated player" rule: right FT shooter 16/21 but changed 21/30 right non-FT picks - REJECTED by Scott; never used (.team/drift_log.md:177).
- Full-court line fit (Stage 1b, frozen): 0 of 60 frames, Adrian and Notus - do NOT fit the whole court; target only the FT half circle in front of the hoop the shot goes to, on still frames (.team/stage1b_frozen_0943/measurement_report.md, top lines).
- Half circle painted: Adrian gym black, Notus gym red; FT lane lines painted: Adrian white, Notus blue/red (Claude Code looked at frames).
- Saved per frame: BODD player/ball/referee boxes, hoop box per series (frames.json); video files local (uploads/...); film of minors stays local.
- rim_first_finder.py: trace_shooter :938, _trace_walk_back :782, emit_moments :1590, RELEASE_TRACE_FACTOR 0.6 :75, TRACE_BEFORE_MS 3000 ms :73, referee boxes key "r", players key "p", hoop per series, is_referee_player :576, _box_xyxy centre-based boxes :491, floor spot = box bottom-centre :776.
- stage1b_court_lines.py: build_paint_mask :118 (gym colour split), extract_lines :185 (Canny + HoughLinesP), CourtModel :276 with ft_circle structure :299-303 and ft_circle_radius_ft / ft_line_y_ft court constants, analyze_frame :652 fits a whole-court homography per frame (the approach to avoid here).
- NFHS: FT line 15 ft from the backboard (NOT FOUND in repo; Claude Code to confirm; ft-per-hoop-width NOT FOUND).
- Spec 39: settings fixed by Claude Code before the run, no change after results (.team/specs/39_shooter_fix_spec.md SETTINGS FIXED block).

3. SECTION A - FT DETECTOR (VIDEO ONLY)
Per moment, after the trace, only when the moment is still:
- Stillness: in [trigger - STILL_WINDOW_MS, trigger], measure each detected player's median move per second between frames 1 s apart, in player heights, nearest-box match. Moment is still when every player present is at or below STILL_MOVE_MAX. Not still -> no FT test, moment untouched.
- Still -> run the half circle finder (B) on the still frame, region from the hoop box of the series.
- Circle found and exactly one player's feet (box bottom-centre) inside the half circle -> moment free_throw = true, shooter = that player (overrides the trace shooter), shooter_box = that player's box.
- Circle found with zero or more than one player inside -> not an FT, no override, no guess which player.
- Stillness holds but the half circle is not found -> orange "ft_circle_not_found"; never guess a circle.
Applies to make and rim moments alike; shot calls, make/miss, and hoop steps untouched.

4. SECTION B - HALF CIRCLE FINDER (SMALLEST THING THAT WORKS)
One still frame, one hoop box:
1. Region from the hoop box. FT line is 15 ft from the backboard; the half circle sits in front of the hoop the shot goes to, centred on the FT line, radius 6 ft. Region: x in [hx - REGION_HALF_W * hoop_w, hx + REGION_HALF_W * hoop_w], y from hoop centre to hoop centre + REGION_DEPTH * hoop_w toward mid-court. Proposed REGION_HALF_W 3 hoop widths (covers the 12 ft circle width once ft-per-hoop-width is known) and REGION_DEPTH 6 hoop widths (reaches toward the 15 ft FT line); both fixed by Claude Code before the run. ft-per-hoop-width NOT FOUND - measured from frames.json hoop boxes before the run. Image direction "toward mid-court" confirmed on the first still frames (NOT FOUND yet).
2. Painted-line pixels by colour/edges. Reuse build_paint_mask (stage1b_court_lines.py:118): gym branch for Adrian (white top-hat + dark black-hat) and liberty (red/blue HSV). Gym colour known without a hand setting: on the first still frame where the region yields line pixels, classify the dominant line colour (dark vs red vs blue vs white) and cache it per gym; Adrian = dark half circle, Notus = red half circle per the frames Claude Code already looked at. Needs <= 3 still frames per gym, frozen before the run; if auto-classification is unclear, one hand-set colour per gym (Claude Code's pre-run choice).
3. Fit. Canny edges on the region paint mask (reuse extract_lines edge scale, stage1b_court_lines.py:185-261), then cv2.fitEllipse on the edge points - NEW, no homography, no whole-court fit (0 of 60 frames Stage 1b). Keep the half of the ellipse nearest the hoop centre (the painted half faces the hoop). Validate: ellipse axes sane, centre inside region, enough edge pixels on the arc; else circle not found.
4. Feet test. Point-in-half-ellipse for each player's box bottom-centre (x, y + h/2, centre-based boxes as in _box_xyxy :491). Exactly one inside -> shooter.
Reused from stage1b_court_lines.py: build_paint_mask (paint extraction), extract_lines Canny/Hough parameter scale, CourtModel ft_circle_radius_ft / ft_line_y_ft court constants only (no homography fit, no analyze_frame). New: ft_region, gym colour auto-detect, ellipse fit + half selection, point-in-half-ellipse, ft_half_circle.py module. No trained model, no tracker, no interpolation.

5. SECTION C - WHERE IT PLUGS IN
New function in .team/shot_detectors/ft_half_circle.py called from emit_moments (rim_first_finder.py :1590) right after trace_shooter returns and before assign_shot_calls, for still moments only. It adds free_throw to the moment and overrides moment["shooter"] / shooter_box only when exactly one player is inside the half circle; orange "ft_circle_not_found" when still but no circle. Shot calls (assign_shot_calls), make/miss (is_make), hoop steps, and every non-FT moment untouched. Finder reads video frames, boxes, and hoop only - no tags, no scoreboard, no database. No new tags.

6. SECTION D - MEASURE
- Tags only to measure: FT tags vs free_throw flags -> found / missed / false counts.
- FT shooter right/wrong on a NEW frozen hand-check sample, seed 40 (random.Random(40) on the sorted t_ms list), FT moments not in the spec-38/39 samples where possible; same hand-check format as spec 39 (release frame with shooter box drawn, plus release-10 and release+5 frames), written to .team/specs/40_handcheck_results.json before any numbers are read.
- Non-FT moments wrongly flagged free_throw: counted, must be near 0 (proposed cap <= 1, fixed by Claude Code before the run).
- Q4 blind only after Scott sees these numbers.

7. SECTION E - 3-POINT ARC (LATER, NOT THIS RUN)
Same finder extends: region set by the hoop box, much wider and deeper (3PT arc radius ~19.75 ft NFHS, centred at the hoop, in front of it), painted-line pixels by colour/edges, same gym colour auto-detect, ellipse/arc fit, no stillness needed (players move around the arc). Reuse CourtModel three_pt_arc structure (:312) for geometry constants. Whether the 3PT arc is painted in these gyms is NOT FOUND - Claude Code to check on frames.

8. SECTION F - NUMBERS TABLE (each number: source, or fixed by Claude Code before the run + proposed value + reason)
STILL_WINDOW_MS - TRACE_BEFORE_MS reuse (rim_first_finder.py:73) - 3000 ms [trigger-3000, trigger], matches the 1-3 s stillness fact
STILL_MOVE_MAX - drift_log.md:179 FT 0.11 median, Q3 0.13, max 0.55 vs 2PT Q1 0.42 / 3PT Q1 0.38 - proposed 0.15 player heights/s, all players in the window at or below
REGION_HALF_W - NFHS 15 ft FT line, half circle radius 6 ft - proposed 3 hoop widths each side of hoop centre x
REGION_DEPTH - 15 ft backboard to FT line - proposed 6 hoop widths toward mid-court; ft-per-hoop-width NOT FOUND, Claude Code sets before the run
GYM_COLOUR_FRAMES - Adrian black / Notus red half circle (frames) - auto from <= 3 still frames per gym, frozen; one hand-set colour per gym only if auto fails
FT_CIRCLE_R_FT - NFHS, NOT FOUND in repo - proposed 6 ft
NON_FT_FT_FALSE_CAP - measure rule "near 0" - proposed <= 1 non-FT moment wrongly flagged free_throw
HANDCHECK_SEED - spec 39 seed 39 pattern - seed 40, FT moments outside spec-38/39 samples where possible

9. RULES
No core edits (court_homography.py and stage1b_court_lines.py read only). No training, no tracker, no interpolation. No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows (OLLAMA.md:31-39), wider column, hoop recenter. Finder reads no tags, no scoreboard, no DB. One try, then stop for Scott. Cursor edits rim_first_finder.py / test_rim_first.py and ONE new file .team/shot_detectors/ft_half_circle.py (+ tests). Every fact from a file read this session or above; otherwise "NOT FOUND - Claude Code to check".
