SPEC 52 - LABEL AUDIT + STABLE ENSEMBLE
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
File: .team/specs/52_label_audit_stable_ensemble_spec.md (this file only; nothing else edited by this spec)

FACTS: Goal (Scott, binding): >= 90% of ALL shots in a game found AND called right (make/miss), minimal coach work.
Round 52 failed: final51 seed0 HSB1 65.4% auto / 70.1% w/ checks (FAIL); 5-seed mean 78.5% auto / 86.9% w/ checks; huge seed variance; failing seeds rejected real misses (P(shot) ~0.01-0.1); silent review zone P(shot) in [0, 0.35).

1. REQUIREMENTS - LABELS
R1. WRITTEN LABEL RULE (round 52): shot := legal basket/FT attempt, ball crosses rim cylinder within hoop window; miss := shot with known outcome, no make; not a shot := near-rim moment with no attempt (pass/rebound/dribble), frame-sheet confirmed; unclear := warmup/halftime/FT-retrace/unknown -> label -1 (excluded from training + real-shot denominator). Encodings: -1 unknown, 0 not-a-shot, 1 miss, 2 make. Unmatched candidates -> -1, never auto 0.
R2. Re-audit every Claude-labelled not-a-shot AND miss in rimrock, hsb, gvg, hsb1 vs R1; coach tags govern adrian/notus; freeze corrected labels sha256 in drift_log before retraining.

2. REQUIREMENTS - TRAINING
R3. train_clip.py: (a) drop GradScaler under bf16 (autocast bf16, direct opt.step); (b) class-balanced batches (per-epoch WeightedRandomSampler, w = 1/max(cnt,1)); (c) softer aug (bright/contr 0.7-1.3, sat 0.6-1.4, gray 10%, blur 20%, flip 20%); (d) best-epoch ckpt on held-out game hsb (miss-recall val), not last epoch; 18 ep, lr 2e-4, bs 8.
R4. Retrain 5-seed ensemble (seeds 0-4) on corrected clips6; save ens52/seed{k}.pt.

3. REQUIREMENTS - GATE
R5. LOGO: 5 folds, 3 seeds per fold (0,1,2) trained on other 4 films; locked postproc thr 0.5, dedup 800 ms.
R6. LOCK BLOCKS: lock only if ensemble auto >= 90% on EVERY held-out game AND 3-seed spread <= 5 pts AND coach-checked score >= 90%; else stop for Scott, no blind test.

4. REQUIREMENTS - COACH CHECK
R7. Coach rule: auto if mean P(shot) = mean(Pmiss+Pmake) >= 0.5; call make if mean Pmake > mean Pmiss; flags: auto shots w/ mean P(shot) < 0.65 or |mean Pmake-0.5| < 0.3; below-thr candidates w/ mean P(shot) >= 0.2 (floor 0.35->0.2); seed-disagreement flags (>=2 seeds disagree -> flag).
R8. Target max coach checks per game: <= 20 (last round mean 15.4, worst 25).

5. REQUIREMENTS - FREEZE + BLIND
R9. Before blind: freeze sha256 of corrected labels (50_rimrock 61906f67..., 51_hsb1 3e265e99..., 50_gv, 50_hsb, re-audits), clips6, postproc52.json (thr 0.5, dedup 800, floor 0.2), ens52 models in drift_log. Blind: Scott-supplied unseen films, labels before any model output, random 20% human label check.
R10. BLIND PASS BAR (fixed in advance): locked ensemble found AND called right >= 90% on blind real shots (coach checks applied); coach checks <= 20/game; random-20% human label check passed.

DISAGREEMENTS
- Claude Code revised plan: DISAGREE that class-balanced batches alone fixes balance (require sampler + inverse-freq). DISAGREE that revised plan left the new below-threshold floor undecided; fixed here at 0.2.
- Muse: DISAGREE primary driver = pooled cross-gym training; architect reads label consistency + single-run seed instability as primary, pooled training secondary. AGREE: fix 0.35 floor before retraining.
- Cursor: AGREE with all 7 confirmed findings; downgrade suspected (aug strength, class weights, moving_ball) to watch items.

Next: Claude Code implements this spec; Muse + Cursor review code changes; gate then blind.

HERMES: SPEC WRITTEN - spec at .team/specs/52_label_audit_stable_ensemble_spec.md
