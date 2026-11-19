# Spec 52E - Two-Stream Shot/Make-Miss Pre-Registration (PRE-REGISTERED) v1.0

Author: HERMES (Architect)
Date: 2026-11-16
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
Outputs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/

## Status

PRE-REGISTERED (v1.0). The change set below is frozen BEFORE any code change or training.

Binding pre-registration for the TWO-CLIP fix chosen by Scott (2026-11-16) after the Spec 52D v3.1 binding
same-5 re-gate FAILED (review52/cursor_gate52d.txt, muse_gate52d.txt, hermes_gate52d.txt; drift_log end).

- Scott decided (2026-11-16) after the 52d FAIL: TWO CLIPS TOGETHER - the short clip (clips7a, 32 frames,
  did well on make/miss and non-shot rejection) decides make vs miss; the long clip (clips8, 44 frames over
  -0.88..+6.0 s) only helps decide shot vs not-shot.

## Binding decision (Scott, 2026-11-16)

- Scott decided (2026-11-16) after the 52d FAIL: try the two-clip-together design. Hermes writes the
  pre-registration, Muse + Cursor review, Scott approves, then the SAME-5 re-gate is the binding pass/fail
  (Scott 'A'); later R10 blind films: NOTUS_A, IDAHO_CITY, RIVERSTONE.
- SAME-5 re-gate stays BINDING for this spec (Scott made it binding, 'A'). Moving to same-5 = diagnostic with
  R10 blind = binding is a Scott decision - flagged here, left to Scott.

## Inputs read this session (no source changed by this spec)

- .team/specs/52d_context_clip_prereg.md (v3.1; the FAIL this spec answers)
- .team/specs/52c_first_shot_sequence_prereg.md (v2; seq-flag superseded by the longer window)
- .team/specs/52b_check_rule_prereg.md (v2; postproc52b check rule)
- .team/specs/52a_class0_restore_prereg.md (v3; class-0 restore)
- .team/mm_clip/ensemble_predict.py, train_clip.py, extract_clips.py, gate52.py, test_mm52.py
- .team/mm_clip/postproc52b.json (frozen for this re-gate; sha .team/review52/spec52c_postproc52b_sha.txt)
- .team/review52/gpu_probe52d.txt, clips7a_sha.txt, clips8_sha.txt, silent3/, truth52_gvg.json, truth52_hsb.json,
  truth52_rimrock.json, labels52a_class0_restore.json (sha d8d2acd4...)
- Liberty_Shot_Outputs/mm_clip/clips7a/, clips8/, runs/logo52a/, runs/logo52c/, runs/logo52d/, runs/choose_e52/

## Gate facts being answered (this spec's binding re-gate: logo52e, E=5, seeds 0 1 2, postproc52b.json)

OVERALL FAIL at logo52d (the baseline this two-clip design must answer):

- adrian: PASS 93.7 (119/127); notus: PASS 93.5 (28/31); gvg: FAIL 95.9 (208/218, checks 140, silent 0);
  hsb: PASS 97.1 (136/140); rimrock: FAIL auto 88.6 (109/123, checks 34, silent 1). OVERALL: FAIL.

- First-shot P(shot) chain: logo52a -> logo52c (seq flag = 1 on all 3): notus 0.083 -> 0.170, rimrock 0.096 -> 0.037, gvg 0.181 -> 0.092. logo52c -> logo52d (long clip): notus 0.170 -> 0.289, gvg 0.092 -> 0.789, rimrock 0.037 -> 0.111 (still silent, t=274807).
- Long clip (52d) made gvg class-0 mean P(shot) 0.21 -> 0.45; rimrock lost 9 shots (6 miss->not-shot, 3 miss->make, 1 not-shot->miss).

## Design Q1 - Fusion: LATE FUSION of separately trained streams (PINNED); joint two-stream NOT chosen.

### Decision (PINNED, v1.0)

- Late fusion at predict time of two separately trained stream models. One jointly trained two-stream model
  is NOT the pinned design.

### Why

- GPU probe (review52/gpu_probe52d.txt; RTX 5060, 8151 MiB card): T=32 bs8 train peak 3938 MiB (0.46 s/step); T=44 bs8
  peak 5176 MiB (0.53 s/step); T=87 bs8 peak 9621 MiB > 8150 MiB card -> not feasible. Joint two-backbone at bs 8
  likely does NOT fit (~9 GB) -> disclose and pin a buildable choice.
- PIN BUILDABLE CHOICE (v1.0): retrain short (clips7a set) + long (clips8 set) separately; late fusion at
  predict time.

### Contamination control

- The team has ALREADY SEEN logo52a/52c/52d same-5 preds; any fusion weight/threshold chosen now and scored on
  those same preds is TUNED ON THE TEST.
- Pinned here: the fusion rule is FIXED FROM FIRST PRINCIPLES WITH NO FREE PARAMETERS; no learned fusion weight
  is fit on the same-5. The fusion is a DECISION-LEVEL split pinned before any scoring (Q2/Q3 below).
- Retrains use FROZEN clip sets + FROZEN labels52a_class0_restore.json (sha d8d2acd4...); no relabel; no new
  threshold by 52e.

## Design Q2 - Long stream vote limited so it cannot flood class-0 (gvg) (PINNED RULE; no new thresholds)

### Pinned rule (v1.0)

- Final shot decision for candidate i:
  - short ens P(shot) >= THR (0.5, FROZEN postproc52b) -> SHOT (final; short owns).
  - else short silent (ens P(shot) < floor 0.2 AND all-seed P(shot) < 0.5) AND long ens P(shot) >= THR (0.5) ->
    RE-OPENED SHOT (final; long owns; long decides make vs miss for this reopened shot).
  - else -> NOT-SHOT (final; short owns; long vote NOT admitted).
- The long stream's vote is LIMITED to the silent-zone re-open; it may not override a confident short call and
  may not create shots. No new threshold introduced by 52e; only FROZEN postproc52b numbers are used (shot_thr
  0.5, floor 0.2, weak 0.65, mm 0.3, dedup_ms 800, seed disagreement).

## Design Q3 - Make/miss from the short stream only (PINNED)

- Final make/miss call = short stream call, except for silent re-opened shots where the long stream decides
  (the first-of-two recovery; the short had missed those, P 0.04-0.18).

## Design Q4 - Build/run order, sha freeze, tests, E=5 seeds 0 1 2, gate52 + postproc52b, fail -> stop.

### Order (post-approval)

0. Prerequisite: this spec (v1.0) written and sha-frozen BEFORE any code change or training; Muse + Cursor
   review; Scott approves; then build/train/re-gate.

1. Sha freeze: sha256 of .team/specs/52e_two_stream_prereg.md -> .team/review52/spec52e_sha.txt
   (form: <sha256> *specs/52e_two_stream_prereg.md).

2. Code changes (.team/mm_clip/only, post-approval): train_clip.py (two stream entry points: short on clips7a
   set, long on clips8 set; R4 recipe otherwise unchanged; E=5; seeds 0 1 2; bs 8 pinned; G8 speed guard);
   ensemble_predict.py (late-fusion predict path implementing the pinned Q2/Q3 rule; final P/PM -> gate52).
   No change: gate52.py, postproc52.json, postproc52a.json, postproc52b.json (postproc52b sha frozen in
   .team/review52/spec52c_postproc52b_sha.txt); no new postproc file.

3. Tests (GPU-free where possible; .team/mm_clip/test_mm52.py): assert the pinned fusion rule (short owns
   make/miss; long re-open only in silent zone; re-open requires long P >= THR; no override outside silent
   zone). Run pytest .team/mm_clip/test_mm52.py -q -> all pass before training.

4. Postproc lock: postproc52b.json UNCHANGED (frozen sha .team/review52/spec52c_postproc52b_sha.txt). No new
   postproc file.

5. Train: short -> runs/logo52e_short (clips7a set, E=5, seeds 0 1 2); long -> runs/logo52e_long (clips8 set,
   E=5, seeds 0 1 2). GPU: RTX 5060; G1/G8 pins from 52d hold (bs 8; speed guard: measured train s/step >
   2x probe (T=44 bs8 0.53 -> 1.06) or shared-memory spill -> STOP for Scott).

6. Re-gate (binding, same 5, combines 52e + 52b): fuse short+long -> final P/PM -> runs/logo52e/logo_preds.npz;
   python3 .team/mm_clip/gate52.py runs/logo52e/logo_preds.npz <5 films> --postproc .team/mm_clip/postproc52b.json
   -> runs/logo52e/gate52_report.json.

7. Fail -> STOP for Scott: no thr/floor/seed/epoch retune, no extra runs, no tuning on the 3 silents; Scott
   decides the next step. Pass -> Scott gate; R10 blind later (NOTUS_A, IDAHO_CITY, RIVERSTONE).

### Stop conditions

- G8 speed guard (measured train s/step > 2x probe for the pinned setup, or shared-memory spill) -> STOP for
  Scott.
- CUDA OOM -> STOP for Scott (no silent bs change).

## Honest read / disclosure

- Expected effect: mechanism-only; no certainty claimed; the re-gate is the test.
- Disclosure: pooled-clip dilution and K_TRIG/weak-track disclosures from 52d stand; GPU memory choice
  disclosed (joint two-stream not buildable at bs 8; late fusion pinned); reverse-confound handling designed
  in via silent-zone gating; no make/miss accuracy claim from this pin; postproc52b unchanged.

HERMES: PREREG WRITTEN