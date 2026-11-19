# Spec 52D - Temporal Context Clip Model Fix (PRE-REGISTERED) v3.1

Author: HERMES (Architect)
Date: 2026-11-15
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
Outputs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/

## Status

PRE-REGISTERED (v3.1). The change set below is frozen BEFORE any code change or training.
This is the binding pre-registration for the temporal-context model fix chosen by Scott
(2026-11-15) after the Spec 52C v2 binding same-5 re-gate FAILED.

- v3.1 AMENDS the v3 pre-registration (Hermes, 2026-11-15; v3 sha .team/review52/spec52d_v3_sha.txt =
  052fd15a0f78c1da74b698b9267c8e504406f8cce78a0b47edc1f12308824ae4; superseding the v3 change
  set below). Changes applied here (binding, before Scott approves / Cursor builds / training;
  clerical fixes from review52/muse_spec52d_v3.txt and review52/cursor_spec52d_v3.txt, NO design
  change): G7 (blocking, NEW): the v2 PIN is NOT buildable on the RTX 5060 8151 MiB card
  (8150.56 MiB).
  Coordinator random-input GPU probe (review52/gpu_probe52d.txt; r2plus1d_18 + Dropout/Linear(512,3)
  head, AdamW, bf16 autocast, input 112x96): T=32 bs8 train peak 3938 MiB, 0.46 s/step (today's
  recipe; ~40 min logo run); T=87 bs8 train peak 9621 MiB > 8150 MiB -> Windows spills to shared
  memory, 21.148 s/step (~46x slower, days); NO OOM error is raised on Windows, so the v2 "OOM ->
  STOP" rule would never fire; v2 pin NOT buildable. T=44 bs8 (STEP=0.16, same -0.88..+6.0 s span):
  5176 MiB, 0.53 s/step (~45-50 min run); T=87 bs4: 5239 MiB, 0.55 s/step per 4 clips (~2x run
  time; bs change = R4 recipe change).
  G8 (binding, NEW): ONE buildable setup pinned below (v3.1 pin; Item 1.4); the v2 G1 STOP rule is
  REPLACED by the v3.1 speed guard (measured train s/step > 2x the probe value for the pinned setup,
  or shared-memory spill seen -> STOP for Scott).

- v2 AMENDS the v1 pre-registration (Hermes, 2026-11-15; v1 sha review52/spec52d_v1_sha.txt =
  a008283e11b04ec96ef5381f4ae713fb979d7f67377873eb8c301340dcbd8482; superseding the Muse +
  Cursor reviews both returning "AGREE WITH CHANGES"). Changes applied here (binding, before
  Scott approves / Cursor builds / training):
  G4 (blocking): head pinned EXACTLY as R4 (pool -> nn.Dropout(0.5) -> nn.Linear(512, 3), no
    seq, no concat; fc = Sequential(Dropout(0.5), Linear(512, 3))); the v1 text ("R4 recipe has
    no dropout / no pool dropout / plain pooled head / Linear(512,3)") was wrong and is
    corrected; Item 1.5 + Item 4 step 2/3 text and tests fixed.
  G1: GPU/time budget ~100-120 min (linear 2376 s x 87/32 ~ 107 min) pinned; train bs 8 pinned;
    predict bs pinned to 8; CUDA OOM -> STOP for Scott, no silent bs change; random-input GPU
    memory probe cited from review52/gpu_probe52d.txt if present.
  G2: pooling dilution (shot ~2.5 s of ~6.9 s under global avg pool) disclosed; dense N=87 /
    STEP=0.08 ACCEPTED now, not switched after results.
  G3: reverse-confound disclosure (class-0 rows with a later shot within +6 s; fail->stop
    covers it).
  G5: track_hoop weak-match freeze / black out-of-frame pad disclosed; "kept glued" claim
    removed.
  G6: kept (6.0 s disclosure honest).

- NOT a 1-bit sequence flag (the Spec 52C model change, now superseded here for the model
  input change).
- NOT a check-rule change (Spec 52B; postproc52b.json stays and is combined into the
  same-5 re-gate).
- NOT a relabel (labels52a_class0_restore.json FROZEN; no labels52c file).
- NOT a thr / floor / seed / epoch retune.

## Binding decision (Scott, 2026-11-15)

- Scott decided (2026-11-15) after the 52c FAIL (review52/hermes_gate52c.txt,
  muse_gate52c.txt, cursor_gate52c.txt; drift_log end): try a DIFFERENT MODEL FIX in which
  the model sees what happens in the seconds after the shot (longer clip or a second context
  clip), not a 1-bit flag.
- Pre-registered; Muse + Cursor review; Scott approves; then the SAME-5 re-gate is the
  binding pass/fail (Scott 'A'); later R10 blind films: NOTUS_A, IDAHO_CITY, RIVERSTONE.
- v3.1 binding pin (2026-11-15, pre-registration): the ONE buildable setup of Item 2 is PINNED
  HERE (option (a): STEP=0.16 / N=44 / bs 8; see Item 1.4); the v2 pin (N=87 / bs 8) was NOT
  buildable (G7). The SAME-5 re-gate remains the binding pass/fail on the v3.1 pin.

## Inputs read this session (no source changed by this spec)

- .team/specs/52a_class0_restore_prereg.md (v3)
- .team/specs/52b_check_rule_prereg.md (v2)
- .team/specs/52_label_audit_stable_ensemble_spec.md (v3; R6/R7/R8)
- .team/specs/52c_first_shot_sequence_prereg.md (v2)
- .team/review52/hermes_gate52c.txt, .team/review52/muse_gate52c.txt, .team/review52/cursor_gate52c.txt
- .team/review52/labels52a_class0_restore.json
  sha256 = d8d2acd4eaa04004924e3919c0fc3a98ee34f93efe5244d6aa33171b229df384
  (FROZEN; not changed by this spec)
- .team/review52/silent3/silent3_answers.json (Scott's label confirmation)
- .team/review52/clips7a_sha.txt
- .team/review52/gpu_probe52d.txt (coordinator random-input GPU probe; v3 G7 source)
- .team/review52/spec52d_v31_sha.txt (this spec, v3.1; written at Item 4 step 1)
- .team/mm_clip/extract_clips.py, train_clip.py, ensemble_predict.py, gate52.py, test_mm52.py
- .team/mm_clip/postproc52.json, postproc52a.json, postproc52b.json
- Liberty_Shot_Outputs/mm_clip/clips7a/, runs/logo52a/, runs/logo52c/, runs/choose_e52/,
  runs/logo52c/gate52_report.json, runs/logo52c/gate52c_stdout.txt

## Gate facts being answered (baseline: logo52c, E=5, seeds 0 1 2, postproc52b.json)

OVERALL FAIL (binding re-gate target):

- adrian: ensemble auto 93.7 pct (119/127) PASS (all conditions true); checks 6; silent_reject 0; honest review 94.5 (120/127).
- notus: auto 87.1 pct (27/31); checks 3; silent_reject 1 -> FAIL (auto_ge_90 false; silent_eq_0 false); honest review 90.3 (28/31).
- gvg: auto 95.4 pct (208/218); checks 20; silent_reject 1 -> FAIL (silent_eq_0 false); checks_le_20 true (20 <= cap 20); honest review 96.3 (210/218).
- hsb: auto 97.1 pct (136/140) PASS (all conditions true); checks 5; silent_reject 0; honest review 98.6 (138/140).
- rimrock: auto 94.3 pct (116/123); checks 21 (cap 20 -> false); silent_reject 1 -> FAIL (checks_le_20 false, silent_eq_0 false); honest review 95.1 (117/123).

- Seed spread <= 3.2 all games (gate bar <= 5).
- The 3 silents (labelled misses, ens P(shot) < floor 0.2, all 3 seeds P(shot) < 0.5):
  notus t=252520, rimrock t=274807, gvg t=1158600. Scott confirmed all 3 are real misses
  (first shot of a 2-shot sequence; review52/silent3/silent3_answers.json).
- First-shot P(shot) logo52a -> logo52c: notus 0.083 -> 0.170, rimrock 0.096 -> 0.037, gvg 0.181 -> 0.092 (seq flag = 1 on all 3).
- 52b check rule worked: gvg checks 150 -> 20, rimrock 77 -> 21 (postproc52b extras_require_seed_disagreement).
- Seq flag (52c, superseded here as the model fix): seq_follower window 6000 ms fired on
  gvg ~46.9 pct and rimrock ~44.7 pct (~45 pct) of candidates; not a shot marker (gvg
  not-a-shot seq rate 0.49 vs labelled shots 0.29; rimrock 0.42 vs shots 0.45). One float
  after a 512-d pool.

## Item 1 - Decision: ONE input change (PINNED FIX): longer post-shot clip window (option (a))

### 1.1 Clip window geometry (extract_clips.py, pre-change code)

- T0 = -0.88 s, STEP = 0.08 s, N = 32 -> window [t_trig - 0.88, t_trig + 1.60] s,
  trigger at K_TRIG = int(round(-T0 / STEP)) = 11; crop 96 x 112 (w x h), BGR uint8;
  fps read from the video; frame k = round((t_trig + T0 + k*STEP) * fps); moment t_ms IS
  the trigger.

### 1.2 What the old window contained / missed

- Ball reaches rim at ~frame 11 (trigger); the window does NOT end before rim contact.
- Post-contact tail (frames 12-31, +0.08 .. +1.60 s after rim contact) of a MISSED first
  shot is the rebound scramble (class 0).
- Second shot at +1160 ms (gvg), +2600 ms (notus), +5233 ms (rimrock) after the first.
  Old window ends +1.60 s -> only gvg's second shot fell inside; notus and rimrock never
  saw it. For 2 of the 3 silents the model never saw the follow-up inside its input.

### 1.3 DECISION (PINNED NOW, v3.1): option (a) - longer/shifted temporal window (v3.1 buildable pin).

DECISION: option (a) longer clip window, AMENDED by the v3.1 buildable pin (Hermes, 2026-11-15;
v3 sha .team/review52/spec52d_v3_sha.txt). Rationale: the 52c finding was that the deficit
was informational - the post-shot seconds were not in the clip and a sequence flag cannot
carry what is not present. A longer window puts the post-shot seconds into the clip; it is
the minimal, single input change (no fusion, no second backbone). Chosen over option (b)
(second context clip): a second clip/backbone + fusion would add head Linear(1024,3) or a
shared-backbone-twice design for the same possession arc, at higher memory / time cost for
information a single longer window already contains.

PIN (v3.1, ONE buildable setup; G8): STEP=0.16 / N=44 / bs 8 (train + predict) over the same
WINDOW_END_S = 6.0 s; see Item 1.4. The v2 pin (N=87 / STEP=0.08 / bs 8) was NOT buildable
(G7) and is superseded here by this v3.1 pin.

### 1.4 Pinned values (THIS SPEC IS THE FREEZE)

- T0 = -0.88 s (UNCHANGED; release/flight context anchor).
- STEP = 0.16 s (PINNED NOW, v3.1 - buildable pin; was 0.08 s in v2). Reason: the full-span
  uniform grid at STEP=0.08 (N=87) is NOT buildable at the R4 batch size on the RTX 5060
  (G7: probe T=87 bs8 peak 9621 MiB > 8150 MiB card; shared-memory spill; 21.148 s/step;
  ~46x slower, days; no OOM raised on Windows). N=44 at STEP=0.16 keeps the same window span
  [t_trig - 0.88, t_trig + 6.0] s. Cost pinned (v3.1, G8): frame rate on the shot halves
  (STEP 0.16); aug re-pinned to +-1 frame (was +-2; +-1 frame at STEP=0.16 = +-0.16 s physical
  jitter - same R4 jitter, NOT +-0.32 s).
- WINDOW_END_S = 6.0 s (UNCHANGED; was +1.60 s). Reason: a putback / second shot is the same
  possession's rebound-and-putback arc; 6.0 s is a round upper bound that strictly covers
  all three observed gaps (1160 / 2600 / 5233 ms; max gap 5233 ms < 6000 ms). Disclosed: the
  6.0 s end did use the max observed gap as a floor of the pin; the round-up is the domain
  reason, not a result-derived number.
- N = 44 frames (PINNED NOW, v3.1 - was 87; derived): N = int(round((WINDOW_END_S - T0) / STEP)) + 1
  = int(round(6.88 / 0.16)) + 1 = 44. Frame k time = t_trig - 0.88 + k*0.16; last frame at
  t_trig + 6.0 s. Frame resolution now 160 ms (halved from the v2 80 ms; pinned, not tuned).
- K_TRIG = int(round(-T0 / STEP)) = 6 (PINNED NOW, v3.1; derived from the pinned T0=-0.88 and
  STEP=0.16; was 11 at STEP=0.08; the trigger frame is now one 0.16 s grid step past the rim-
  contact moment t_trig + 0.08; pinned as the trigger anchor, disclosed).
- Crop: UNCHANGED (hoop-centred, 2.6 x hoop width x 3.0 x hoop width, resize 96 x 112,
  BGR uint8). Reason: the deficit is temporal, not spatial; the extra seconds stay rim-centred
  and interpretable (second shooter / putback / scramble) while the hoop track holds.
- DISCLOSURE G5 (v2): the crop is NOT kept glued across the longer span. track_hoop keeps the
  previous position when the template match < 0.45 and pads black (BORDER_CONSTANT) when out of
  frame; a weak / frozen track means the crop freezes and pads (no loud failure). DISCLOSED; the
  "kept glued" claim is withdrawn.

### 1.5 Fusion and head (PINNED NOW, v2 - G4 FIX + G2 DISCLOSURE)

- Single clip -> single global temporal pool (backbone temporal pool over the clip) ->
  nn.Dropout(0.5) -> nn.Linear(512, 3) head. NO seq, NO concat.
- Head PINNED EXACTLY AS R4 (v2 G4 fix, BLOCKING): pooled clip -> nn.Dropout(0.5) -> nn.Linear(512, 3)
  (fc = Sequential(Dropout(0.5), Linear(512, 3)); R4 / ens51 / final51 checkpoint keys
  fc.0 / fc.1.weight / fc.1.bias). The v1 text was wrong: it claimed "R4 recipe has no dropout;
  52c added Dropout(0.5) only to support the seq concat" and "NO pool dropout / plain pooled
  head / Linear(512,3)". Corrected: R4 had Dropout(0.5) before the Linear on the pooled features;
  52c had pool_dropout + concat seq -> Linear(513, 3), superseded here. NO seq, NO concat, NO pool
  dropout. Head in_features = 512 (Linear in_features; Dropout(0.5) precedes it). Bare
  Linear(512,3) would be a recipe change - NOT pinned.
- DISCLOSURE G2 (v2, accepted now, not switched after results): the r2plus1d backbone ends in
  a global average pool over the clip; with the pinned window (v2 pin N=87, ~6.9 s; v3.1 pin N=44,
  ~6.9 s; [t_trig - 0.88, t_trig + 6.0] = 6.88 s span) the shot itself is ~2.5 s of the ~6.9 s
  window, so the pooled feature dilutes the shot cue. DISCLOSED as accepted for this pin; N=44
  / STEP=0.16 (v3.1 pin; N=44 is coarsened, NOT dense) is ACCEPTED NOW (frozen), not to be switched
  after results (N=87 / STEP=0.08 / bs4, and the 32-dense + coarse-tail alternatives, remain
  future options only).
- Head in the R4 layout (Sequential(Dropout(0.5), Linear(512,3))) is architecture-compatible with
  the R4 / ens51 / final51 checkpoints; fresh training on clips8 is still pinned (no checkpoint
  reuse).

### 1.6 Why not (b) or the flag

- (b) second context clip: rejected as the pinned choice (memory / time / fusion cost).
- 52c flag: rejected as the fix (information absent from input; scalar after 512 pool; fired
  on ~45 pct of candidates; ignored / not a shot marker).

### 1.7 Missed first shot vs scramble in the extra seconds; whether the rim crop shows it

- With WINDOW_END_S = 6.0 s the tail beyond +1.60 s is now inside the clip: rebound
  scramble for the rebound, and - when the gap allows - the second shot / putback itself.
- gvg t=1158600 (second +1160 ms) was ALREADY inside the old window; for gvg the longer
  window adds no second-shot information, and the 52c flag was the only vehicle (and it
  failed). For notus (+2600 ms) and rimrock (+5233 ms) the longer window now brings the
  follow-up shot into the input, so the model can learn "shot then shot" without any flag.
- DISCLOSURE G3 (v2): reverse confound now disclosed. Class-0 rows with a shot within +6 s
  (gvg 17/145, rimrock 18/241) now contain a later shot -> false-shot risk (the model can
  learn "shot later in clip -> shot"); same structural confound class as the 52c seq flag.
  DISCLOSED; the fail -> stop protocol (Item 8) covers it.
- Rim crop: UNCHANGED 96x112 hoop-centred crop; track_hoop keeps the previous position on weak
  match (<0.45) and pads black out of frame, so the crop can freeze over the longer span; the
  extra seconds (second shooter / putback / scramble) remain visible in the crop WHILE THE
  TRACK HOLDS (G5 disclosure).

### 1.8 Disclosure: where the 3 gaps influenced the pin

- The 3 gaps (1160 / 2600 / 5233 ms) influenced WINDOW_END_S = 6.0 s (round upper bound
  above max gap 5233 ms). Disclosed above; the value is now frozen in this spec, not tuned
  on results.

## Item 2 - Pin the GPU / memory / run-time cost and the clip rebuild (PINNED)

### 2.1 GPU / memory / run-time cost (PINNED, v3.1 - G1 FIX / G7 + G8)

- NVIDIA GeForce RTX 5060, 8151 MiB (~8 GiB) GPU-0, CUDA 13.2, driver 595.61, 8 W TGP; 33C;
  Windows GPU venv.
- Current logo run: ~40 min for 15 model-fits (E=5, seeds 0 1 2, same-5 LOGO, clips7a) on
  this GPU (logo52a 2357 s, logo52c 2376 s ~ 39.3 / 39.6 min).
- clips8 (v3.1 pin: N=44 frames; v2 pin was N=87) vs clips7a (N=32): larger inputs -> memory /
  time increase. PIN: same GPU, env and recipe; re-measure (train writes res["seconds"]; report)
  and budget the pinned run at ~45-55 min on this GPU (probe 0.53 vs 0.46 s/step x 2376 s ->
  ~45 min; T=44 bs8 probe ~45-55 min run; G8 speed guard: measured s/step > 2x probe or spill
  -> STOP for Scott). The stale v2 current-budget figures (~100-120 min; ~107 min; ~68 min) are
  kept ONLY as labelled v2 history below - not current budgets.
- G1 pins (v2, binding): train bs 8 PINNED (R4 recipe value); predict bs PINNED to 8 (the
  train_clip.predict default bs=16 is not used for 52d); on CUDA OOM -> STOP for Scott, no
  silent bs change (a bs change would alter the R4 recipe). Random-input GPU memory probe (no
  data, no training) by the coordinator: review52/gpu_probe52d.txt; cite its result if present.
- G7 (v3.1, blocking, NEW): the v2 PIN is NOT buildable (see Status / Item 1.4). Probe
  (review52/gpu_probe52d.txt; random input, no project data, no training; r2plus1d_18 +
  Dropout/Linear(512,3) head, AdamW, bf16 autocast, input 112x96): T=32 bs8 train peak
  3938 MiB, 0.46 s/step (today's recipe; ~40 min logo run); T=87 bs8 train peak 9621 MiB >
  8150 MiB card -> Windows spills to shared memory, 21.148 s/step (~46x slower, days); NO OOM
  error is raised on Windows, so the v2 OOM -> STOP rule would never fire; v2 pin NOT buildable.
  T=44 bs8 (STEP=0.16, same -0.88..+6.0 s span): 5176 MiB, 0.53 s/step (~45-50 min run); T=87
  bs4: 5239 MiB, 0.55 s/step per 4 clips (~2x run time; bs change = R4 recipe change).
- G8 (v3.1, binding, NEW): ONE buildable setup pinned (v3.1 pin; Item 1.4): STEP=0.16 / N=44 /
  bs 8 (train + predict). Speed guard REPLACES the v2 OOM-only STOP: if measured train s/step
  > 2x the probe value for the pinned setup (T=44 bs8 probe 0.53 s/step -> 1.06 s/step) or
  shared-memory spill seen -> STOP for Scott; no silent bs change (bs stays 8 PINNED, R4).

### 2.2 Clip rebuild (PINNED): new clips dir from the SAME candidates and labels52a

- New clips dir: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/clips8/
  ({adrian,gvg,hsb,notus,rimrock}.npz).
- Source: SAME candidates (cand5/<film>_mv.json) and SAME frozen labels
  (labels52a_class0_restore.json, sha d8d2acd4..., FROZEN) as clips7a; t_ms arrays align
  (same moments), frames change only via the new window.
- SHA freeze: sha256 of each clips8/<film>.npz -> .team/review52/clips8_sha.txt BEFORE
  training.

### 2.3 Extract command (PINNED)

python .team/mm_clip/extract_clips.py <film> /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/cand5/<film>_mv.json <video> gvfmt:/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/labels52a_class0_restore.json /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/clips8/<film>.npz

with <video> = the film's source video (same tokens as used for clips7a).

## Item 3 - Recipe otherwise R4 unchanged; run protocol

- R4 recipe UNCHANGED: bf16 autocast without GradScaler; WeightedRandomSampler
  w = 1/max(cnt, 1); plain CE + label_smoothing 0.05 (no class weights); soft augmentation;
  lr 2e-4, bs 8, AdamW wd 0.05, OneCycle pct_start 0.15; time-shift +-1 frame (PINNED NOW, v3.1;
  was +-2 frames in v2; +-1 frame at STEP=0.16 = +-0.16 s physical jitter, same R4 jitter; NOT
  +-2 frames = +-0.32 s).
- G1 pins (v2, binding): train bs 8 PINNED; predict bs PINNED to 8; on CUDA OOM -> STOP for
  Scott, no silent bs change. (v3.1 G8 REPLACES that STOP with the speed guard; bs stays 8 PINNED,
  R4; the v3.1 pin changes STEP/N/aug, not bs.)
- E = 5 pinned (not choose_e).
- Seeds 0 1 2.
- Runs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52d/
  -> {log.txt, logo_report.json, logo_preds.npz, gate52_report.json}.
- Gate: gate52 with postproc52b.json; same-5 binding (Scott 'A'); fail -> stop for Scott;
  R10 blind later (NOTUS_A, IDAHO_CITY, RIVERSTONE).
- Silent definition UNCHANGED (labelled miss AND ensemble mean P(shot) < floor 0.2 AND all M
  seeds P(shot) < 0.5; gate requires silent_eq_0 per game).

## Item 4 - Exact build + test + run order

0. Prerequisite: this spec written and sha-frozen (step 1) BEFORE any code change or
   training. Muse + Cursor review; Scott approves; then the re-gate runs.

1. Sha freeze (this spec, v3.1):
   sha256 of .team/specs/52d_context_clip_prereg.md -> .team/review52/spec52d_v31_sha.txt
   (form: <sha256> *specs/52d_context_clip_prereg.md).

2. Code changes (.team/mm_clip/only):
   - extract_clips.py: window parameterized (T0 / STEP / WINDOW_END_S / N); 52d values
     pinned (T0 = -0.88, STEP = 0.16, WINDOW_END_S = 6.0, N = 44; OUT_W/OUT_H/crop UNCHANGED);
     K_TRIG = int(round(-T0 / STEP)) = 6.
   - train_clip.py: 52d model = single pooled clip -> nn.Dropout(0.5) -> nn.Linear(512, 3) head
     (PIN EXACTLY AS R4 per G4 fix; fc = Sequential(Dropout(0.5), Linear(512, 3)); NO seq, NO
     concat, NO pool dropout); forward(x) single input, no seq, no concat; train/predict
     accept seq=None (no seq) for this model; predict: FORCE bs=8 explicitly (train_clip.predict
     default bs=16 overridden; Item 4 step 2); R4 recipe otherwise UNCHANGED.
   - ensemble_predict.py: predict path for 52d models = single pooled clip, no seq
     (predict_all without seq / seq=None for 512-head models); predict: FORCE bs=8 explicitly
     in train_clip.predict calls (Item 4 step 2).
   No change: gate52.py, postproc52.json, postproc52a.json, postproc52b.json (52b check rule
   stays; sha frozen in .team/review52/spec52c_postproc52b_sha.txt).

3. Tests (GPU-free where possible; run on the Windows .venv per existing convention; WSL
   fallback: python3 -m pytest .team/mm_clip/test_mm52.py -q, deselect the 3 Windows-path
   holdout_names tests):
   - Extend .team/mm_clip/test_mm52.py: assert the v3 pin: window N = 44 / K_TRIG = 6 / STEP =
     0.16; single-input head = Dropout(0.5) -> Linear(512,3) (PIN EXACTLY AS R4 per G4 fix); no
     seq, no concat; train/predict seq=None; R4 recipe unchanged (incl. Dropout(0.5)); time-shift
     +-1 frame; predict bs=8; 52b check-rule tests unchanged. Tests MUST assert the v3 pin (N=44,
     K_TRIG=6, STEP 0.16, time-shift +-1, Dropout(0.5)->Linear(512,3), predict bs 8).
   - Run pytest .team/mm_clip/test_mm52.py -q -> all pass before training.

4. Postproc lock (52b check rule combined in this re-gate): postproc52b.json UNCHANGED
   (as frozen in .team/review52/spec52c_postproc52b_sha.txt). No new postproc file.

5. Clips rebuild: new clips dir clips8 from the SAME candidates and labels52a via the
   pinned extract command; sha freeze -> .team/review52/clips8_sha.txt; confirm clips8
   t_ms arrays equal the clips7a t_ms arrays (same candidates, frames differ only).

6. Train logo52d (E=5, seeds 0 1 2; no choose_e):
   python3 .team/mm_clip/train_clip.py logo \
     /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/clips8 \
     /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52d \
     --films adrian notus gvg hsb rimrock --epochs 5 --seeds 0 1 2
   Outputs: runs/logo52d/{log.txt, logo_report.json, logo_preds.npz}.

7. Re-gate (binding, same 5, combines 52d + 52b):
   python3 .team/mm_clip/gate52.py \
     /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52d/logo_preds.npz \
     adrian=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json=tags \
     notus=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json=tags \
     gvg=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/truth52_gvg.json=labels \
     hsb=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/truth52_hsb.json=labels \
     rimrock=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/truth52_rimrock.json=labels \
     --postproc /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/postproc52b.json
   Writes runs/logo52d/gate52_report.json.

8. Fail -> STOP for Scott: no thr/floor/seed/epoch retune, no extra runs, no tuning on the
   3 silents; Scott decides the next step. Stop rule (v3.1, G8, REPLACES the v2 OOM-only STOP):
   if measured train s/step > 2x the probe value for the pinned setup (T=44 bs8 probe
   0.53 s/step -> 1.06 s/step) or shared-memory spill seen -> STOP for Scott; no silent bs
   change. Pass -> Scott gate; R10 blind later (NOTUS_A, IDAHO_CITY, RIVERSTONE) as the stronger
   test.

## Item 5 - Honest read

Expected effect: mechanism-only. With WINDOW_END_S = 6.0 s the second shot / putback of
every first-of-two-shots sequence is inside the clip, so the longer clip carries the
follow-up cue without any sequence flag; the head (Dropout(0.5) -> Linear(512,3), no seq) learns
from the clip directly. No certainty is claimed. The re-gate (R6 conditions on the same 5) is the
test: ensemble auto >= 90%, seed spread <= 5, honest review >= 90%, checks <= 20 hard, silent_reject
== 0 per game, OVERALL PASS required.

Honest trade-off on make/miss accuracy (v3.1 pin; binding pass is the SAME-5 re-gate on the
v3.1 pin): the v3.1 PINNED setup (STEP=0.16 / N=44 / bs 8) halves the frame rate on the shot itself
(~2.5 s shot -> ~16 frames vs ~31 at STEP=0.08; aug time-shift re-pinned to +-1 frame = +-0.16 s
physical jitter) and samples the post-shot tail at 160 ms. The make/miss accuracy trade-off is
stated honestly: the expected effect is mechanism-only (longer context now present), the
accuracy delta is unmeasured (no training has run; the v2 probe was random-input only), and the
pinned STEP=0.16 / N=44 vs STEP=0.08 / N=87 / bs4 vs dense+coarse-tail alternatives are pins,
not tuned numbers. No make/miss accuracy claim is made from this pin.

HERMES: PREREG V3.1 WRITTEN
