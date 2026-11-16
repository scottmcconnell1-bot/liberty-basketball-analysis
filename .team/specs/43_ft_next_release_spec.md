VETTED WITH CONDITIONS V1-V5 (Claude Code 2026-11-08). Conditions win over the text below.
- V1 Stillness: annotate_free_throws computes the stillness value once; <= 0.15 normal decision; (0.15, 0.25] decision then maybe rule (N3); > 0.25 or None -> not_still with no frame read. MAYBE_STILL_MAX 0.25 is a named constant.
- V2 Gate also covers the maybe band: prototype + N3 vs Cursor on every moment with stillness <= 0.25 in the three seen runs.
- V3 Idaho labels: Claude Code labels EVERY shot moment of run42base_idaho as FT / not FT / unclear from video frames (trigger-1 s and trigger), plus the FT shooter's feet when FT, into .team/specs/43_idaho_ft_labels.json BEFORE the spec-43 retrace. Scoring script .team/specs/43_idaho_score.py written before the retrace too. Unclear moments are reported, not scored.
- V5 Interface for the maybe band: decide_ft gets keyword stillness: Optional[float] = None. When stillness is given it decides (still arg ignored): stillness None or > 0.25 -> not_still; (0.15, 0.25] -> run the decision; free_throw_line becomes {free_throw: False, ft_reason: "maybe_free_throw", ft_shooter_box: None, ft_maybe_shooter_box: <record>}; any other result -> not_still; <= 0.15 -> normal decision. When stillness is None the old still bool path is unchanged (tests keep working). annotate_free_throws computes ft.stillness() once, skips the frame read when > 0.25 or None, and passes stillness=value. _apply_ft_decision on maybe_free_throw: free_throw False, store ft_maybe_shooter_box, append "maybe_free_throw" to moment["flags"] (create list if missing), trace shooter unchanged. Gate (V2) compares prototype decide_full(d, gray, still) with Cursor decide_ft(stillness=value): same reason, same shooter / maybe shooter feet within 1 px.

- V4 Coach load is a reported number: on Idaho, count orange items added by spec 43 (maybe_free_throw) and errors the coach would have to fix (false FT, wrong FT shooter, missed FT that is labeled FT).

FT NEXT-CANDIDATE + RELEASE SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/43_ft_next_release_spec.md (this file only; nothing else is edited by this spec)
Lineage: spec 42 (VETTED WITH CONDITIONS M1-M6, 2026-11-08; Muse AGREE) -> spec 43. Scott binding 2026-11-08: "I want you to do better. I do not want to overwhelm the coach." and "We have not [exhausted possibilities] with free throws." Claude Code picks every setting before the run. Cursor codes; Claude Code gates and measures; Hermes does not edit source.

Status: v1 - not run. One measured try on Idaho City (blind), then stop for Scott. Q1-Q3/Q4 seen films are reported, not a test (settings were chosen after seeing all that data). Idaho City is the new game: Liberty home gym, gym "liberty", 1280x720 25 fps, never looked at. Claude Code labels FT moments from video frames BEFORE spec 43 runs on it.

----------------------------------------------------------------
SETTINGS FIXED (Claude Code 2026-11-08; do not change)
----------------------------------------------------------------
- Everything in spec 42 unchanged EXCEPT:
- N1 Next candidate: a candidate that fails too_far_from_hoop, no_lane_lines or release_not_shooter does NOT end the decision; try the next candidate (box-key order). If none passes: reason = the FIRST failure reason seen (else line_not_one / ft_line_not_found as before).
- N2 Release check, after lanes: if the moment has a release_frame and ball points exist, take the ball point nearest in frame to release_frame (tie -> earlier frame); |ball x - box centre x| / box h > RELEASE_DX_MAX 0.8 -> fail "release_not_shooter". No release_frame or no ball point -> check skipped (passes).
- N3 Maybe band: stillness in (STILL_MOVE_MAX 0.15, MAYBE_STILL_MAX 0.25] -> run the same decision; if it would be free_throw_line -> free_throw false, ft_reason "maybe_free_throw", ft_maybe_shooter_box = that player, and the moment gets flag "maybe_free_throw" in moment["flags"] so the coach page shows it orange. Trace shooter unchanged. Otherwise reason "not_still". Stillness > 0.25 -> "not_still", no frame read.
- RELEASE_DX_MAX 0.8. STILL_MOVE_MAX 0.15, MAYBE_STILL_MAX 0.25 (unchanged from spec 42).
- decide_ft takes release_frame (moment.get("release_frame")) as a keyword; annotate_free_throws passes it. Cursor must confirm release_frame is set on the moment before the FT step in BOTH live run and retrace; if not, say so (do not move steps).

----------------------------------------------------------------
A. Detector steps (plain words, exactly the SETTINGS block)
----------------------------------------------------------------
0. Spec 41 gate, unchanged: not still -> free_throw false "not_still", trace unchanged. No hoop -> "no_hoop". Frame unreadable -> "frame_unreadable".
1. Candidates: still-frame boxes that held the ball in [trigger-3000 ms, trigger] (spec 41 candidates()), tried in box-key order.
2. FT line per candidate (spec 41, unchanged): players erased from the paint mask; Hough segments near the feet, near-perpendicular to feet->hoop, Adrian darker-than-both-sides; line = median angle, GROUP_DEG group, mean endpoints, extent along the direction. No line -> try the next candidate.
3. Band: signed distance of the player's feet from the line (normal chosen so the hoop centre is on the negative side, positive = away from hoop). In band when 0.0 <= s <= 0.35 x player height and the along-line position lies within the line extent +/- END_PAD x player height. Need exactly one in-band player and that player must be a candidate -> that player is b (feet f, height bh). Otherwise try the next candidate.
4. Hoop distance: |hoop centre - f| / bh > 3.8 -> free_throw false, reason "too_far_from_hoop", trace unchanged. N1: do not stop; try the next candidate; remember the first failure reason.
5. Lane lines: from the same erased Hough segment list (the set lane_crossings uses on this candidate's line), a lane segment has undirected angle to the FT line direction >= 30 deg; both endpoints signed distance <= +0.15 bh (hoop side); nearest endpoint |signed distance| <= 1.0 bh; Adrian darker-than-both-sides when gym == adrian. Extend it to cross the FT line; r = (crossing projection - f projection) / bh along the FT line direction. Need one segment with r in [-2.5, -0.2] and one with r in [+0.2, +2.5]. Missing either side -> free_throw false, reason "no_lane_lines", trace unchanged. N1: do not stop; try the next candidate; remember the first failure reason.
6. Release check (N2, after lanes): if the moment has a release_frame and ball points exist, take the ball point nearest in frame to release_frame (tie -> earlier frame); |ball x - box centre x| / box h > 0.8 -> free_throw false, reason "release_not_shooter", trace unchanged. N1: do not stop; try the next candidate; remember the first failure reason. No release_frame or no ball point -> check skipped (passes).
7. Hoop distance + lane lines + release check all pass -> free_throw true, shooter b, reason "free_throw_line", trace unchanged. Stop: a decision is made.
8. If no candidate passes: free_throw false, reason = the first failure reason seen across candidates (hoop, then lane, then release, in candidate order); else if any line existed -> "line_not_one"; no line at all -> "ft_line_not_found". Trace unchanged.
9. Stillness band (N3): stillness in (0.15, 0.25] -> run steps 1-8 on the same still frame; if it would be free_throw_line -> free_throw false, ft_reason "maybe_free_throw", ft_maybe_shooter_box = that player, moment gets flag "maybe_free_throw" in moment["flags"] (coach page shows it orange). Trace shooter unchanged. Otherwise reason "not_still". Stillness > 0.25 -> "not_still", no frame read.

----------------------------------------------------------------
B. Code plan (Cursor only)
----------------------------------------------------------------
- ft_half_circle.py:
  * Constant RELEASE_DX_MAX = 0.8 (spec 43). All spec 42 constants unchanged (BAND_BACK 0.35, HOOP_DIST_MAX 3.8, LANE_ANGLE_MIN 30, LANE_HOOP_SIDE 0.15, LANE_GAP 1.0, LANE_REACH 2.5, LANE_MIN_OFF 0.2).
  * decide_ft(): new keyword release_frame: Optional[int] = None. N1: a fail at too_far_from_hoop / no_lane_lines / release_not_shooter records the first failure reason and continues to the next candidate in box-key order; at the end, return the first failure reason seen, else line_not_one / ft_line_not_found as before. Both pass -> free_throw_line with shooter b.
  * N2 release check after lanes: if release_frame is not None and ball points exist, take the ball point nearest in frame to release_frame (tie -> earlier frame); |ball x - box centre x| / box h > 0.8 -> fail "release_not_shooter". No release_frame or no ball point -> check skipped (passes).
  * Debug views: add "release_checked" (bool) and "release_dx_h" (float or None) to each candidate view; hoop_dist_h and lane_segments unchanged (M4).
  * lane_crossings() unchanged (spec 42 shape, out_segments param kept).
- test_ft_half_circle.py (synthetic):
  * Release check passes: |dx| <= 0.8h; release check fails: |dx| = 1.41h (the 20920 number) -> release_not_shooter.
  * No release_frame and no ball point -> release check skipped (passes).
  * Tie in frame distance to release_frame -> earlier frame chosen.
  * Next candidate: first candidate fails too_far_from_hoop, second passes -> free_throw_line, shooter = second candidate; first failure reason is not returned.
  * All candidates fail: reason = the FIRST failure reason seen (e.g. too_far_from_hoop from candidate 1 even if candidate 2 fails no_lane_lines).
  * Band edges and lane tests from spec 42 kept unchanged.
- rim_first_finder.py:
  * annotate_free_throws: read moment.get("release_frame") and pass it as release_frame to decide_ft. Confirm release_frame is set on the moment before the FT step in both the live run and the retrace; if not, say so (do not move steps).
  * _apply_ft_decision: accepts the two spec-42 reason names ("too_far_from_hoop", "no_lane_lines") plus "release_not_shooter" as free_throw false. New: ft_reason "maybe_free_throw" -> free_throw false, ft_maybe_shooter_box = the maybe shooter box, trace shooter unchanged, flag "maybe_free_throw" added to moment["flags"] so the coach page shows it orange. Decide_ft call and debug_image call unchanged in shape. No other change in the finder.
- rim_first_measure.py: count/report release_not_shooter and maybe_free_throw in the FT reasons section, and list maybe moments with their tag. No other change.
- No other file. court_homography.py and stage1b files are read only.

----------------------------------------------------------------
C. Gate before the measured run
----------------------------------------------------------------
- Full retrace of run37_adrian / run37_notus / run37_adrian_q4_blind with video: prototype logic (spec 43_ft_proto.py, decide()) on the SAME raw frames vs Cursor's decide_ft on every moment with stillness <= 0.25; same free_throw, same reason, same shooter feet within 1 px. Any mismatch -> stop for Scott. Do not proceed to the measured run.
- Also: the --ft-off run must still equal run39b on both films (FT off changes nothing for non-FT moments).
- Cursor confirms release_frame is set on the moment before the FT step in both the live run and the retrace; if not, say so (do not move steps).

----------------------------------------------------------------
D. Measure
----------------------------------------------------------------
- Seen films (Adrian Q1-Q3, Adrian Q4, Notus Q1): reported, NOT the test (settings were chosen after seeing this data). Known facts: Q4 blind (spec 42, already run): FT found 4, missed 1 (3461760 no_lane_lines), false 0, too_far 0, shooter right 4/4 (hand-check corrected: 3449040 was right); Q4 has 6 FT tags, 5 matched to moments, 6th tag (3804500) has only an orange non-shot moment 3806360, also no_lane_lines. Q1-Q3 (tuning): Adrian found 23/29, false 0, duplicate 1 (3021480); Notus 9/9, false 0. Maybe counts on seen films are NOT FOUND until the N3 rerun - Claude Code to check.
- Idaho City blind (THE test): Claude Code writes frozen FT labels .team/specs/43_idaho_ft_labels.json from video frames BEFORE the rule runs. One try: retrace of rim_first/run42base_idaho with video --gym liberty. Report FT found / missed / false / maybe, and which were real FTs; shooter right / wrong by hand-check written BEFORE reading the score. One try; then stop for Scott. No re-run, no tuning after seeing the score.

----------------------------------------------------------------
E. Numbers table (each number: fixed by Claude Code before the run + fact behind it)
----------------------------------------------------------------
RELEASE_DX_MAX 0.8 - fixed - fact: true FT picks |ball x - box x| <= 0.54 box heights (n 27 with a release frame, proto44.py); 20920 (3PT jumper, #51 passes band/hoop/lanes) = 1.41. N2 with 0.8 stops 20920 and passes all true FTs.
STILL_MOVE_MAX 0.15 - fixed - fact: spec 40 Q1; rules without stillness flag ~30 non-FT moments, so stillness stays.
MAYBE_STILL_MAX 0.25 - fixed - fact: all-moments check (stillness off); FT-tagged moments with stillness in (0.15, 0.25] that pass every rule: 3 (0.206-0.241); non-FT moments in the same band that pass every rule: 4 (3PT, 0.153-0.236). Hoop distance does not separate them (2.2-2.5 player heights). Stillness > 0.25 -> not_still, no frame read.
Q4 seen results - fact (already run, spec 42): FT found 4, missed 1 (3461760 no_lane_lines), false 0, shooter right 4/4 (corrected hand-check). Both Q4 misses were first-candidate failures (bench player holding a second ball; #0 on the half-circle arc); the next candidate (the real shooter) passes every check. 6th FT tag 3804500 has orange non-shot 3806360, also no_lane_lines.
Maybe counts on seen films - NOT FOUND - Claude Code to check (N3 rerun on Q1-Q3/Q4).
Idaho City blind results - NOT FOUND - Claude Code to check (the blind test; labels file frozen first, hand-check verdicts written before the score is read).
Duplicate rule - fixed - fact: 3021480 is a duplicate moment of tagged FT 3021000 (12 frames later, same shot); report "duplicate of a found FT", not false (spec 42 M3).

----------------------------------------------------------------
Rules
----------------------------------------------------------------
- Settings fixed by Claude Code before code and run; Cursor picks no setting.
- Q1-Q3/Q4 seen films are reported, not a test (chosen after seeing them). The test is one Idaho City blind try.
- Hand-check verdicts for every Idaho City flagged FT / maybe moment are written before the score is read. Then stop for Scott. No re-run, no tuning.
- No core edits, no training, no tracker, no interpolation, no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows = OLLAMA.md:31-39, wider column, hoop recenter).
- Finder reads no tags, scoreboard, or database.
- Labels file .team/specs/43_idaho_ft_labels.json is written before the rule runs and is frozen after.
- Every fact above comes from a file read in this session or the user's message; anything else is "NOT FOUND - Claude Code to check".

End of spec.
