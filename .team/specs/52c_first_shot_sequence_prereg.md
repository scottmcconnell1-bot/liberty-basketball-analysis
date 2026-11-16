# Spec 52C - First-Shot-of-Sequence Model Fix (PRE-REGISTERED) v2

Author: HERMES (Architect)
Date: 2026-11-15
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
Outputs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/

## Status

PRE-REGISTERED (v2). The change set below is frozen BEFORE any code change or training.
This is the binding pre-registration for the first-shot-of-sequence model fix, combined
with spec 52b (check rule) in ONE re-gate using postproc52b.json.

## Binding decision (Scott, 2026-11-15)

- Scott decided (2026-11-15): the team designs a MODEL fix for the blind spot on the
  first shot of a 2-shot sequence (shot then putback / second shot).
- Pre-registered; Muse + Cursor review; Scott approves; then the SAME-5 re-gate is the
  binding pass/fail (Scott 'A'); later R10 blind films: NOTUS_A, IDAHO_CITY, RIVERSTONE.
- The re-gate combines this spec (52c model change) with spec 52b (check rule) in ONE
  re-gate using postproc52b.json.

## Inputs read this session (no source changed by this spec)

- .team/specs/52a_class0_restore_prereg.md (v3)
- .team/specs/52b_check_rule_prereg.md (v2)
- .team/specs/52_label_audit_stable_ensemble_spec.md (v3; R6/R7/R8)
- .team/review52/hermes_gate52a.txt, .team/review52/muse_gate52a.txt,
  .team/review52/cursor_gate52a.txt
- .team/review52/labels52a_class0_restore.json
  sha256 = d8d2acd4eaa04004924e3919c0fc3a98ee34f93efe5244d6aa33171b229df384
  (labels52a is FROZEN and is NOT changed by this work; no labels52c file is created)
- .team/review52/silent3/silent3_answers.json (Scott's label confirmation)
- .team/mm_clip/extract_clips.py, train_clip.py, ensemble_predict.py, gate52.py,
  postproc52.json, postproc52a.json, test_mm52.py
- .team/review52/clips7a_sha.txt (clips7a frozen: adrian, gvg, hsb, notus, rimrock npz;
  sha file at /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/clips7a_sha.txt)
- Liberty_Shot_Outputs/mm_clip/runs/logo52a/gate52_report.json (baseline being answered)

## Gate facts being answered (baseline: logo52a, E=5, seeds 0 1 2)

OVERALL FAIL (binding re-gate target):

- adrian: ensemble auto 94.5 PASS (all conditions PASS)
- notus: auto 90.3, silent_reject 1 -> FAIL (silent_eq_0)
- gvg: auto 95.9, checks 150 (cap 20), silent_reject 1 -> FAIL
- hsb: auto 97.1 PASS (all conditions PASS)
- rimrock: auto 95.1, checks 77 (cap 20), silent_reject 1 -> FAIL
- honest coach review 93.5-99.3; spread <= 5 all games.

The 3 silents (labelled misses, ens P(shot) < floor 0.2, all 3 seeds P(shot) < 0.5):
notus t=252520, rimrock t=274807, gvg t=1158600. Scott confirmed all 3 first shots are
real misses (review52/silent3/silent3_answers.json).

## Item 1 - Diagnosis from CODE and DATA DEFINITIONS first (no tuning on the 3 silents)

### 1.1 Clip window geometry (extract_clips.py)

- T0 = -0.88 s, STEP = 0.08 s, N = 32 -> window [t_trig - 0.88, t_trig + 1.60] s,
  32 frames, trigger at index K_TRIG = int(round(-T0/STEP)) = 11 (frame 11 of 32,
  i.e. 34% through the clip, exactly at t_trig).
- Crop: hoop-centred, 2.6 x hoop width x 3.0 x hoop width, resized 96 x 112 (BGR uint8).
- fps: read from the video at extract (cv2.CAP_PROP_FPS); frame k sampled at
  round((t_trig + T0 + k*STEP) * fps). There is NO extra offset between candidate t_ms
  and the clip: the moment t_ms IS the trigger, so the clip is anchored on t_ms.
- Frame k time = t_trig - 0.88 + k*0.08.

### 1.2 What the candidate t_ms means (trigger2.py)

- Moment = FIRST frame where the ball is within R_TRIG = 1.0 hoop width of that frame's
  hoop centre, after a ball point was above the rim (y < hy - 0.3*hw, within 3.0 hw in x)
  within LOOKBACK_S = 1.2 s. Triggers closer than MERGE_S = 1.5 s merge; moment = first
  trigger frame of the group; hoop = that frame's hoop.
- Consequence: t_ms approximates ball AT / NEAR THE HOOP (rim contact), NOT the release.
- For a jump shot/3PT, release-to-rim is roughly 0.8-1.2 s, so release is at
  t_trig - 0.8 .. t_trig - 1.2, i.e. at or just before the window start (frame 0):
  the clip opens on late flight, shows rim contact at frame 11, then the aftermath.

### 1.3 Where the first shot sits inside its 32-frame window

- The ball reaches the rim at ~frame 11 (trigger time) - INSIDE the window. The window
  does NOT end before the ball reaches the rim.
- BUT the post-contact part of the clip (frames 12-31, +0.08 to +1.60 s after rim
  contact) of a MISSED first shot is the rebound scramble (ball loose, players reaching)
  - i.e. the class-0 'rebound scramble' pattern. A label-1 first-shot MISS clip therefore
  shows shot/rim-contact in its first third and class-0 scramble in its last two-thirds.
- The second shot of the sequence arrives +1160 ms (gvg), +2600 ms (notus),
  +5233 ms (rimrock) after the first. Inside the 32-frame window (ends +1.60 s after
  trigger) only gvg's (+1160 ms, frame ~25) falls in; notus (+2600 ms, frame ~43) and
  rimrock (+5233 ms, frame ~76) are OUTSIDE the clip. For 2 of the 3 silents the model
  never sees the follow-up shot inside its input.

### 1.4 First-of-sequence training rows, from labels alone (labels52a_class0_restore.json)

Definition: a real shot row (y in {1,2}) with another real shot row within N s after it
(same film, labels alone, no model output). Counts per film:

|| N after first shot | adrian /121 | notus /30 | gvg /218 | hsb /140 | rimrock /123 | TOTAL /632 ||
||---|---|---|---|---|---|---|---||
|| 2000 ms | 2 | 1 | 14 | 9 | 8 | 34 ||
|| 4000 ms | 6 | 3 | 22 | 13 | 16 | 60 ||
|| 6000 ms | 13 | 3 | 32 | 23 | 21 | 92 (~15%) ||
|| 8000 ms | 17 | 5 | 44 | 29 | 22 | 117 ||
|| 10000 ms | 25 | 7 | 56 | 34 | 25 | 147 ||

- First-of-sequence shots are ~15% of all training shot rows at N=6000 ms - not rare;
  they are just INVISIBLE to the clip model because the follow-up shot is outside the
  window and the input carries no sequence information.
- Confirmed silent rows are all y = 1 (miss) in labels52a and each has a second real
  shot after it: notus 252520 -> 255120 (+2600 ms), rimrock 274807 -> 280040 (+5233 ms),
  gvg 1158600 -> 1159760 (+1160 ms). Model P(shot): first shot 0.08-0.18 (all 3 seeds
  < 0.5); second shot 0.94-0.995.

### 1.5 Root cause (code/definition level)

The model input is a single rim-centred 32-frame window anchored on the first shot's
rim contact, plus nothing else. After a missed first shot the clip's tail is rebound
scramble (class 0 appearance), and the second shot - the only cue that this was a shot
attempt rather than a scramble - lies outside the window for notus and rimrock. There is
no sequence information in the input at train or predict time, so the model cannot learn
"another shot follows within a few seconds -> this first event IS a shot".

## Item 2 - ONE model-side change (PINNED FIX)

Options weighed: (a) longer/shifted temporal window (rebuilds all clips, dilutes the
shot event, still misses rimrock's +5233 ms gap unless the window is made very long);
(b) add a second context clip or a 'next shot within N s' sequence feature;
(c) oversample first-of-sequence shots (does not fix the missing information; the clip
still does not show the follow-up shot); (d) other.

DECISION: option (b) - a 'next shot within N s' sequence feature, one scalar, no clip
rebuild, no input-shape change beyond +1 feature.

### 2.1 Sequence feature (PINNED NOW, not taken from the 3 silent P values or any
logo52a gate number)

- SEQ_WINDOW_MS = 6000 (6 s). Reason: a putback / second shot is the same possession's
  rebound-and-putback, which resolves within a few seconds; a gap greater than 6 s is a
  new possession, not the 2-shot sequence. 6000 ms is a round upper bound on continuous
  possession action and happens to cover all three observed gaps (1160 / 2600 / 5233 ms);
  4000 ms would not cover rimrock's 5233 ms. It is NOT chosen to include or exclude the
  3 gaps and NOT chosen from any silent P value or gate number.
- seq_follower(t) = 1.0 iff another candidate moment exists with t_ms in
  (t, t + 6000] (inclusive end), else 0.0. Computed PER FILM over that film's full
  candidate T (incl. -1/0 rows), never across films:
  - Train: from the clips npz t_ms array, one npz / Fm == f (full film T for follower
    lookup even though the loss mask drops Y < 0).
  - Predict: from the candidate moment T, one film at a time.
  Identical computation at train and predict; NO labels used; no label peeking;
  cross-film concat is forbidden (it invents false followers).
- Float32 (B, 1), 0.0/1.0, no scaling.

### 2.2 Model (PINNED NOW)

- Backbone: torchvision r2plus1d_18 (Kinetics-400 pretrained), fine-tuned end to end -
  UNCHANGED.
- Head: global pooled 512-d features -> nn.Dropout(0.5) applied to the pool ONLY;
  seq_follower concatenated AFTER dropout (never dropped); nn.Linear(513, 3).
- forward(x, seq): x = (B,3,T,H,W) normalised clip; pooled 512-d features concat seq
  (B,1) float32 flags -> head.
- Old Linear(512, 3) checkpoints are INCOMPATIBLE with the new 513 head.
- All R4 recipe hyperparameters UNCHANGED: bf16 autocast without GradScaler;
  WeightedRandomSampler w = 1/max(cnt,1); plain CE + label_smoothing 0.05 (no class
  weights); soft augmentation; lr 2e-4, bs 8, AdamW wd 0.05, OneCycle pct_start 0.15;
  time-shift +-2 frames augmentation unchanged.

### 2.3 Training / predict wiring (PINNED NOW)

- train_clip.py logo mode: seq computed per film from T (npz t_ms), passed to train()
  and predict(); the DataLoader/sampler indexes seq identically to X/Y.
- ensemble_predict.predict_all(X, models, seq=None): seq computed per film from
  candidate T; seq=None -> all-zero flags for NEW 513 models only (not logo52a .pt
  load compatibility).
- shot_list() (52b wiring): below-thr extras are flagged only if
  seed_disagreement(PM, i) when postproc52b review.extras_require_seed_disagreement is
  true; uncorroborated band extras are not flagged. postproc52.json / postproc52a.json
  keep the flat band (key absent).
- gate52.py, silent_reject_count(), honest_review_score(): UNCHANGED.
  The feature is a model input only; the 52b corroboration gate alters which below-thr
  extras become coach checks; it does not alter shot listing or the silent-reject
  definition.

### 2.4 Expected effect (mechanism only, not a promise; not a number picked from results)

All 3 silents have another candidate within 6000 ms (flags become 1), giving the model
the follow-up-shot cue the 32-frame window cuts off. Whether first-shot P(shot) rises
above floor 0.2 with all seeds >= 0.5 on the re-gate is the test. No certainty is
claimed in this pre-registration.

## Item 3 - Disclosure

- The change IS motivated by the 3 observed silents (notus 252520, rimrock 274807,
  gvg 1158600). Stated in writing per the honesty rule.
- The same-5 re-gate (adrian, notus, gvg, hsb, rimrock) is the BINDING pass/fail
  (Scott 'A', 2026-11-15). R10 blind films NOTUS_A / IDAHO_CITY / RIVERSTONE are the
  STRONGER test and remain for later (Riverstone: no readable board).
- The silent-reject definition is UNCHANGED (labelled miss AND ensemble mean P(shot)
  < floor 0.2 AND all M seeds P(shot) < 0.5; gate requires silent == 0 on every game).
- No labels52c file; labels52a_class0_restore.json untouched; no thr / floor / seed /
  epoch retune; this is NOT a clean unqualified pre-registration (motivation is
  post-hoc; values are pinned now with domain reasons, not from the silent P values or
  logo52a gate numbers).
- F2 confound (disclosed): seq_follower fires on ~13-47% of candidates per film
  (notus 13%, gvg 47%) and the flag is not shot-only: on gvg most flagged rows are
  label -1/0 scramble candidates, so the flag can fire on non-shots. In-session-only
  gating: NO. Reason (not from results): session.json is not a frozen input of this
  spec and is unavailable for rimrock (None = no filter), so gating follower lookup on
  session membership would make the flag film-dependent and add an unfrozen external
  dependency; per-film candidate t_ms only keeps the definition label-free, uniform
  across films, and identical at train and predict.

## Item 4 - Exact build + run order

0. Prerequisite: this spec written and sha-frozen (step 1) BEFORE any code change or
   training. Muse + Cursor review; Scott approves; then the re-gate runs.

1. Sha freeze (this spec):
   sha256 of .team/specs/52c_first_shot_sequence_prereg.md written to
   .team/review52/spec52c_v2_sha.txt, form:
     <sha256> *specs/52c_first_shot_sequence_prereg.md

2. Code changes (.team/mm_clip/only):
   - train_clip.py: make_model head = Dropout(0.5) on the 512-d pool only, then concat
     seq (never dropped), nn.Linear(513, 3); train() and predict() accept seq (B,1)
     float32 from per-film T.
   - ensemble_predict.py: predict_all(X, models, seq=None); seq per film from candidate
     T; seq=None -> zeros for new 513 models only. shot_list: extras flagged only if
     seed_disagreement(PM, i) under postproc52b.
   No other file changed.

3. Tests (GPU-free where possible; run on the Windows .venv per existing convention;
   WSL fallback: python3 -m pytest .team/mm_clip/test_mm52.py -q, deselect the 3
   Windows-path holdout_names tests):
   - Extend .team/mm_clip/test_mm52.py: seq_follower computed PER FILM over that film's
     full candidate T (incl. -1/0 rows), never across films; pure function, 0/1 float32,
     window (t, t+6000] inclusive end (test line asserts flag at t+6000 and no flag at
     t+6001); model forward with seq -> (B,3) logits, head in_features 513, Dropout on
     pool only then concat; predict_all accepts seq; seq=None -> zeros for new 513
     models; old Linear(512,3) state dicts fail to load.
   - 52b tests: extras flagged only if seed_disagreement(PM, i); uncorroborated band
     extra not flagged; auto flags unchanged; silent backstop unchanged.
   - Run pytest .team/mm_clip/test_mm52.py -q -> all pass before training.

4. Postproc lock (52b check rule combined in this re-gate):
   Write .team/mm_clip/postproc52b.json exactly:
     {
       "shot_thr": 0.5,
       "dedup_ms": 800,
       "session_filter": true,
       "review": {
         "flag_below_thr_candidates_with_shot_prob_at_least": 0.2,
         "flag_auto_shots_with_shot_prob_below": 0.65,
         "flag_auto_shots_with_abs_pmake_minus_half_below": 0.3,
         "flag_seed_disagreement": true,
         "extras_require_seed_disagreement": true
       }
     }
   postproc52.json and postproc52a.json: review key has NO
   extras_require_seed_disagreement key (flat band kept). Sha freeze postproc52b.json to
   .team/review52/spec52c_postproc52b_sha.txt:
     <sha256> *mm_clip/postproc52b.json

5. Clips: NO new extract. clips7a is already frozen
   (/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/clips7a;
   sha in .team/review52/clips7a_sha.txt). t_ms unchanged -> seq_follower derivable at
   train (clips npz t_ms per film) and predict (candidate T per film). labels52a frozen
   (sha above); no relabel, no new clips dir.

6. Train logo52c (E=5, seeds 0 1 2; no choose_e - E pinned):
   python3 .team/mm_clip/train_clip.py logo \
     /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/clips7a \
     /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52c \
     --films adrian notus gvg hsb rimrock --epochs 5 --seeds 0 1 2
   Outputs: runs/logo52c/{log.txt, logo_report.json, logo_preds.npz}.

7. Re-gate (binding, same 5, combines 52c + 52b):
   python3 .team/mm_clip/gate52.py \
     /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52c/logo_preds.npz \
     adrian=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json=tags \
     notus=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json=tags \
     gvg=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/truth52_gvg.json=labels \
     hsb=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/truth52_hsb.json=labels \
     rimrock=/mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/truth52_rimrock.json=labels \
     --postproc /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/postproc52b.json
   Writes runs/logo52c/gate52_report.json.

8. Fail -> STOP for Scott: no thr/floor/seed/epoch retune, no extra runs, no tuning on
   the 3 silents; Scott decides the next step. Pass -> Scott gate; R10 blind films
   (NOTUS_A, IDAHO_CITY, RIVERSTONE) later as the stronger test.

## Item 5 - Honest read

Expected effect: mechanism-only (the sequence flag gives the model the follow-up-shot
information the 32-frame window cuts off; all 3 silent gaps fall inside 6000 ms). Not
certainty. R6 conditions on the same 5 are the test: ensemble auto >= 90%, seed spread
<= 5, honest review >= 90%, checks <= 20 hard, silent_reject == 0 per game, OVERALL
PASS required.

HERMES: PREREG V2 WRITTEN
