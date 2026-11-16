VETTED WITH CONDITIONS V1-V7 (Claude Code 2026-11-09). Conditions win over the text below.
- V1 Wrapper pattern = the old run_d1_q4.py (swap only the shot list). rim_first_make_miss.py has 3 steps: (a) tracks: build a track file from moments with collect_q4_bodd.collect_samples / groups / BODD-ball pick / hoop pick / v6_ball unchanged (same code path as collect_q4_bodd.main's track loop, "result" field absent); (b) D1: call keep_ball_detections.main steps extract and arc-rule-report UNCHANGED, with only kbd.FILMS / kbd.load_build_shot_list swapped inside the wrapper (monkeypatch) so the shot list = the track file; (c) vote + make_miss.json + summary.md. D1 sees t = start_ms (track t) everywhere, exactly as tag tracks use the tag time as window start.
- V2 Truth: shot rows carry gt_make None. If unchanged D1 report code needs a bool, the wrapper passes False and marks the file "truth absent"; its truth-based summary counts are not used. Vote reads only new_pred.
- V3 Gates (Claude Code runs; not inside pytest): G1 track step fed the 18 Adrian Q4 tag times with TRACK_LEAD_MS 0 == Liberty_Shot_Outputs/q4_guard/v6_tracks_q4.json exactly (hoop, ball, bodd per shot). G2 D1 step fed the 140 build-shot tracks == existing new_pred for v6 (ball_arc/d1_results.json) and d2v1 (d2_train/test2/d2_results.json) on all 140. G3 pytest (vote table incl. no_track, no-truth rows, start_ms arithmetic, wrapper never opens a tags file). Any mismatch -> stop for Scott.
- V4 D1 plain: no --fall-through-guard, no --double-count-cut (G2 proves it matches the page's results files).
- V5 Seen report: all moments of run43_adrian (Q1-Q3 part only; Q4 is its own run run43_adrian_q4) and run43_notus; matched moments scored against tags; unmatched moments' calls listed too (coach load from extras).
- V6 GV labels: real shot = a player releases the ball at the hoop during game play (warm-ups/dead-ball shots = not a shot). Make = ball goes through the net. Unclear -> reported, not scored. Labels + score script frozen before the FT retrace and before make/miss runs.
- V7 GV FT step: spec-43 retrace of run44base_gv with --gym liberty (Liberty home gym, as Idaho), unchanged rule.

RIM-FIRST MAKE/MISS SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/44_rim_first_make_miss_spec.md (this file only; nothing else is edited by this spec)
Lineage: spec 43 (VETTED WITH CONDITIONS V1-V5, 2026-11-08; Muse AGREE) -> spec 44. Scott binding 2026-11-09: makes/misses "took several days and multiple attempts... We exhausted all possibilities" -> NO new make/miss logic, no tuning; only feed the existing make/miss steps from the program's own shot moments instead of coach tags. "I do not want to overwhelm the coach." Claude Code picks every setting. Cursor codes; Claude Code gates and measures; Hermes does not edit source.
Status: v1 - not run. One measured try on Garden Valley (blind), then stop for Scott. Q1-Q3/Q4 seen films are reported, not a test (settings chosen after seeing them).

----------------------------------------------------------------
SETTINGS FIXED (Claude Code; do not change)
----------------------------------------------------------------
S1 Shot list = every moment in the run's moments.json (t_ms, frame, hoop, series, release_frame). No tags, no scoreboard, no truth read anywhere in the make/miss path.
S2 Track start = moment t_ms - TRACK_LEAD_MS (TRACK_LEAD_MS = 1000 ms, named constant). Then the existing collect_q4_bodd.py functions UNCHANGED (collect_samples 80 frames, groups, BODD ball conf >= 0.28, hoop nearest the BODD balls, v6_ball, same models BODD_yolov8n_0001.pt and v6 best.pt). Track "t" = start ms. Why 1000: puts the rim about 1 s into the 3.2 s window, like tag tracks (fixed now from seen data, not tuned).
S3 D1 twice (v6 weights; d2v1 weights Liberty_Shot_Outputs/d2_train/runs/d2v1/weights/best_basketball.pt) with the SAME functions (keep_ball_detections.run_arc_and_rule_on_shot); only the shot list is swapped, via a new wrapper (no edit to keep_ball_detections.py, collect_q4_bodd.py, make_review_queue_page.py). d2v1 uses --mapping-proof-json from the v6 run as spec 23 v3. Truth fields absent -> gt_make None; the wrapper must not crash on it.
S4 Vote as make_review_queue_page.py: both make -> "make", exactly one -> "coach", none -> "miss". No hoop or no ball track -> "no_track" (counted as coach load).
S5 Output only a new folder (one make_miss.json per moment: t_ms, start_ms, hoop, v6 pred+reason, d2v1 pred+reason, call; summary.md counts). NOT added to the coach page in this test (quarantine).

----------------------------------------------------------------
A. Steps in plain words
----------------------------------------------------------------
0. The wrapper takes one run dir (its moments.json + video) and one output folder. It never reads tags, scoreboard, or a database.
1. Build the shot list: every moment in moments.json (S1).
2. For each moment: start_ms = t_ms - TRACK_LEAD_MS (S2). Run collect_q4_bodd.collect_samples (80 frames from start), groups (hoop candidates), keep BODD balls with conf >= 0.28, hoop = nearest candidate to the BODD balls, v6_ball series (crop around the hoop, conf 0.28, imgsz 640, sequential reads from the start frame). Track = {t: start_ms, hoop, ball, bodd}. No hoop or no ball series -> call "no_track", skip D1.
3. Run D1 on that track twice with the unchanged functions: v6 weights and d2v1 weights (best_basketball.pt). d2v1 passes --mapping-proof-json from the v6 run (spec 23 v3). Each run returns pred + reason.
4. Vote (S4): both make -> "make"; exactly one -> "coach"; none -> "miss"; no_track -> "no_track".
5. Write one make_miss.json per moment into the new output folder only: t_ms, start_ms, hoop, v6 pred + reason, d2v1 pred + reason, call. Write summary.md with the counts. Nothing else is written; the coach page is not touched (quarantine).

----------------------------------------------------------------
B. Code plan (new files only; no other file is edited)
----------------------------------------------------------------
- .team/shot_detectors/rim_first_make_miss.py: the S1-S5 wrapper. Imports collect_q4_bodd (unchanged) and keep_ball_detections.run_arc_and_rule_on_shot (unchanged). CLI: run dir (moments.json + video), v6 weights, d2v1 weights, mapping-proof-json, output folder, TRACK_LEAD_MS default 1000. D1 twice per moment; vote; per-moment make_miss.json + summary.md. No truth anywhere in the path; gt_make None when absent; never crashes on missing truth.
- .team/shot_detectors/test_rim_first_make_miss.py: pytest. (1) Gate C reproduction: wrapper fed the 140 tag shots with TRACK_LEAD_MS 0 and the existing track files must reproduce the existing D1 new_pred for v6 (ball_arc/d1_results.json) and d2v1 (d2_train/test2/d2_results.json) on all 140 shots; any mismatch fails and stops for Scott. (2) Unit votes mapping both make/make/coach/miss/no_track. (3) Wrapper does not crash on moments without truth fields. No edits to existing files; no other test file.

----------------------------------------------------------------
C. Gate (before anything is reported)
----------------------------------------------------------------
1. Reproduction: the wrapper fed the 140 tag shots with TRACK_LEAD_MS 0 on the existing track files reproduces the existing D1 new_pred for v6 and d2v1 on all 140 shots, compared against ball_arc/d1_results.json and d2_train/test2/d2_results.json. Mismatch -> stop for Scott; no tuning, no retry.
2. pytest passes. Mismatch -> stop for Scott.

----------------------------------------------------------------
D. Seen report (not a test)
----------------------------------------------------------------
Adrian Q1-Q3 run43_adrian moments and Notus run43_notus moments, each matched to its tag by time (signed moment_ms - tag_ms: Adrian Q1-Q3 median 420 ms, 2PT 760, 3PT 1650, FT 1460, range -1780..3760; Notus median 190 ms). Run make/miss (TRACK_LEAD_MS 1000, S1-S5) on those matched moments and report: makes right, misses called make, makes called miss, coach, no_track. Seen tag-based context only (not this run's numbers): 140 build shots, both models say make 28/28 real, disagree 7/140; Adrian Q4 blind: both models 2/5 makes, 1 false make. This section's numbers are NOT FOUND until the run - Claude Code to check.

----------------------------------------------------------------
E. Garden Valley blind (the test)
----------------------------------------------------------------
Game: LIBERTY_H_v_GARDEN_VALLEY_A, home gym, no tags exist, never looked at. Finder base run (--ft-off) -> rim_first/run44base_gv; its moments.json feeds S1.
0. Claude Code labels EVERY GV moment from video frames BEFORE the run: real shot y/n, make/miss, FT y/n, shooter feet. Frozen into .team/specs/44_gv_labels.json before any make/miss run.
1. Score script .team/specs/44_gv_score.py is written and frozen BEFORE the run. It scores the make/miss output against the labels: auto make right/wrong, auto miss right/wrong (silent errors), coach items, no_track, FT found/missed/false/maybe (spec 43 FT retrace, unchanged rule, re-scored on GV too).
2. Hand-check verdicts for every flagged GV moment are written BEFORE the score is read. One make/miss try; then stop for Scott. No re-run, no tuning after seeing the score. Labels stay out of the coach page (quarantine).

----------------------------------------------------------------
F. Numbers table (fixed by Claude Code before the run + fact behind each)
----------------------------------------------------------------
TRACK_LEAD_MS      1000 ms   fixed   fact: seen data puts the rim about 1 s into the 3.2 s collect window, like tag tracks; moment_ms - tag_ms medians 420 ms (Adrian Q1-Q3) / 190 ms (Notus), so the rim moment is ~0.2-0.4 s after the tag and a 1 s lead keeps it inside the window.
Both-make real     28/28     seen    tag-based context only; NOT FOUND for rim-first start until gate/run.
Disagree rate         7/140  seen    tag-based context only.
GV labels / score          NOT FOUND - Claude Code to check (labels frozen first, hand-check before the score).
Every number here not marked "seen" is NOT FOUND - Claude Code to check.

----------------------------------------------------------------
Rules
----------------------------------------------------------------
- No core edits, no training, no tuning, no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows OLLAMA.md:31-39, wider column, hoop recenter). collect_q4_bodd.py, keep_ball_detections.py, make_review_queue_page.py are unchanged; only the two new files are added.
- Finder and make/miss read no tags, scoreboard, or database.
- One try on Garden Valley; then stop for Scott. No re-run, no tuning after seeing the score.
- Every fact above comes from a file read in this session or the binding; anything else is "NOT FOUND - Claude Code to check".

End of spec.
