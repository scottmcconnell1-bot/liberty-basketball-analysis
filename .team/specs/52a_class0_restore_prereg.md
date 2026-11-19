# Spec 52A - Class-0 Restore + Predict-Time Game-Session Filter (PRE-REGISTERED) v3

Author: HERMES (Architect)
Date: 2026-11-14
Repo: /mnt/c/Users/scott/Documents/liberty-basketball-analysis
Outputs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/

## Status

PRE-REGISTERED (v3). The change set below is frozen BEFORE any training. This is the binding
pre-registration for proposal (a).

## Binding decision (Scott, 2026-11-14)

- Scott decided (binding, 'A', 2026-11-14): approve proposal (a) from the gate review.
- The re-gate on the SAME 5 LOGO games (adrian, notus, gvg, hsb, rimrock) - spec 52 R6 unchanged - is the
  binding pass/fail.

## Inputs read this session (no source changed)

- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/specs/52_label_audit_stable_ensemble_spec.md (v3)
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/hermes_gate52.txt
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/muse_gate52.txt
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/cursor_gate52.txt
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/drift_log.md (tail)
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/labels52_v2.json
  sha256 = 56f18cf0a9c32b7ffb9768885f822d8bd7e1bc794a4a184526c5ca47ee4aec44
  (labels52_v2.json is FROZEN and is NOT to be changed by this work)
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/train_clip.py
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/ensemble_predict.py
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/postproc52.json
- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/gate52.py
- /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/game_session_48b/** (session.json outputs)

## Gate facts being answered (logo52 run, E=5, seeds 0 1 2, labels52_v2 frozen)

- auto adrian 94.5, notus 90.3, gvg 95.9, hsb 98.6, rimrock 95.1
- review 93.5-99.3
- OVERALL FAIL
- FAIL reasons: checks (gvg 200 / rimrock 97), silent_reject (notus 1 / rimrock 1), spread (rimrock 6.5)
- false shots: gvg 299 (seeds 0 and 2 call most GV not-shot moments a shot); the class-0 not-a-shot
  learned almost only from rimrock; adrian and notus have ZERO class-0 rows.

## v2 - fixes applied from the v1 reviews (Cursor DISAGREE; Muse DISAGREE -> AGREE WITH CHANGES after fixes)

### O1 (Cursor/Muse DISAGREE -> AGREE WITH CHANGES): FIXED - paths
Every path is now written /mnt/c/Users/scott/Documents/... (the v1 text dropped the "scott" segment and
wrote /mnt/c/Users/Documents/...).

### O2 (Cursor/Muse DISAGREE -> AGREE WITH CHANGES): FIXED - class-0 counts / notus source / far-from-tag
Cursor: under the pinned 48b out-of-session rule, class-0 after restore = adrian 6 / notus 0 / hsb 4
(gvg/rimrock unchanged). The v1 "notus 9" was wrong - it contradicted the pinned rule (48b dropped 0/36
notus finder moments as out-of-session, so notus gets no out-of-session restore). Muse required the
notus class-0 source to be pinned and the adrian 6-of-8 restore selection to be stated.

v2 pins: notus class-0 source = none from 48b (0/36 dropped); notus class-0 comes from the new fixed
far-from-tag rule (O5) below (+6). Adrian's restore = 6 from 48b out-of-session + the far-from-tag set.

### O3 (Cursor DISAGREE -> AGREE WITH CHANGES): FIXED - clips coverage
Cursor: clips7 t_ms == labels52_v2 t_ms for all five films (0 missing, 0 extra); all restore t_ms
already in clips7; no new extract needed for the adrian rows; notus source now stated.

v2 answers: YES - every class-0 row that this pre-registration adds already has a clip in clips7 with the
same t_ms (adrian restores from the 48b dropped moments; adrian/notus far-from-tag restores from
labels52_v2 t_ms); no new extract step is pinned.

### O4 (Cursor DISAGREE -> AGREE WITH CHANGES): FIXED - session_filter wiring + scoring
Cursor: gate52/ensemble_predict do NOT implement session_filter today (postproc52 still false; old
postproc.py is not the gate path); scoring must state that a filtered candidate is omitted from the shot
list and a filtered real shot = recall miss; HSB miss t=2631233 is out of session -> recall risk.

v2 pins (below, Item 2): ensemble_predict.shot_list applies the session filter; postproc52.json
session_filter -> True for the logo52a run; test_mm52.py asserts the filtered behaviour; scoring =
omit, filtered real shot = recall miss.

### O5 (Cursor DISAGREE -> AGREE WITH CHANGES): APPLIED - fixed far-from-tag gap pinned now
Cursor: fixed far-from-tag rule on in-session y=-1 (e.g. >=8 s from any coach tag) -> class 0 gives
adrian ~26 + notus ~6 without peeking; this is the only (a)-compatible way to add meaningful multi-gym
class-0.

v2 applies: GAP pinned NOW at 8000 ms (see Item 1).

## v3 - fixes applied from the v2 reviews (round cursor/muse v2v8; Claude Code re-verified counts; Cursor DISAGREE on counts; Muse AGREE WITH CHANGES)

### Counts corrected (Claude Code verified independently, scratchpad overlap52a.py; Cursor right, Muse corrected)

- Every adrian out-of-session y=-1 row is ALSO >= 8 s from any coach tag (oos is a subset of far; oos dists
  47.8-176 s). Unique adrian class-0 = 26 (NOT 32; the v2 text double-counted the 6 out-of-session + the 26
  far-from-tag as disjoint). Notus 6; hsb 4; gvg 145; rimrock 241. Hold-out-gvg train class-0 = 277 (NOT 283;
  = 241 rimrock + 4 hsb + 26 adrian + 6 notus).
- adrian y=-1 n=45 (39 in-session + 6 oos by 48b in_session(is_ft=True), pinned THAT definition); remaining
  -1: adrian 19, notus 3. Fix every count.

### Build order pinned (v3; amends spec 52 R7)

- Cursor implements session_filter in ensemble_predict.shot_list + gate52 path (per-film session json
  mapping, omit scoring) + tests and writes labels52a + .team/pre52a_sha256.txt; Claude Code verifies; Muse +
  Cursor confirm; only then training. State explicitly that this amends spec 52 R7 (postproc52
  session_filter false -> true for logo52a only; R7 lock re-frozen with new sha).

### Honesty (v3; same-5 re-gate)

- Scott chose the same-5 re-gate as binding (2026-11-14, 'A'); Muse and Cursor's dissent (same-5 = diagnostic,
  blind R10 binding) is recorded, and R10 blind on NOTUS_A / IDAHO_CITY / RIVERSTONE stays available after a pass.

## Item 1 - Class-0 restore (PINNED FIX, v2)

### 1.1 Pinned rule (fixed BEFORE any training; no logo52 predictions used)

The restore is the conjunction of two source-pinned rules:

(i) 48b out-of-session candidates -> class 0 (y=0). Source:
/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/game_session_48b/<film>/session.json (48b dropped the
out-of-session finder moments; adrian 8/136 dropped; notus 0/36 dropped).

(ii) In-session untagged candidates (y=-1) on adrian and notus whose distance to the nearest
coach-tagged shot is >= GAP -> class 0; else stay -1.

GAP pinned NOW: 8000 ms (>= 8 s). Cursor computed: >=8 s -> adrian ~26, notus ~6; >=15 s -> adrian ~18, notus
~4; >=30 s -> adrian 7, notus 1.

- adrian: y=-1 n=45 (39 in-session + 6 out-of-session, pinned 48b in_session(is_ft=True)); dist>=8 s -> 26
  -> class 0; dist<8 s -> stay -1.
- notus: in-session untagged n=9; dist>=8 s -> 6 -> class 0; dist<8 s -> stay -1.

Gap choice (architect, stated): pinned at 8000 ms, because it is the fixed threshold at which the
far-from-tag in-session untagged sets become a meaningful multi-gym not-a-shot pool for the D1 gyms
(adrian ~26 + notus ~6), versus >=15 s which would under-restore (adrian ~18 + notus ~4). Risk accepted in
writing: some far -1 may be an untagged real shot (coach miss / scramble). Scott ruling: putbacks are
separate shots, so a putback is evaluated as its own shot (own candidate, own coach-tag window), not
folded into the original tagged shot.

### 1.2 Exact post-restore class counts (computed from the pinned rule)

Under rule (i) alone (the v1 pinned rule, before the far-from-tag gap was pinned): adrian 6 / notus 0 /
hsb 4 / gvg 145 / rimrock 241.

Under the full pinned v2 rule ((i) AND (ii), GAP=8000 ms; gvg/rimrock frozen unchanged; hsb unchanged):

- adrian: class-0 AFTER restore = 26 (unique; oos ⊂ far, so the v2 "6 + 26 = 32" double-counted; NOT 32).
Real shots 121 (y1=79, y2=42). In-session untagged staying -1 = 19 (39 in-session - 20 far-in-session, dist>=8 s).
- notus: class-0 AFTER restore = 0 (from 48b out-of-session) + 6 (from in-session far-from-tag,
  dist>=8 s) = 6. Real shots 30 (y1=22, y2=8). In-session untagged staying -1 = 9 - 6 = 3.
- hsb: class-0 AFTER restore = 4 (labels52_v2 unchanged; no new restores; in-session untagged 2 stay -1).
  Unchanged.
- gvg: class-0 AFTER restore = 145 (labels52_v2 unchanged, frozen). Unchanged.
- rimrock: class-0 AFTER restore = 241 (labels52_v2 unchanged, frozen). Unchanged.

Hold-out-gvg training class-0 after the full restore: rimrock 241 + hsb 4 + adrian 26 + notus 6 = 277
(vs 245 before the restore; the not-a-shot signal is no longer rimrock-only).

### 1.3 New frozen labels file + sha

- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/review52/labels52a_class0_restore.json
- NEW file name (labels52_v2.json is NOT changed; a NEW labels file name is written).
- Same schema as labels52_v2.
- sha procedure: sha256 of the new frozen file is computed and frozen BEFORE any training; it is written
  to /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/pre52a_sha256.txt in the form:
      <sha256> *review52/labels52a_class0_restore.json
- Training must not start until that sha is frozen.

### 1.4 t_ms list source

- (i) adrian out-of-session restores: t_ms from the 48b dropped moments in
  /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/game_session_48b/adrian/session.json.
- (ii) adrian/notus far-from-tag restores: t_ms from labels52_v2 <film> t_ms (y=-1 rows) with
  min|t - coach_tag_t| >= 8000 ms; coach tags:
  /mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json
  and /mnt/c/Users/scott/Documents/liberty-basketball-analysis/data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json.

## Item 2 - Predict-time game-session filter (PINNED FIX, v2)

- Function: in_session / filter_moments in
  /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/shot_detectors/game_session.py (kept
  unchanged; spec 48 V9 behaviour).
- Per-film session source (48b outputs), paths fixed:
  - adrian: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/game_session_48b/adrian/session.json
  - notus: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/game_session_48b/notus/session.json
  - gvg: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/game_session_48b/gv/session.json
  - hsb: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/hybrid49/hsb/session/session.json
  - rimrock: no readable board / no 48b session output -> no change.
- When a film has no readable board (Riverstone-type case): no change (no filtering applied; the moments
  pass through unfiltered).
- Wiring pinned (v2): gate52's score_film calls ensemble_predict.shot_list(P, T, PM=PM); the session
  filter is applied inside ensemble_predict.shot_list driven by postproc52.json "session_filter" (True
  for the logo52a run); test_mm52.py asserts the filtered behaviour; the old postproc.py path is NOT the
  gate scoring path and is not used.
- Scoring pinned (v2): a filtered candidate is OMITTED from the shot list (not emitted; not scored as
  not-a-shot); a filtered real shot is simply missing -> counts against auto recall (unmatched truth) ->
  recall miss; a filtered non-shot reduces false shots / below-thr extras / checks.
- HSB miss t=2631233: out of session (gap 2624000-2712000, neither interval nor ft_window) -> expected
  recall loss; ACCEPTED IN WRITING in this pre-registration. Adrian/notus: 0/127 and 0/31 coach tags out
  of session (safe). GVG: 0 real shots out of session; ~175 non-shot/-1 candidates droppable.

## Item 3 - Unchanged

- R4 recipe; E=5; seeds 0 1 2; R6 thresholds; floor 0.2; checks cap 20. No other change.

## Item 4 - Flip intent (Muse)

- Train augmentation flip dims=[3] on (C,T,H,W); TTA flip dims=[4] on (B,C,T,H,W); both index the width
  axis, i.e. both are horizontal mirrors. No temporal flip intended.

## Item 5 - Run order and outputs

1. Rebuild clips from the new frozen labels; train logo with E=5 and seeds 0 1 2.
   python /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/train_clip.py logo <clips_dir> <out_dir> --films adrian notus gvg hsb rimrock --epochs 5 --seeds 0 1 2
2. Outputs: /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52a/
   - log.txt
   - logo_preds.npz
   - logo_report.json
   - gate52_report.json
3. Score with gate52.py exactly as logo52.
   python /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/mm_clip/gate52.py /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/runs/logo52a/logo_preds.npz \
   adrian=<tags.json> notus=<tags.json> gvg=<labels.json> hsb=<labels.json> rimrock=<labels.json>
4. Fail -> stop for Scott.

## Item 6 - Honest read + stop for Scott

- Whether the training change is expected to fix D1: YES in mechanism, NOT in certainty. The class-0
  restore adds multi-gym not-a-shot examples (gvg-held-out train pool: rimrock 241 + hsb 4 + adrian 26 +
  notus 6 = 277), addressing the D1 cause (not-a-shot learned almost only from rimrock; adrian/notus had
  ZERO class-0 rows). The re-gate is the test.
- Item 2 (predict-time session filter) is the main lever on the gvg checks (gvg 200 checks > hard cap 20;
  ~175 droppable non-shot/-1 candidates; 0 real shots out of session on gvg).
- A fail stops for Scott.

## Item 7 - Blind films available for later R10 (info)

- NOTUS_A, IDAHO_CITY, RIVERSTONE (all Liberty home gym). Riverstone: no readable board.

HERMES: SPEC WRITTEN
