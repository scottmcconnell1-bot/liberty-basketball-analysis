SPEC 53 - REFEREE HAND SIGNALS

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/53_referee_signals_spec.md (this file only; nothing else edited by this spec)
Status: v2 written for team agreement (Muse DISAGREED on v1; rewritten below per Muse findings and Scott's binding addendum .team/review52/addendum_ref53_scott.txt). Nothing is built until Hermes/Muse/Cursor agree.

FACTS:
- Goal (Scott, binding, 2026-11-14, team request): referee calls during a shot attempt are detected from the referee's hands; find all referee calls/hand signals and include them in shot decisions based on hand motions. Nothing is built until the team agrees.
- Scott rule (binding, 2026-11-14, amends spec 52 R1): fouled missed attempts, waved-off shots and warm-up shots do NOT count as shots; putbacks are separate; airballs count. Warm-ups stay -1.
- Current shot model (r2plus1d clip crop around the rim, .team/mm_clip/) cannot see referees, so fouled/waved-off cases become errors or coach checks today.
- Tools on disk: BODD/player detector referee class (models/player_detector.pt; .team/shot_detectors/rim_first_finder.py REFEREE_CLASS, is_referee_player; frames.json key "r" referees, never merged into players). YOLO pose via ultralytics in the GPU env (env path to verify at build) can add shoulders/elbows/wrists keypoints. Films are 720p broadcast/NFHS; referees are often small and sometimes off screen when the camera pans.
- Spec 52 training is running (choose_e). Do not change spec 52; this is additive. Spec 53 output feeds spec-52 scoring (section 8).

STANDARD NFHS SIGNALS (2024-25 chart, .team/review52/nfhs_signals_reference.md — supersedes the from-memory list in prompt_team_refsignals53.txt):
- #1 start clock: arm raised open hand, chopped down
- #2 stop clock: one arm straight up, open hand
- #3 stop clock for jump/held ball: arm up, then both thumbs up
- #4 stop clock for foul: one arm straight up, CLOSED FIST (#5 optional bird dog: fist + other arm pointing at fouler)
- #16 no score / waved off: both arms crossing/scissoring in front at waist-chest height, out to sides
- #17 goal counts: arm up then dropped down (pull-down)
- #18 points scored: arm out to side with 1 or 2 fingers
- #19 3-point attempt: one arm raised with three fingers; 3-point made: BOTH arms straight up
- #20 free throw: finger(s) up showing number of FTs
- #22 travel: rotating fists (rolling arms in front of chest)
- #39 technical foul: T with hands
- Report-type foul signals after the stop-clock fist: #31-#38 (illegal use of hands, hand check, holding, blocking, pushing/charging, player/team control, intentional, double, technical)

POSE LIMIT (hard, not a tuning knob): COCO keypoints 0-15 (shoulders, elbows, wrists) have no finger or thumb joints. Closed fist / thumbs-up / three fingers are NOT directly detectable. Directly measurable proxies only: arm raised (wrist above shoulder/head height) and both arms up. Fist/thumbs/3-finger cues are resolved only through cue fusion (section 2) or output "unknown" -> coach-review flag; never guessed.

Scott's examples (first known cases, .team/review52/spot_check_52_answers.json): rimrock:77 travel (#22) on the shot -> no shot; rimrock:253 no score (#16) -> waved off, no shot; gvg:149 shooting foul (#4 fist) -> fouled miss, no shot; hsb:91 fouled shot -> no shot; gvg:349 jump ball (#3 thumbs up) -> held-ball context, deduce or unknown; rimrock:325 fouled before clip -> no referee in clip -> no change.

1. WHAT TO DETECT (buildable chain):
- ref box -> pose keypoints -> arm events with times (frame + t_ms).
- Referee box from frames.json "r" (BODD referee class, own list, never merged into players, .team/shot_detectors/rim_first_finder.py _compact_frame / _is_referee_box). Held-fixed box semantics: is_referee_player tests the tested box geometry against nearby referee boxes; no player-box matching (that was spec 36's failure mode).
- Pose step (additive, GPU env): crop the referee box, run YOLO pose, read shoulder/elbow/wrist keypoints, compute per-frame arm state: raised / both-arms-up / chop / waving-across-body / unresolved (fist/thumbs/3-finger not resolvable from pose alone). Emit events with frame and t_ms.
- Per-shot fusion (Scott addendum #2, binding): combine arm-raised timing vs the shot (release/rim time), fist vs open hand where resolvable, which referee (nearest/lead), play stopping (players stop, ball handed to referee, clock overlay stops where readable, free-throw setup/lane lineup next), score overlay change (or not), next restart (throw-in vs free throws).

2. HOW EACH EVENT CHANGES A SHOT DECISION (additive; finder/measure/candidates level, no core model edits):
- fouled miss -> shot_call not_a_shot "possible_fouled_miss" (Scott: fouled missed attempt = not a shot).
- waved off -> shot_call not_a_shot "waved_off" (#16 no score).
- violation on the shot -> not_a_shot + violation tag (#2 stop clock then #22 travel etc.; direction signal where visible).
- and-one (foul on made basket) -> make stays make, foul tagged (#17 goal counts / #18 points plus #4 fist).
- 3-pt attempt tag -> kind 3PT (#19 one arm up); 3-pt made -> both arms up, make stays make.
- stop clock / start clock -> dead-ball and game-session help (#2 open hand up; #1 chop down).
- no referee visible -> NO change (no cue); never guess.
- unresolved signal -> category "unknown" + evidence listed; coach-review flag within the <=20 cap; never force a category.

3. WHY THIS WILL NOT REPEAT SPEC 36:
- Spec 36 cues (fouled_miss, referee_holding) fired on real game shots; dropped after false fires (drift_log line ~149; Scott approved). Root cause proven on run36 frames: is_referee_player followed a matching PLAYER box; BODD often labels the person "referee" only, so no player box matched and the cue logic mis-fired. With the picked box held fixed, a referee box sat inside it on 8 and 12+ of the +-12 frames.
- Spec 53 keeps the fixed-box semantics (no player-box matching), adds pose only for directly measurable proxies (arm raised / both arms up — no finger/thumbs classification), replaces the strict per-signal classifier with cue fusion + an "unknown" route to coach review, and keeps the no-referee-visible fail-safe (no change, never guess).

4. MEASUREMENT ON SEEN FILMS ONLY (labelled shots + Scott's examples) BEFORE ANY BLIND USE; fixed pass numbers; no new human review loops (Scott refused more clip reviews; any human role is one-time and bounded):
- SEEN films: Rimrock, GVG, HSB, GV, Idaho, Adrian, Notus A1 (labelled sets .team/specs/36_extras_truth_labels.json, 44_gv_labels.json, 49_hsb_labels.json, 50_*_cand_labels.json, 51_hsb1_cand_labels.json, labels52_v2.json; Scott's examples rimrock:77, rimrock:253, gvg:149, hsb:91, gvg:349, rimrock:325).
- Pass protocol: run the referee cue chain on SEEN films only; check cue events against labelled not_a_shot / shot moments; pass bar = cue fires on the known fouled/waved-off examples and not on labelled warm-ups / breaks / halftime; Scott decides fixed pass numbers before the run (pattern: spec 36 K8, spec 38 S8, spec 41 L7).
- No blind use: unseen films (Adrian Q4, HSB1 remaining, new films) only after Scott approves.

5. SHOT-CALL HOOK (Cursor audit target):
- .team/shot_detectors/rim_first_finder.py assign_shot_calls accepts referee_boxes and does not read it today ("Referee boxes stay in frames.json and do not change shot_call"). The spec-53 hook plugs in there: referee events -> referee category + evidence per moment, applied after the existing spec-37 flags and before the final shot_call; finder signature stays video + models + out dir only. No core model edits; no changes to .team/mm_clip/.

6. HOW OUTPUT FEEDS SPEC-52 SCORING (per Scott addendum #3 / spec-52 retrain replies):
- fouled_miss and waved_off are scored as not_a_shot; review flags catch model firings on those.
- Fouled / waved-off / warm-up excluded from the auto e2e denominator; the agent checks Scott's blind labels — Scott does not review more clips.
- Spec 52 itself is unchanged.

7. BUILD ORDER (smallest prototype; nothing built until the team agrees):
- Step 1: fixed referee box + frames.json "r" on ONE seen film; pure-function tests for cue gating (arm-raised timing window, fusion rules, unknown route).
- Step 2: YOLO pose on referee boxes; arm-event -> shot_decision mapping; prototype on 3 seen clips first (Cursor), before any full-film run.
- Step 3: measure on SEEN films (section 4); before/after make/miss safety check (section 9).

8. NUMBERS TABLE (Scott decides before the run; fixed, not retuned after results):
- foul_ref_window_ms: Scott's ~1.3 s -> 1500 ms (Scott confirms)
- waved_off window: Scott decides
- 3PT arm-up min height: Scott decides (NOT spec 38 S8; S8's 8 frames / 1.5 hoop widths = track-break gap / FT pass line, misattributed in v1)
- coach-review cap: <=20 (fixed)
- no-referee-visible -> no cue (fixed)

9. MAKE/MISS SAFETY (unchanged make/miss outputs):
- Before and after: run the spec-52 make/miss review-page comparison (gray/orange groups per TEAM_RECOVERY.md) on the seen films; require unchanged gray count / orange count / shot count and the same 3 combined groups. Any difference -> STOP for Scott. Exact gate command and pass counts are scoped by Cursor before the run (same fixed-numbers rule), not tuned after.

10. RULES:
- No core edits; no banned trials; no tuning after results; one try; Scott decides numbers; no blind peeking; unknown -> coach flag, never guess.

11. ROLES & GATES:
- Cursor codes. Claude Code vets (no core edits, numbers fixed before run, finder takes only video + models + out dir). Muse checks AGREE or DISAGREE. Stop for Scott with the numbers table.

FACTS SOURCES: team request 2026-11-14; drift_log 2026-11-06 spec 36/37 and 2026-11-14 lines 391-393; .team/specs/36_rim_first_extras_fix_spec.md; .team/specs/52_label_audit_stable_ensemble_spec.md; .team/review52/spot_check_52_answers.json; .team/review52/nfhs_signals_reference.md; .team/review52/addendum_ref53_scott.txt; .team/shot_detectors/rim_first_finder.py (REFEREE_CLASS, is_referee_player, assign_shot_calls, _compact_frame); .team/mm_clip/ (trigger2.py, candidates.py, ensemble_predict.py, gate52.py).

HERMES: SPEC WRITTEN
