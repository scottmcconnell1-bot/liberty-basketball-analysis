HYBRID PULL SPEC v1 - not run

AMENDMENT A1 (2026-11-11, Scott: "Test on HSB instead"). Wins over the text below. Riverstone stopped at H7 step 2: it is filmed by an auto-panning camera with no scoreboard overlay, so spec 48b cannot run (drift_log). Nothing else ran on Riverstone; it stays unseen. The blind film is now HSB (uploads/LIBERTY_A_v_HSB_H_20260809_221334.mp4; Liberty away, a gym none of the 3 training games used; its static board box sits at the home-overlay position 1012,560 242x137, found by numbers only). Every "Riverstone" below reads "HSB". Unchanged and already frozen: model.json (sha256 5a570819...), 49_rs_score.py (sha256 a1a38b6f...), T 0.70, P1-P5, the H7 order. Added for HSB: (a) finder base run rim_first/run49base_hsb (same command as Riverstone's run45base_rs), not opened until H7 step 3; (b) board type check: if HSB does not match a stored board type, the spec-48b "new board" path applies (mark ~20 frames, clock only, no make/miss information) and Muse is told before the session runs; (c) spec 45 film-scale stop band 0.55-0.80 applies to HSB unchanged; HSB is 720p like the home films.

Architect: Claude Code (2026-11-11; same route as 48b, Scott: "Go ahead"). Reviewers: Muse and Cursor. Builder: Cursor.

SCOTT (binding, 2026-11-10): "Go with Cursors version" = corrected features + hybrid hidden-make coach pull, judged once on Riverstone with labels frozen first. Scott 2026-11-10: "No starts can be counted when the game is not in session."

WHAT IT DOES: the make/miss rules (spec 46) keep every call they make. A second score, from 4 measurements that look the same in every gym, picks out rules-"miss" shots that are probably makes and sends them to the coach to check. Only shots inside game time (spec 48b) are judged at all. Riverstone (unseen; finder already run, output never opened) gets one fair test.

WHY THIS SHAPE (seen games only, drift_log 2026-11-10): the rules miss many makes on gyms they were not built on (GV: 37 of 64 makes silently called miss after spec 46). Spec 47's full learned model failed every held-out game (fixed 0.80/0.20 band, F14/F15 copy the rules). The 4 stable features rank makes well across games (out-of-game AUC Adrian 0.76, Notus 0.86, GV 0.82). As a pull on real game shots at T 0.7: Adrian 12 pulled, 7 of 17 hidden makes caught; Notus 3 pulled, 0 of 3; GV 41 pulled, 17 of 37. Without a game-time filter most GV pulls were warm-ups -> spec 48b first.

## SETTINGS FIXED BY CLAUDE CODE (do not change)
- H1 Rules = spec 46 exactly, as run on GV (mm46_gv): `tracks --moments-json <finder moments> --video <film> --out-json tracks.json --scaled-crop` (no --reuse-hoops-from: Riverstone has no earlier track file), then `d1 --film-scale --scaled-crop --crop-scale-json crop_scale.json` with v6 weights, then the same with d2v1 weights and `--mapping-proof-json v6/candidates.json`, then `vote`. Weights: v6 = C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt; d2v1 = Liberty_Shot_Outputs/d2_train/runs/d2v1/weights/best_basketball.pt. Spec 45 stop-check stays: film_scale outside 0.55-0.80 -> stop for Scott before any make/miss number is read.
- H2 Game time = spec 48b game_session.py run (with S7b). On Riverstone: board type check and the 30-frame clock check by eye first (clock only); any warning, or any dropped segment holding finder moments, goes to Scott with its time range before any make/miss result is read.
- H3 Features = mm_learned.build_features_doc (spec 47 S3, unchanged code) on the Riverstone tracks + v6/d2 results. Use 4 of its 15: F4_crossing_x_hw, F5_max_depth_hw, F6_in_column_count, F12_net_motion_after divided by that film's own median F12 over all its rows (1.0 if the median is 0). F14/F15 never used (they copy the rules).
- H4 Model = trained ONCE, before any Riverstone step, on the frozen spec-47 files (mm_learned/frozen/features_{adrian,notus,gv}.json + labels_*.json, sha256 in frozen.json; rows with label 0 or 1 only): StandardScaler + LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000), all 3 games together. Saved as a file with its coefficients, scaler mean/scale, the 3 per-film F12 medians, and its sha256 -> drift_log. Same code as scratchpad design48.py (copied to .team/design49/design48.py).
- H5 Pull = a moment that is (in session by in_session(), FT window allowed only for FT-flagged moments) AND (rules call "miss") AND (p >= 0.70). No cap. Rules "make" and "coach" calls are kept as the rules made them. Out-of-session moments get no call at all: never counted, never sent to the coach.
- H6 Coach list = rules "coach" items in session + pulls. Each pull carries p and the time. The coach page is NOT changed in this spec (report only).
- H7 Riverstone order (each step's output frozen, sha256 to drift_log, before the next): (1) model file (H4) and the score script .team/specs/49_rs_score.py (written by Claude Code before step 2); (2) game session (H2); (3) labels: Claude Code labels every Riverstone finder moment from frames (same sheets and verdict rules as GV, specs/44_gv_handcheck.md: shot yes/no/unclear, result make/miss/unclear, ft yes/no/unclear), with no rules, pull or model output in existence for Riverstone; (4) FT step (spec 43), rules (H1), features (H3), pull (H5); (5) score ONCE. No re-run, no retune, no second threshold after step 5.
- H8 Seen check before Riverstone (not proof): the new code, run on the saved seen-game files, must reproduce the design48.py pull counts at T 0.7 with out-of-game scores: Adrian pulled 12 caught 7, Notus 3 caught 0, GV 41 caught 17 (real game shots only, as design48.py counts them). Any difference -> stop, no Riverstone step.

## PASS BAR (fixed now, before any Riverstone number)
Counted on labelled real game shots (shot "yes") only; "unclear" rows excluded and reported.
- P1 Game time (spec 48b proof): every labelled real shot is in session (FT window counts for FTs). Each shot outside is listed. Any miss = 48b FAILS on an unseen game (reported to Scott; H-results still reported).
- P2 Pull catches >= 1/3 of the hidden makes (real makes the rules called "miss", in session).
- P3 At least 1 in 3 pulls is a real make.
Spec 49 PASSES only if P1, P2 and P3 all hold.
- P4 (Muse, information only, never changes the verdict): the same P2/P3 numbers at T 0.60 and 0.80, so Scott can see whether 0.70 was lucky. Why T is fixed at 0.70 from seen games: every setting must come from seen games and be locked before the blind one; it is locked here, before any Riverstone output exists, and is never changed after.
- P5 (Muse, no unexplained drops): every Riverstone finder moment out of session is accounted for in the report: inside a listed dropped_segment (with its reason), in a stretch with no running clock (before the first tip, after the last end, or a segment with no tip), or in a gap between a period end and the next segment. Counts per group; the times of any labelled real shot among them. Whatever the result, Scott gets the plain numbers: real makes; makes the rules found; makes pulled to the coach; makes still hidden; real misses called make; non-shots called make; non-shots pulled; coach list size; moments dropped as out of session.

## A. STEPS IN PLAIN WORDS
1. Train the second score on the 3 seen games and lock it.
2. Work out Riverstone's game time from its clock. Show Scott anything odd.
3. Label every Riverstone moment by eye and lock the labels.
4. Run the rules and the second score on Riverstone.
5. Score once against the locked labels. Report to Scott.

## B. CODE PLAN
- NEW .team/shot_detectors/hybrid_pull.py: train (H4, writes model json + sha256), features (H3: calls mm_learned.build_features_doc, then writes features_<film>.json with the same format as spec 47's), pull (H5: inputs make_miss.json from vote, features json, session.json, model json, FT moments json; writes pull.json = every moment with t_ms, in_session, rules call, p or null, pulled true/false), seen-check (H8). CLI for each.
- NEW .team/shot_detectors/test_hybrid_pull.py: synthetic: F12 film-median scaling (and median 0); pull only when in session AND miss AND p >= 0.70 (edges 0.6999 / 0.70); make/coach calls unchanged; out-of-session moments have no call; FT window only for FT-flagged moments; model json round-trip gives the same p; F14/F15 not read (source check).
- NEW .team/specs/49_rs_score.py (Claude Code, frozen before step 2): reads labels, session.json, make_miss.json, pull.json; prints P1-P3 and the plain numbers.
- No edit to any existing file. Outputs only under Liberty_Shot_Outputs/hybrid49/<film>/.

## C. GATES
1. pytest .team/shot_detectors all pass. 2. H8 seen check exact. 3. Protected sha256 unchanged (Claude Code). 4. Riverstone in the H7 order, each sha256 logged before the next step.

## D. NUMBERS (sources)
T 0.70, C 1.0, balanced, 4 features: drift_log 2026-11-10 "Go with Cursors version" + design48.py. Seen pulls: same entry. GV spec-46 rules: makes found 20 of 64, silent 37 (drift_log spec 46 GV line). Film-scale stop band 0.55-0.80: spec 45 V. Riverstone video uploads/LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4; finder run rim_first/run45base_rs (unopened). Riverstone gym and board type: NOT FOUND - checked in H2.

Rules: no score digits anywhere in the pipeline (labels may use the score display only to judge a make, as on GV); nothing to the coach page; HSB/HSB1/Rimrock untouched; no banned trials (linear interpolation, ByteTrack, DeepSORT, early windows OLLAMA.md:31-39, wider column, hoop recenter).
