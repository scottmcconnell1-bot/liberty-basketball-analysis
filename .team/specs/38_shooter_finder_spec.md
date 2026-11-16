VETTED WITH CONDITIONS by Claude Code, 2026-11-06: v1 read against rim_first_finder.py (trace_shooter, slice_trace_window), shot_rules_measure.py (:132, :163, :270, :37-45), OLLAMA.md, AGENT_OPERATIONAL_PROTOCOL.md:45, run37 read-only check. S1-S8 OVERRIDE the text below.
S1 "Early windows" IS defined: OLLAMA.md:31-39 - the MAKE-detection window started 2 s earlier for missed makes (0 of 7). The backward walk changes no make or shot window; it walks inside the Scott-approved 3000 ms trace window. Not banned. OLLAMA.md is in the repo.
S2 Start point: release_estimate_frame; if None, the latest detected ball point at or before the trigger (same window). "no release frame" orange only when the window has no ball point at all.
S3 Measure 1 (FT spot) uses the floor spot relative to that moment's hoop in hoop widths ((fx-hx)/hw, (fy-hy)/hw), never raw pixels (camera pans/zooms). Report per hoop: median distance of each FT floor spot from the per-hoop median FT spot. Proposed pass line 1.5 hoop widths - Scott decides before the run.
S4 Measure 2 (3PT vs 2PT) is report only, same hoop-width units; picture perspective noted as a limit.
S5 Hand-check sample fixed before the run: per film, seed 38, 20 tag-matched moments with shooter found (stratified 2PT/3PT/FT as available) + 5 orange. Claude Code views still frames locally (scratchpad only; minors) and writes agree/disagree/unclear per moment to a JSON before reading the measure output. Count is Scott decides (proposed 20 + 5).
S6 No video: add retrace mode to rim_first_finder.py that reads saved moments.json + frames.json (run37_*), rebuilds the per-series hoop samples by re-running the same hoop steps on saved "h" (band, collapse, dedupe, carry, pairing - no model), takes v6 points from saved series rows, re-runs ONLY the shooter trace, and writes a NEW dir (rim_first/run38_adrian, run38_notus; refuse if exists). Shot calls and every other moment field copied unchanged. Gate: with the backward walk switched OFF, retrace must reproduce run37 status/reason/release_frame for every moment and the rebuilt series count/ref_x must match saved series rows; any difference -> STOP for Scott.
S7 Measure (rim_first_measure.py): shooter found/orange by reason, found split by series, Measures 1-3, and a side-by-side list (moment time, tag player, floor spot) for Scott's review. No tag read by the finder or retrace.
S8 Numbers needing Scott before the run: track-break gap 8 frames (existing MAKE_GAP_FRAMES; proposed keep), FT pass line 1.5 hoop widths, hand-check 20 + 5 per film. All others existing/Scott-approved. One try; Q4 blind (saved run37_adrian_q4_blind frames) only after Scott sees the numbers.
SCOTT APPROVED S8, 2026-11-06: "Yes" - track-break gap 8 frames, FT pass line 1.5 hoop widths, hand-check 20 found + 5 orange per film. Order: shooter step first, then a 3-point line + referee arm-signal plan (Hermes) next.

SHOOTER FINDER SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto.
File: .team/specs/38_shooter_finder_spec.md (new file only; nothing else edited).
Cursor edits rim_first_finder.py (trace only), test_rim_first.py, rim_first_measure.py (shooter measures).

1. GOAL (Scott, agreed plan)

After the shot finder (spec 35/36/37, rim_first_finder.py), find the SHOOTER of each shot moment from video only: shooter box at release and floor spot (bottom-centre of the box, picture pixels). The finder still reads no tags, no scoreboard, and no database.

2. WHAT IS TRUE (read this session; anything else is "NOT FOUND - Claude Code to check")

- run37 (one try, no number changed): Adrian 116 moments, Notus 36 moments; found 97/109 and 27/31; shooter trace fell to Adrian 10/116, Notus 8/36 (drift_log.md lines 153-156).
- On the not-found moments: "ball not inside a player box" 85 (Adrian) / 18 (Notus), "no release frame" 21 / 10 (drift_log.md line 155).
- At the chosen release frame on those moments, the ball is above the head of the nearest player in 98% (Adrian) / 100% (Notus), median 0.64 / 0.71 player heights above the box top; nearest player centre is a median 1.2 / 1.3 x max(w,h) away (the hold circle is 0.6); chosen release frame is a median 1.04 s / 0.78 s before the rim trigger; where the shooter WAS found it is a median 2.96 / 2.98 s before (drift_log.md line 155).
- So release_estimate_frame (last ball frame before the ball first rises above the rim) picks a point already in flight; the true release is earlier (drift_log.md line 159).
- Spec 37 lowered found from 21/124 to 10/116 on Adrian; cause Unknown (inferred: fewer series means fewer v6 crops feeding the track) - spec 38 checks this by reporting found split by series with and without v6 points.
- ball_inside_player(mode="release"): distance ball centre to player box centre < max(w,h) * 0.6 (shot_rules_measure.py:132-153); release_trace_factor = 0.6 Scott-approved (shot_rules_measure.py:37-45, rim_first_finder.py:72).
- trace_shooter (rim_first_finder.py:474) today checks ball_inside_player on ONE frame - release_estimate_frame - then stops. No backward walk. slice_trace_window (rim_first_finder.py:449) builds the 3000 ms look-back window ending at the trigger (TRACE_BEFORE_MS = 3000, rim_first_finder.py:70; Scott-approved; do not widen it).
- combine_ball_track (shot_rules_measure.py:163-175): per frame, v6 if present else best-conf BODD; no average, no fill across gaps.
- MAKE_GAP_FRAMES = 8 (rim_first_finder.py:57, used at collect_q4_bodd.py:220).
- Saved run37 data: per-frame BODD balls/players/referees, per-series v6 points (drift_log.md: run37 frames.json + series points).
- "early windows" definition: NOT FOUND - Claude Code to check (AGENT_OPERATIONAL_PROTOCOL.md:45 and CLAUDE.md:28 ban it; neither defines it; OLLAMA.md is not in the repo).

3. A. THE RELEASE RULE (walk backward from the in-flight point)

For each moment whose series is a hoop (series_ok), inside the existing 3000 ms look-back ending at the trigger (TRACE_BEFORE_MS, not widened):

1. Build the ball track for the window: slice_trace_window gives v6 points and per-frame BODD balls; combine_ball_track picks v6 first, else best-conf BODD ball on that frame. No filling of missing frames - not interpolation.
2. Start at release_estimate_frame (the in-flight point: last ball frame before the ball first rises above the rim, shot_rules_measure.py:270).
3. Walk BACKWARD frame by frame along detected ball points only.
4. At each frame, for each player box on that frame (BODD players; referees excluded - BODD_CLASSES = basketball/hoop/player, referee separate, rim_first_finder.py:43 and :89), test ball_inside_player(ball, player, 0.6, mode="release"): distance < max(w,h) * 0.6.
5. First frame walking backward where the ball is inside a player box = the hold frame. That player is the shooter. Shooter box = that box. Floor spot = bottom-centre of the box in picture pixels: x = box.x, y = box.y + box.h / 2.0 (rim_first_finder.py:557 already computes this).
6. Stop at the first hold. One try, then stop.

What counts as "track breaks" (walk stops, moment goes orange):
- A gap between consecutive detected ball frames greater than MAKE_GAP_FRAMES (8) - or the Scott-decided number if he overrides before the run - breaks the walk; nothing earlier than the break can be the hold.
- A frame with no ball detection is a missing point, not interpolated; the walk continues to the next earlier detected point unless the gap to it exceeds the break threshold.
- The walk cannot go before lo_ms = trigger - 3000 ms (TRACE_BEFORE_MS boundary).
- No more detected points before the window start ends the walk without a hold.

If two or more player boxes satisfy the hold test on the same hold frame: do not pick by distance. Mark the moment orange "two players hold" (both boxes recorded for audit, no floor spot committed). The finder never guesses between two players.

4. B. WHAT GOES ORANGE (with reasons)

- "no release frame": release_estimate_frame is None (ball never rises above the rim in the window; current behavior, rim_first_finder.py:523).
- "no ball at release frame": the track has no detected point at that frame.
- "no player at release frame": no BODD player box on the hold frame.
- "ball not inside a player box": the walk reached the window start or a track break without ball_inside_player(mode="release") 0.6 ever passing.
- "track broken": gap > 8 (or Scott-decided number) between consecutive detected ball points before any hold was found.
- "two players hold": two or more player boxes pass the hold test on the hold frame.

Orange carries status = orange, shooter_box = null, floor_spot = null, release_frame = null (last frame checked kept for audit), reason recorded (shape _orange at rim_first_finder.py:562-569).

5. C. MEASUREMENT WITHOUT SCOTT HAND-TAGGING (Scott: "I do not want to manually tag video then you check my tags")

Use only what is already tagged: Adrian Q1-Q3 and Notus Q1 tags carry player name and 2PT/3PT/FT. Q4 stays blind until Scott sees the Q1-Q3 numbers.

Measure 1 - FT spot check: for FT tags, floor spots at one hoop should cluster within N hoop widths (N = Scott decides before the run; proposed 1.5 hoop widths). Report median FT floor-spot spread per hoop. Validates the floor spot with no new tags.
Measure 2 - 3PT vs 2PT distance: for found moments matched to tags (match_shots 8000 ms, spec 36), report floor-spot distance from the hoop in hoop widths, split by tag eventtype 2PT vs 3PT. Expect 3PT farther than 2PT; Scott decides the separation number before the run (proposed: report only, no threshold).
Measure 3 - timing: for found moments, release frame to trigger in seconds, split found vs not-found (run37 read-only check: ~1 s before trigger for not-found, ~2.96 s / 2.98 s for found, drift_log.md line 155).
Measure 4 - name agreement: requires a box-to-player label, which does not exist (NOT FOUND - new). Report box + floor spot side-by-side with tag.player for Scott's review page; Scott decides before the run whether to add a label and how.

Claude Code hand-check: a small fixed sample of still frames, local only, minors. Proposed before the run: 20 per film (40 total), chosen by fixed seed from found moments, stratified across 2PT/3PT/FT and across found/orange. Claude Code checks the hold frame vs the shooter box visually and records agree/disagree. Scott decides the count and selection before the run.

6. D. NUMBERS TABLE (each number with source, or "Scott decides before the run" + proposed value)

- TRACE_BEFORE_MS = 3000 ms - source: rim_first_finder.py:70; spec 33 Scott-approved (shot_rules_measure.py:40 detection_window_before_ms). Do not widen.
- MAKE_GAP_FRAMES = 8 frames - source: rim_first_finder.py:57 (is_make call collect_q4_bodd.py:220). Track-break threshold: gap > 8 between consecutive detected ball frames breaks the walk. Scott may override before the run (proposed: keep 8).
- release_trace_factor = 0.6 - source: shot_rules_measure.py:43 (SCOTT_APPROVED_2026_11_04), rim_first_finder.py:72; ball_inside_player mode="release" at shot_rules_measure.py:132-153 (distance < max(w,h) * factor).
- Hold test = ball_inside_player(mode="release") - source: shot_rules_measure.py:132.
- Ball track = combine_ball_track (v6 first, else BODD best-conf, no fill, not interpolation) - source: shot_rules_measure.py:163-175.
- Release start point = release_estimate_frame - source: shot_rules_measure.py:270; called at rim_first_finder.py:521.
- Floor spot = box bottom-centre - source: rim_first_finder.py:557.
- V6 crop - source: collect_q4_bodd.py:121-125 (rim_first_finder.py:45-49: HX 260 px, HY above 200 / below 240, conf 0.28, imgsz 640). BODD conf 0.12, imgsz 960 - rim_first_finder.py:40-41.
- Scott decides before the run (proposed values): track-break gap override = 8; FT spot clustering = 1.5 hoop widths across FTs at one hoop; 3PT vs 2PT separation = report only; Claude Code still-frame sample = 20 per film, fixed seed, stratified by kind and outcome.
- Proven results (read-only, not acceptance thresholds): run37 shooter found Adrian 10/116, Notus 8/36; "ball not inside a player box" 85/18; "no release frame" 21/10 (drift_log.md line 155). Spec 38 re-reports these after the change.

7. E. SCOPE

Cursor edits rim_first_finder.py (trace_shooter backward walk only), test_rim_first.py, rim_first_measure.py (shooter measures: hold rate, floor spot per moment, orange reasons). Shot calls, make/miss, and numbers from spec 36/37 are untouched.

Can it run from saved run37 frames.json + series points without video? Yes. The trace needs only ball points per frame (BODD plus per-series v6), player boxes per frame, hoop samples, and the trigger frame - all in the saved run37 frames.json / series points (per-frame BODD balls/players/referees, per-series v6 points). No model inference, no video decode. Applies to the build films (Adrian Q1-Q3, Notus Q1) and to the saved Q4 blind frames (rim_first/run37_adrian_q4_blind, drift_log.md lines 157-158). No video re-run is needed for the build films.

8. F. BANNED TRIALS

No linear interpolation, ByteTrack, DeepSORT, early windows, a wider column, hoop recenter (AGENT_OPERATIONAL_PROTOCOL.md:45; CLAUDE.md:28).

"early windows" definition: NOT FOUND - Claude Code to check. The ban is cited in AGENT_OPERATIONAL_PROTOCOL.md:45 and CLAUDE.md:28 ("evidence in OLLAMA.md") but neither file defines it, and OLLAMA.md is not in the repo.

Why the backward walk is not a wider or earlier detection window: it starts at release_estimate_frame (already computed from existing detections), walks only along already-detected ball points, never adds frames, never extends TRACE_BEFORE_MS (3000 ms, not widened), never changes detector thresholds, crops, or confidences, and never re-detects anything. It is a trace on saved points, not a detection window.

9. G. HONEST LIMITS

- One try, then stop for Scott. No retune after the run (spec 33 E9 pattern).
- The walk assumes release_estimate_frame is after the true release - proven by the run37 read-only check (ball above the nearest player's head at the chosen release frame, 98% / 100%, drift_log.md line 155). If the true release frame has no ball detection, the walk stops at the nearest detected point before a break; unrecoverable without interpolation (banned).
- Two players holding the ball goes orange; the finder never guesses between players.
- Q4 blind only after Scott sees the Q1-Q3 numbers (drift_log.md line 132 note carried forward).
- Found-rate expectations are not targets: run37 was 10/116 Adrian, 8/36 Notus; cause of the spec-37 drop is Unknown (inferred: fewer series, fewer v6 crops).
- Referee boxes are never players (BODD_CLASSES excludes referee; rim_first_finder.py:43 and :89).

10. ROLES & GATES

- Cursor codes the trace in rim_first_finder.py, tests in test_rim_first.py, shooter measures in rim_first_measure.py.
- Claude Code vets: backward walk only inside TRACE_BEFORE_MS; no interpolation or gap fill; no banned trials; numbers quoted with file:line; "Scott decides" numbers fixed before the run.
- Muse checks the Vetter: AGREE or DISAGREE; DISAGREE stops for Scott.
- Stop for Scott before the run on any "Scott decides" number; Q4 blind only after Scott sees Q1-Q3 numbers.

11. FACT SOURCES

Every fact above comes from a file read this session or the prompt; otherwise "NOT FOUND - Claude Code to check".

Key lines read this session:
- rim_first_finder.py:449 slice_trace_window, :474 trace_shooter, :557 floor spot, :57 MAKE_GAP_FRAMES, :70 TRACE_BEFORE_MS, :72 RELEASE_TRACE_FACTOR, :43 BODD_CLASSES, :89 referee excluded.
- shot_rules_measure.py:132 ball_inside_player mode="release", :163 combine_ball_track, :270 release_estimate_frame, :37-45 SCOTT_APPROVED_2026_11_04.
- drift_log.md lines 132, 153-159 (run37 numbers, shooter trace, Q4 blind).
- AGENT_OPERATIONAL_PROTOCOL.md:45; CLAUDE.md:28 (banned trials; "early windows" not defined).

Not in repo: OLLAMA.md - "early windows" definition NOT FOUND - Claude Code to check.
