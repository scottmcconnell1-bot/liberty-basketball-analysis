VETTED WITH CONDITIONS V1-V10 (Claude Code 2026-11-10; V6 replaced and V9-V10 added after MUSE DISAGREE). Conditions win over the text below.
- V1 Two different files, do not mix them (Hermes text A4/B mixes them): (a) `tracks --scaled-crop --out-json X` writes the track list X whose "ball" series come from v6_ball_scaled, plus crop_scale.json beside X ({crop_scale, film_hoop_median, n_tracks_used, n_tracks_total, ref_hoop_w 98.0}). Name it crop_scale.json (NOT film_scale.json) so it never collides with spec 45's d1 film_scale.json. (b) `d1 --film-scale` (spec 45, unchanged) still writes its own <out-dir>/tracks_scaled.json + film_scale.json (scale keys, V9). X is what you pass as --tracks-json.
- V2 d1 CLI: --film-scale is a flag with no value (spec 45). `d1 --scaled-crop` REQUIRES --film-scale (else exit). s for the kbd crop = the same film_scale_info(tracks)["film_scale"] d1 already computes. Optional --crop-scale-json PATH: if given, its crop_scale must equal that s exactly (else exit). Real rebuilt runs (Notus, GV) pass it; gate G2 on the old Adrian file has none (s computes to 1.0). Never write into C:/Users/scott/AppData/Local/Temp.
- V3 kbd constants: set kbd.CROP_LEFT_RIGHT/CROP_ABOVE/CROP_BELOW/ZONE_BELOW_PX = 260*s/200*s/240*s/300*s only when --scaled-crop is on, restore the original values in try/finally (also on SystemExit). Record the four used values in film_scale.json (key "kbd_crop").
- V4 tracks --scaled-crop order: pass 1 BODD samples + hoop pick for every moment (exactly the spec 44 cmd_tracks code); median -> s; pass 2 fresh VideoCapture, v6_ball_scaled per track with that s. With the flag off the code path is exactly spec 44 (no second pass, no crop_scale.json). Tag-time input for Notus/Adrian gates = --tag-times-json with the "t" values of the existing track file, --lead-ms 0.
- V5 Gates exact: G1 (Claude Code, real model + video) v6_ball_scaled(s=1.0) vs collect_q4_bodd.v6_ball on the same hoop (taken from the existing track file) for the 18 Adrian Q4 starts (q4_guard/v6_tracks_q4.json) and the first 20 Adrian build starts (v6_tracks.json order): series identical, element for element. G2 Adrian d1 --film-scale --scaled-crop on v6_tracks.json, v6 + d2v1: s 1.0 exactly, NO-OP PROOF passes, new_pred + new_reason == d1_results.json / d2_results.json on all sent adrian rows (801800/3314200 not sent, as spec 45 G1). G3 pytest synthetic (incl. constants restored after an exception). Any miss -> stop for Scott.
- V6 (REPLACED, see V10) Seen reports use reused hoops, so the only change is the ball series: Notus scaled = tracks --scaled-crop --reuse-hoops-from C:/Users/scott/AppData/Local/Temp/v6_tracks_notus_q1.json (tag starts, lead 0) -> rim_first/s46_notus; control = rim_first/s45_notus (spec 45). GV scaled = tracks --scaled-crop --reuse-hoops-from rim_first/mm44_gv/tracks.json -> rim_first/mm46_gv; control = rim_first/mm45_gv. Then d1 --film-scale --scaled-crop --crop-scale-json v6 + d2v1, vote; GV scored with frozen 44_gv_labels.json / 44_gv_score.py (sha256 re-checked). Noise level reported: v6_ball (unscaled, now) vs the old file's ball series on the 31 Notus starts (points identical / within 1 px). Report makes found, false makes, coach load, reasons on missed makes, next to spec 44/45. Not tests (all seen).
- V7 Section E corrections: Riverstone rows are out of scope (S6) - ignore. "Adrian makes right" is gate G2 vs d1_results.json / d2_results.json, not "28/28" (that was precision context). RESIDUAL_HOOP_W_FRAC and ZONE_HOOP_WIDTHS_H are already in hoop widths - no scaling needed.
- V8 Disclosure: the 0.35 step weight and the 80-frame window are unchanged; any remaining film differences after (c) go to step (b), not to more tuning here.

- V9 (Muse Q3) Crops must be pixel-identical between the tracker and D1 extract: v6_ball_scaled uses x0 = int(max(0, hx - 260*s)), y0 = int(max(0, hy - 200*s)), x1 = int(min(w, hx + 260*s)), y1 = int(min(h, hy + 240*s)) - the SAME expressions keep_ball_detections uses with CROP_* = 260*s/200*s/240*s (kbd ~196-199). v6 and d2v1 d1 runs use the same tracks file and the same s, so the v6 candidates.json (the d2v1 --mapping-proof-json) carries the same scaled constants as the d2v1 payload; MAPPING PROOF compares like with like. The v6 run's own mapping gate (rate >= 0.90, unchanged, never caught) is the real check that the two crops agree on Notus and GV; a v6 mapping stop -> stop for Scott.
- V10 (Muse Q5) No BODD re-run for seen reports: tracks gets --reuse-hoops-from PATH (only with --scaled-crop): for each start t take hoop and bodd from that file (match by "t", or by "moment_t_ms" for rim-first files; missing match -> exit), compute s from those hoops (film_scale_info), then pass 2 only (fresh VideoCapture, v6_ball_scaled). Output keeps every other key of the source track; "ball" replaced; "result" dropped. So scaled vs control differ ONLY in the ball series (plus v6 detector run-to-run noise, measured per V6).
SCALED BALL CROP SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/46_scaled_crop_spec.md (this file only; nothing else is edited by this spec)
Lineage: spec 45 (VETTED V1-V9, 2026-11-09; Muse AGREE) -> spec 46 (step c of the team plan). Scott binding 2026-11-10: "try your suggestion to fix the issue. Ask the other AIs for their opinion." Team (Hermes, Cursor, Muse all AGREE): (c) cheap fix first on SEEN films only, then (b) a hoop-width feature model with leave-one-game-out, then blind tests. This spec = step (c) only. Claude Code picks every setting.
Status: v1 - not run. Seen films only. Results go to Scott with the plan for step (b).

----------------------------------------------------------------
FACTS (Claude Code, Proven unless marked)
----------------------------------------------------------------
- v6_ball (collect_q4_bodd.py:110-146) crops hoop_x +-260 px, hoop_y -200/+240 px, keeps detections within 220 px of the hoop, picks nearest to hoop (+0.35 x squared step from previous pick).
- keep_ball_detections.py extract (used by v6 AND d2v1 D1 runs) uses the same crop via module constants CROP_LEFT_RIGHT 260, CROP_ABOVE 200, CROP_BELOW 240 and ZONE_BELOW_PX 300; these are module globals read at call time, so a wrapper can override them (as spec 44 already swaps kbd.FILMS).
- At 720p (hoop ~64 px) that crop covers ~8x7 hoop widths vs ~5x4.5 at Adrian (hoop 98 px). GV frames 1388000 and 6291880: v6 follows the shooter's ball below the rim / a floor ball before the shot; rule ball_starts_well_below then rejects real makes (14 of 43 GV missed makes).
- Spec 45 (rule distances x film scale) on seen films: Notus makes 2/9 -> 2/9; GV 10/64 -> 17/64, false makes 4 -> 6. Adrian G1 identical at scale 1.0.
- Three games, three gyms (frames): Adrian "MUSTANGS", Notus A1 "PATRIOTS", GV "LIBERTY". Riverstone gym unknown, never looked at.
- Film scale (spec 45 S1/S2): median grouped hoop width over the film's track set / 98.0. Adrian 1.0, Notus 0.6582, GV 0.6571.

----------------------------------------------------------------
SETTINGS FIXED BY CLAUDE CODE (copy into a SETTINGS FIXED block; do not change)
----------------------------------------------------------------
S1 Same film scale s as spec 45 (median hoop width of the film's tracks / 98.0), but the hoop widths come from the BODD hoop picks of the tracks step itself (pass 1: BODD samples + hoop pick for every moment; median; pass 2: v6 ball series). Order matches collect_q4_bodd.main (all BODD first, then a fresh capture for v6). No tags, labels or scoreboard.
S2 Scaled ball tracker = a copy of v6_ball inside the wrapper (v6_ball_scaled(model, cap, fps, row, hoop, s)): crop hoop_x +-260*s, hoop_y -200*s / +240*s, pick radius 220*s. Unchanged: conf 0.28, imgsz 640, the 0.35 step weight, 80 frames, sequential reads. At s = 1.0 it must give exactly the v6_ball output.
S3 D1 crop: when the flag is on, the wrapper sets kbd.CROP_LEFT_RIGHT = 260*s, kbd.CROP_ABOVE = 200*s, kbd.CROP_BELOW = 240*s, kbd.ZONE_BELOW_PX = 300*s before extract and arc-rule-report, for v6 and d2v1 alike; plus spec 45 --film-scale for the rule. The scaled tracks (tracks_scaled.json path, spec 45 V9) still feed the no-op proof.
S4 CLI: tracks gets --scaled-crop (writes film_scale.json beside the track file with s, median, n); d1 gets --scaled-crop (reads that s, refuses if missing or if it differs from the --film-scale value). Default off -> spec 44/45 output unchanged byte for byte.
S5 No edit to collect_q4_bodd.py, keep_ball_detections.py, small_fixes_v6_copy.py, ai_bridge.py, make_review_queue_page.py. Only rim_first_make_miss.py and test_rim_first_make_miss.py change.
S6 SEEN films only. No Riverstone, no HSB/HSB1/Rimrock, no blind test in this spec. Results go to Scott with the plan for step (b).

----------------------------------------------------------------
A. Steps in plain words
----------------------------------------------------------------
0. The wrapper takes one run dir (its moments.json + video) and one output folder. It never reads tags, scoreboard, or a database.
1. BODD pass: build all moment tracks (collect_samples + groups + hoop pick + BODD balls) exactly as spec 44/45 cmd_tracks. This gives a hoop pick for every moment.
2. Compute film scale s = median of track["hoop"][2] over all tracks with a hoop / 98.0. Write film_scale.json beside the track file with s, median, n_tracks_used.
3. v6_ball_scaled pass: re-open the video, run a copy of v6_ball with crop and pick radius multiplied by s (S2). Build tracks_scaled.json with the scaled ball series. This is a fresh capture (second pass on the video).
4. D1: run cmd_d1 with --scaled-crop and --film-scale. The wrapper reads s from film_scale.json, refuses if missing or if it differs from the --film-scale value passed on the CLI. Before extract and arc-rule-report, it sets the four kbd module constants to 260*s, 200*s, 240*s, 300*s (S3). Both v6 and d2v1 runs use the same s. The tracks_scaled.json (from step 3) is the --tracks-json; spec 45 V9 ensures the no-op proof compares like with like.
5. Vote: unchanged from spec 44/45 (both make -> make; one make -> coach; none -> miss; no_track -> no_track). Output folder refused if exists. Write make_miss.json and summary.md with film_scale, film_hoop_median, n_tracks_used copied into every row.
6. Do this for the three seen films only: Adrian (v6_tracks.json, lead 0 for build tracks; v6_tracks_q4.json for Q4), Notus A1 (v6_tracks_notus_q1.json, lead 0), GV (rim_first/mm44_gv/tracks.json, lead 1000). No Riverstone, no HSB, no blind test.

----------------------------------------------------------------
B. Code plan (the two files only)
----------------------------------------------------------------
- .team/shot_detectors/rim_first_make_miss.py:
  * Add --scaled-crop flag to tracks and d1 subcommands (default OFF).
  * In cmd_tracks with --scaled-crop: after the BODD pass (all tracks built), compute s = median hoop[2] / 98.0 over tracks with hoop, write film_scale.json beside out_json with {film_scale, film_hoop_median, n_tracks_used, n_tracks_total, ref_hoop_w: 98.0}. Then re-run v6_ball_scaled(model, cap, fps, row, hoop, s) for each track (fresh video capture), replace the ball series, write the scaled tracks to out_json. When --scaled-crop is OFF, behaviour is exactly spec 44/45 (no film_scale.json, no second v6 pass, tracks identical).
  * In cmd_d1 with --scaled-crop: read film_scale.json from the same directory as tracks_json (refuse if missing). Verify its film_scale equals the --film-scale value passed on CLI (refuse if different). Before building shots and calling kbd.main for extract and report, set kbd.CROP_LEFT_RIGHT = 260*s, kbd.CROP_ABOVE = 200*s, kbd.CROP_BELOW = 240*s, kbd.ZONE_BELOW_PX = 300*s. Restore them after the run (try/finally). The tracks_json passed to kbd.FILMS is the scaled tracks file (tracks_scaled.json from step 3), so the no-op proof reads the scaled copy from disk (spec 45 V9).
  * v6_ball_scaled function (copy of v6_ball with s multiplier on crop bounds and pick radius) defined inside the wrapper.
  * No edit to collect_q4_bodd.py, keep_ball_detections.py, small_fixes_v6_copy.py, ai_bridge.py, make_review_queue_page.py.
- .team/shot_detectors/test_rim_first_make_miss.py:
  * Synthetic tests only (no models, no video).
  * (1) v6_ball_scaled(s=1.0) == collect_q4_bodd.v6_ball exactly (same hoop, same frames) on synthetic inputs.
  * (2) --scaled-crop OFF -> cmd_tracks output byte-identical to spec 44/45 (no film_scale.json, tracks unchanged).
  * (3) film_scale.json written with correct fields; d1 refuses if missing or mismatched.
  * (4) kbd constants set and restored correctly (check values before/after).
  * (5) No tags/labels/scoreboard file opened in the scale step.

----------------------------------------------------------------
C. Gates (Claude Code runs; any miss -> stop for Scott)
----------------------------------------------------------------
G1 v6_ball_scaled(s=1.0) == collect_q4_bodd.v6_ball exactly (same hoop, same frames) on the 18 Adrian Q4 tag starts and 20 Adrian build tag starts.
G2 Adrian D1 with --scaled-crop + --film-scale at s 1.0 on v6_tracks.json == d1_results.json / d2_results.json (new_pred + new_reason, as spec 45 G1).
G3 pytest synthetic (crop math, flag off unchanged, film_scale.json checks, kbd constants restored after the run).

----------------------------------------------------------------
D. Seen reports (not tests)
----------------------------------------------------------------
Notus A1 Q1: 31 tag times rebuilt with --scaled-crop (lead 0, like the build tracks) -> D1 v6 + d2v1 -> vote vs coach tags.
GV: all 532 moments of run44base_gv rebuilt with --scaled-crop (lead 1000) -> new folder rim_first/mm46_gv -> D1 + vote -> score with frozen 44_gv_labels.json / 44_gv_score.py (sha256 re-checked).
Report makes found / false makes / coach load / reasons on missed makes, next to spec 44 and spec 45.

----------------------------------------------------------------
E. Numbers table (fact behind each; unknowns "NOT FOUND - Claude Code to check")
----------------------------------------------------------------
REF_HOOP_W              98.0 px    fixed   fact: Adrian build median (111 tracks), named constant, fixed now.
Adrian film_scale       1.0        gate    fact: Adrian build median 98.0 / 98.0 = 1.0; whole film track set (spec 45 S2).
Notus film_scale        0.658      fact    fact: Notus Q1 median 64.50 / 98.0 = 0.658; whole film track set (spec 45 S2).
GV film_scale           0.657      fact    fact: GV rim-first median 64.40 / 98.0 = 0.657; whole run track set (spec 45 S2).
Riverstone film_scale   NOT FOUND  -       fact: will be computed from run45base_rs tracks by the new code.
Adrian makes right      NOT FOUND  -       fact: gate G2 requires byte-match to spec 44 (28/28 both-make real).
Notus makes right       NOT FOUND  -       fact: 31 build shots, scale 0.658; before vs after vs tags.
GV makes right          NOT FOUND  -       fact: re-score with frozen labels/score script; hashes unchanged.
Riverstone makes right  NOT FOUND  -       fact: blind test, hand-check before score read.
Arc step pixel scaling  NOT DONE   limit  fact: ZONE_BELOW_PX 300, crop 260/200/240 in keep_ball_detections are NOT scaled in this spec (S4 - wait, S3 scales them; arc step pixel numbers like RESIDUAL_HOOP_W_FRAC 0.15 are NOT scaled).
Every number not marked "fixed", "gate", or "fact" is NOT FOUND - Claude Code to check.

----------------------------------------------------------------
Rules
----------------------------------------------------------------
- No core edits, no training, no tuning after seeing any test number, no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows OLLAMA.md:31-39, wider column, hoop recenter).
- Finder and make/miss read no tags, scoreboard, or database.
- Nothing to the coach page.
- Never weaken NO-OP PROOF.
- Every fact from a file you read or above; otherwise "NOT FOUND - Claude Code to check".

End of spec.