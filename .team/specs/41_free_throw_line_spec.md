VETTED WITH CONDITIONS by Claude Code, 2026-11-08: v1 read against Scott's "Use the line", ft_half_circle.py, rim_first_finder.py annotate_free_throws :2285 / _apply_ft_decision :2240, rim_first_measure.py :396-432 / :806, and the calibration prototype 41_ftline_calibration_proto.py. L1-L8 OVERRIDE the text below. Settings in section 2 fixed by Claude Code before code and run.
L1 Hoop: decide_ft gets a new keyword hoop (dict with x, y = hoop box centre, the moment's saved "hoop"); annotate_free_throws passes moment.get("hoop"). No hoop on a still moment -> free_throw false, ft_reason "no_hoop", trace unchanged.
L2 Files: Cursor may edit ft_half_circle.py, test_ft_half_circle.py, rim_first_finder.py (reason names in _apply_ft_decision, the decide_ft call, the debug_image call) and rim_first_measure.py (count reason ft_line_not_found instead of ft_circle_not_found; same section otherwise). No other file.
L3 Reason names: "free_throw_line" (flag), "ft_line_not_found" (orange), "line_not_one" (line found, 0 or 2+ in band, or the one in band is not a candidate; trace unchanged), plus not_still / no_frame / frame_unreadable / no_hoop as now.
L4 Angle: angle between two undirected lines, 0-90 deg (segment direction vs feet->hoop-centre direction), as in the prototype (both taken mod 180, then min(d, 180-d)).
L5 Signed distance: the line normal is chosen so the hoop centre is on the negative side; positive = away from the hoop.
L6 Debug: views carry the kept segments, the FT line (point + direction + extent) and the band polygon; debug_image draws them on the still frame with all cleaned player feet. run_ft_debug unchanged otherwise.
L7 Gate (section 6) = Claude Code runs run_ft_debug on the 6 calibration FTs with Cursor's code and compares to the prototype printout (shooter feet adrian 250600 (488,834), 950760 (484,858), 2587840 (1425,872); notus 144920 (801,556), 371600 (798,552), 763760 (474,552)). Any difference -> stop for Scott.
L8 Measure adds: every non-FT moment (by tags) flagged free_throw is listed with t_ms so Claude Code can look at it; target 0.

FREE THROW LINE SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
Branch: team/auto
File: .team/specs/41_free_throw_line_spec.md (new file only; nothing else edited)
Read first: .team/specs/40_free_throw_half_circle_spec.md Q1-Q9 block, .team/shot_detectors/ft_half_circle.py, .team/specs/41_ftline_calibration_proto.py, last 8 lines of .team/drift_log.md (2026-11-08 Scott: "Use the line").

1. GOAL (Scott 2026-11-08, binding)
"Use the line." The half-circle ellipse fit of spec 40 is dropped. FT = players still AND exactly one player standing just behind the straight painted FT line (the flat side of the half circle), between the lane lines; that player is the shooter. Claude Code picks every setting before the run; Scott: aim for higher results. No tuning after results; one try, then stop for Scott.

Calibration FT moments (drift_log.md last 8 lines): adrian 250600, 950760, 2587840; notus 144920, 371600, 763760.

2. SETTINGS FIXED BY CLAUDE CODE BEFORE CODE AND RUN (do not change)

Stillness: median over players of per-player move per second over [trigger-3000 ms, trigger-1000 ms] <= STILL_MOVE_MAX 0.15 player heights; spec 40 Q1 code unchanged.
Still frame: frame nearest trigger-1000 ms; spec 40 Q1/Q2 code unchanged.
Candidates: players the ball was inside (release 0.6) at least once in [trigger-3000 ms, trigger], after spec-39 merge and referee drop; tried in spec-40 order.
Paint: build_paint_mask from stage1b_court_lines.py with its yaml, read-only, on the still frame; gym per film from CLI --gym (adrian or liberty); erase every cleaned player box (pad 3 px) to 0.
Segments: HoughLinesP on the full-frame paint mask, rho 1, theta 1 deg, yaml hough_threshold, minLineLength max(12, yaml min_line_length_at_1280 x W/1280), maxLineGap max(4, yaml max_gap_at_1280 x W/1280).
Keep a segment for candidate c (feet f = box bottom-centre, height h) when all hold: perpendicular distance f to the segment line <= LINE_NEAR 0.25 h; projection of f on the segment within [-0.5 h, length + 0.5 h]; angle between the segment and the f-to-hoop-box-centre direction >= ANGLE_MIN 60 deg; Adrian only: segment darker than BOTH sides by >= DARK_MIN 10 grey levels (8 px x W/1280 off the line, 20 samples).
FT line: median angle of kept segments; group = kept segments within 5 deg of the median angle; line through the mean of the group endpoints; extent = min..max projection of the group endpoints on that direction.
Band: a cleaned player p is behind the line when its signed distance from the line (positive away from the hoop) is in [-0.15 p.h, +1.2 p.h] and its projection is within extent +- 0.5 c.h.
Decision per moment: not still -> untouched. Candidates tried in spec-40 order; the first candidate whose FT line has exactly one player in the band AND that player is a candidate -> free_throw true, shooter = that player (overrides the trace), reason "free_throw_line". Still but no FT line for any candidate -> orange "ft_line_not_found" (never guess). Line found but 0 or 2+ players in band -> free_throw false, trace unchanged.

3. FACTS (each from a file read this session or above; otherwise NOT FOUND - Claude Code to check)
- Spec 40 ellipse fit: wrong on most frames (player bodies, 3PT arc, big loops). Not used.
- FT line colour: painted in the half-circle colour; Adrian black, Notus red. Each gym also has lines from another court: Adrian white, Notus blue; one runs almost parallel to and close to the FT line in both gyms. build_paint_mask keeps only red for liberty (use_blue false) and only dark for adrian (use_white_tophat false).
- Shooter feet (box bottom-centre) sit 0.07-0.10 player heights from the FT line, on the side away from the hoop.
- Angle between a segment and the feet-to-hoop-box-centre direction: FT line 75-81 deg; lane lines 25-35 deg.
- Adrian false match fixed in calibration: a lane player matched the dark floor strip beside a white other-court line. Fix: the Adrian segment must be darker than BOTH sides (8 px x W/1280 off the line, 20 samples) by 10+ grey levels.
- Prototype result: 6/6 FTs give exactly one player in the band, and it is the shooter; no lane player picked. Lane-player candidates that find the FT line give the same shooter.
- Adrian FT line comes out in short Hough pieces (union 0.41-0.95 player heights), Notus 1.1-1.5; so NO length minimum (it would fail Adrian). Paint coverage along the line did not separate cases; not used.
- Calibration only: 6 moments, settings chosen after seeing them, so the measured run needs a fresh hand-check sample.
- Hoop centre per series from the saved hoop box (frames.json / rim_first_finder series hoop); how the line finder receives it NOT FOUND - Claude Code to check.

4. SECTION A - DETECTOR STEPS (plain words, exactly the SETTINGS block) plus gates
Per moment, after the trace, only when still:
1. Stillness: median move per second over [trigger-3000 ms, trigger-1000 ms] <= 0.15 player heights; not still -> untouched, no FT test.
2. Candidates: ball-held players in [trigger-3000 ms, trigger] after spec-39 merge and referee drop, tried in spec-40 order.
3. Still frame: nearest trigger-1000 ms.
4. Paint: build_paint_mask on the still frame; erase cleaned player boxes (pad 3 px).
5. Segments: HoughLinesP on the full-frame paint mask with the yaml thresholds scaled by W/1280.
6. Keep per candidate: distance <= 0.25 h, projection within [-0.5 h, length + 0.5 h], angle >= 60 deg to feet-to-hoop direction, Adrian darkness >= 10 vs both sides.
7. FT line: median angle of kept segments, group within 5 deg, line through mean endpoints, extent min..max projection.
8. Band: every cleaned player behind the line when signed distance in [-0.15 p.h, +1.2 p.h] and projection within extent +- 0.5 c.h.
9. Decision: first candidate with exactly one in-band player who is a candidate -> free_throw true, reason free_throw_line; still but no line for any candidate -> orange ft_line_not_found; line found but 0 or 2+ in band -> free_throw false, trace unchanged. No length minimum on segments.

5. SECTION B - CODE PLAN (Cursor edits; Hermes writes no code)
- .team/shot_detectors/ft_half_circle.py: replace the ellipse step with the line step. Remove remove_straight, ransac_ellipse, feet_inside, the ellipse helpers (_ellipse_axes, _local_points, ellipse_distance, _point_in_ellipse) and the Ellipse type alias: nothing outside this module imports them and they are dead after the swap, so dead code stays out under one-try-stop discipline. Keep stillness, is_still, still_frame_index, candidates, _cleaned_players, paint_in_region, region_for unchanged. Rewrite decide_ft to the line step (reason free_throw_line, orange ft_line_not_found, no feet_not_one). debug_image draws the kept segments and the band. Hoop centre plumbing NOT FOUND - Claude Code to check.
- rim_first_finder.py: edit only where it string-matches old reason names (free_throw_half_circle, ft_circle_not_found, feet_not_one); otherwise no edit. Names become free_throw_line and ft_line_not_found.
- test_ft_half_circle.py: synthetic mask tests - FT line found with the shooter in the band; lane line rejected by angle (25-35 deg vs 60 deg minimum); Adrian light floor strip beside a white line rejected by darker-than-both-sides; 0 and 2+ players in band -> not FT, exactly one candidate in band -> FT.
- No other file touched.

6. SECTION C - GATE BEFORE THE MEASURED RUN
run_ft_debug on the 6 calibration FTs must reproduce the prototype: exactly one player in the band on all 6, and that player is the shooter; no lane player picked. Claude Code looks at the images. Miss on any -> stop for Scott; no tuning.

7. SECTION D - MEASURE
Same as spec 40 Q8: free_throw flags vs FT tags (found / missed / false); non-FT moments flagged free_throw (target 0); orange ft_line_not_found count; FT shooter right/wrong.
Hand-check seed 41: up to 10 flagged FT moments per film, excluding the 6 calibration moments and the spec-38/39/40 samples. Frozen rule file .team/specs/41_handcheck_rule.json written before the run; verdicts written before any numbers are read. Q4 blind only after Scott sees these numbers.

8. SECTION E - NUMBERS (each: fixed by Claude Code before the run + calibration fact behind it)
- STILL_MOVE_MAX 0.15 player heights/s: drift_log.md:179 FT median 0.11, Q3 0.13, max 0.55 vs 2PT Q1 0.42 / 3PT Q1 0.38; still FT preparation.
- LINE_NEAR 0.25 h: shooter feet sit 0.07-0.10 h from the FT line; 0.25 h catches the shooter and keeps lane players out.
- ANGLE_MIN 60 deg: FT line 75-81 deg vs lane lines 25-35 deg to the feet-to-hoop direction.
- DARK_MIN 10 grey levels, Adrian only: Adrian lane player matched the dark floor strip beside a white other-court line; darker than both sides removes it.
- Band [-0.15 p.h, +1.2 p.h]: feet 0.07-0.10 h from the line on the away-from-hoop side; band starts just in front of the line and reaches 1.2 h behind it.
- Segment projection [-0.5 h, length + 0.5 h]: feet may sit just short of or past the short Adrian Hough pieces.
- Group within 5 deg of the median angle: keeps the near-parallel other-court line out when its angle differs.
- NO segment length minimum: Adrian FT line unions 0.41-0.95 h (Notus 1.1-1.5 h); a minimum fails Adrian.
- Paint coverage along the line: NOT used; calibration fact - it did not separate cases.
- ft_line_not_found: orange, never guess; still-but-no-line stays orange.
- Non-FT free_throw false flags: target 0 (spec 40 Q8 near-0 rule).
- Hand-check seed 41: up to 10 flagged FT moments per film; excludes the 6 calibration moments and spec-38/39/40 samples.
- .team/specs/41_handcheck_rule.json frozen before the run; verdicts before numbers.

9. SECTION F - RULES
No core edits (court_homography.py and stage1b files read only). No training, no tracker, no interpolation. No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows (OLLAMA.md:31-39), wider column, hoop recenter. Finder reads video frames, boxes and hoop only - no tags, no scoreboard, no database. One try, then stop for Scott. Every fact from a file read this session or above; otherwise "NOT FOUND - Claude Code to check". New file only; nothing else edited; nothing run that writes.
