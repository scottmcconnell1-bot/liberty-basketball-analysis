VETTED WITH CONDITIONS by Claude Code, 2026-11-06: v2 read against the v1 REJECTED stamp, rim_first_finder.py (dedupe_hoops :659, pair_hoops_to_series :637-656, assign_frame_hoops, assign_shot_calls :830-1020), shot_rules_measure.py:42-43, run36 frames/moments (read-only checks). Points 1, 2, 3a, F1 pass. L1-L6 OVERRIDE the text below.
L1 Same-hoop distance is ONE number: MISS_RIM_ZONE_WIDTHS 0.735 x film median hoop width (Adrian 97.6 -> 71.7 px; Notus 64.2 -> 47.2 px), inclusive (<=). Drop "or equivalently 80 px" - they are not equivalent. Say plainly: the 608/679 pair (71 px) sits at the edge of 71.7 px.
L2 Replace "two series cannot form on one hoop" with: (a) stops a second series starting from two boxes on one hoop in the same frame; (b) is the net for any pair (a) misses. Not Proven until the run.
L3 (b) exact rule: each moment stores run_first_frame and run_last_frame (first/last frame of its v6 run). Two moments on different series are duplicates when hypot(hoop x diff, hoop y diff) of their moment hoops <= L1 distance AND earlier.run_last_frame + MAKE_GAP_FRAMES (8) >= later.run_first_frame. Later (by trigger frame) -> not_a_shot "same_shot_merged", merged_into_frame = earlier trigger frame. Chains resolve to the earliest.
L4 Shot-call order: not_a_hoop -> same_shot_merged (same-series as today, or cross-series L3) -> possible_shoot_around (>=12 total frames with >=3 BODD balls in [trigger-3000 ms, trigger]) -> shot. referee_holding and possible_fouled_miss code paths removed from calls; referee boxes still saved in frames.json "r".
L5 Per-frame hoop filter order: width band 0.5-1.5 x film median first, then the L1 same-hoop collapse (highest conf kept), then existing 80 px bucket dedupe, then pairing. Dropped boxes do not pair, start a series, or feed the carry. film_median_hoop_w from raw BODD hoops (unchanged function) computed after the BODD pass, before the v6 pass; written to moments.json.
L6 Tests (pure, hand data): band drop before pairing (a 1.7x box starts no series); same-frame same-hoop collapse at 0.735 widths (inside -> one, just outside -> two); cross-series merge positive; different hoop not merged; runs too far apart not merged; shoot-around 11 frames -> shot, 12 -> orange; referee boxes present no longer change shot_call. No new numbers; nothing needs Scott before the run (all numbers Scott-approved or existing).

RIM-FIRST CUE FIX SPEC v2 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto.
Deliverable: this one file only. Nothing else is edited; nothing runs that writes outputs.
Author: Hermes (Architect). Cursor codes; Claude Code vets; Muse checks AGREE/DISAGREE.
v1 stands rejected: .team/specs/37_rim_first_cue_fix_spec_v1_REJECTED.md carries Claude Code's REJECTED stamp (2026-11-06). Points 1, 2, 3a pass; 3b is replaced below. Binding input: .team/specs/36_rim_first_extras_fix_spec.md K1-K8 (top block) stays binding unless changed here.

1. SCOTT'S DECISIONS 2026-11-06 (Points 1-3, all binding)

The spec-36 run hid real game shots: 38 real shots taken off the shot list -
shoot_around 19, fouled_miss 13, referee_holding 5, match shift 1 (run36
frames.json / moments.json + measure results).

Point 1 - drop the referee checks completely.
Remove possible_fouled_miss AND referee_holding from assign_shot_calls
(.team/shot_detectors/rim_first_finder.py). Referee boxes are still collected
and saved in frames.json (key "r" in _compact_frame; collection in detect_span)
but are never used for a shot call. Fouled misses and blocks are then counted
WRONG by the measure (rim_first_measure.py --truth), said plainly; the finder
does not guess foul, block, or game time.

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
rim_first_finder.py:792-800) with a count of frames in
[trigger_ms - TRACE_BEFORE_MS, trigger_ms].

Point 3 - fix the order so merge and fake-hoop checks can work.
Order inside one detect span: detect -> hoop check -> series pairing -> runs
-> moments -> calls.
3a. Fake-hoop size check PER FRAME, BEFORE hoops are paired into series: keep
a BODD hoop box only when its width is in
[HOOP_W_MIN_WIDTHS, HOOP_W_MAX_WIDTHS] = [0.5, 1.5] x the film median hoop
width (spec 36 K8; rim_first_finder.py:78-80). A dropped hoop box does not
pair to a series, does not start a series, and does not feed the hoop carry
(resolve_frame_hoops / build_hoop_carry).
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

2. SHOT-CALL ORDER (assign_shot_calls, rim_first_finder.py:830-1020)

First rule that fires sets shot_call; flags list every rule that fired:
1 not_a_hoop -> not_a_shot (series filter, unchanged from spec 36)
2 same_shot_merged -> not_a_shot + merged_into_frame (same-series merge KEPT
as-is, release mode 0.6; see section 3)
3 possible_shoot_around -> orange, 12-of-3000-ms frame count (Point 2)
4 otherwise shot, shot_reason None
Referee_holding and possible_fouled_miss are REMOVED (Point 1). K1-K3 shapes
stay binding: shot_call in {shot, orange, not_a_shot} plus shot_reason;
shooter kept separate with shooter_reason; scorecard on shot_call; any group
entry called shot is WRONG whatever its tags say. Referee groups now land in
that "called shot = WRONG" bucket plainly.
test_rim_first.py: add pure-function tests for the 12-of-3000-ms count and the
per-hoop pre-pair width filter. No catch-0.5 test (catch 0.5 is not adopted).

3. SAME-HOOP FIX: STOP TWO SERIES ON ONE HOOP (replaces Point 3b)

What Claude Code verified, read-only, on run36 frames.json / moments.json:
- catch 0.5 x diagonal = 117 px vs release 0.6 x max = 129 px for the median
  player box (90 x 215 px). On close moment pairs the held-frame count changes
  by 0-14; the one same-series F pair (48040 -> 52400 ms) is 26 vs 26.
- Real put-back pairs show 7-77 held frames; the F pair shows 26. Player
  proximity in the picture does not separate same-shot from put-back here.
- 6 of 7 F (same shot twice) entries are two DIFFERENT series on the SAME
  physical hoop: moment pairs (t_ms series hoop_x):
  Adrian 135280 s1 1106 / 135800 s2 1118; 3021000 s0 823 / 3021480 s2 831;
  1791800 s0 608 / 1792840 s1 679; Notus 144960 s2 479 / 145200 s0 482;
  194720 s1 840 / 194760 s0 873. (Adrian 3093480 s2 104 / 3094200 s0 493 are
  different hoop x: 104 vs 493.) Triggers 40-1040 ms apart.
- same_shot_merged only compares moments in one series (groups by series id,
  rim_first_finder.py:950-961), so it never sees cross-series pairs.
- How a second series starts on one hoop, from the code: dedupe_hoops
  (rim_first_finder.py:659) keeps one box per int(x // 80) bucket PER FRAME,
  so two boxes on one hoop in different buckets both survive (608 -> bucket 7,
  679 -> bucket 8; 479 -> 5, 482 -> 6). pair_hoops_to_series (:637-656)
  pairs nearest x with NO distance limit but marks one series used per frame,
  so an unassigned box starts a new series with ref_x = its x
  (assign_frame_hoops :742-749). Series never close and nothing merges two
  series on the same hoop. A carried hoop plus a detected box cannot co-occur
  in one frame (resolve_frame_hoops :627-634 returns detected hoops when any
  exist). Same-hoop boxes detected 40-1040 ms apart are in different frames,
  so dedupe never compares them.

Fix: BOTH (a) and (b), no new numbers, no new time number.
(a) Same-hoop collapse per frame BEFORE pairing: collapse hoops on the same
hoop to one box (highest conf) using the existing same-hoop distance
MISS_RIM_ZONE_WIDTHS 0.735 x film median hoop width (about 72 px at Adrian's
98 px median, ADRIAN_MEDIAN_HOOP_W rim_first_finder.py:66; the HOOP_X_BUCKET_PX
80 px distance covers it too) - max observed same-hoop split is 71 px
(608 vs 679). Applied per frame before pair_hoops_to_series, so one box per
hoop per frame; since series never close, one box per hoop per frame means one
series per hoop - two series cannot form on one hoop. Dropped duplicates do not
pair, start a series, or feed the carry.
(b) Cross-series duplicate rule in assign_shot_calls: two moments on different
series whose hoops are within the same same-hoop distance and whose triggers
fall inside one another's v6 run (frames of the earlier run overlap or touch
the later run within MAKE_GAP_FRAMES 8, rim_first_finder.py:56, passed as
gap/lookback at :1501-1507) -> later moment is not_a_shot "same_shot_merged"
with merged_into_frame. This is the safety net for any pair (a) misses; today
same_shot_merged is same-series only, so cross-series duplicates are invisible
without it.
Same-series merge: KEPT as-is (release 0.6, trace_shooter untouched).
Catch 0.5 is NOT adopted: it changes nothing for the F pair (26 vs 26 held
frames) and 0-14 frames on close pairs; do not claim catch 0.5 fixes F.

4. NUMBERS TABLE (every number used by this spec)

SHOOT_AROUND_MIN_FRAMES 12 frames - Scott decided 2026-11-06 AFTER SEEING the
run-36 frame counts (not "not picked from run results"). Total frames in
[trigger - 3000 ms, trigger], not consecutive.
SHOOT_AROUND_MIN_BALLS 3 BODD basketballs - spec 36 K8, Scott decided
2026-11-05; rim_first_finder.py:84.
TRACE_BEFORE_MS 3000 ms - spec 33 Scott-approved; rim_first_finder.py:70;
reused for the shoot-around look-back.
HOOP_W_MIN_WIDTHS 0.5 - spec 36 K8, Scott decided 2026-11-05;
rim_first_finder.py:78.
HOOP_W_MAX_WIDTHS 1.5 - spec 36 K8, Scott decided 2026-11-05;
rim_first_finder.py:80.
MIN_SERIES_V6_POINTS 3 - spec 36 K8, Scott decided 2026-11-05;
rim_first_finder.py:82; series-level traffic check, unchanged.
ball_inside_player merge factor 0.6, mode "release" - UNCHANGED
(shot_rules_measure.py:42; trace_shooter); catch 0.5 NOT adopted, no new number.
SAME-HOOP DISTANCE - no new number: MISS_RIM_ZONE_WIDTHS 0.735 x film median
hoop width (about 72 px at Adrian's 98 px median), or equivalently the
HOOP_X_BUCKET_PX 80 px distance; max observed same-hoop split 71 px.
MAKE_GAP_FRAMES 8 - rim_first_finder.py:56; reused for the cross-series
run-overlap test; no new time number.
FOUL_REF_WINDOW_MS 1500 ms - REMOVED (was spec 36 K8, rim_first_finder.py:86);
referee_holding and possible_fouled_miss removed from shot calls.

No looser cutoffs: no band widening, no extra time, no removal of the size
check, no catch-0.5 merge change. All other spec-36 K8 numbers unchanged.

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
same_shot_merged: YES, exactly - frames.json holds per-frame balls and players
(keys "b", "p"); possession between two trigger frames is recomputable.
fake-hoop-before-pairing and same-hoop collapse: NO, not exactly - run36
series already absorbed fake hoops because pair_hoops_to_series has no distance
limit (rim_first_finder.py:637-656), so re-filtering run36 frames would not
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
- The 12-frame warm-up number was chosen after seeing these two films; it is
not independent. The Q4 blind run is the real test.

7. RULES

- No core edits (event_generator.py, ai_bridge.py, court_memory.py,
net_detector.py untouched). Cursor may edit rim_first_finder.py and
test_rim_first.py only; rim_first_measure.py is not edited (see section 5).
- No training; existing v6 and BODD weights only.
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows,
wider column, hoop recenter.
- Per-frame dedupe of hoop boxes is NOT hoop recenter; the make rule's hoop
position is untouched.
- Finder reads no tags, no scoreboard, no DB; referee boxes saved but unused
for calls; DB read-only; images local only.
- No tuning after results; one try, then stop for Scott. Q4 blind last.
- Claude Code vets, Muse checks AGREE or DISAGREE per VETTED/PASS; a
DISAGREE stops the loop for Scott; stop for Scott with the numbers table.
