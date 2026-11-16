VETTED WITH CONDITIONS V1-V8 (Claude Code 2026-11-10). Conditions win over the text below.
- V1 Who reads what: ONLY the `labels` subcommand reads coach tags (find_shots_measure.load_shot_tags, the existing loader - no new time math) and 44_gv_labels.json. `features`, `logo`, `final` read labels_<film>.json only as y; tracks/features never see a tag. Step A0 "never reads tags" is wrong for `labels`; this condition replaces it.
- V2 Adrian = run43_adrian + run43_adrian_q4 moments together, matched against all Adrian Make/Miss tags in one call (spans 0-3897037). Notus = run43_notus vs Notus tags (span 0-883400). GV moments key = moment t_ms (string) in 44_gv_labels.json.
- V3 Video for F12/F13: `features` takes --video per film. Track point frame numbers are offsets from the track start frame (start_frame = round(t / 1000 * fps), t = track "t"); crossing frame = start_frame + offset of the second point of the crossing pair; with no crossing use the moment frame (round(moment_t_ms / 1000 * fps)). Boxes clipped to the frame; empty box -> ratio 0. Denominator 0 -> ratio 0.
- V4 No-hoop moments (track "hoop" None): F1, F2 counted; F3 = F9 = 0; F4 = F10 = 3.0; F5, F6, F7, F11 = 0; F8 = 3.0; F12 = F13 = 0; F14/F15 = 0 (rules call no_track). Rule side: no_track.
- V5 Rule side, same moments and labels: Adrian/Notus = spec-46 vote make_miss.json from mm_learned/rules_<film>/vote (tracks from S1, d1 --film-scale --scaled-crop --crop-scale-json, v6 + d2v1 with --mapping-proof-json); GV = rim_first/mm46_gv/vote/make_miss.json. Counting for BOTH sides over scored moments (label 0 or 1; excluded never counted): makes found = call make & label 1; false makes = call make & label 0 (real miss + non-shot reported separately where the label says which); coach load = call coach (rules: coach + no_track); silent makes = call miss & label 1.
- V6 G1 also prints, per game, how many label-1 moments came from a matched tag vs GV labels, and lists the excluded moments (t_ms + nearest Make tag). Labels sha256 logged before `features` runs; features sha256 logged before `logo` runs. `logo` refuses to run if those files changed (sha256 check against a frozen.json written at freeze time).
- V7 Determinism: LogisticRegression solver default (lbfgs), no random state needed; StandardScaler fit on the training folds only (test asserts it). Save per-fold predictions (moment, p, call, label) to mm_learned/logo_preds.json.
- V8 Out of scope reminder: no blind film, no coach page; S6 fail -> stop for Scott with the report, no second LOGO run.

LEARNED MAKE/MISS SPEC v1 - not run

Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/47_learned_make_miss_spec.md (this file only; nothing else is edited by this spec)
Lineage: spec 46 (VETTED V1-V10, 2026-11-10) -> step (b) of the team plan (Hermes, Cursor, Muse all AGREE on 2026-11-10). Scott binding 2026-11-10: "Go to step 2 to learn." Earlier: "try your suggestion to fix the issue." Team: Claude Code picks every setting.
Status: v1 - not run. Seen films only. Results go to Scott with blind test plan.

----------------------------------------------------------------
FACTS (Claude Code, Proven unless marked)
----------------------------------------------------------------
- Hand rules after spec 46 (seen films): Notus makes found 4/9 (false 0, coach 3); GV 20/64, real misses called make 8, non-shots called make 13, coach load 114. Adrian Q1-Q3 (tuned set) 27/38; Adrian Q4 2/5.
- Three games, three gyms: Adrian "MUSTANGS" 1080p, Notus A1 "PATRIOTS" 720p, GV "LIBERTY" 720p.
- Finder moments (rim-first, no tags): rim_first/run43_adrian (116, Q1-Q3), run43_adrian_q4 (20), run43_notus (36, span 0-883400 = Notus Q1, the only tagged part), run44base_gv (532).
- Labels: Adrian coach tags data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json (127 shots, 43 make); Notus coach tags jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json (31, 9 make, Q1); GV Claude Code frame labels .team/specs/44_gv_labels.json (frozen; 184 real shots 64 make, 326 not shots, 22 unclear).
- Signed moment minus tag time on matched shots: Adrian median 420 ms, range -1780..3760; Notus median 190 ms.
- Team: no video classifier (too few shots); hoop-width features + simple model; leave-one-game-out (LOGO); must beat the rules on each held-out game before any blind test; blind tests later (an away game and Riverstone), not in this spec.

----------------------------------------------------------------
SETTINGS FIXED BY CLAUDE CODE (copy into a SETTINGS FIXED block; do not change)
----------------------------------------------------------------
S1 Data = finder moments of the 3 seen games only. Tracks: Adrian (run43_adrian + run43_adrian_q4) and Notus (run43_notus) built with `tracks --moments-json ... --scaled-crop` (lead 1000, spec 46) into Liberty_Shot_Outputs/mm_learned/tracks_<film>.json; GV reuses rim_first/mm46_gv/tracks.json. Rule calls per moment from spec 46 d1/vote on the same tracks (Adrian/Notus d1 runs go to mm_learned/rules_<film>/).
S2 Labels per moment (label = 1 if a basket is made at that moment, else 0). GV: from 44_gv_labels.json (shot yes + make -> 1; shot yes + miss -> 0; shot no -> 0; unclear or result unclear -> excluded). Adrian/Notus: match moments to coach tags one-to-one with find_shots_measure.match_shot_indices, window MATCH_LABEL_MS = 4000; matched tag Make -> 1, Miss -> 0. Unmatched moment inside the tagged span: within 4000 ms of any Make tag -> EXCLUDED (could be a second moment of a make); otherwise -> 0 (not a basket). Tags with no moment are counted as finder misses, not model data. Notus only inside 0-883400 ms. Labels never feed the finder, the tracks, or the features.
S3 Features (hoop center hx, hy, width hw from the track; all distances / hw; v6 series = track "ball", bodd = track "bodd"; crossing = first pair of consecutive v6 points going from y < hy to y >= hy):
  F1 v6 point count; F2 bodd point count; F3 has_crossing (0/1); F4 |x - hx|/hw at the crossing (3.0 if none); F5 max depth (y - hy)/hw of v6 points after the crossing with |x - hx| < 0.6 hw (0 if none); F6 count of v6 points with 0 < (y - hy)/hw < 2.5 and |x - hx| < 0.6 hw; F7 largest upward move (hw) between consecutive v6 points after the crossing; F8 max |x - hx|/hw over the 10 frames after the crossing; F9-F11 = F3, F4, F5 computed on the bodd series; F12 net motion = mean absolute grayscale frame difference in the box x hx +-0.5 hw, y hy .. hy + 1.2 hw over frames crossing .. crossing+12, divided by the same measure in a same-size box at x hx + 1.5 hw (crossing = moment frame if none); F13 the same ratio over the 12 frames before the crossing; F14 spec-46 v6 new_pred (0/1); F15 spec-46 d2v1 new_pred (0/1); no_track moments: F1-F15 computed as defined (zeros/sentinels). No other feature.
S4 Model: scikit-learn LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000) after StandardScaler, fit on training games only. Call: p >= 0.80 -> make, p <= 0.20 -> miss, else -> coach. No other model, no threshold search.
S5 LOGO: 3 folds (hold out Adrian, Notus, GV in turn; train on the other two). Per held-out game report makes found / real makes, real misses called make, non-shots called make, coach load, silent makes (real makes called miss), side by side with the spec-46 rule vote on the SAME moments and labels. Run once.
S6 Pass bar (fixed now): on EVERY held-out game the learned model must have makes found >= rules, (real misses + non-shots called make) <= rules, and coach load <= rules. Any fold fails -> stop for Scott; no feature, model or threshold change after seeing LOGO numbers.
S7 If S6 passes: fit the final model on all 3 games, save it (joblib) with the feature list and a sha256, and stop for Scott. Blind tests are a later spec.
S8 Code: NEW files only: .team/shot_detectors/mm_learned.py (labels, features, LOGO, final fit; CLI) and .team/shot_detectors/test_mm_learned.py (synthetic). No edit to any existing file. Outputs only under Liberty_Shot_Outputs/mm_learned/. Nothing to the coach page. Riverstone, HSB, HSB1, Rimrock untouched.
S9 GV labels are Claude Code's (not coach tags): kept in training (most makes, one of 3 gyms); disclosed; the GV LOGO fold shows any label effect. Hermes's earlier advice to exclude them is noted and answered here.

----------------------------------------------------------------
A. Steps in plain words
----------------------------------------------------------------
0. The wrapper never reads tags, scoreboard, or database. All inputs are finder moments and tracks from spec 46.
1. Load tracks for each film from Liberty_Shot_Outputs/mm_learned/tracks_<film>.json. Load rule calls from mm_learned/rules_<film>/ for comparison.
2. Build labels per S2. Print counts per game: label=1, label=0, excluded, finder-missed tags. Freeze with sha256 in drift_log before any feature or model run.
3. Compute features F1-F15 per S3 for every moment in every track file. Write feature matrices per game. Freeze each with sha256 in drift_log before LOGO.
4. Run LOGO (S5): for each held-out game, train LogisticRegression on the other two games (S4), predict on held-out, apply thresholds (p>=0.80 make, p<=0.20 miss, else coach). Produce side-by-side report with rule vote on identical moments/labels.
5. Check pass bar (S6). If any fold fails, stop for Scott. If all pass, fit final model on all three games, save joblib with feature list and sha256, stop for Scott.
6. Write LOGO report (makes found, real misses called make, non-shots called make, coach load, silent makes) and numbers table (E) to Liberty_Shot_Outputs/mm_learned/.

----------------------------------------------------------------
B. Code plan (two new files only)
----------------------------------------------------------------
.team/shot_detectors/mm_learned.py:
- CLI: subcommands labels, features, logo, final, report.
- labels: reads tracks + coach tags (Adrian/Notus) or 44_gv_labels.json (GV), applies match_shot_indices with MATCH_LABEL_MS=4000, implements exclusion rule, writes labels_<film>.json + summary with counts and sha256.
- features: reads tracks, computes F1-F15 per S3, writes features_<film>.npz + feature_list.json + sha256.
- logo: loads labels + features for 3 games, runs 3-fold LOGO with LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, StandardScaler fit on train only), applies thresholds, prints per-fold table vs rule vote, checks pass bar (S6), exits non-zero on fail.
- final: if LOGO passes, fits on all data, saves model.joblib + feature_list.json + sha256.txt.
- report: writes Liberty_Shot_Outputs/mm_learned/logo_report.md and numbers_table.md.

.team/shot_detectors/test_mm_learned.py (synthetic, no models/video):
- test_label_matching: hand-made tag/finder times covering match, exclusion (unmatched moment within 4000ms of Make tag -> excluded), unmatched moment outside -> 0, finder-missed tags counted separately; Notus span filter 0-883400.
- test_features: hand-made tracks with known hoop/ball/bodd series; verify each F1-F15 matches manual calculation; no_track moments produce zeros/sentinels.
- test_band_mapping: probabilities map to make/miss/coach per S4 thresholds.
- test_logo_no_leak: LOGO never trains on held-out game (check train indices).
- test_final_save: joblib loads, feature_list matches, sha256 verifies.

----------------------------------------------------------------
C. Gates (Claude Code runs; any miss -> stop for Scott)
----------------------------------------------------------------
G1 labels: counts per game (1 / 0 / excluded / finder-missed tags) printed and frozen (sha256 in drift_log) BEFORE any feature or model run.
G2 features: feature file per game frozen (sha256 in drift_log) before LOGO.
G3 pytest synthetic: label matching incl. exclusion rule, each feature on hand-made tracks, band mapping, LOGO never trains on held-out game.
G4 LOGO report (S5/S6): per held-out game table with learned vs rule vote; pass bar (makes found >= rules, false calls <= rules, coach load <= rules) on EVERY fold.

----------------------------------------------------------------
D. LOGO report (S5/S6)
----------------------------------------------------------------
Per held-out game (Adrian, Notus, GV):
- makes_found / real_makes (learned vs rule)
- real_misses_called_make (learned vs rule)
- non_shots_called_make (learned vs rule)
- coach_load (learned vs rule)
- silent_makes (real makes called miss) (learned vs rule)
- pass/fail on S6 (all three inequalities must hold for learned vs rule)

----------------------------------------------------------------
E. Numbers table (fact behind each; unknowns "NOT FOUND - Claude Code to check")
----------------------------------------------------------------
Adrian_moments_Q1_Q3      116        fact: run43_adrian finder moments (rim_first)
Adrian_moments_Q4         20         fact: run43_adrian_q4 finder moments
Notus_moments_Q1          36         fact: run43_notus finder moments (span 0-883400)
GV_moments                532        fact: run44base_gv finder moments
Adrian_coach_tags         127        fact: jrhigh_adrian tag file (43 make)
Notus_coach_tags_Q1       31         fact: jrhigh_notus tag file (9 make)
GV_labels_shots           184        fact: 44_gv_labels.json (64 make)
GV_labels_non_shots       326        fact: 44_gv_labels.json
GV_labels_unclear         22         fact: 44_gv_labels.json
Adrian_label_1            NOT FOUND  -       fact: to be printed at G1
Adrian_label_0            NOT FOUND  -       fact: to be printed at G1
Adrian_excluded           NOT FOUND  -       fact: to be printed at G1
Adrian_finder_missed_tags NOT FOUND  -       fact: to be printed at G1
Notus_label_1             NOT FOUND  -       fact: to be printed at G1 (inside 0-883400)
Notus_label_0             NOT FOUND  -       fact: to be printed at G1
Notus_excluded            NOT FOUND  -       fact: to be printed at G1
Notus_finder_missed_tags  NOT FOUND  -       fact: to be printed at G1
GV_label_1                NOT FOUND  -       fact: to be printed at G1 (from 44_gv_labels.json)
GV_label_0                NOT FOUND  -       fact: to be printed at G1
GV_excluded               NOT FOUND  -       fact: to be printed at G1
LOGO_Adrian_makes_found   NOT FOUND  -       fact: G4 output
LOGO_Adrian_false_calls   NOT FOUND  -       fact: G4 output (real misses + non-shots called make)
LOGO_Adrian_coach_load    NOT FOUND  -       fact: G4 output
LOGO_Notus_makes_found    NOT FOUND  -       fact: G4 output
LOGO_Notus_false_calls    NOT FOUND  -       fact: G4 output
LOGO_Notus_coach_load     NOT FOUND  -       fact: G4 output
LOGO_GV_makes_found       NOT FOUND  -       fact: G4 output
LOGO_GV_false_calls       NOT FOUND  -       fact: G4 output
LOGO_GV_coach_load        NOT FOUND  -       fact: G4 output
Final_model_sha256        NOT FOUND  -       fact: S7 output if S6 passes

----------------------------------------------------------------
Rules
----------------------------------------------------------------
- No edits to existing files, no tuning after LOGO numbers, no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows OLLAMA.md:31-39, wider column, hoop recenter).
- Finder and tracks read no tags/scoreboard/DB.
- Nothing to the coach page.
- Every fact from a file you read or above; otherwise "NOT FOUND - Claude Code to check".

End of spec.