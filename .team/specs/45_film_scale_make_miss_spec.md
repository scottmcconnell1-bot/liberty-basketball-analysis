VETTED WITH CONDITIONS V1-V9 (Claude Code 2026-11-09). Conditions win over the text below.
- V1 Where the scale lives: the wrapper has subcommands tracks / d1 / vote (rim_first_make_miss.py). --film-scale is a flag on the `d1` subcommand. One d1 call = one --tracks-json = one film's track set (S2). The scale is set on the tracks before the shot list reaches keep_ball_detections; the input tracks.json is never rewritten (see V9: a scaled copy is written in --out-dir). With the flag, d1 writes film_scale.json into its --out-dir: {film_scale, film_hoop_median, n_tracks_used, n_tracks_total, ref_hoop_w: 98.0, tracks_json}. vote: if film_scale.json exists in the v6 and d2v1 result dirs it must be identical in both (else exit non-zero), and its film_scale / film_hoop_median / n_tracks_used are copied into every make_miss.json row and summary.md. Without the flag: no film_scale.json, no new keys, output identical to spec 44.
- V2 pytest is synthetic only (no models, no video, no 140-shot replay inside pytest; spec 44 V3 rule). Tests: median/scale math (odd and even counts, tracks without hoop skipped, n counts); flag OFF -> track dicts passed on are identical to input (no keys added); flag ON -> both keys == film_scale on every track incl. hoop-without-ball tracks; vote copies the fields and rejects mismatched film_scale.json; scale step opens no tags/labels/scoreboard file. Section B test (2) byte replay is replaced by gate G1 below (OFF path already proven by spec 44 G2).
- V3 G1 exact commands: d1 --film-scale --tracks-json C:/Users/scott/AppData/Local/Temp/v6_tracks.json (all 111) for v6 and for d2v1 (d2v1 with --mapping-proof-json from this v6 run). Pass = film_scale.json shows film_scale 1.0 exactly and n_tracks_used 111, AND new_pred + new_reason equal ball_arc/d1_results.json (v6) and d2_train/test2/d2_results.json (d2v1) on all 109 adrian rows, matched by t. Any difference -> stop for Scott.
- V4 Notus seen report: d1 --film-scale on v6_tracks_notus_q1.json (all 31; scale 64.50/98 = 0.6582). Report vs the frozen tag results in the gate files: v6, d2v1 and vote makes right / makes called miss / misses called make, before vs after. Not a test.
- V5 GV seen report: NEW folder rim_first/mm45_gv (mm44_gv is never written). d1 v6 + d2v1 with --film-scale on mm44_gv/tracks.json, vote, then 44_gv_score.py with the frozen 44_gv_labels.json and run44_gv moments. Both sha256 re-checked against the drift_log values before scoring. Not a test (GV is seen).
- V6 Riverstone stop-check (fixed now, before any Riverstone number): after tracks and before D1, if film_scale is outside 0.55-0.80 (720p films measured 0.657-0.658), STOP for Scott. That would mean the hoop pick broke. It is a stop, not a clamp; the value is never changed.
- V7 Disclosures: (a) d2v1 was trained on Scott's ball boxes from 64 Riverstone crops (56 ball / 8 no-ball, spec 23 v2), same as GV (59) in spec 44. Ball location only, no make/miss. Riverstone is blind for the make/miss rule and labels, not frame-unseen by d2v1. (b) Arc step pixel numbers not scaled (S4). (c) Section F "Adrian makes right" row: G1 compares to d1_results.json / d2_results.json, not to "spec 44"; 28/28 is precision context (both-make calls all real), not makes found.
- V9 (added after Muse AGREE; Muse re-asked) No-op proof reads tracks from disk: the arc-rule-report step calls prove_noop_identity (keep_ball_detections.py:1180), which runs ai_bridge.run_saved_v6_rule(timestamps, path) and that re-opens the track FILE (ai_bridge.py ~959). Scale only in memory -> disk tracks unscaled vs memory scaled -> NO-OP PROOF FAILED on every film with scale != 1.0 (Adrian 1.0 would hide it). Fix: with --film-scale, d1 writes the full track list with both keys set on every track to <out-dir>/tracks_scaled.json (refuse if exists) and uses THAT path as tracks_path for build_shot_list_from_tracks and kbd.FILMS track_candidates, so the proof compares like with like (and also proves ai_bridge and small_fixes apply the scale the same way). Never catch, skip or weaken NO-OP PROOF. Without the flag: no file, spec 44 path unchanged. pytest adds: scaled copy written with keys on every track, input file byte-unchanged, shot rows point at the scaled copy.
- V8 Output dirs (each refused if it exists): rim_first/run45base_rs (finder --ft-off), rim_first/run45_rs (FT retrace --gym liberty), rim_first/mm45_rs (tracks, v6, d2, vote). Labels from frames at moment times of run45base_rs only. Labels + 45_rs_score.py frozen, sha256 in drift_log before run45_rs and mm45_rs start.

FILM-SCALE MAKE/MISS SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/45_film_scale_make_miss_spec.md (this file only; nothing else is edited by this spec)
Lineage: spec 44 (VETTED WITH CONDITIONS V1-V7, 2026-11-09; Muse AGREE after order note) -> spec 45. Scott binding 2026-11-09: makes/misses "took several days and multiple attempts... We exhausted all possibilities" -> NO new make/miss logic, no tuning. "I do not want to overwhelm the coach." Scott on the scale fix: "your idea seems worth a chance to test it". Claude Code picks every setting.
Status: v1 - not run. One measured try on Riverstone (blind), then stop for Scott.

----------------------------------------------------------------
FACTS PROVEN THIS SESSION (Claude Code; do not change)
----------------------------------------------------------------
- Spec 44 GV blind: 10 of 64 real makes called make; 51 real makes called miss silently.
- Cause: decide_shot distances are fixed pixels (80/180 px below rim, 50 px starts below, 60 px jump, 200 px, 12 px/frame, 70/40/150/100 px) tuned on Adrian (1920x1080). Each is already multiplied by scale_y or geo_mean_scale = sqrt(scale_x*scale_y), read from track keys _court_scale_x/_court_scale_y, default 1.0. No code sets them for make/miss, so they are 1.0 on every film.
- Keys reach the rule: run_arc_and_rule_on_shot and apply_arc_replacements copy every track key except "result", so keys set on a track reach decide_shot in both the old and new (arc) calls, for v6 and d2v1.
- Median grouped hoop width track["hoop"][2]: Adrian build tracks (Temp/v6_tracks.json, 111 tracks) 98.00 (range 69.6-115.5); Notus Q1 (v6_tracks_notus_q1.json, 31) 64.50; GV rim-first (rim_first/mm44_gv/tracks.json, 497 with hoop of 532) 64.40 (range 40.7-236.4); Adrian Q4 alone (q4_guard/v6_tracks_q4.json, 18) 90.55.
- Seen, coach tag times: v6 makes called make Adrian 27/38, Notus 2/9.
- Gate files: ball_arc/d1_results.json and d2_train/test2/d2_results.json, 140 shots each = adrian 109 + notus_a1 31.
- Team consult: Cursor showed a per-track scale (hoop_w/98) changes ~65% of Adrian tracks; one scale per film keeps Adrian at 1.0. Hermes, Muse agreed to one test.

----------------------------------------------------------------
SETTINGS FIXED (Claude Code; do not change)
----------------------------------------------------------------
S1 Film scale = median of track["hoop"][2] over ALL tracks with a hoop in that film's track set, divided by REF_HOOP_W = 98.0 (named constant; = Adrian build median, fixed now). Same value set as _court_scale_x and _court_scale_y on every track of that film. No rounding, no clamp. Computed from the film's own tracks only: no tags, no scoreboard, no truth, no labels.
S2 "Film's track set" = every track the run builds or loads for that one video. For a rim-first run = all moment tracks of the run. For the gate = the whole film's track file (Adrian: v6_tracks.json, all 111; Notus: v6_tracks_notus_q1.json, all 31). Never a subset (Adrian Q4 alone would give 0.924).
S3 Code: wrapper only. Add the scale step to .team/shot_detectors/rim_first_make_miss.py (after tracks are built, before D1) behind a CLI switch --film-scale (default OFF, so spec 44 output is unchanged when off), plus tests in test_rim_first_make_miss.py. No edit to ai_bridge.py, small_fixes_v6_copy.py, keep_ball_detections.py, collect_q4_bodd.py, make_review_queue_page.py. The scale and the hoop median are written into summary.md and each make_miss.json (film_scale, film_hoop_median, n_tracks_used).
S4 Scale applies to both D1 runs (v6 and d2v1) with the same value. The arc step's own pixel numbers (ZONE_BELOW_PX 300, crop 260/200/240) are NOT scaled in this spec (disclose as a known limit).
S5 Vote, no_track, quarantine, output folder: unchanged from spec 44 S4/S5.

----------------------------------------------------------------
A. Steps in plain words
----------------------------------------------------------------
0. The wrapper takes one run dir (its moments.json + video) and one output folder. It never reads tags, scoreboard, or a database.
1. Build the shot list: every moment in moments.json (spec 44 S1).
2. For each moment: start_ms = t_ms - TRACK_LEAD_MS (1000 ms). Run collect_q4_bodd.collect_samples (80 frames from start), groups (hoop candidates), keep BODD balls with conf >= 0.28, hoop = nearest candidate to the BODD balls, v6_ball series (crop around the hoop, conf 0.28, imgsz 640, sequential reads from the start frame). Track = {t: start_ms, hoop, ball, bodd}. No hoop or no ball series -> call "no_track", skip D1.
3. NEW: After all tracks are built for the run, compute the film's hoop median = median of track["hoop"][2] over all tracks with a hoop. film_scale = film_hoop_median / 98.0. Write film_scale, film_hoop_median, n_tracks_used into summary.md and into every per-moment make_miss.json. Set track["_court_scale_x"] = track["_court_scale_y"] = film_scale on every track.
4. Run D1 on each track twice with the unchanged functions: v6 weights and d2v1 weights (best_basketball.pt). d2v1 passes --mapping-proof-json from the v6 run (spec 23 v3). Each run returns pred + reason. Scale applies to both runs with the same film_scale value.
5. Vote (spec 44 S4): both make -> "make"; exactly one -> "coach"; none -> "miss"; no_track -> "no_track".
6. Write one make_miss.json per moment into the new output folder only: t_ms, start_ms, hoop, v6 pred + reason, d2v1 pred + reason, call, film_scale, film_hoop_median, n_tracks_used. Write summary.md with the counts plus film_scale, film_hoop_median, n_tracks_used. Nothing else is written; the coach page is not touched (quarantine).

----------------------------------------------------------------
B. Code plan (only the two files in S3)
----------------------------------------------------------------
- .team/shot_detectors/rim_first_make_miss.py: add CLI switch --film-scale (default OFF). After tracks are built (cmd_tracks or loaded from tracks_json) and before cmd_d1, if --film-scale is ON: iterate tracks, collect hoop[2] for every track with hoop, compute median, film_scale = median / 98.0, set _court_scale_x and _court_scale_y = film_scale on every track. Write film_scale, film_hoop_median, n_tracks_used into summary.md and into each make_miss.json row. cmd_d1 uses the modified tracks. When --film-scale is OFF, behaviour is exactly spec 44 (no scale keys added, no median computed, no summary keys added).
- .team/shot_detectors/test_rim_first_make_miss.py: add pytest tests. (1) Median/scale math: synthetic tracks with known hoop widths -> median and scale computed correctly. (2) Switch OFF: wrapper fed the 140 tag shots with TRACK_LEAD_MS 0 on existing track files reproduces spec 44 output byte-for-byte (new_pred AND new_reason for v6 and d2v1 on all 140). (3) Keys set on every track when ON: _court_scale_x and _court_scale_y present and equal to film_scale on all tracks. (4) No tags/labels file opened anywhere in the scale step. No edits to existing files; no other test file.

----------------------------------------------------------------
C. Gates (Claude Code runs; any miss -> stop for Scott)
----------------------------------------------------------------
G1 Adrian film scale computed by the new code from v6_tracks.json == 1.0 exactly, and D1 with --film-scale on the 109 Adrian build shots reproduces new_pred AND new_reason byte-for-byte in d1_results.json (v6) and d2_results.json (d2v1).
G2 pytest passes: median/scale math, switch OFF == spec 44 output, keys set on every track, no tags/labels file opened.

----------------------------------------------------------------
D. Seen reports (not tests)
----------------------------------------------------------------
Notus 31 build shots with scale 0.658 (makes right/missed vs tags, before vs after).
GV: re-run D1 + vote only on existing mm44_gv/tracks.json with --film-scale, re-score with the frozen 44_gv_labels.json and 44_gv_score.py (hashes unchanged: 44_gv_labels.json sha256 9a8a102d240d6127d047e9fc23d801311a81af8a178d477af4cc244af0e612d9, 44_gv_score.py sha256 d0891a022bc6316f28ae3f6847b156654f7129b3858366a4a5e49ba82fff8f72).
Numbers are NOT FOUND until the run - Claude Code to check.

----------------------------------------------------------------
E. Riverstone blind (the test)
----------------------------------------------------------------
Game: uploads/LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4 (720p, 25 fps, never looked at).
1. Finder base run: rim_first_finder.py --ft-off -> rim_first/run45base_rs.
2. Claude Code labels EVERY moment from frames (as spec 44 V6) into .team/specs/45_rs_labels.json. Real shot = player releases the ball at the hoop during game play (warm-ups/dead-ball = not a shot). Make = ball goes through the net. Unclear -> reported, not scored.
3. Labels + score script .team/specs/45_rs_score.py frozen, sha256 logged in drift_log, BEFORE any FT or make/miss run.
4. Spec-43 FT retrace unchanged, --gym liberty (H = Liberty home).
5. Tracks, D1 v6 + d2v1 with --film-scale, vote.
6. Hand-check every flagged moment written BEFORE the score is read.
7. One try, then stop for Scott.

----------------------------------------------------------------
F. Numbers table (fact behind each number; unknowns "NOT FOUND - Claude Code to check")
----------------------------------------------------------------
REF_HOOP_W              98.0 px    fixed   fact: Adrian build median (111 tracks), named constant, fixed now.
Adrian film_scale       1.0        gate    fact: Adrian build median 98.0 / 98.0 = 1.0; whole film track set (S2).
Notus film_scale        0.658      fact    fact: Notus Q1 median 64.50 / 98.0 = 0.658; whole film track set (S2).
GV film_scale           0.657      fact    fact: GV rim-first median 64.40 / 98.0 = 0.657; whole run track set (S2).
Riverstone film_scale   NOT FOUND  -       fact: will be computed from run45base_rs tracks by the new code.
Adrian makes right      NOT FOUND  -       fact: gate G1 requires byte-match to spec 44 (28/28 both-make real).
Notus makes right       NOT FOUND  -       fact: 31 build shots, scale 0.658; before vs after vs tags.
GV makes right          NOT FOUND  -       fact: re-score with frozen labels/score script; hashes unchanged.
Riverstone makes right  NOT FOUND  -       fact: blind test, hand-check before score read.
Arc step pixel scaling  NOT DONE   limit  fact: ZONE_BELOW_PX 300, crop 260/200/240 in keep_ball_detections are NOT scaled in this spec (S4).
Every number not marked "fixed", "gate", or "fact" is NOT FOUND - Claude Code to check.

----------------------------------------------------------------
Rules
----------------------------------------------------------------
- No core edits, no training, no tuning after seeing any test number, no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows OLLAMA.md:31-39, wider column, hoop recenter).
- Finder and make/miss read no tags, scoreboard, or database.
- Nothing to the coach page.
- One try on Riverstone; then stop for Scott. No re-run, no tuning after seeing the score.
- Every fact above comes from a file read in this session or the binding; anything else is "NOT FOUND - Claude Code to check".

End of spec.