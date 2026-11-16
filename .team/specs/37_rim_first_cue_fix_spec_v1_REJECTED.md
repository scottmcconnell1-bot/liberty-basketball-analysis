REJECTED by Claude Code, 2026-11-06 (in part): Points 1, 2, 3a pass. 3b fails on the saved run36 data (scratchpad check, read-only): catch 0.5 x diagonal is 117 px vs release 0.6 x max 129 px for the median player box (90x215) - on close moment pairs frames_held changes by 0-14 frames and the F pair 48040->52400 is 26 vs 26. Root cause of F found: 6 of 7 F entries are two DIFFERENT series on the same physical hoop (hoop x 1106/1118, 823/831, 482/479, 840/873, 608/679; 104/493 differs), trigger 0.04-1.0 s apart - same_shot_merged is same-series only, so no circle size can fix them. Also section 4 says 12 frames was "not picked from run results"; Scott chose it after seeing the run-36 frame counts - say so. Rewrite as v2.

RIM-FIRST CUE FIX SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto.
Deliverable: this one file only. Nothing else is edited; nothing runs that writes outputs.
Author: Hermes (Architect). Cursor codes; Claude Code vets; Muse checks AGREE/DISAGREE.
Binding input: .team/specs/36_rim_first_extras_fix_spec.md K1-K8 (top block) stays binding unless changed here.

1. SCOTT'S DECISION 2026-11-06 (three points, all binding)

The spec-36 run hid real game shots: 38 real shots taken off the shot list -
shoot_around 19, fouled_miss 13, referee_holding 5, match shift 1 (run36
frames.json / moments.json + measure results).

Point 1 - drop the referee checks completely.
  Remove possible_fouled_miss AND referee_holding from assign_shot_calls
  (.team/shot_detectors/rim_first_finder.py). Referee boxes are still
  collected and saved in frames.json (key "r" in _compact_frame; collection in
  detect_span) but are never used for a shot call. Fouled misses and blocks are
  then counted WRONG by the measure (rim_first_measure.py --truth), said
  plainly; the finder does not guess foul, block, or game time.

Point 2 - warm-up check needs the extra balls to LAST.
  possible_shoot_around fires only when, in the 3000 ms before the trigger
  (TRACE_BEFORE_MS = 3000 ms, rim_first_finder.py:70, reused), at least
  SHOOT_AROUND_MIN_FRAMES = 12 frames contain >= SHOOT_AROUND_MIN_BALLS = 3
  BODD basketballs (SHOOT_AROUND_MIN_BALLS = 3, spec 36 K8,
  rim_first_finder.py:84). The 12 frames are TOTAL in the window, not
  consecutive: no file read for this spec says consecutive, and the spec-36
  grounding is a frame count (most of the 19 hidden real shots had >= 3 balls
  on only 1 frame of the 75 before; a few had 7-21). This replaces the current
  any-frame check (_frames_touch_window on hot_frames,
  rim_first_finder.py:982-985) with a count of frames in
  [trigger_ms - TRACE_BEFORE_MS, trigger_ms].

Point 3 - fix the order so merge and fake-hoop checks can work.
  Order inside one detect span: detect -> hoop check -> series pairing -> runs
  -> moments -> calls.
  3a. Fake-hoop size check PER FRAME, BEFORE hoops are paired into series: keep
      a BODD hoop box only when its width is in
      [HOOP_W_MIN_WIDTHS, HOOP_W_MAX_WIDTHS] = [0.5, 1.5] x the film median
      hoop width (spec 36 K8; rim_first_finder.py:78-80). A dropped hoop box
      does not pair to a series, does not start a series, and does not feed the
      hoop carry (resolve_frame_hoops / build_hoop_carry).
      Rationale from the run: pair_hoops_to_series pairs by nearest x with NO
      distance limit (rim_first_finder.py:637-656), so a fake hoop joins a real
      series and is averaged away before hoop_series_ok (:332-363) runs; the
      series filter dropped NO series (4 per film, all kept, widths 0.94-1.04x
      of film median).
      Where: compute film_median_hoop_w (:675-686) right after the BODD pass,
      before the v6 pass (it is currently called after the v6 pass at
      detect_span :1403); filter each frame's hoops by the band before
      assign_frame_hoops (:723-754); build hoop_samples and the carry from kept
      hoops only (_hoop_samples_from_raw :1182-1198).
  3b. Smaller "has the ball" circle for the merge: possession_between
      (rim_first_finder.py:931-946) calls ball_inside_player in mode "catch"
      with factor 0.5 (shot_rules_measure.py:42-43, spec 33 Scott-approved)
      instead of mode "release" at 0.6 (rim_first_finder.py:72). trace_shooter
      keeps release mode 0.6. No new number is needed - catch 0.5 is an
      existing proven rule. If Scott wants a different merge factor, that is a
      new number "Scott decides before the run", not picked from these results
      (same_shot_merged fired 0 times in run 36, so the run gives no merge
      number).

2. SHOT-CALL ORDER (assign_shot_calls, rim_first_finder.py:830-1020)

First rule that fires sets shot_call; flags list every rule that fired:
  1 not_a_hoop -> not_a_shot (series filter, unchanged from spec 36)
  2 same_shot_merged -> not_a_shot + merged_into_frame, catch-mode circle
      (Point 3b)
  3 possible_shoot_around -> orange, 12-of-3000-ms frame count (Point 2)
  4 otherwise shot, shot_reason None
Referee_holding and possible_fouled_miss are REMOVED (Point 1). K1-K3 shapes
stay binding: shot_call in {shot, orange, not_a_shot} plus shot_reason;
shooter kept separate with shooter_reason; scorecard on shot_call; any group
entry called shot is WRONG whatever its tags say. Referee groups now land in
that "called shot = WRONG" bucket plainly.
test_rim_first.py: add pure-function tests for the 12-of-3000-ms count, the
per-hoop pre-pair width filter, and catch-mode merge.

3. FAKE HOOP - OPTIONAL SHAPE/POSITION CHECK (proposal only)

The width band catches 6 of the 8 labelled fake-hoop moments from the same
film (Adrian misses: 0.62x and 1.36x of film median; Notus catches: 1.55x and
3.60x among the 1.55-3.95x values). Do not add a second check in run 37
unless Scott decides. Optional proposal, "Scott decides before the run": add
hoop h/w band and box-bottom position - real shots h/w 1.00-1.33 with box
bottom in the top 32% of the picture; fakes h/w 0.25-1.72 with several at the
bottom edge (y about 1051 of 1080). Risk: those h/w and bottom numbers came
from the same two films as the fakes, so a tuned band overfits them, and a
real shot near the band edge (real h/w up to 1.33) could be dropped. Width-
only for run 37; any shape/position number is a Scott decision before the run;
no proposed value is set here.

4. NUMBERS TABLE (every number used by this spec)

SHOOT_AROUND_MIN_FRAMES 12 frames - Scott decided 2026-11-06 (NEW). Total
  frames in [trigger - 3000 ms, trigger], not consecutive; not picked from run
  results.
SHOOT_AROUND_MIN_BALLS 3 BODD basketballs - spec 36 K8, Scott decided
  2026-11-05; rim_first_finder.py:84.
TRACE_BEFORE_MS 3000 ms - spec 33 Scott-approved; rim_first_finder.py:70;
  reused for the shoot-around look-back.
HOOP_W_MIN_WIDTHS 0.5 - spec 36 K8, Scott decided 2026-11-05; rim_first_finder.py:78.
HOOP_W_MAX_WIDTHS 1.5 - spec 36 K8, Scott decided 2026-11-05; rim_first_finder.py:80.
MIN_SERIES_V6_POINTS 3 - spec 36 K8, Scott decided 2026-11-05; rim_first_finder.py:82; series-level traffic check, unchanged.
ball_inside_player merge factor 0.5, mode "catch" - shot_rules_measure.py:42, spec 33 Scott-approved; existing proven rule, no new number.
FOUL_REF_WINDOW_MS 1500 ms - REMOVED (was spec 36 K8, rim_first_finder.py:86); referee_holding and possible_fouled_miss removed from shot calls.

No looser cutoffs: no band widening, no extra time, no removal of the size
check. All other spec-36 K8 numbers are unchanged.

5. MEASURE AND RUNS

Measure: rim_first_measure.py --truth is UNCHANGED and is NOT edited - it only
reads tags and scores the shot_call the finder emits.
Runs (new output dirs; both scripts refuse if a dir exists):
  Liberty_Shot_Outputs/rim_first/run37_adrian  - Adrian 0..3317100 ms
  Liberty_Shot_Outputs/rim_first/run37_notus   - Notus 0..883400 ms
  then measure37_adrian and measure37_notus with --truth.
Spans from spec 36 K7. Q4 blind (Adrian 3317100..3897037 ms) only after Scott
sees the run37 numbers.

Can shot calls be recomputed from saved run36 frames.json without video?
  possible_shoot_around: YES, exactly - frames.json holds per-frame BODD ball
  counts (key "b"); count window frames with >= 3 balls.
  same_shot_merged: YES, exactly - frames.json holds per-frame balls and
  players (keys "b", "p"); possession between two trigger frames is
  recomputable.
  fake-hoop-before-pairing: NO, not exactly - run36 series already absorbed
  fake hoops because pair_hoops_to_series has no distance limit
  (rim_first_finder.py:637-656), so re-filtering run36 frames would not
  reproduce the re-paired series.
Therefore run 37 re-detects both films from video into the new dirs above.

Make/miss check before and after: make_review_queue_page.py --wide-combined
(gray 30 / orange 9 / 42 shots, same 3 combined groups) run against the
current spec-36 code and against the spec-37 code. Require identical groups
and counts; any difference -> STOP, Scott decides. collect_q4_bodd.py and the
make/miss files are untouched.

6. HONEST LIMITS

- Fouled misses and blocks: counted WRONG by the measure, said plainly
  (Point 1); video cannot see a foul or confirm a block.
- After-buzzer shot (Q4 #41): no clock in the video and the scoreboard is not
  permitted, so it is not fixable in the finder.
- The 12-frame warm-up number and any optional shape number were chosen after
  seeing these two films; they are not independent. The Q4 blind run is the
  real test.

7. RULES

- No core edits (event_generator.py, ai_bridge.py, court_memory.py,
  net_detector.py untouched). Cursor may edit rim_first_finder.py and
  test_rim_first.py only; rim_first_measure.py is not edited (see section 5).
- No training; existing v6 and BODD weights only.
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows,
  wider column, hoop recenter.
- Finder reads no tags, no scoreboard, no DB; referee boxes saved but unused
  for calls; DB read-only; images local only.
- No tuning after results; one try, then stop for Scott. Q4 blind last.
- Claude Code vets, Muse checks AGREE or DISAGREE per VETTED/PASS; a
  DISAGREE stops the loop for Scott; stop for Scott with the numbers table.
