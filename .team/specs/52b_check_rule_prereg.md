# Spec 52B - First-Principles R7 Check Rule (PRE-REGISTERED) v2

Author: HERMES (Architect)
Date: 2026-11-14
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
Outputs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/

## Status

PRE-REGISTERED (v2) for proposal (b): the first-principles rule for which moments a coach must see
(R7 review checks), pre-registered before any re-gate; Scott approves before any re-gate.

## Binding decision (Scott, 2026-11-14)

- Scott decided (binding, 'A', 2026-11-14) on proposal (a): multi-gym class-0 restore + predict-time
  game-session filter; NO thr/floor retune, no extra seeds/epochs; the SAME-5 re-gate is the binding
  pass/fail.
- Scott decided (2026-11-14): the team writes a first-principles R7 check rule for which moments a
  coach must see, pre-registered, Scott approves before any re-gate.

## Inputs read this session (no source changed by this spec)

- .team/specs/52_label_audit_stable_ensemble_spec.md (v3; R6/R7/R8)
- .team/review52/hermes_gate52a.txt, .team/review52/muse_gate52a.txt, .team/review52/cursor_gate52a.txt
- .team/specs/52a_class0_restore_prereg.md (v3)
- .team/mm_clip/ensemble_predict.py, gate52.py, postproc52.json, postproc52a.json, test_mm52.py
- .team/review52/labels52_v2.json, .team/review52/labels52a_class0_restore.json,
  .team/review52/truth52_gvg.json, truth52_hsb.json, truth52_rimrock.json
- Liberty_Shot_Outputs/mm_clip/runs/logo52a/ (logo_preds.npz, gate52_report.json)
- .team/drift_log.md (tail)

## Gate 52a - the failure being answered

OVERALL FAIL (binding re-gate, logo52a, E=5, seeds 0 1 2, labels52_v2 frozen).

- auto: adrian 94.5 PASS, notus 90.3 FAIL silent 1, gvg 95.9 FAIL checks 150 + silent 1, hsb 97.1 PASS,
  rimrock 95.1 FAIL checks 77 + silent 1.
- spread <= 5 all. honest coach review 93.5-99.3.
- FAIL reasons: checks (gvg 150 / rimrock 77, both over the hard cap 20); silent_reject (notus 1 /
  rimrock 1, gvg 0 -> 1); spread (rimrock 6.5 -> 4.1, fixed by the restore).

Check failure mode: checks = flagged autos + below-thr extras in the floor band [0.2, 0.5). After the
class-0 restore + session filter the check counts were gvg 150 and rimrock 77; most landed on label-0
(not-a-shot) rows (gvg 97, rimrock 51). A flat absolute-probability band is not a shot-evidence filter.

Silent rejects: notus t=252520 (ens P(shot) ~0.08; same as logo52), rimrock t=274807 (~0.1; same as
logo52), gvg t=1158600 (~0.18; seeds ~0.10/0.09/0.34; new in logo52a).

## What a check is FOR (first principles)

Scott's binding goal (spec 52 R6): >= 90% of ALL shots in a game found AND called right (make/miss),
minimal coach work, honest coach review >= 90%, checks <= 20 per game HARD (no truncation).

A coach check exists to catch (i) a real shot the auto list would lose (finder did not call it / called it
not-a-shot) and (ii) a miscall (auto called it wrong / flagged weakly / ambiguous / seed-split). If
neither holds, the coach does not need to see the moment.

## Options weighed (this session)

1. rank-and-cap: top-K by risk, K fixed by the cap (20).
2. corroboration: band candidate flagged only with a second shot cue (seed disagreement, ball near rim /
   trajectory, later referee/score cue).
3. per-minute budget.
4. others (raise floor; drop extras; retune thr).

## Decision (v2): pick one - CORROBORATION; state why

DECISION: option 2 - corroboration, v2 formulation.

Why: the check's purpose is evidence-driven (catch real shots lost or miscoded; minimal coach work;
>= 90%). Rank-and-cap needs an undefined risk ordering and can drop uncertain real shots without a
fail-backstop; per-minute budget throttles rather than decides; raising the floor / dropping extras moves
the silent zone instead of fixing the predicate. Corroboration asks "is there independent shot evidence
here?" and flags only then, keeping the >= 90% goal, minimal coach work and the fail surface coherent.

## Pre-registered rule (v2)

Inputs carried over unchanged from postproc52 / postproc52a: shot_thr 0.5, dedup_ms 800, floor 0.2,
weak 0.65, make/miss 0.3, seed disagreement true; session_filter true for the re-gate (postproc52a
wiring).

- check(i) := flagged_auto(i) OR corroborated_extra(i).
- flagged_auto(i) := auto called i as a shot AND (P_shot(i) < weak OR |P_make(i) - 0.5| < mm
  OR seed_disagreement(PM, i)).
- corroborated_extra(i) := NOT auto called i AND in-session AND floor <= P_shot(i) < thr AND
  corroborated(i).
- corroborated(i) := seed_disagreement(PM, i) ONLY for this re-gate; ball_near_rim / trajectory /
  referee_score cues marked FUTURE (not built; referee = spec 53), not part of the rule.

checks per game = #{i : check(i)}; HARD cap 20 (no truncation); >20 -> FAIL.

## Silent-reject definition and its relation to the new rule

Definition (pinned, unchanged in meaning): a labelled miss AND ensemble mean P(shot) < floor (0.2) AND all
M seeds P(shot) < 0.5 -> silent reject; gate requires silent == 0 on every game.

Relation: the new rule does not change the silent definition or the silent fail condition; silent is the
fail-backstop for a real shot below every flag. After the new rule, a real shot that is not auto-called,
not flagged, and below the confidence floor is silent -> FAIL. The new rule must not be implemented by
raising the floor, dropping extras, or truncating checks; the silent fail must remain reachable, and a
real shot below every flag must still count as a fail.

- v2 (Scott-confirmed labels; reviews muse + cursor AGREE WITH CHANGES): silent definition UNCHANGED
  (option i); 52b does NOT fix the 3 silents; Scott confirmed ALL 3 labels are CORRECT
  (review52/silent3/silent3_answers.json: each is the first shot of a 2-shot sequence; notus 252520 = 3PT miss
  then missed putback, rimrock 274807 = miss then make 5.2 s later, gvg 1158600 = miss then second miss 1.2 s
  later); no labels52b for them (labels are correct; labels52_v2.json untouched); silent fix = separate
  model-side workstream (2-shot/putback-aware sequence cue), NOT in this prereg; no sequence cue here.

## Honest review scoring

Unchanged in meaning (R8): non-flagged auto calls stand; each flagged item answered once by simulated
coach = its own candidate label; flagged real shot -> added with true call (one-to-one, unused tags
within 2 s, first mark every true tag matched by a non-flagged auto); flagged non-shot -> removed; never
insert truth at unflagged times. Flagged set = flagged autos + corroborated extras.

## Cap 20 unchanged unless argued from first principles

Cap 20 UNCHANGED (first-principles argument: it is Scott's coach-work budget / minimal-coach-involvement
goal, not a model-quality knob). Hard, no truncation; >20 -> FAIL.

## Validation

- The same-5 re-gate stays binding (Scott 'A').
- DISCLOSURE (v2): the rule is motivated by the observed gate52a check failure (checks 150 / rimrock 77 over
  the cap; band noise). Values all carried over unchanged from postproc52 / postproc52a (thr 0.5, dedup_ms 800,
  floor 0.2, weak 0.65, mm 0.3, seed flag true) - NOT picked from logo52a numbers. It must NOT be called a
  clean pre-registration unqualified: the motivation is post-hoc (observed failure), the values are
  carried over frozen / unpicked.
- R10 blind films (NOTUS_A, IDAHO_CITY, RIVERSTONE) are the STRONGER test.

## Code surface + tests (post-approval)

- ensemble_predict: corroborating-cue evaluation for below-thr extras (seed disagreement already
  available via PM); defaults from postproc52.json.
- gate52: score path reads the new postproc file for the re-gate; conditions unchanged.
- NEW .team/mm_clip/postproc52b.json: locked file for the spec-52b re-gate, carrying the new check rule;
  postproc52.json and postproc52a.json UNCHANGED (logo52 / logo52a reproducible).
- tests: .team/mm_clip/test_mm52.py extensions (corroborated extras flagged; uncorroborated not flagged;
  auto flags unchanged; silent backstop unchanged; honest scoring unchanged).

## Next step (pending Scott)

- The 3-clip silent-reject label check is RESOLVED: Scott's answers (review52/silent3/silent3_answers.json) confirm ALL 3 labels are CORRECT (each is the first shot of a 2-shot sequence); NO labels52b file needed; labels52_v2.json untouched.
- Silent fix = separate model-side workstream (2-shot/putback-aware sequence cue); NOT in this prereg; no sequence cue here.
- Next: Scott approves this v2 prereg; then run the SAME-5 re-gate (Scott 'A') with postproc52b.json.

HERMES: PREREG WRITTEN
