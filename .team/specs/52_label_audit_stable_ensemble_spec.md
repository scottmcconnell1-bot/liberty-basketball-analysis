SPEC 52 V3 - LABEL AUDIT + STABLE ENSEMBLE
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/52_label_audit_stable_ensemble_spec.md (this file only; nothing else edited by this spec)

FACTS: Goal (Scott, binding): >= 90% of ALL shots in a game found AND called right (make/miss), minimal coach work.
Round 52 failed: final51 seed0 HSB1 65.4% auto / 70.1% w/ checks (FAIL); 5-seed mean 78.5% auto / 86.9% w/ checks; seed variance; silent review zone P(shot) in [0, 0.2).

APPLIED IN V3 (both reviewers DISAGREEd on v1 and v2; v3 = their fixes applied exactly):
- Claude V1-V4: airball-inclusive shot rule; fixed E from LOGO inner split; sampler only + plain CE + smoothing 0.05; seed-disagreement defined.
- Cursor items 1-9 + C1-C3: adrian/notus unmatched -> -1 rebuild; honest review scoring; silent-reject gate; all-shots e2e denominator; buildable E rule; M-seed disagreement; hard <=20 checks; second-person spot-check; deliverables; C1: after E is chosen, each outer LOGO fold trains on its 4 games for exactly E (last weights), seeds 0,1,2 - that is what the gate scores; final fit on all 5 games also exactly E, seeds 0-4; C2: E search uses seed 0 only per fold; E = median of the 5 fold best-epochs; C3: miss_recall = mean(pred_class > 0 | Y == 1), tie-break shots_correct_overall.
- Muse items 1-9 + M1-M7: renumber R1-R10 sequentially, one requirement per number, sections in order; pin postproc52.json schema exactly; final fit and LOGO: lr 2e-4, batch size 8, AdamW wd 0.05, OneCycle pct_start 0.15; nested split wording; silent-reject diagnostic; silent zone P(shot) in [0, 0.2); honest score implementable.

A. LABELS:
R1. shot := FG/FT attempt toward this hoop incl. airballs, judged from shooter motion + ball flight; miss; not a shot; unclear -> -1. Encodings -1 unknown, 0 not-a-shot, 1 miss, 2 make. Unmatched -> -1 EVERYWHERE: labels_tagmatch (near tag -> -1 duplicate; far tag -> -1 unknown; never auto 0) and labels_tags; adrian/notus unmatched -> rebuild clips6.
R2. Re-audit rimrock, hsb, gvg vs R1; hsb1 re-audit DIAGNOSTIC ONLY (never trained). Coach tags govern adrian/notus. Freeze corrected label sha256 in drift_log before retraining.
R3. Second-person spot-check before freeze: all 0<->1 flips up to 60 per film + random 10% of unchanged 0/1 rows; record in drift_log.

B. TRAINING (train_clip.py):
R4. bf16 autocast, NO GradScaler (direct opt.step); WeightedRandomSampler class-balanced (w = 1/max(cnt,1)); plain CE + label_smoothing 0.05, NO loss weights; softer aug (bright/contr 0.7-1.3, sat 0.6-1.4, gray 10%, blur 20%, flip 20%); final fit and LOGO: lr 2e-4, batch size 8, AdamW wd 0.05, OneCycle pct_start 0.15 (as now).
R5. Epoch E: for outer fold k (held-out game k), the 4 remaining games: inner-train on 3, inner-val on the 4th (the inner-val game = the next game in the fixed order adrian, notus, gvg, hsb, rimrock after k, wrapping, skipping k); best epoch by miss_recall = mean(pred_class > 0 | Y == 1) (a labelled miss kept as a shot); tie-break shots_correct_overall; search epochs 1..18; E = median of the 5 fold best-epochs (each fold's epoch search uses seed 0 only); final fit runs exactly E (last weights); after E is chosen, each outer LOGO fold trains on its 4 games for exactly E epochs (last weights), seeds 0,1,2 - that is what the gate scores; final fit on all 5 games also exactly E, seeds 0-4.

C. GATE (STOP FOR SCOTT if any fails):
R6. E2E scoring vs ALL real shots (coach tags adrian/notus; complete labelled lists others; no candidate = not found); per held-out game 3-seed mean-softmax auto >= 90% (the scored ensemble = outer LOGO fold trained on the other 4 games for exactly E, last weights, seeds 0,1,2); seed spread per game best-minus-worst seed auto % <= 5 pts; honest coach-review >= 90%; checks <= 20 per game HARD (no truncation); silent-reject diagnostic = 0 (per held-out game, over labelled misses: ensemble mean P(shot) < floor (0.2) AND all M seeds P(shot) < 0.5 -> silent reject; gate requires 0 on every game).

D. COACH CHECK: R7. NEW locked file postproc52.json, schema pinned exactly: {"shot_thr":0.5,"dedup_ms":800,"session_filter":false,"review":{"flag_below_thr_candidates_with_shot_prob_at_least":0.2,"flag_auto_shots_with_shot_prob_below":0.65,"flag_auto_shots_with_abs_pmake_minus_half_below":0.3,"flag_seed_disagreement":true}}. thr 0.5, dedup 800 ms, weak-shot flag P(shot) < 0.65, make/miss flag |P(make|shot) - 0.5| < 0.3, floor 0.2, M-model seed-disagreement (>=1 shot AND >=1 non-shot, or make/miss split; M=3 LOGO, M=5 final). ensemble_predict reads postproc52.json.

E. HONEST REVIEW: R8. non-flagged auto calls stand; each flagged item answered once by simulated coach = its own label; flagged real shot -> added with true call, one-to-one, first mark every true tag matched (one-to-one, 4 s) by a NON-flagged auto shot as used; flagged items may only match unused tags (nearest within 2 s); flagged non-shot -> removed; never insert truth at unflagged times.

F. FREEZE + BLIND: R9. Before blind freeze (sha256 in drift_log): corrected labels, rebuilt clips, postproc52.json, ens52 models, train_clip.py, extract_clips.py, ensemble_predict.py, finder config / new_film.sh.
R10. Blind: >= 2 new unseen films from Scott, at least one in an unseen gym; candidates labelled before any model output; random 20% second-person label check with fixed sampling seed; if checker disagrees on > 10% of sample, labels redone before scoring; pass bar fixed now: e2e found-and-called-right >= 90% WITH honest review on EACH film, checks <= 20 per film.

G. DELIVERABLES for Cursor + DISAGREEMENTS:
- Deliverables (files/functions to change): extract_clips.py labels_tagmatch+labels_tags -> -1, rebuild adrian/notus clips; train_clip.py --seed logo/fit, WeightedRandomSampler, no GradScaler, plain CE+smoothing 0.05, softer aug, E; ensemble_predict.py postproc52.json read, seed-disagreement flag, honest score; new postproc52.json.
- Disagreements: Cursor and Muse both DISAGREEd on v1 and v2 and their items are applied; builder = Cursor (Claude Code verifies).

Next: Cursor implements this spec (Claude Code verifies); Muse + Cursor review code changes; gate then blind.

HERMES: SPEC WRITTEN
