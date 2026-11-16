REJECTED by Claude Code, 2026-11-05: read against Scott's rules (prompt_hermes_spec36.txt), rim_first_finder.py, rim_first_measure.py.
R1 C (fouled miss), D (block), B (not game time) are left as finder shots and "fixed" only in the MEASURE by reading Foul/Block tags. That breaks Scott's rule: the finder is video-only and on a new game there are no tags, so it would report fouled misses and halftime shots as shots. Each must be handled IN THE FINDER from video, or sent to ORANGE by the finder. The measure must score what the finder emits: a fouled miss / block / halftime moment the finder calls a shot = WRONG; orange = acceptable.
R2 "status" today is the SHOOTER trace result (found / orange), not whether it is a shot. Most moments are trace-orange, so "orange = correct" would excuse almost everything. Split into shot_call (shot / orange / not_a_shot, with reason) and shooter (found / orange, with reason). Score on shot_call.
R3 F (same shot twice): drop merge_window_ms. Use the decider you wrote, with no time number: a second moment on the same series is a new shot only if between the two moments the BODD ball was inside a player box (ball_inside_player release 0.6); otherwise merge into the earlier one. Put-backs and free-throw pairs keep (a player had the ball); rim bounces and FT rattles merge.
R4 H (referee holding): Scott said "not a shot", not orange: ball inside a BODD referee box at the trigger frame -> shot_call not_a_shot, reason referee_holding (kept in output for audit).
R5 B: propose a video-only signal (e.g. several BODD basketballs on the court in the same frames, as in the halftime shoot-around) -> orange, number "Scott decides"; or say plainly none works. Scoreboard stays optional, never required.
R6 C: propose a video-only signal for "fouled" (e.g. after a non-make moment, play stops: ball inside a referee box, then a moment at the same hoop with players still) -> orange "possible fouled miss"; a make followed by free throws stays a shot (and-one). Numbers "Scott decides". If no signal is honest, say C stays a shot call and is counted WRONG.
R7 Facts: Liberty_Shot_Outputs/rim_first/ exists (you could not see it from the sandbox). Spans: Adrian 0..3317100 ms, Notus 0..883400 ms (drift_log 2026-11-05). Save v6 points and referee boxes in frames.json this time.
A (hoop filter) is acceptable with its three Scott-decides numbers; E and G as written are fine once R2 is done.

RIM-FIRST EXTRAS FIX SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto. Deliverable: this one file only. Nothing else is edited; nothing runs.

Frozen input (already written by Claude Code, before any run): .team/specs/36_extras_truth_labels.json — 41 entries {n, run, t_ms, frame, label}; labels A_not_a_hoop (8), B_not_game_time (8), C_fouled_shot (9), D_blocked (1), E_putback_real_shot (1), F_same_shot_twice (7), G_unclear_orange (4), H_referee_holding (1), Q4_not_examined (2, Q4 blind, not scored).

SCOTT'S RULES (2026-11-05, binding)
- Fouled shot that misses: NOT a shot. Fouled make / and-one IS a shot (official stats).
- Blocked shot: NOT a shot.
- Put-back and tip: each is its own shot, counted separately.
- Same shot counted twice: our bug, fix it.
- Unclear: orange coach card.
- Ball held by the referee: not a shot, our bug.
- Finder stays video-only: no tags, no scoreboard, no DB (spec 35 section 1). Scoreboard may NOT be required.
- Q4 extras #39-#40 not examined; Q4 stays the blind check, never designed from.

FIX PER GROUP (video-only rule / code reused file:line / new number)
A. Not a hoop, 8 (Adrian #16,17,18,22,23,24; Notus #33,34): drop a BODD hoop series when its hoop width is outside [0.5, 1.5] x the film median hoop width, or when the series has fewer than 3 v6 detections across the span (real hoops see repeated ball traffic; a logo/wall patch gets 0-2). Dropped series emit no moments and no trace. Reuse: distance_hoop_widths rim_first_finder.py:103; series points and accumulation :663 and :595-665; ADRIAN_MEDIAN_HOOP_W :65 (Notus median computed at runtime; its value NOT FOUND in any file read). New numbers, Scott decides before the run: hoop_w_min_widths 0.5, hoop_w_max_widths 1.5, min_series_v6_points 3.
B. Not game time, 8 (Adrian #10-15, #19 halftime; Q4 #41 post-buzzer): no fix possible — video shows no clock and the scoreboard is not permitted (spec 35 E7 and section 1). Moments stay in finder output and appear as measure extras listed by time; Scott verifies against tags. Not orange.
C. Fouled miss, 9 (Adrian #2,4,5,6,7,20,21; Notus #27,32; #4 and #5 fouled put-backs): finder emits the rim moment — video cannot see a foul (knowable only from a Foul/Personal tag within ~1.3 s or from FTs after at the same hoop; finder has no tags). Measure reclassifies an extra matched to a Foul/Personal tag within extra_match_window_ms as a Scott-rule drop, correct; the finder never guesses. Reuse: match_shots indexing pattern rim_first_measure.py:69-70; tags via load_shot_tags. New number: extra_match_window_ms 1500 ms, Scott decides.
D. Blocked, 1 (Notus #35, Block tag +0.5 s): video cannot confirm a block (a blocked ball and a missed ball look the same); the Block tag decides. Same measure cross-check vs Block tags. Not guessable by the finder.
E. Put-back, real shot, 1 (Notus #30, OffRebound tag -4.9 s, no 2PT tag): keep as one separate shot. Put-back = ball entered a player's hands (ball_inside_player at release 0.6, rim_first_finder.py:474) then went up again → new run via split_runs gap 8 (:161) → separate moment kept. Truth expects exactly one found moment. Reuse: trace_shooter / ball_inside_player :410-495.
F. Same shot counted twice, 7 (Adrian #1,3,8,25,26; Notus #28,29): one moment per run already (moment_for_run :238); add merge_moments — on the same series, moments within merge_window_ms keep the earlier one, applied in emit_moments before the sort (:744). Same-shot-again vs put-back decider: same-shot = ball never left the rim zone (0.735 widths, miss_trigger_frame :180) and never entered a player box (:474) → merged; put-back = player-box possession between the two events → kept separate.
G. Unclear, 4 (Adrian #9; Notus #31,36,37): status orange with reason; reuse trace_shooter _orange paths (:458-481 and :498). Finder never guesses make/miss.
H. Referee holding ball, 1 (Notus #38): BODD keeps the referee class (classes are {basketball, hoop, player, referee}; the finder currently drops referee, rim_first_finder.py:42); detect_span saves referee boxes beside players; at the trigger frame, ball inside a referee box (ball_inside_player, 0.6) → moment status orange "referee_holding", not a shot. Reuse: _box_item / player collection :748-793; ball_inside_player :474. New number: none.

GROUPS THE VIDEO CANNOT SETTLE -> ORANGE (stated plainly)
C: a fouled miss needs the Foul/Personal tag or the FTs after at the same hoop; the finder has no tags. D: a block needs the Block tag; video cannot tell it from a miss. B: game time needs the scoreboard, which is not permitted. These go to measure tag cross-check and the truth file; the finder emits what it sees and never labels foul, block, or game time itself.

MEASURE (rim_first_measure.py is the only script that reads tags)
Scorecard on the frozen truth file for n=1-38 (Adrian Q1-Q3 + Notus Q1); Q4 entries n=39-41 listed, not scored (Q4 blind last). Match finder extras (unmatched moments, t_ms and status already reported, rim_first_measure.py:112-120) to truth by film and |t_ms diff| <= extra_match_window_ms (1500 ms, Scott decides). Per entry: found = label E_putback_real_shot and exactly one status==found moment; missed = label E and zero found moments; wrong = a status==found moment at any other label time, two found moments at one truth entry (double count not fixed), or a found extra matching no truth entry; orange = any non-E label with no found moment (silent drop or status orange — "dropped or orange = correct", covers C/D/G/H). Report found / missed / wrong / orange per film, plus the existing tag report (2PT/3PT/FT, match_shots 8000 ms rim_first_measure.py:23, Q4 tags filtered out :65, extras listed by time :208-212). Code change: optional --truth reading .team/specs/36_extras_truth_labels.json and the per-film truth table added to results.json/summary.md; all existing fields and CLI kept. Outputs to a NEW dir under Liberty_Shot_Outputs/rim_first/ (refuse_existing_out_dir rim_first_measure.py:28); proposed name measure_36_extras_fix/. Finder outputs moments.json + frames.json to a separate NEW dir (proposed rim_first_36_extras/), same refuse rule (rim_first_finder.py:97).

MAKE/MISS SAFETY (untouched)
Before and after, run: .venv/Scripts/python.exe .team/shot_detectors/make_review_queue_page.py --wide-combined --out-dir <NEW>. Require gray 30 / orange 9 / 42 shots and the same 3 combined groups (page_v6 printed "combined groups (film, times, first, last, length)"). Any difference → STOP, Scott decides.

CODE AND OUTPUTS
Files: rim_first_finder.py, rim_first_measure.py, test_rim_first.py only. Test additions are pure-function tests (hand tracks) for merge_moments, the hoop-series filter, the referee-box orange, and the truth verdicts. No new input file is needed — the truth file already exists at .team/specs/36_extras_truth_labels.json. Output dirs: NEW dirs under Liberty_Shot_Outputs/rim_first/; both scripts refuse if the dir exists. The run writes finder moments.json/frames.json and measure results.json/summary.md.
Frames.json reuse: PARTIAL. frames.json has ball/hoop/player per frame (compact :763-776) so group A's hoop filter can run on saved detections without re-running BODD. It does NOT save referee (needed for H) and does NOT save v6 points (needed for A/B series traffic), so the spec 36 finder run re-runs detection over Adrian Q1-Q3 and Notus Q1 (video + models only, E7).
NOT FOUND - Claude Code to check: Adrian Q1-Q3 and Notus Q1 span start-ms (Adrian end Q4_MS 55:17.1, collect_q4_bodd.py:28; start and Notus Q1 end come from an existing source, recorded in the run log, never from tags); video file paths; model file paths; tag file path read by load_shot_tags. Liberty_Shot_Outputs/rim_first/ does not exist on disk yet (spec 35 measure_*/summary.md not found), so every output dir is new.

RULES
- No core edits (event_generator.py, ai_bridge.py, court_memory.py, net_detector.py untouched).
- No training; uses existing v6 and BODD weights.
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter.
- No tuning after results — every number fixed before this run.
- One try, then stop for Scott. Q4 blind last.
- DB read-only.

ROLES & GATES
- Cursor codes; Claude Code vets (no core edits, numbers fixed before run, output-dir refusal, finder takes only video + model + out dir); Muse checks AGREE or DISAGREE with each VETTED/PASS — a DISAGREE stops the loop for Scott. Stop for Scott with the table of "Scott decides" numbers.

NUMBERS TABLE
- merge_window_ms 300 ms (Scott decides; spec 35 table already proposed it).
- hoop_w_min_widths 0.5 (Scott decides).
- hoop_w_max_widths 1.5 (Scott decides).
- min_series_v6_points 3 (Scott decides).
- extra_match_window_ms 1500 ms (Scott decides; Scott's C note is ~1.3 s).
Reused unchanged, not retuned: v6 crop 260/200/240 px, conf 0.28, imgsz 640, prev*0.35 (collect_q4_bodd.py:121-125); MAKE 0.55 / 180 px / 8 frames, widths 2.2/0.9/1.3 hoop_w (collect_q4_bodd.py:49); MISS_RIM_ZONE 0.735 widths and RIM_BAND 40 px scaled by hoop_w/98 (spec 35; court_memory.py:165, :190); release_trace_factor 0.6 and TRACE_BEFORE_MS 3000 (spec 33; rim_first_finder.py:69-71); match_window_ms 8000 (manual_tag_teach.py:18; rim_first_measure.py:23); BODD conf 0.12 and imgsz 960 (collect_flight_tracks.py:311-312); HOOP_X_BUCKET_PX 80 (collect_q4_bodd.py:40).

FACT SOURCES
Everything above comes from files read this session (.team/specs/35_rim_first_shot_finder_spec.md including the E1-E9 binding block, .team/shot_detectors/rim_first_finder.py, rim_first_measure.py, test_rim_first.py, .team/specs/36_extras_truth_labels.json) or from the prompt. NOT FOUND - Claude Code to check: Notus median hoop width; Adrian Q1-Q3 and Notus Q1 span start-ms; video paths; model paths; tag file path for load_shot_tags.
