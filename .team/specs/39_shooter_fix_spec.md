VETTED WITH CONDITIONS by Claude Code, 2026-11-06: v1 read against spec 38 S1-S8, 38_handcheck_results.json, rim_first_finder.py; read-only checks on run38 frames/moments (spec-38 sample only; Q4 not used). P1-P6 OVERRIDE the text below.
P0 Hermes is right on two counts Claude Code gave wrong: orange-avoidable in the spec-38 sample is 6 (not 10); non-shot rows are 4 (Adrian 15, Notus 0, 1, 14), not 3.
P1 F1 as written fails: player-box overlap / player area caught 0 of 4 referee picks at the release frame (a referee box sits INSIDE the larger mislabelled player box, e.g. 0.40 of the player box; on 1 of 4 there is no referee box on that frame). Replace: a player box is "referee" when, on at least REF_MIN_FRAMES of the frames within +-REF_WINDOW_FRAMES of the frame tested, some referee box has area(player box INTERSECT referee box) / area(referee box) >= REF_INSIDE 0.5, the player box being matched across those frames by IoU >= 0.5 with the tested box. Such a box can never hold. Check on the spec-38 sample: the 4 referee picks have 9, 13, 18, 20 such frames within +-12; the 33 other found picks have 0 (one has 1). Numbers Scott decides before the run: REF_INSIDE 0.5, REF_WINDOW_FRAMES 12 (0.5 s), REF_MIN_FRAMES 5 - chosen after seeing the spec-38 sample, said plainly; the seed-39 sample is the test.
P2 F2 kept: merge same-frame player boxes with IoU >= 0.5, keep the larger. Check: in "two players hold" orange the max pair IoU is >= 0.5 in 21 of 36 (Adrian) and 6 of 14 (Notus). Numbers Scott decides: 0.5, larger box.
P3 F3 DROPPED. Hold length does not separate right from wrong on the spec-38 sample: right shooters 1-73 frames, wrong lane players 1-8; K=3 would drop about 6 right picks and fix 2 of 4 lane picks. "Longest hold" was also checked: it changes 9 right picks to fix 1. E2 (FT lane player) is NOT fixed in spec 39 - said plainly.
P4 Order: P1 referee filter -> P2 merge -> existing walk_back hold test (release 0.6, 8-frame break, 3000 ms; unchanged). Still orange: two distinct players hold, no hold, track broken.
P5 Gate: all fixes OFF reproduces run38 moments exactly (moments_differ = 0). New frozen sample seed 39 (rule as spec 38, file .team/specs/39_handcheck_rule.json written before the run), verdicts to 39_handcheck_results.json before reading numbers; also re-score the spec-38 sample.
P6 Live run passes referee boxes with frame numbers; retrace reads frames.json "r". No new tags, no tracker; matching by IoU across nearby frames is the same box-overlap test as P2, not ByteTrack/DeepSORT.
SETTINGS FIXED BY CLAUDE CODE, 2026-11-06 (Scott: "aim for higher results"; memory settings-are-claudes-call): REF_INSIDE 0.5, REF_WINDOW_FRAMES 12, REF_MIN_FRAMES 5, MERGE_IOU 0.5 keep larger box, cross-frame match IoU 0.5. Fixed before code and run; no change after results. Also explored and rejected on the spec-38 sample before the run: hold length K, longest hold, climb-start release (fixed 1 FT, broke 4 jump shots/layups). FT lane-player error moves to the court-line step (FT shooter = player at the FT line).

SHOOTER FIX SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis, branch team/auto.
File: .team/specs/39_shooter_fix_spec.md (new file only; nothing else edited).
Cursor edits rim_first_finder.py, rim_first_measure.py, test_rim_first.py only.

1. GOAL (Scott 2026-11-06: "Yes, fix the shooter first")
Fix the shooter trace errors from spec 38 (E1, E2, E4) before the 3-point line / referee-signal step. Video only; no tags; shot calls and make/miss untouched.

Spec 38 result (one try, retrace from saved run37 files, no video; drift_log.md line 166): shooter found Adrian 75/116, Notus 22/36. Orange: Adrian 41 (two players hold 36, no hold 4, track broken 1); Notus 14 (two players hold 14). Hand-check (frozen sample, written before numbers): found right Adrian 15/20, Notus 9/17; orange right 3/5, 1/5.

2. ERRORS FROM THE SPEC-38 HAND-CHECK (.team/specs/38_handcheck_results.json)
E1 referee picked as shooter 4 times (Adrian i=1, i=10; Notus i=9, i=12) - a BODD box on a referee under the rim read as "player". Referee boxes are saved in frames.json key "r" and exist in the live run, but _trace_walk_back never sees them; _is_referee_box (rim_first_finder.py:477-482) only catches boxes already classed "referee", which a mislabelled "player" box is not.
E2 free throw: lane player next to the shooter picked 4 times (Adrian i=2, i=5; Notus i=5, i=11) - walking backward, the ball passes in front of lane players on its way up and the first box it is inside wins on a single frame.
E3 non-shot moments 3 times (dribbler in transition, hoop marker on a referee head or bench) - a shot-finder issue, not the trace; not fixed here.
E4 "two players hold" orange: Adrian 36 of 41 orange, Notus 14 of 14 - in the sample two BODD boxes on the SAME player, or the FT shooter plus a lane player.
E5 defender contesting picked once (Notus i=7).

3. FIXES
F1 (E1) - drop a player box that overlaps a referee box on the same frame. Overlap = area(player ∩ referee) / area(player box). Drop the player box when overlap >= T_ref. Referee boxes come from frames.json key "r" (retrace reads key "r" with balls/players; live run passes the referee list) and are threaded into the trace per frame alongside player boxes. T_ref: Scott decides before the run; proposed 0.5.
F2 (E4) - merge player boxes on one frame that overlap heavily (same body) into one box before the hold test. Overlap = IoU = area(intersection) / area(union) of two same-frame player boxes. Merge when IoU >= T_merge; keep the larger-area box (same body; saved player boxes carry no confidence). T_merge: Scott decides before the run; proposed 0.5. Keep rule: Scott decides before the run; proposed larger area. Runs per frame, before _holders_on_frame.
F3 (E2; considered for E5, not adopted - see section 4) - a hold must LAST: the ball inside the same player's box on at least K detected ball frames in a row in the backward walk before it counts. "Same player" across adjacent detected frames = box IoU >= M (intersection/union); no tracker (ByteTrack/DeepSORT banned), no interpolation (banned). K: Scott decides before the run; proposed K = 3 detected ball frames in a row. M: Scott decides before the run; proposed IoU 0.5.
Walk rule: stop at the FIRST continuous K-frame hold met walking backward from release_estimate_frame (the hold nearest the release is the shooting hold); short runs (< K) are walked past. Do NOT keep walking to the earliest continuous hold before a break: an earlier hold is a different possession (dribble/pass), and the 8-frame track break already ends the walk. Reaching the window start or a break without a K-frame hold = orange "ball not inside a player box".

4. NOT FIXED HERE (and why)
E3: non-shot moments are a shot-finder problem (the moment should not exist), not a trace problem. Spec 39 touches the shooter trace only; shot calls are untouched.
E5: defender contesting picked once - one occurrence, not a pattern. A K-frame hold rule cannot distinguish a contesting defender whose hands bracket the ball for K frames from the shooter, and one try means no retune on a single case. Stays found/orange as-is.

5. ORDER OF FIXES
F1 -> F2 -> F3. Referees out first, so a referee box cannot win a hold or merge with a player; same-body duplicates merged next, so "two players hold" is never two boxes on one body; duration test last, filtering transient lane-player (E2) and defender (E5-considered) intersections.

6. WHAT STILL GOES ORANGE
"no release frame", "no ball at release frame", "no player at release frame", "ball not inside a player box" (no K-frame hold before the window start or a track break), "track broken" (gap > 8 between consecutive detected ball points), "two players hold" (two distinct players each hold for K frames - a real contest/jump ball). E3 non-shot moments and E5 defender contests unchanged.

7. MEASURE (same as spec 38)
Retrace from saved run37 files (frames.json + series points), no video; retrace writes run39_adrian / run39_notus, refuse if exists.
Gate (required): with F1/F2/F3 all OFF, retrace must reproduce spec-38 outputs - Adrian 75/116, Notus 22/36 found; orange reasons two players hold 36/14, no hold 4, track broken 1; FT spot pass Adrian 9/14, Notus 4/4; floor-spot medians 2PT 4.3 / 3PT 8.4 Adrian, 2PT 4.1 / 3PT 7.2 Notus (hoop widths) - with moments_differ = 0. Any difference -> STOP for Scott. The spec-38 walk-off/equality gate is not needed again.
New hand-check: a NEW frozen sample, seed 39 (not the spec-38 seed 38 sample), same rule - 20 found + 5 orange per film (Adrian Q1-Q3, Notus Q1), random.Random(39) on the sorted t_ms list (round-robin 2PT/3PT/FT for found; sample for orange), release frame with shooter box drawn plus release-10 and release+5 frames, agree/disagree/unclear written to .team/specs/39_handcheck_results.json BEFORE reading measure39 numbers.
Re-score the spec-38 sample: report how many of the 13 found disagreements change (file: referee 4 = E1, FT lane 4 = E2, defender 1 = E5, non-shot-family 4: Adrian i=15, Notus i=0/i=1/i=14; prompt states E3 = 3, the dribbler-transition/hoop-marker rows, and Notus i=0 "not a shot frame" is the extra row - that split is NOT FOUND in the file, Claude Code to check) and how many orange-avoidable change (file shows 6: Adrian i=21, i=23; Notus i=17, i=18, i=19, i=21; the prompt's "10 orange-avoidable" does not match the file's 6 - NOT FOUND, Claude Code to check). FT spot and 2PT/3PT distance as before (hoop widths; Measure 1 FT pass line 1.5 hoop widths, spec 38 S8).

8. NUMBERS TABLE (each number: source, or "Scott decides before the run" + proposed value)
| Number | Source | Value |
| TRACE_BEFORE_MS | rim_first_finder.py:73; spec 33 Scott-approved | 3000 ms, unchanged, not widened |
| Track-break gap (MAKE_GAP_FRAMES) | rim_first_finder.py:58, :60 | 8 frames, unchanged |
| release_trace_factor (hold-test circle) | rim_first_finder.py:75; shot_rules_measure.py:43 | 0.6, unchanged (no looser cutoffs) |
| F1 overlap measure | defined here | area(player ∩ referee) / area(player box) |
| F1 threshold T_ref | Scott decides before the run | proposed 0.5 |
| F2 merge IoU | defined here | area(intersection) / area(union) of two same-frame player boxes |
| F2 threshold T_merge | Scott decides before the run | proposed 0.5 |
| F2 keep rule | Scott decides before the run | proposed larger-area box |
| F3 hold length K | Scott decides before the run | proposed 3 detected ball frames in a row |
| F3 same-player match M | Scott decides before the run | proposed IoU 0.5 across adjacent detected frames |
| Hand-check seed and count | spec 38 handcheck rule pattern | seed 39; 20 found + 5 orange per film |
| FT spot pass line | spec 38 S8 | 1.5 hoop widths, unchanged |

9. RULES
No core edits (collect_q4_bodd.py etc. untouched); no training; no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter); shot calls and make/miss untouched; finder reads no tags; one try, then stop for Scott; Q4 blind last.

10. FACT SOURCES
Every fact above comes from a file read this session or the prompt; otherwise "NOT FOUND - Claude Code to check".
Key lines read: rim_first_finder.py:43, :57-60, :70, :72-75, :449 slice_trace_window, :477 _is_referee_box, :561 _holders_on_frame, :628 _trace_walk_back, :744 trace_shooter; shot_rules_measure.py:37-45, :132 ball_inside_player mode="release", :163 combine_ball_track, :270 release_estimate_frame; .team/specs/38_handcheck_rule.json; .team/specs/38_handcheck_results.json; .team/drift_log.md line 166.
Not confirmed: OLLAMA.md ("early windows" definition) NOT FOUND - Claude Code to check; the 10 orange-avoidable count (file shows 6) NOT FOUND - Claude Code to check; the E3 split 3 vs 4 NOT FOUND - Claude Code to check.