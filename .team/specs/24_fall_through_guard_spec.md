FALL-THROUGH GUARD SPEC v1 - run once 2026-11-02: FAIL (140: 20 makes right, 5 misses called makes; Q4: 1/5 makes, 1 miss called make) - stopped for Scott
VETTED by Claude Code, 2026-11-02: numbers fixed before running (180/3/0.5/5 from existing lines); code by Hermes, 3 fixes by Claude Code, 61 tests passed (repo venv pytest .team/shot_detectors); Muse AGREE.

# 1. Goal and Scott's words

Scott 2026-11-02: "Yes, go with that revised version of Option A." He wants the make-calls of the new ball model d2v1 restricted so a make needs the ball SEEN falling through the hoop.

The net-movement branch is dropped: net_moved_after_shot is True on 40 of 95 build misses and on 3 of the 5 false makes (C:/Users/scott/Documents/Liberty_Shot_Outputs/net_moved_build_results.json, net_moved_summary.md).

# 2. The Rule (locked in writing by Scott — copy exactly)

- The ball center must cross the rim's horizontal plane (hoop_y) moving DOWN.
- During that descent the ball x must stay strictly within the rim's diameter: |x - hoop_x| < 0.5 * hoop_w.
- The track must continue below rim level while keeping that alignment, even if the path is short.

For "how far below rim" and "how many points", use ONLY a number that already exists in small_fixes_v6_copy.py or keep_ball_detections.py (name the line), or ask Scott. Do not invent a new number.

Existing numbers in small_fixes_v6_copy.py that may serve:
- 180 px (line 239): `y_rel <= (180.0 * scale_y)` — net_depth_frames depth limit
- 80 px (lines 299, 308): `y_rel >= (80.0 * scale_y)` — column-ratio zone / deep-points threshold
- 150 px (line 149): `max_y < (150.0 * scale_y)` — short-track threshold in short_track_stays_in_net
- 5 px (line 483): `max_depth - (5.0 * scale_y)` — bounce-back tolerance
- 70 px (line 138): `max_y + (70.0 * scale_y)` — body-track band after last ball frame
- 40 px (line 143): `y0 + (40.0 * scale_y)` — falling body-track check

# 3. Code change

Files to create/modify (in .team/shot_detectors/ only):
- New default-OFF switch or wrapper function in a new file (e.g., fall_through_guard.py) or added to small_fixes_v6_copy.py alongside the existing switches.
- Switch name: `switch_fall_through` (or equivalent), default `False`.
- Applied in `decide_shot` (small_fixes_v6_copy.py line 174) — called by `step_arc_rule_report` (keep_ball_detections.py line 1098).
- No edits to ai_bridge.py, models/ball_detector.pt, or any core file.
- ball_confidence 0.28 unchanged.
- applied_to_core: false.

Behavior when switch is ON:
- After the existing crossing is accepted (cross_idx), verify the three conditions above on the ball track points from that crossing forward.
- Can only turn a make into a miss; never a miss into a make.
- If any condition fails, return False with a new reason (e.g., "fall_through_fail").

Tests (must pass before Scott sees results):
- Switch OFF gives today's d2_results exactly (makes_right=29, misses_called_makes=5).
- Hand-made tracks:
  - Straight drop inside rim (|x - hoop_x| < 0.5 * hoop_w all the way down) → make kept.
  - Drop outside 0.5 * hoop_w at any point during descent → make turned to miss.
  - Ball goes up after crossing (y decreases) → make turned to miss.
  - Track ends at the rim (no points below hoop_y) → make turned to miss.

# 4. Rebuild Adrian Q4 tracks

How: run the existing Q4 build scripts in order, using the video and tags already on disk:
1. collect_q4_bodd.py — collects hoop/ball boxes for the 18 Q4 tags, appends to bodd_shots.json, writes v6_tracks_q4.json to C:\Users\scott\AppData\Local\Temp\v6_tracks_q4.json (outside the repo).
2. (If needed) extend_q4_tracker.py / build_q4_candidate_tracks.py / generate_q4_forced_tracks.py — per the October pipeline, to produce a complete track file for the 18 Q4 shots.
3. No core edits; the scripts already exist at repo root and write to the Temp path.

Then D1 extract on Q4:
- Baseline: run run_saved_v6_rule (v6) on the rebuilt Q4 tracks → record makes_right, missed_makes, misses_called_makes.
- d2v1 best_basketball.pt: run the D1 extractor (the d2v1 pipeline) on the same Q4 tracks → record same metrics.

# 5. Runs — each ONCE, numbers fixed now

(a) Safety test on 140 build shots with guard ON:
- Pass = misses_called_makes == 0 AND makes_right >= 29.

(b) Adrian Q4 blind test with guard ON:
- Pass = misses_called_makes == 0 AND makes_right >= v6 baseline makes_right on Q4.

Report both results, then stop for Scott. No tuning after results; any fail goes to Scott once.

# 6. Who

- Claude Code vets the plan and the code.
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS; a DISAGREE stops the loop for Scott.
- Coder named by Scott's roster (Cursor codes the main program).
- Hermes and Muse check the diff.

---

Every fact from a file read or the lines above; otherwise "NOT FOUND - Claude Code to check".