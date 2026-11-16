VETTED WITH CONDITIONS M1-M6 (Claude Code 2026-11-08). Conditions win over the text below.
- M1 Gate (replaces C first bullet): the prototype cached JPEG frames, so it is not compared on the cache. Gate = full Q1-Q3 retrace of run37_adrian / run37_notus with video; on every still moment Claude Code's gate script runs the prototype logic on the SAME raw frame and inputs and compares with Cursor's decide_ft: same free_throw, same reason, same shooter feet (within 1 px). Plus --ft-off == run39b both films. Any mismatch -> stop for Scott.
- M2 Caches live in Claude Code's scratchpad, not rim_first; not used by the gate.
- M3 Duplicates (rim_first_measure.py, ft section): a moment flagged free_throw with no FT tag match, within 1000 ms of a flagged moment that matches an FT tag, is listed as "duplicate_of_found_ft" and not counted false. Unit test for it.
- M4 decide_ft returns, on too_far_from_hoop / no_lane_lines, ft_shooter_box None and free_throw false; views (collect_debug) add "lane_segments" [(x1,y1,x2,y2,r)] and "hoop_dist_h".
- M5 Q4 measure = q4_measure.py (spec 37 Q4 blind script: build_report with Q4 tags only), copied into .team/specs/42_q4_measure.py unchanged. Retrace: rim_first_finder.py --retrace-from rim_first/run37_adrian_q4_blind --out-dir rim_first/run42_adrian_q4_blind --video uploads/nfhs_gam0a66d85e12.mp4 --gym adrian.
- M6 Hand-check: Claude Code draws every Q4 moment with free_throw true (and every Q4 moment stopped by too_far_from_hoop / no_lane_lines) and writes verdicts to .team/specs/42_handcheck_results.json before reading measure42_adrian_q4_blind. Only the FT reasons/flags may differ from run37_adrian_q4_blind moments; anything else -> stop.

FT BAND + LANE SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/42_ft_band_lane_spec.md (this file only; nothing else is edited by this spec)
Lineage: spec 41 (VETTED WITH CONDITIONS L1-L8, 2026-11-08; Muse AGREE) -> spec 42. Scott binding 2026-11-08: "try it" -> build the narrower band + lane-line check, test once on held-out Adrian Q4. Claude Code picks every setting before the run. Cursor codes; Claude Code gates and measures; Hermes does not edit source.

Status: v1 - not run. One measured try on Adrian Q4 (blind), then stop for Scott. Q1-Q3 is reported, not a test (settings were chosen after seeing Q1-Q3).

----------------------------------------------------------------
SETTINGS FIXED (Claude Code 2026-11-08; do not change)
----------------------------------------------------------------
- Everything in spec 41 unchanged EXCEPT:
- BAND_FRONT 0.0, BAND_BACK 0.35 (signed distance in the band player's own height; positive = away from hoop).
- After the first candidate line with exactly one in-band player who is a candidate (player b, feet f, height bh):
  1. Hoop distance: |hoop centre - f| / bh > HOOP_DIST_MAX 3.8 -> free_throw false, reason "too_far_from_hoop", trace unchanged.
  2. Lane lines: from the same Hough segment list (players erased; Adrian darker-than-both-sides check), a lane segment has undirected angle to the FT line direction >= LANE_ANGLE_MIN 30 deg; both endpoints signed distance <= +0.15 bh (hoop side); nearest endpoint |signed distance| <= LANE_GAP 1.0 bh. Extend it to cross the FT line; r = (crossing projection - f projection) / bh along the FT line direction. Need one lane segment with r in [-2.5, -0.2] AND one with r in [+0.2, +2.5] (LANE_REACH 2.5, LANE_MIN_OFF 0.2). Missing either side -> free_throw false, reason "no_lane_lines", trace unchanged.
  3. Both pass -> free_throw true, "free_throw_line" (as spec 41).
- Fails at step 1 or 2 end the decision (no further candidates tried), as in the prototype.
- Order: hoop distance first, then lane lines.

----------------------------------------------------------------
A. Detector steps (plain words, exactly the SETTINGS block)
----------------------------------------------------------------
0. Spec 41 gate, unchanged: not still -> free_throw false "not_still", trace unchanged. No hoop -> "no_hoop". Frame unreadable -> "frame_unreadable".
1. Candidates: still-frame boxes that held the ball in [trigger-3000 ms, trigger] (spec 41 candidates()), tried in box-key order.
2. FT line per candidate (spec 41, unchanged): players erased from the paint mask; Hough segments near the feet, near-perpendicular to feet->hoop, Adrian darker-than-both-sides; line = median angle, GROUP_DEG group, mean endpoints, extent along the direction. No line -> try the next candidate.
3. Band: signed distance of the player's feet from the line (normal chosen so the hoop centre is on the negative side, positive = away from hoop). In band when 0.0 <= s <= 0.35 x player height and the along-line position lies within the line extent +/- END_PAD x player height. Need exactly one in-band player and that player must be a candidate -> that player is b (feet f, height bh). Otherwise try the next candidate.
4. Hoop distance: |hoop centre - f| / bh > 3.8 -> free_throw false, reason "too_far_from_hoop", trace unchanged. Stop: no further candidates are tried.
5. Lane lines: from the same erased Hough segment list, a lane segment has undirected angle to the FT line direction >= 30 deg; both endpoints signed distance <= +0.15 bh (hoop side); nearest endpoint |signed distance| <= 1.0 bh. Extend it to cross the FT line; r = (crossing projection - f projection) / bh along the FT line direction. Need one segment with r in [-2.5, -0.2] and one with r in [+0.2, +2.5]. Missing either side -> free_throw false, reason "no_lane_lines", trace unchanged. Stop.
6. Both pass -> free_throw true, shooter b, reason "free_throw_line", trace unchanged.
7. If no candidate reaches step 3 with exactly one in-band candidate: any line existed -> "line_not_one"; no line at all -> "ft_line_not_found". Trace unchanged. (Spec 41 L3 reason names; the two new names above are added for rim_first_finder.py _apply_ft_decision and rim_first_measure.py counting only.)

----------------------------------------------------------------
B. Code plan (Cursor only)
----------------------------------------------------------------
- ft_half_circle.py:
  * Constants: BAND_FRONT = 0.0, BAND_BACK = 0.35 (replace 0.15 / 1.2). in_band() already multiplies by each player's own height, so only the constants change there.
  * band_polygon(): rectangle spanning s in [0.0, 0.35 x h] for debug draw.
  * decide_ft(): at the first line with exactly one in-band candidate (player b, feet f, height bh): (a) hoop-distance step -> fail "too_far_from_hoop"; (b) new lane_crossings() step on the same erased Hough segment list -> fail "no_lane_lines"; (c) both pass -> "free_throw_line" with b as shooter. A fail ends the decision; no later candidate is tried.
  * lane_crossings(line, f, bh, hoop, segments, gray, gym, width): lane segment = angle to FT line direction >= 30 deg, both endpoints signed distance <= +0.15 bh, nearest endpoint |signed distance| <= 1.0 bh, Adrian darker-than-both-sides when gym == adrian; extend to the FT line crossing; r = (crossing projection - f projection) / bh; return the r values on each side. decide_ft needs one r in [-2.5, -0.2] and one in [+0.2, +2.5].
  * Debug views: add lane segments (with side and r) so debug_image draws them on the still frame next to the kept segments, FT line, band polygon, and cleaned feet (L6 unchanged otherwise).
- test_ft_half_circle.py (synthetic):
  * Band edges 0 / 0.35: feet exactly on the line (s = 0) in band; feet at 0.35h in band; feet at 0.350001h out; feet on the hoop side (s < 0) out.
  * Lane pair found: synthetic segments crossing at r in both reach windows, hoop distance passing -> free_throw_line.
  * Lane on one side only -> no_lane_lines.
  * Too far from hoop: feet more than 3.8h from hoop -> too_far_from_hoop, and a later candidate that would pass is NOT tried.
- rim_first_finder.py: _apply_ft_decision accepts the two new reason names ("too_far_from_hoop", "no_lane_lines") as free_throw false; decide_ft call and debug_image call unchanged in shape. No other change.
- rim_first_measure.py: count/report the two new reason names in the same section as ft_line_not_found. No other change.
- No other file. court_homography.py and stage1b files are read only.

----------------------------------------------------------------
C. Gate before the measured run
----------------------------------------------------------------
- Claude Code runs .team/specs/42_ft_lane_proto.py logic (band [0, 0.35] + lane-line check) on the cached Q1-Q3 still moments (adrian + notus, C:\Users\scott\Documents\Liberty_Shot_Outputs\rim_first, c42_adrian / c42_notus caches) and compares it to Cursor's ft_half_circle.py code on the same cached still moments.
- Pass requirement: same decision (free_throw true/false plus reason) and the same shooter on every still moment.
- Also: the --ft-off run must still equal run39b on both films (FT off changes nothing for non-FT moments).
- Any mismatch -> stop for Scott. Do not proceed to the measured run.

----------------------------------------------------------------
D. Measure
----------------------------------------------------------------
- Q1-Q3 retrace (reported, NOT the test): FT flags vs FT tags - found / missed / false, reasons count (too_far_from_hoop, no_lane_lines, line_not_one, not_still, ft_line_not_found, free_throw_line), shooter right / wrong. Baselines from spec 41: Adrian found 16/29 (missed 13: line_not_one 8, not_still 5), false 2 (20920, 2223600), orange ft_line_not_found 1; Notus found 7/9, missed 2 (line_not_one), false 0. Expect the narrow band to clear line_not_one misses; these numbers are reported only because settings were fixed after seeing Q1-Q3.
- Adrian Q4 blind retrace (THE test): 3317100..3897037 ms, retrace of rim_first/run37_adrian_q4_blind with video, one try. Report FT flags vs FT tags - found / missed / false, duplicates (a moment that is a duplicate of a found FT, e.g. 3021480 of 3021000, 12 frames later same shot, is reported "duplicate of a found FT", not false), reasons count, shooter right / wrong.
- Hand-check before the Q4 numbers are read: Claude Code looks at every Q4 flagged FT moment (Q4 is small) and writes verdicts (.team/specs/42_handcheck_results.json or spec-42 scratchpad) before reading the Q4 numbers.
- One try on Q4; then stop for Scott. No re-run, no tuning after seeing the numbers.

----------------------------------------------------------------
E. Numbers table (each number: fixed by Claude Code before the run + fact behind it)
----------------------------------------------------------------
BAND_FRONT 0.0 - fixed - fact: band [0, 0.35] found 24/25 FT-tagged Adrian still moments and 9/9 Notus (42_ft_lane_proto.py, cached Q1-Q3 still moments); true shooters sit 0.04-0.21 player heights behind the line (spec 41 miss diagnosis, drift log 2026-11-08).
BAND_BACK 0.35 - fixed - fact: same source; extra band players at the 3PT line sit 0.81-1.19 player heights (one 0.37); hoop-side extras -0.14 to -0.04. Spec 41 band [-0.15, 1.2] is too deep (camera foreshortens floor depth).
HOOP_DIST_MAX 3.8 - fixed - fact: feet-to-hoop-centre distance / shooter box height on all 34 true FTs is 1.98-3.14 (Adrian 2.09-3.14, Notus 1.98-2.71); the 20920 false flag (3PT jumper on the arc) is 4.67 (42_ft_lane_proto.py).
LANE_ANGLE_MIN 30 deg - fixed - fact: lane lines run 25-35 deg vs the FT line at 75-81 deg to the feet->hoop direction (41_ftline_calibration_proto.py); every true FT has a lane crossing on both sides; 2223600 has none (42_ft_lane_proto.py).
LANE_GAP 1.0 bh, endpoint hoop side <= +0.15 bh - fixed - fact: prototype settings (42_ft_lane_proto.py); the lane check stops 2223600 (wide camera view, no lane-like segment crosses the line near the player) and passes all true FTs.
LANE_REACH 2.5, LANE_MIN_OFF 0.2 - fixed - fact: prototype settings; r windows [-2.5, -0.2] and [+0.2, +2.5] of shooter height along the FT line from the shooter's feet.
Duplicate rule - fixed - fact: 3021480 is a duplicate moment of tagged FT 3021000 (12 frames later, same shot); report "duplicate of a found FT", not false (42_ft_lane_proto.py / drift log 2026-11-08).
Q4 range 3317100..3897037 ms - fixed - fact: drift log spans (collect_q4_bodd.py:28).
Band-alone false flags - fact (not a setting): 20920 (3PT jumper, feet->hoop 4.67h, picked player on the 3PT arc) and 2223600 (wide view, untagged, no lane-like segment near the player) remain after the band; hoop distance removes 20920 (4.67 > 3.8), lane lines remove 2223600 (no crossing).
Q1-Q3 expected movement - NOT a pass/fail number: spec 41 line_not_one misses (Adrian 8) should shrink with the narrow band; 1751920 (two players at the line, ball unseen) stays a miss; 899600 should flip to found. NOT FOUND - Claude Code to check until the retrace runs.
Adrian Q4 results - NOT FOUND - Claude Code to check (the blind test; not read until hand-check verdicts are written).

----------------------------------------------------------------
Rules
----------------------------------------------------------------
- Settings fixed by Claude Code before code and run; Cursor picks no setting.
- Q1-Q3 numbers are reported, not a test (chosen after seeing Q1-Q3). The test is one Adrian Q4 blind try.
- No core edits: court_homography.py and stage1b files read only.
- No training, no tracker, no interpolation.
- No banned trials (linear interpolation, ByteTrack, DeepSORT, early windows = OLLAMA.md:31-39, wider column, hoop recenter).
- Finder reads no tags, scoreboard, or database.
- One try on Q4; hand-check verdicts for every Q4 flagged FT moment are written before the Q4 numbers are read. Then stop for Scott. No re-run, no tuning.
- Every fact above comes from a file read in this session or the user's message; anything else is "NOT FOUND - Claude Code to check".

End of spec.
