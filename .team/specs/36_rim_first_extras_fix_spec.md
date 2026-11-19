VETTED WITH CONDITIONS by Claude Code, 2026-11-05: v2 read against the R1-R7 rejection, Scott's rules (memory what-counts-as-a-shot), rim_first_finder.py, rim_first_measure.py, .team/specs/36_extras_truth_labels.json. v2 still misses R2 and R3 and keeps tag excuses in C/D; K1-K8 OVERRIDE the text below.
K1 (R2) Every moment gets shot_call in {shot, orange, not_a_shot} + shot_reason, and separately shooter in {found, orange} + shooter_reason. The truth scorecard and the tag report score on shot_call only; "status" is not used for scoring.
K2 (R3) No merge_window_ms. Two moments on the same series: the later one is merged into the earlier unless the BODD ball was inside a player box (ball_inside_player, release 0.6) on some frame strictly between them. No time number.
K3 (R1) No tag excuses. C: finder rule - a moment with kind_hint rim, if the ball is inside a BODD referee box on any frame within foul_ref_window_ms after the trigger -> shot_call orange "possible_fouled_miss" (kind_hint make stays shot: and-one). D: no finder cue -> stays shot -> scored WRONG, said plainly. B: frames with >= shoot_around_min_balls BODD basketballs within the 3000 ms before the trigger -> orange "possible_shoot_around". In the scorecard a C/D/B/F/H entry with shot_call shot = WRONG, whatever the tags say.
K4 H: ball inside a BODD referee box at the trigger frame -> shot_call not_a_shot "referee_holding" (Scott: "not a shot").
K5 A: series filter as written (median hoop width vs film median of all BODD hoops in the span; v6 point count) -> series dropped, moments kept in output as not_a_shot "not_a_hoop" for audit.
K6 Cost check: the tag report must also list TAGGED shots whose shot_call became orange or not_a_shot, by reason - a fix that hides real shots must show.
K7 Detection re-run (frames.json must add referee boxes and v6 points per series). Spans Adrian 0..3317100 ms, Notus 0..883400 ms. Then Adrian Q4 blind (3317100..3897037) only after Scott sees the numbers. New out dirs: rim_first/run36_adrian, run36_notus, measure36_adrian, measure36_notus.
K8 Scott decides before the run: hoop_w_min_widths 0.5, hoop_w_max_widths 1.5, min_series_v6_points 3, shoot_around_min_balls 3, foul_ref_window_ms 1500, extra_match_window_ms 1500 (truth entry <-> moment). One try; no change after results.
SCOTT APPROVED K8, 2026-11-05: "Well, we need to test it. Proceed and we can adjust as needed." Six numbers fixed as listed for this one run. Any change after results is a new Scott decision and a new run, not tuning inside this run.

RIM-FIRST EXTRAS FIX SPEC v2 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto.
Deliverable: this one file only. Nothing else is edited; nothing runs that writes outputs.

1. WHY V1 WAS REJECTED (R1-R7, all binding)

- R1: C (fouled miss), D (block), B (not game time) cannot be "fixed" only in the measure by reading Foul/Block tags. The finder is video-only; on a new game there are no tags. Each group must be handled in the finder from video, or sent to ORANGE by the finder. The measure scores what the finder emits: a fouled-miss / block / halftime moment the finder calls a shot = WRONG; orange = acceptable.
- R2: split shot_call (shot / orange / not_a_shot, with reason) from shooter (found / orange, with reason); score on shot_call.
- R3: F (same shot twice): drop merge_window_ms as the only fix. One moment per run stays; add the player-box decider (ball_inside_player release 0.6) for cross-run pairs.
- R4: H (referee holding): ball inside a BODD referee box at the trigger frame -> shot_call not_a_shot / orange "referee_holding", kept in output for audit.
- R5: B: propose a video-only signal (several BODD basketballs in the same frames) -> orange "possible_shoot_around", number "Scott decides", or say plainly none works. Scoreboard stays optional, never required.
- R6: C: propose a video-only signal (ball inside a referee box after a non-make moment = play stopped) -> orange "possible_fouled_miss"; a make followed by free throws at the same hoop stays a shot (and-one). Numbers "Scott decides". If no signal is honest, C stays a shot call and is counted WRONG.
- R7: save referee boxes and v6 points in frames.json this time. Spans: Adrian 0..3317100 ms, Notus 0..883400 ms (drift_log 2026-11-05).

2. SCOPE RULE (unchanged, spec 35 section 1)

Finder reads no tags, no scoreboard, no DB. CLI: --video --start-ms --end-ms --out-dir --bodd --v6. Only rim_first_measure.py reads tags.

3. THE 41 EXTRAS

Frozen truth file .team/specs/36_extras_truth_labels.json (written by Claude Code before any run; 41 entries {n, run, t_ms, frame, label}):

A_not_a_hoop 8 (Adrian 16,17,18,22,23,24; Notus 33,34): BODD put a hoop on the centre-court logo, the bottom edge of the picture, or a wall; v6 then fired on a ball near it.
B_not_game_time 8 (Adrian 10-15 halftime shoot-around, people in street clothes several balls at once; Adrian 19 halftime; Adrian Q4 #41 after the final buzzer).
C_fouled_shot 9 (Adrian 2,4,5,6,7,20,21; Notus 27,32; #4 and #5 were fouled put-backs): Scott tagged Foul/Personal within ~1.3 s.
D_blocked 1 (Notus 35, Block tag +0.5 s).
E_putback_real_shot 1 (Notus 30, OffRebound tag -4.9 s): a REAL shot by Scott's rule even with no 2PT tag.
F_same_shot_twice 7 (Adrian 1,3,8,25,26; Notus 28,29): rim bounce coming down again, ball dropping after a make, FT rattling.
G_unclear_orange 4 (Adrian 9; Notus 31,36,37).
H_referee_holding 1 (Notus 38).
Q4_not_examined 2 (Adrian Q4 #39,#40): listed, not scored - Q4 stays the blind check.

4. FIX PER GROUP (video-only rule / reused code and number, file:line / new number, Scott decides before the run)

A. Not a hoop, 8. Hoop-series filter: after hoops are paired into series (assign_frame_hoops rim_first_finder.py:611-642; points accumulate :645-665), drop a whole series - no moments, no trace - when its median hoop width (median_hoop :289-299) is outside [hoop_w_min_widths, hoop_w_max_widths] x the film median hoop width, or when it has fewer than min_series_v6_points v6 detections (real hoops see repeated ball traffic; a logo/wall patch gets 0-2). Dropped series emit nothing. Reuse: distance_hoop_widths :103; ADRIAN_MEDIAN_HOOP_W = 98.0 :65 (Notus median computed at runtime; value NOT FOUND - Claude Code to check). New numbers: hoop_w_min_widths 0.5, hoop_w_max_widths 1.5, min_series_v6_points 3 (all Scott decides).

B. Not game time, 8. Halftime shoot-around: several balls at once, visible in video. The finder already counts BODD basketballs per frame (_compact_frame :763-776); frames with >= shoot_around_min_balls concurrent basketballs mark shoot-around frames; moments at those frames -> status orange "possible_shoot_around". Q4 #41 after the final buzzer: no clock in the video and the scoreboard is not permitted (spec 35 E7, section 1), so it cannot be fixed in the finder; the moment stays, listed by time in the measure extras, Q4 blind and not scored. New number: shoot_around_min_balls 3 (Scott decides); or say no signal works if Scott disagrees.

C. Fouled miss, 9. Video cannot see a foul; knowable only from a Foul/Personal tag within ~1.3 s or from FTs after at the same hoop; the finder has no tags. Rule: on a non-make rim moment, if the ball is inside a referee box within foul_ref_window_ms after the trigger (play stopped, referee has the ball) -> status orange "possible_fouled_miss". Otherwise the moment stays "found" and the measure cross-checks the Foul/Personal tag within extra_match_window_ms (drop correct; no tag -> WRONG, reported plainly). A make followed by FTs at the same hoop stays a shot (and-one, official stats). Reuse: referee boxes (new collection, see H); ball_inside_player :474. New number: foul_ref_window_ms 1500 ms (Scott decides, matches Scott's ~1.3 s); extra_match_window_ms 1500 ms reused (rim_first_measure.py:23).

D. Blocked, 1. Video cannot confirm a block; a blocked ball and a missed ball look the same (a block may only show as the ball never reaching the rim). No honest finder cue: the finder does not guess. The rim moment stays "found" and the measure cross-checks the Block tag within extra_match_window_ms (drop correct; no Block tag -> WRONG, reported plainly). If the ball never enters the rim zone the miss trigger never fires (miss_trigger_frame :180-219) and the moment is already dropped. State plainly: D may score one wrong; Scott decides whether to add a block-exit orange cue (number Scott decides).

E. Put-back, real shot, 1. Keep as its own shot. Put-back = ball entered a player's hands (ball_inside_player release 0.6, :474) then went up again -> new run via split_runs gap 8 (:161) -> separate moment kept; truth expects exactly one found moment. Reuse: trace_shooter / ball_inside_player :410-495; split_runs :161.

F. Same shot counted twice, 7. One moment per run already (moment_for_run :238): rim bounce down again, ball dropping after a make, FT rattle all stay in one run and the first trigger wins. Cross-run pairs on the same series: add merge_moments, applied in emit_moments before the sort (:744) - keep the earlier moment unless between the two moments the BODD ball was inside a player box (ball_inside_player release 0.6, :474), which means possession and a real put-back/tip, so keep both separate. Same-shot-again = ball never left the rim zone (0.735 hoop widths) and never entered a player box -> merged; put-back = player-box possession between the two events -> kept separate. New number: none (merge_window_ms REMOVED by K2).

G. Unclear, 4. Status orange with reason; the finder never guesses make/miss. Reuse: trace_shooter _orange paths (:458-481, helper :498).

H. Referee holding, 1. BODD classes are {basketball, hoop, player, referee}; the finder currently keeps only basketball/hoop/player and drops referee (:42; detect_span ball/hoop/player split :886-891). Change: collect referee boxes separately; at the trigger frame, ball inside a referee box (ball_inside_player :474 at 0.6) -> status orange "referee_holding", not a shot, kept in output for audit. Reuse: _box_item :748-760. New number: none.

5. GROUPS THE VIDEO CANNOT SETTLE -> ORANGE (stated plainly)

C: a fouled miss needs the Foul/Personal tag or the FTs after at the same hoop; the finder has no tags. D: a block needs the Block tag; video cannot tell it from a miss. B Q4 #41: game time needs the scoreboard, not permitted. These go to measure tag cross-check and the truth file; the finder emits what it sees and never labels foul, block, or game time itself. Where the finder's video cue fires (referee holding, multi-ball), status is orange, not a guess.

6. PUT-BACK vs SAME-SHOT-AGAIN

Same-shot-again: the ball never left the rim zone (0.735 hoop widths, miss_trigger_frame :180-219) and never entered a player box (ball_inside_player release 0.6, :474) between the two rim touches -> merged into the earlier moment. Put-back: the ball came down into a player's hands (inside a player box), then went up again -> possession between the events -> separate run via split_runs gap 8 (:161) -> separate moment; truth expects exactly one found moment.

7. MEASURE (rim_first_measure.py is the only script that reads tags)

Scorecard on the frozen truth file for n=1-38 (Adrian Q1-Q3, Notus Q1); Q4 entries n=39-41 listed, not scored (Q4 blind last). Match truth entries to the finder's unmatched moments (extras, listed by time, :112-120) by film and |t_ms diff| <= extra_match_window_ms (1500 ms, :23). Verdicts: found = label E_putback_real_shot and exactly one status==found moment at its time; missed = label E and zero found moments; wrong = status==found at any non-E label time, two found moments at one truth entry (double count, the F bug), or a found moment matching no truth entry; orange = any non-E label with zero found moments (silent drop or status orange = correct - covers A dropped series, B orange, C/D/G/H dropped or orange). Report found / missed / wrong / orange per film, plus the existing tag report (2PT/3PT/FT via match_shots 8000 ms :69-70, Q4 tags filtered out :65, extras listed by time :112-120, trace found/orange rates). Code change: optional --truth reading .team/specs/36_extras_truth_labels.json; per-film truth table added to results.json/summary.md; all existing fields and CLI kept. Output: NEW dir Liberty_Shot_Outputs/rim_first/measure_36_extras_fix/ (refuse if exists, :28); proposed name, Scott decides.

8. MAKE/MISS SAFETY (unchanged)

Before and after: .venv/Scripts/python.exe .team/shot_detectors/make_review_queue_page.py --wide-combined --out-dir <NEW>. Require gray 30 / orange 9 / 42 shots and the same 3 combined groups. Any difference -> STOP, Scott decides.

9. CODE AND OUTPUTS

Files: rim_first_finder.py, rim_first_measure.py, test_rim_first.py only (or one new file, name it). Test additions: pure-function tests for merge_moments, the hoop-series filter, the referee-box orange, and the truth verdicts. Outputs: finder moments.json + frames.json to a NEW dir Liberty_Shot_Outputs/rim_first/rim_first_36_extras/ (refuse if exists, rim_first_finder.py:97); measure results.json + summary.md to measure_36_extras_fix/ (refuse if exists, rim_first_measure.py:28). Both scripts refuse if the out dir exists. Frames.json reuse: NO - spec-35 frames.json (compact :763-776) has ball/hoop/player per frame but not referee (needed for H) and not v6 points (needed for A's series traffic); no saved frames.json exists yet (Liberty_Shot_Outputs/rim_first/ absent, spec 35 was "not run"). The spec-36 finder run re-runs detection over Adrian Q1-Q3 and Notus Q1 - video + models only (spec 35 E7).

10. RULES

- No core edits (event_generator.py, ai_bridge.py, court_memory.py, net_detector.py untouched).
- No training; existing v6 and BODD weights only.
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter.
- No tuning after results - every number fixed before this run.
- One try, then stop for Scott. Q4 blind last.
- DB read-only.

11. ROLES & GATES

- Cursor codes. Claude Code vets: no core edits, numbers fixed before run, output-dir refusal, finder takes only video + model + out dir, test greps finder imports for tag/scoreboard/DB modules. Muse checks AGREE or DISAGREE with each VETTED/PASS; a DISAGREE stops the loop for Scott. Stop for Scott with the "Scott decides" numbers table.

12. NUMBERS TABLE

merge_window_ms - REMOVED by K2 (no time number; player-box decider only).
hoop_w_min_widths 0.5 (Scott decides).
hoop_w_max_widths 1.5 (Scott decides).
min_series_v6_points 3 (Scott decides).
shoot_around_min_balls 3 (Scott decides).
foul_ref_window_ms 1500 ms (Scott decides).
extra_match_window_ms 1500 ms (Scott decides; Scott's C note ~1.3 s).

Reused unchanged, not retuned: v6 crop 260/200/240 px, conf 0.28, imgsz 640, prev*0.35; MAKE 0.55 / 180 px / 8 frames, widths 2.2/0.9/1.3 hoop_w; MISS_RIM_ZONE 0.735 hoop_w / RIM_BAND 40*hoop_w/98 px; TRACE_BEFORE_MS 3000 / release_trace_factor 0.6; match_window_ms 8000; BODD conf 0.12 / imgsz 960; HOOP_X_BUCKET_PX 80; ball_inside_player release 0.6.

13. FACT SOURCES

Everything above comes from files read this session (.team/specs/35_rim_first_shot_finder_spec.md E1-E9 binding block, .team/specs/36_rim_first_extras_fix_spec_v1_REJECTED.md R1-R7 binding block, .team/shot_detectors/rim_first_finder.py, .team/shot_detectors/rim_first_measure.py, .team/shot_detectors/test_rim_first.py, .team/specs/36_extras_truth_labels.json, .team/shot_detectors/collect_q4_bodd.py) or the user prompt. NOT FOUND - Claude Code to check: Notus median hoop width; Adrian Q1-Q3 and Notus Q1 span start-ms; video file paths; model file paths; tag file path read by load_shot_tags; whether any saved frames.json exists under Liberty_Shot_Outputs/rim_first/.