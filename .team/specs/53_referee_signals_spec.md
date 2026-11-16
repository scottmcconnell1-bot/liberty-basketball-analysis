SPEC 53 - REFEREE HAND SIGNALS

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/53_referee_signals_spec.md (this file only; nothing else edited by this spec)
Status: v9 for team agreement (Hermes owns the rewrite; v7 applied as written (pass-bar vs rules conflict resolved; ft_next added to the fouled_miss predicate); Scott's binding numbers (.team/review52/scott_numbers53.txt, 2026-11-14) binding). v8 applies, exactly: (1) DETECTABLE event rotate_hands (NFHS #22 travel) ADDED: both wrists near chest height (between shoulder and hip keypoints), close together (< ~1 shoulder width apart), moving in opposite-phase circular paths for >= 1 full cycle within ~2 s; wrist-trajectory pattern (not a finger/fist cue) -> claimable from pose; (2) violation_travel predicate = arm_raised (stop clock) followed within ~2 s by rotate_hands, near the shot/putback time window, + play_stopped; output category "violation" -> that shot (and the putback it covers) is not a shot (Scott rule: waved-off/violation attempts do not count); (3) pass bar: rimrock:77 must output "violation" (no longer "unknown is OK" for 77); rimrock:253 rule from v7 stays; (4) fist (#4), thumbs, fingers remain not claimable from pose. v8 applied as written; v9 changes: the pass bar applies ONLY when the referee step is enabled (after the Step 0 80% keypoint gate passes); if Step 0 fails, the step stays OFF and no pass bar is read; stale violation-row wording fixed (v8 has violation_travel). Nothing is built until Hermes/Muse/Cursor agree.

FACTS:
- Goal (Scott, binding, 2026-11-14, team request): referee calls during a shot attempt are detected from the referee's hands; find all referee calls/hand signals and include them in shot decisions based on hand motions. Nothing is built until the team agrees.
- Scott rule (binding, 2026-11-14, amends spec 52 R1): fouled missed attempts, waved-off shots and warm-up shots do NOT count as shots; putbacks are separate; airballs count. Warm-ups stay -1.
- Current shot model (r2plus1d clip crop around the rim, .team/mm_clip/) cannot see referees, so fouled/waved-off cases become errors or coach checks today.
- Tools on disk: BODD/player detector referee class (models/player_detector.pt; .team/shot_detectors/rim_first_finder.py REFEREE_CLASS, is_referee_player; frames.json key "r" referees, never merged into players). YOLO pose via ultralytics in the GPU env (env path to verify at build) can add shoulders/elbows/wrists keypoints. Films are 720p broadcast/NFHS; referees are often small and sometimes off screen when the camera pans.
- Spec 52 training is running (choose_e). Do not change spec 52; this is additive. Spec 53 output feeds spec-52 scoring (section 7).

STANDARD NFHS SIGNALS (2024-25 chart, .team/review52/nfhs_signals_reference.md - supersedes the from-memory list in prompt_team_refsignals53.txt):
- #1 start clock: arm raised open hand, chopped down
- #2 stop clock: one arm straight up, open hand
- #3 stop clock for jump/held ball: arm up, then both thumbs up
- #4 stop clock for foul: one arm straight up, CLOSED FIST (#5 optional bird dog: fist + other arm pointing at fouler)
- #16 no score / waved off: both arms crossing/scissoring in front at waist-chest height, out to sides
- #17 goal counts: arm up then dropped down (pull-down)
- #18 points scored: arm out to side with 1 or 2 fingers
- #19 3-point attempt: one arm raised with three fingers; 3-point made: BOTH arms straight up
- #20 free throw: finger(s) up showing number of FTs
- #22 travel: rotating hands / wrist circles (rolling arms in front of chest); DETECTABLE as rotate_hands wrist-trajectory event (v8): both wrists near chest height (between shoulder and hip keypoints), close together (< ~1 shoulder width apart), moving in opposite-phase circular paths for >= 1 full cycle within ~2 s
- #39 technical foul: T with hands
- Report-type foul signals after the stop-clock fist: #31-#38 (illegal use of hands, hand check, holding, blocking, pushing/charging, player/team control, intentional, double, technical)

POSE LIMIT (hard, not a tuning knob): COCO keypoints 0-15 (shoulders, elbows, wrists) have no finger or thumb joints. Closed fist / thumbs-up / 3-finger cues are NOT directly detectable. Directly measurable proxies only: arm raised (wrist above shoulder/head height) and both arms up. #22 travel via rotate_hands (wrist-trajectory pattern) IS claimed from pose (v8); fist / thumbs / 3-finger cues remain NOT claimable from pose; they are resolved only through Per-shot cue fusion (section 2) or output "unknown" -> coach-review flag; never guessed.

DETECTABLE EVENTS (v1, from CURSOR audit; v8 adds rotate_hands): arm raised (one arm above head), both arms up, lateral wave/scissor (#16 no score), chop down (#1 start clock), rotate_hands (#22 travel; v8: wrist-trajectory pattern - both wrists near chest height (between shoulder and hip keypoints), close together (< ~1 shoulder width apart), moving in opposite-phase circular paths for >= 1 full cycle within ~2 s - claimable from pose). Fist vs open hand, thumbs, fingers, T = NOT detectable by COCO pose at this size -> never claimed; only inferred through Per-shot cue fusion (section 2; arm raised + play stops + FT setup / restart context + score change) per Scott's addendum; otherwise category "unknown" -> coach flag (<=20 cap).

Scott's examples (first known cases, .team/review52/spot_check_52_answers.json): rimrock:77 travel (#22, rotate_hands DETECTABLE) -> violation, no shot; rimrock:253 no score (#16) -> waved off, no shot; gvg:149 shooting foul (#4 fist) -> fouled miss, no shot; hsb:91 fouled shot -> no shot; gvg:349 jump ball (#3 thumbs up) -> held-ball context, deduce or unknown; rimrock:325 fouled before clip -> no referee in clip -> no change.

1. WHAT TO DETECT (buildable chain):
- ref box -> pose keypoints -> arm events with times (frame + t_ms).
- Referee box from frames.json "r" (BODD referee class, own list, never merged into players, .team/shot_detectors/rim_first_finder.py _compact_frame / _is_referee_box). Held-fixed box semantics: is_referee_player tests the tested box geometry against nearby referee boxes; no player-box matching (that was spec 36's failure mode).
- Pose step (additive, GPU env): crop the referee box, run YOLO pose, read shoulder/elbow/wrist keypoints, compute per-frame arm state: raised / both-arms-up / chop / waving-across-body / rotate_hands (#22 travel; v8 wrist-trajectory) / unresolved (fist/thumbs/3-finger not resolvable from pose alone). Emit events with frame and t_ms.
- Moment window only (CURSOR): pose runs ONLY within about -1 s .. +4 s around each candidate/shot, on the 1-2 nearest BODD "r" boxes from the existing frames.json; NO full-film pose pass.

2. PER-SHOT CUE FUSION (Scott addendum #2, binding; restored in v4):
Scott binding (2026-11-14, .team/review52/addendum_ref53_scott.txt): "Go with the book, but some wiggle room. Some things may have to be deduced with several factors because referees do not always follow the book, or clearly indicate their intent." => The design must NOT be a strict per-signal classifier only; it combines cues.

Per candidate shot, collect the cue set within the moment window (section 1) and store the evidence list per shot:
- Arm-event type and its time relative to release/rim time: pose emits arm events with frame + t_ms; the event time is compared to the shot release/rim time (t_release / t_rim); fist vs open hand, thumbs, 3-finger are resolved only where pose permits (arm raised + play stops + FT setup / restart context + score change).
- Which referee (nearest / lead, distance to play): attribute cues to the nearest / lead BODD "r" referee; distance-to-play context where readable.
- Play stopping (players stop / clock overlay stops where readable): stop cue recorded; "ball handed to ref" dropped/deferred until a safe source exists (was the spec-36 false-fire proxy).
- Next restart (FT setup / restart context: free-throw lineup in lane vs play on; "throw-in restart" deferred until a safe source exists / no detector): restart context recorded.
- Score overlay change or not (where readable): score-change cue recorded; 48b game_session = clock/session/FT windows only, NOT a score reader; score-change cue uses scoreboard_clock.py / scoreboard_pair_rises.py only where a readable score track exists, else the cue is omitted (never inferred).

Cue -> source file table (CURSOR v4; builders must not invent proxies):
| Cue | Concrete source |
|---|---|
| Arm event + t_ms | New - pose on "r" crops (ref_signals.py proposed) |
| Time vs release/rim | Yes - moment t_ms / release_frame in finder |
| Nearest / lead ref | Yes - "r" geometry (distance logic new, boxes exist) |
| Players stop | Yes - ft.stillness in ft_half_circle.py |
| Clock overlay stops | Yes, where board exists - 48b samples.json clock holds; Rimrock has no 48b board |
| FT lineup next | Yes - decide_ft ft_reason "free_throw_line" / "maybe_free_throw" (ft_reason strings from decide_ft, not function names) |
| Score overlay change / not | Not 48b - score API = scoreboard_clock.py + scoreboard_pair_rises.py; track on disk = Adrian only; else cue omitted (never inferred) |
| Ball handed to ref | No safe source - deferred (spec-36 false-fire proxy) |
| Throw-in restart | No detector - deferred |
| #22 travel (rotate_hands) | Yes - pose wrist-trajectory event rotate_hands (v8); fists/thumbs/fingers remain not pose-detectable |

How cues combine into one category per shot (fouled_miss, waved_off, violation, and_one, none, unknown):
- WRITTEN COMBINATION TABLE (v6; formalized from the v1 combination prose per MUSE's non-blocking v4 residual; NO learned model in v1; deduction may use several factors (Scott addendum) because referees do not always follow the book or clearly indicate intent). Each category row below is a BOOLEAN FUSION predicate over DETECTABLE inputs only (vocabulary: arm_raised, both_arms_up, wave_scissor, chop, rotate_hands, timing_vs_rim_release, nearest_ref, play_stopped (ft.stillness / clock hold), ft_next (decide_ft ft_reason), score_changed where readable). #22 travel via rotate_hands IS a DETECTABLE pose class (v8); #4 fist / thumbs / fingers / #18 remain NOT pose primitives; those NFHS meanings are what a predicate infers, never claimed from pose.
| Category | Combination |
|---|---|
| fouled_miss | (`arm_raised` AND `timing_vs_rim_release` within `foul_ref_window_ms` of release/rim AND `play_stopped` AND `ft_next`) AND shot missed -> fouled_miss; made -> and_one (make stays make, foul tagged) |
| waved_off | (`wave_scissor` AND `timing_vs_rim_release` (wave start within 1000 ms after rim/release; last <= 1500 ms) AND `score_changed` == False) -> waved_off; score cue omitted (no readable score track, e.g. Rimrock) -> waved_off no-score rule: predicate that would cancel a real shot without the score cue -> "unknown" (coach flag, <=20 cap) under Scott's 0-false-fire rule (2026-11-14, .team/review52/scott_numbers53.txt); no stricter no-score rule stated in v6 -> binding rule stands |
| violation | stop clock (#2) then #22 travel: violation predicates that exist (v8, DETECTABLE-only boolean fusions): stop_clock_in_shot = (`arm_raised` stop-clock cue timed vs release/rim within shot window AND `play_stopped`); violation_travel = `arm_raised` (stop clock) followed within ~2 s by `rotate_hands` (NFHS #22 travel: both wrists near chest height, close together, opposite-phase circular motion >= 1 full cycle within ~2 s) near the shot/putback time window AND `play_stopped` -> category "violation" -> that shot (and the putback it covers) is not a shot; no other violation predicate in v8. |
| and_one | (`arm_raised` AND `timing_vs_rim_release` within `foul_ref_window_ms` AND `play_stopped` AND `ft_next`) AND shot made AND `score_changed` -> and_one; make stays make, foul tagged |
| none | cues present (e.g. `arm_raised` / `chop` / `wave_scissor` / `both_arms_up`) but no category boolean fires -> no foul/wave on the shot |
| unknown | predicate unresolved (unreadable input) -> coach-review flag, never guess |
- CATEGORY PRECEDENCE ORDER (v6, binding; first match wins): and_one > fouled_miss > waved_off > violation > none > unknown.
- One category per shot; evidence list stored per shot (cues, times, referee, stop/score context).

Unknown -> coach-review flag; never guess; no referee visible -> no change:
- unresolved signal -> category "unknown" + evidence listed; coach-review flag within the <=20 cap; never force a category, never guess.
- no referee visible -> NO change (no cue).

How the category feeds spec 52 scoring and later shot calls:
- fouled_miss / waved_off categories feed the spec-52 scoring flow (section 7): fouled / waved-off / warm-up excluded from the auto e2e denominator; TEAM decision (spec 52 scoring, decided).
- Later shot calls: category -> assign_shot_calls referee hook (section 6), applied after the existing spec-37 flags and before the final shot_call; measured on seen films first (section 5).

3. HOW EACH EVENT CHANGES A SHOT DECISION (additive; finder/measure/candidates level, no core model edits):
- fouled miss -> shot_call not_a_shot "possible_fouled_miss" (Scott: fouled missed attempt = not a shot).
- waved off -> shot_call not_a_shot "waved_off" (#16 no score).
- violation on the shot -> not_a_shot + violation tag (#2 stop clock then #22 travel via violation_travel: arm_raised stop clock followed within ~2 s by rotate_hands near the shot/putback time window + play_stopped); that shot (and the putback it covers) is not a shot (Scott rule: waved-off/violation attempts do not count).
- and-one (foul on made basket) -> make stays make, foul tagged (#17 goal counts / #18 points plus #4 fist).
- 3-pt attempt tag -> kind 3PT (#19 one arm up); 3-pt made -> both arms up, make stays make.
- stop clock / start clock -> dead-ball and game-session help (#2 open hand up; #1 chop down).
- no referee visible -> NO change (no cue); never guess.
- unresolved signal -> category "unknown" + evidence listed; coach-review flag within the <=20 cap; never force a category.

4. WHY THIS WILL NOT REPEAT SPEC 36:
- Spec 36 cues (fouled_miss, referee_holding) fired on real game shots and hid them; dropped after false fires (drift_log line ~149; Scott approved). Root cause: the pose pipeline was never used; the ball-in-referee-box / referee-holding proxies were the weak proxies that fired on real game shots and hid them.
- The v2 spec-36 root-cause wording blaming is_referee_player was WRONG; corrected here: is_referee_player was a spec-39 shooter bug, not the spec-36 cause.
- Spec 53 v3 avoids the repeat because it uses pose arm events only (no ball-in-box / referee-holding proxies), is gated on labelled TRUE shots, and keeps the no-ref -> no change fail-safe (no cue, never guess).

5. MEASUREMENT ON SEEN FILMS ONLY (labelled shots + Scott's examples) BEFORE ANY BLIND USE; fixed pass numbers; no new human review loops (Scott refused more clip reviews; any human role is one-time and bounded):
- SEEN films: Rimrock, GVG, HSB, GV, Idaho, Adrian, Notus A1 (labelled sets .team/specs/36_extras_truth_labels.json, 44_gv_labels.json, 49_hsb_labels.json, 50_*_cand_labels.json, 51_hsb1_cand_labels.json, labels52_v2.json; Scott's examples rimrock:77, rimrock:253, gvg:149, hsb:91, gvg:349, rimrock:325).
- Pass bar (MUSE C2 / CURSOR, decided; v5; v7; v8): pass = Scott's 6 examples detected as the expected category (rimrock:77 travel -> violation, no shot; rimrock:253 waved off -> no shot; gvg:149 shooting foul -> fouled miss, no shot; hsb:91 fouled shot -> no shot; gvg:349 jump ball -> held-ball context, deduce or unknown; rimrock:325 fouled before clip -> no referee in clip -> no change), AND false fires on labelled true shots (labels52_v2 class 1/2 rows on seen films) at or below a fixed number written now, marked SCOTT'S RULE (0 allowed; any labelled real shot cancelled or changed = referee step OFF, from .team/review52/scott_numbers53.txt, 2026-11-14). Warm-ups/breaks alone are not enough. v8 pass-bar change: rimrock:77 must output 'violation' (no longer 'unknown is OK' for 77); rimrock:253 (waved off) rule from v7 stays. Scott's 0-false-fire rule wins over coverage. v9 pass-bar change: the pass bar applies ONLY when the referee step is enabled (after the Step 0 80% keypoint gate passes); if Step 0 fails, the step stays OFF and no pass bar is read.
- Pass protocol: run the referee cue chain on SEEN films only; check cue events against labelled not_a_shot / shot moments; Scott's binding numbers from .team/review52/scott_numbers53.txt are fixed before the run (pattern: spec 36 K8, spec 38 S8, spec 41 L7).
- No blind use: unseen films (Adrian Q4, HSB1 remaining, new films) only after Scott approves.

6. SHOT-CALL HOOK (Cursor audit target):
- .team/shot_detectors/rim_first_finder.py assign_shot_calls accepts referee_boxes and does not read it today ("Referee boxes stay in frames.json and do not change shot_call"). The spec-53 hook plugs in there: referee events -> referee category + evidence per moment, applied after the existing spec-37 flags and before the final shot_call; finder signature stays video + models + out dir only. No core model edits; no changes to .team/mm_clip/.
- Moment-window / build surface (CURSOR): new .team/shot_detectors/ref_signals.py (crop "r" -> pose -> events JSON) + test_ref_signals.py; thin optional hook in postproc/ensemble_predict (override to not_a_shot only when event fires); do not touch spec 52 training, core finder, ball model. First prototype: 3 seen clips (rimrock:77, gvg:149, rimrock:253) with keypoint overlay dump.

7. HOW OUTPUT FEEDS SPEC-52 SCORING (per Scott addendum #3 / spec-52 retrain replies):
- fouled_miss and waved_off are scored as not_a_shot; review flags catch model firings on those.
- Fouled / waved-off / warm-up excluded from the auto e2e denominator; the agent checks Scott's blind labels - Scott does not review more clips.
- TEAM decision (spec 52 scoring, decided): fouled / waved-off / warm-up attempts are EXCLUDED from the auto e2e denominator; spec 53 output may later turn them into automatic not-shots, measured on seen films first. Spec 52 itself is unchanged.

8. BUILD ORDER (smallest prototype; nothing built until the team agrees):
- Step 0 (MUSE C3): small-referee pose test as an explicit FIRST gate: on gvg/hsb/notus (smallest refs, ~47-56 px wide) pad/upscale crop of the referee from the FULL frame; pose keypoints must be found on >= 80% of referee-visible moments before anything else runs (SCOTT'S RULE from .team/review52/scott_numbers53.txt; else the referee step stays OFF).
- Step 1: fixed referee box + frames.json "r" on ONE seen film; pure-function tests for cue gating (arm-raised timing window, fusion rules, unknown route).
- Step 2: YOLO pose on referee boxes; arm-event -> shot_decision mapping; prototype on 3 seen clips first (Cursor), before any full-film run.
- Step 3: measure on SEEN films (section 5); before/after make/miss safety check (section 10).

9. NUMBERS TABLE (fixed, not retuned after results; v6 applies Scott's binding numbers from .team/review52/scott_numbers53.txt, 2026-11-14):
- foul_ref_window_ms: 1500 ms (Scott confirms; stands).
- waved_off window: SCOTT'S RULE (2026-11-14, .team/review52/scott_numbers53.txt, verbatim: "pretty immediate and short lasting"): wave must start within 1000 ms after the ball reaches the rim (or release if rim time unknown) and last <= 1500 ms.
- 3PT arm-up min height: SCOTT'S RULE (2026-11-14, .team/review52/scott_numbers53.txt, verbatim: "his hand over his head"): wrist keypoint above the nose/eye keypoints BY A STATED MARGIN (e.g. >= 0.25 x shoulder width; Scott's "by a margin"); NOT spec 38 S8 (S8's 8 frames / 1.5 hoop widths = track-break gap / FT pass line, misattributed in v1).
- small-ref pose keypoint-found share: >= 80% of referee-visible moments must have arm keypoints found; else the referee step stays OFF (SCOTT'S RULE, Scott chose "8 out of 10"; MUSE C3 first gate, before anything else runs).
- labelled-true-shot false-fire pass bar: 0 allowed (SCOTT'S RULE, Scott: "Never. It is very rare a referee gives a wrong shot signal."): any labelled real shot cancelled or changed = referee step OFF (MUSE C2; fixed before the run).
- coach-review cap: <=20 (fixed)
- no-referee-visible -> no cue (fixed)

10. MAKE/MISS SAFETY (unchanged make/miss outputs):
- Before and after: run the spec-52 make/miss review-page comparison (gray/orange groups per TEAM_RECOVERY.md) on the seen films; require unchanged gray count / orange count / shot count and the same 3 combined groups. Any difference -> STOP for Scott. Exact gate command and pass counts are scoped by Cursor before the run (same fixed-numbers rule), not tuned after.

11. RULES:
- No core edits; no banned trials; no tuning after results; one try; Scott's binding numbers fixed before the run; no blind peeking; unknown -> coach flag, never guess.

12. ROLES & GATES:
- Cursor codes. Claude Code vets (no core edits, numbers fixed before run, finder takes only video + models + out dir). Muse checks AGREE or DISAGREE. Stop for Scott with the numbers table.

FACTS SOURCES: team request 2026-11-14; drift_log 2026-11-06 spec 36/37 and 2026-11-14 lines 391-393; .team/specs/36_rim_first_extras_fix_spec.md; .team/specs/52_label_audit_stable_ensemble_spec.md; .team/review52/spot_check_52_answers.json; .team/review52/nfhs_signals_reference.md; .team/review52/addendum_ref53_scott.txt; .team/review52/cursor_ref53.txt; .team/review52/muse_round52_53.txt; .team/shot_detectors/rim_first_finder.py (REFEREE_CLASS, is_referee_player, assign_shot_calls, _compact_frame); .team/mm_clip/ (trigger2.py, candidates.py, ensemble_predict.py, gate52.py).

HERMES: SPEC WRITTEN