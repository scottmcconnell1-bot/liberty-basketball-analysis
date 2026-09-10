# AI Analysis Quality — Measured Baseline (2026-09-10)

Branch: `claude/local-standup` · Machine: Linux workstation, CPU-only · Reporting: Proven / Inferred / Unknown

## Why this document exists

Before this, "is the AI analyzing the film correctly?" had no reproducible answer on the
default branch. The measurement instrument existed but was split: the scorer
(`scripts/score_manual_q1_regression.py`) and matcher (`tag-exports/manual_vs_ai_q1_compare.py`)
were on `jason-5-may-updates`, while the **ground truth** — Scott's hand-tagged Wilder Q1
(`tag-exports/liberty-manual-tags-backup.json`) — only existed on the unmerged July branch
`cursor/film-tool-reports-fix-ac1f` (commit `3749831`). The scorer also had three latent bugs
that made it unrunnable from a clean checkout (§4).

This document records the instrument, the number it produces today, and what the number means.

## 1. The instrument (Proven)

| Piece | Where | Notes |
| --- | --- | --- |
| Ground truth | `tag-exports/liberty-manual-tags-backup.json` | 71 manual Film Tool tags for **Wilder Q1**, game id `game-1784304093435`, exported 2026-07-18. 66 after Q1 filter; 53 are "action" tags (`2PT 3PT FT Assist Block DefRebound OffRebound Foul Steal Turnover`). Extracted with `git show 3749831:…`; no July code merged. |
| Footage | `videos/Q1.mp4` (LFS, 184,343,135 B, 906 s) | **Verified to be the Wilder Q1**: duration matches the 14:31 compare window and the frame at t=60 hashes identically to `data/videos/Q1_snippet.mp4`, which is its first 300 s. |
| Matcher | `tag-exports/manual_vs_ai_q1_compare.py::event_level_match` | Greedy nearest-neighbour, **±10 s**, pass 1 exact type+result (`2PT|Make`, `Rebound`, `Steal`…), pass 2 same coarse family → "near/wrong". AI `make`/`miss`/`possession_change` rows are dropped; `shot` rows carry the result. |
| Scorer | `scripts/score_manual_q1_regression.py` | Now runs from a clean checkout; new `--window-end-sec`, `--per-tag`, per-type breakdown, and a chance-match estimate. Tests: `tests/test_score_manual_q1_regression.py`. |

Run it:

```bash
# 5-minute snippet window (any analysis of data/videos/Q1_snippet.mp4)
.venv/bin/python scripts/score_manual_q1_regression.py --analysis-key <key> --window-end-sec 300 --no-fail --per-tag
# full Q1 (an analysis of videos/Q1.mp4)
.venv/bin/python scripts/score_manual_q1_regression.py --analysis-key <key> --no-fail --per-tag
```

## 2. Result — first 300 s, strict matching (Proven)

Analysis `smoke_q1_local` (CLI `ai_analyzer.py` on the snippet, default settings, CPU, 1,038 s wall-clock):

| Metric | Value |
| --- | ---: |
| Manual action tags in window | **13** |
| AI raw events in window | 1,374 |
| AI comparable rows (after dropping make/miss/possession_change) | **754** |
| True positives (exact type+result, ±10 s) | 8 |
| AI extras — false positives | **744** |
| Manual tags missed | 3 |
| Near but wrong label | 2 |
| **Precision** | **0.0106** |
| **Recall (strict)** | 0.6154 |
| Recall (loose, counts near/wrong) | 0.7692 |
| F1 | 0.0209 |
| AI comparable rows per second | 2.51 |
| Expected same-key candidates inside ±10 s for a random tag | **~50** |

Per manual tag type — matched / near-wrong / missed: `2PT 3/0/0 · Assist 2/0/0 · DefRebound 1/0/0 · Steal 1/0/0 · Turnover 1/0/0 · 3PT 0/2/0 · Foul 0/0/3`.

Every manual tag, with the AI verdict:

| t | Manual | Verdict | AI said |
| ---: | --- | --- | --- |
| 34.3 s | 3PT Miss (Opp #1) | NEAR/WRONG | 2PT Make, Δ0.7 s |
| 37.6 s | Def Reb (#15) | MATCH | Δ1.4 s |
| 40.7 s | 2PT Make (#11) | MATCH | Δ0.5 s |
| 40.7 s | Assist (#15) | MATCH | Δ3.6 s |
| 94.8 s | Foul (#10) | **MISSED** | — |
| 126.7 s | Steal (#10) | MATCH | Δ3.7 s |
| 126.7 s | Turnover (Opp #4) | MATCH | Δ3.7 s |
| 130.8 s | 2PT Make (#10) | MATCH | Δ2.8 s |
| 158.9 s | 3PT Miss (Opp #2) | NEAR/WRONG | 2PT Make, Δ0.6 s |
| 179.7 s | Foul (Opp #2) | **MISSED** | — |
| 202.0 s | 2PT Make (#2) | MATCH | Δ0.7 s |
| 202.0 s | Assist (#11) | MATCH | Δ0.7 s |
| 291.1 s | Foul (#4) | **MISSED** | — |

### How to read this (Inferred)

- **Precision ≈ 1% is the headline.** 99 of every 100 AI suggestions are noise. At this rate
  the Review queue receives ~1,350 items per 5 minutes of film (~9,000 per game), which no
  coach can review; the product's "AI suggests, human accepts" loop cannot start.
- **The recall figure is mostly chance.** With 2.5 comparable AI rows per second, a random
  manual tag has ~50 same-family AI rows inside ±10 s. Recall cannot be evaluated honestly
  until precision rises by at least an order of magnitude. Do not quote 62% recall.
- **The two 3PT misses became "2PT Make"** — type and result both wrong. Cause (Proven):
  AI `shot` events carry `details_json = {ball_rise, lateral_travel, peak_frame}` with **no
  `shot_type`**, so the matcher's default of `2PT` applies to every AI shot. Separately,
  `film_analysis.py::classify_shot_type` writes `shot_classifications` (528 of 578 as `3pt`
  for this clip — implausible for junior-high film) keyed by `event_id`, but neither the
  events row nor the matcher reads it. Two subsystems disagree and the comparison sees neither.
- **All three fouls were missed.** The pipeline emitted one `foul` in five minutes.
- These numbers are **consistent with Scott's own baseline** recorded in the scorer
  (`BASELINE`: precision 0.008, recall 0.415, 22 exact / 2,726 AI-only over the full 871 s).
  The instrument reproduces across machines; the problem is the pipeline, not the measurement.

## 3. Full-quarter result (videos/Q1.mp4, 871 s window)

_Pending — `wilder_q1_full_local` analysis running on CPU; this section is filled in when it
completes. Compare against `BASELINE` in the scorer._

## 4. Bugs fixed in the instrument (Proven)

`scripts/score_manual_q1_regression.py` was moved from `tag-exports/` to `scripts/` at some
point without updating three relative references, so it could not run from a clean checkout:

1. `load_manual_rows` queried `film_tool_games` and crashed with `OperationalError` on any DB
   that never had that table (it exists only on the July branch) → now falls back to the JSON.
2. `BACKUP_PATH` pointed next to the script → now `ROOT/tag-exports/…`.
3. `sys.path` insert for `manual_vs_ai_q1_compare` was script-relative → now `ROOT/tag-exports`.

Plus: `--window-end-sec`, `--per-tag`, `per_type` breakdown, chance-candidate estimate,
docstring usage corrected, and three tests.

## 5. Where the errors come from (Proven on this clip; see `docs/agent_handoffs/LOCAL_STANDUP_2026-09-09.md` for images)

1. **Detection recall** on this fixed wide-angle 720p camera is roughly half: at t=60 the
   person detector boxed ~5 of 11 people, with false boxes on empty floor and the centre logo.
   Ball found at ≥0.25 confidence in **12.4%** of frames.
2. **Tracking fragments**: 1,036 tracker IDs for ~13 people in 5 minutes. The "10 players" in
   `player_minutes` are clusters, not identities; jersey OCR read 0 numbers (EasyOCR absent).
3. **Event heuristics amplify**: every possession change → a shot/rebound/block cycle;
   constant per-type confidences (`shot .52, make .40, miss .45, block .32, assist .28`);
   a "make" at 6.5 s during the opening jump ball.

## 6. What the unmerged July branch adds (Inferred from commit contents; not run here)

`cursor/film-tool-reports-fix-ac1f` contains the *learning* half of this loop: persisting
manual tags to the DB (`film_tool_games`), an in-app manual-vs-AI report, `event_calibrator.py`
+ `scripts/teach_from_manual_q1.py` ("teach AI event labels from manual Q1 ground truth"), and a
regression score file. Its own `manual_q1_regression_score.json` should say what precision it
reached after calibration — **Unknown** until someone checks out that branch and re-runs the
scorer with the same tolerance. That comparison is the natural next experiment.

## 7. Recommended order of work (Inferred)

1. **Make precision the gate.** The scorer's `MIN_PRECISION` is 0.08; today's is 0.01. Nothing
   ships to the Review queue until this passes. Run the scorer on every pipeline change.
2. **Fix the event layer's suppression first, not the detector.** Precision is dominated by
   heuristic over-firing (754 comparable rows for 13 real events). Rate-limiting shot/rebound
   cycles per possession and dropping constant-confidence emissions would cut FP by >10×
   without touching models. The July `event_calibrator` is a candidate implementation.
3. **Link shot type.** Carry `shot_classifications.shot_type` into the event (or the matcher);
   then fix `classify_shot_type`'s 3-pt threshold against the manual 3PT/2PT split.
4. **Then detection.** Recall ~50% on people and 12% on the ball caps what any event logic can
   do. Ground truth for detection exists (`benchmark/`, `dataset-v2` branch). Camera-specific
   fine-tuning of the person/ball detectors is the long pole.
5. **Fouls are a separate problem** — 0 of 3 found; there is no whistle/ref-signal path in
   the pipeline (an `experiments/detect_referee_signals.py` exists, unwired).

Every item above is a product/priority decision for Scott; nothing here changes pipeline
behaviour. The only code changed for this document is the scorer (§4).
