FIND SHOTS - MEASURE WHAT EXISTS SPEC v1 - run once 2026-11-03 (Cursor coded; 113 tests): detector rows (precision+rim_arc; 'tagged_gap' excluded as tag-derived) Adrian Q1-Q3 78/109 found, 106 extra; Adrian Q4 blind 7/18, 25 extra; Notus Q1 23/31, 31 extra; median timing 1.4-2.0 s. Scoreboard 43/43 Adrian makes (old 25 s pairing). Stopped for Scott.
VETTED by Claude Code, 2026-11-03, with conditions that OVERRIDE the body: (1) Do NOT rerun event_generator. Claude Code checked film_analysis.db (read-only): the AI shot finders' output is already stored - events rows source_type='ai', event_type='shot', details_json has 'generator' (e.g. 'precision', 'rim_arc') and 'peak_frame'. Adrian game_id '...__rerun_20261006_033941': 220 such rows (+9 whose details mention tags - EXCLUDE any row not carrying a 'generator' key); Notus 'jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334': 209. Measure these rows, open the DB read-only (sqlite uri mode=ro), grouped by generator and all together. Derived made_*/missed_* rows are NOT separate shots (they copy the 'shot' row). (2) Notus tags cover Q1 ONLY (31 shots, all quarter Q1) but the finder ran on the whole film: count extras for Notus only inside the Q1 span = first tag time - window .. last Q1 tag time + window; say so in the summary. Adrian tags cover all 4 quarters; Q4 = tags with quarter Q4 and finder rows in Q4's span, reported separately. (3) Window 8000 ms from MATCH_TOLERANCE_MS (manual_tag_teach.py) is allowed (existing code); because it is wide, ALSO report the matched timing error as median and max and a count of matches with |delta| <= 1000 ms, <= 3000 ms (reporting only, no decision). (4) Scoreboard rises: include only if a saved rises file exists (Liberty_Shot_Outputs/scoreboard/pairs_results.json); measured against MAKE tags only; else 'not measured'. (5) Tag time and events.timestamp_ms are the same film clock (Claude Code: tag 0:39.4 = timestamp_ms 39400 in the tagged game). Output dir Liberty_Shot_Outputs/find_shots (refuse if exists). No core file edit, no DB write.

This spec defines STEP 1 ONLY: measure every existing shot-finding method against Scott's manual tags. No new detector, no training, no tuning.

1. EXISTING SHOT FINDERS INVENTORY

For each finder: name, file+function, what it outputs, whether it runs on an UNTAGGED game (needs no manual tags).

| # | Finder name | File + Function | Output written | Runs untagged? | Notes |
|---|-------------|-----------------|----------------|----------------|-------|
| 1 | Precision shot pass | `event_generator.py` → `generate_precision_events_from_segments()` → `detect_shot_from_segment()` (primary + secondary) | Writes `event_type='shot'` rows to `events` table with `shot_result` make/miss + `details_json` (peak_frame, ball_rise, lateral_travel, shot_kind, through_rim, net_moved). Also writes `made_two`/`made_three`/`made_free_throw`/`missed_two`/`missed_three`/`missed_free_throw` rows derived from each shot. | YES | Opt-in via `ai.event_generator_mode = "precision"`. Uses possession segments + ball track. Two passes: primary (min_rise=80px, `live_shot_min_ball_rise`=170px) and secondary (relaxed, min_rise=10px, ball_y_threshold=550). Refractory: 6s per possessor, 4s global. |
| 2 | Expanded shot pass | `event_generator.py` → `generate_expanded_events_from_segments()` → `detect_shot_from_segment()` (primary + secondary) | Same event types as precision, but different thresholds and higher volume. | YES | Default mode (`expanded`). Primary: `min_ball_rise=10`. Secondary: `SECONDARY_MIN_BALL_RISE=10`, `SECONDARY_BALL_Y_THRESHOLD=550`. No refractory gating between shots. |
| 3 | Scoreboard rise finder | `.team/shot_detectors/scoreboard_pair_rises.py` → `find_rises()` | Returns list of confirmed score rises `{team, t, from, to, points}`. Does NOT write to DB. Used only for measurement/pairing (Stage C). | YES (needs scoreboard track) | Reads scoreboard track via `scoreboard_clock.py`. A "rise" = score value holds for 3 readable 1s samples. Rise time = FIRST sample showing new value. Proven 43/43 makes on Adrian (TEAM_RECOVERY.md). Only finds MAKES (score changes); misses = no rise. |
| 4 | `rim_arc_shots` | `event_generator.py` → `rim_arc_shots(ball_track, hoop_samples, min_rise=170, max_dist=280, cluster_ms=4000)` | Returns list of dicts: `{timestamp_ms, peak_frame, peak_x, peak_y, ball_rise, rim_distance}`. Does NOT write to DB. | YES (if called) | "Defined and not called" (BRAD.md, ACTIVE.md). Finds peaks where kept ball rises, falls, and is within 280px of hoop. On Adrian matches tagged shots AND moments with no tag (BRAD.md). |
| 5 | `run_saved_v6_rule` | `ai_bridge.py` → `run_saved_v6_rule(tag_timestamps, v6_tracks_path, homography_matrix)` | Returns dict: `{total_tags, right, makes_missed, misses_called_makes, results[], applied_to_core:false}`. Each result: `{tag_ts, true, pred, details}`. | NO | Make/miss CLASSIFIER only — requires tag timestamps as input. Scores on SAVED v6 tracks (ball+bodd+hoop). Not a shot-time finder. |
| 6 | `net_moved_after_shot` | `net_detector.py` → `net_moved_after_shot(frame_reader, peak_frame, hoop, rim_r)` | Returns bool (net moved = make). | NO | Make/miss CLASSIFIER only — requires peak_frame (shot time) as input. Called from precision pass after shot detected. |
| 7 | `ball_through_rim` | `court_memory.py` → `ball_through_rim(ball_box, hoop)` | Returns bool (ball through rim = make). | NO | Make/miss CLASSIFIER only — requires ball box at shot time. Called from precision pass. |
| 8 | Experimental detectors | `experiments/detect_v3.py` `find_shots()`, `experiments/detect_v5.py` `find_shots()`, `experiments/detect_shots_distance.py` | CSV outputs (`shots_v3.csv`, `shots_v5.csv`, etc.). Not integrated into pipeline. | YES (standalone) | Research-only. Not in production code path. |

Summary: Only finders #1, #2, #3, #4 can produce shot times on an untagged game. #3 only produces MAKE times (score changes). #4 is not called. #1 and #2 are the main production finders.

2. MEASUREMENT PROTOCOL

2.1 Films and Tags (Answer Key)

| Film | Tag file | Video | Shots (2PT/3PT/FT) | Quarters |
|------|----------|-------|-------------------|----------|
| Adrian | `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` | `uploads/nfhs_gam0a66d85e12.mp4` (25 fps) | 127 (111 Q1-Q3, 18 Q4) | Q1-Q4 |
| Notus A1 | `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` | `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` | 31 | Q1 only |

Tag loader: `.team/shot_detectors/pixel_miss/measure_net_moved.py` → `load_shot_tags()` (lines 73-97). Filters: `eventtype in {2PT,3PT,FT}`, `result in {Make,Miss}`, `quarter in {Q1,Q2,Q3,Q4}`.

2.2 Matching Window

One number fixed BEFORE the run. Sources in priority order:
- Existing code constant (name the line)
- If no constant exists: "Scott decides before the run" and propose one.

Candidate windows from code:
- `MATCH_TOLERANCE_MS = 8000` in `manual_tag_teach.py` (TEACH_ISSUE_ANALYSIS.txt line 36: "AI-detected shot event should only be rejected as a duplicate if there exists a MANUAL TAGGED SHOT within 8 seconds")
- `shot_refractory_ms = 6000` in `PRECISION_DEFAULTS` (event_generator.py line 712)
- `shot_global_refractory_ms = 4000` in `PRECISION_DEFAULTS` (line 714)
- `WINDOW_MS = 25000` in `scoreboard_pair_rises.py` (line 17) — shot t to shot t + 25s (for scoreboard rise pairing, not shot matching)

Proposed default: **8000 ms** (from `MATCH_TOLERANCE_MS`, the teach duplicate-rejection window). Scott confirms or overrides before run.

2.3 Matching Rule

- Each tag matches at most ONE finder shot (nearest within window).
- Each finder shot matches at most ONE tag (nearest within window).
- Greedy: sort all (tag, finder) pairs by absolute time difference, take closest first, remove both from pools, repeat.
- Unmatched tags = missed (false negatives). Unmatched finder shots = extra (false positives).

2.4 Per-Film and Per-Kind Reporting

For each film (Adrian Q1-Q3, Adrian Q4, Notus A1) and each shot kind (2PT, 3PT, FT), report:

| Metric | Definition |
|--------|------------|
| **Tagged** | Total tags of this kind in this film |
| **Found (Recall)** | Tags matched to a finder shot |
| **Extra** | Finder shots with no matching tag |
| **Timing error (ms)** | Median |tag_t - finder_t| for matched pairs |
| **Precision** | Found / (Found + Extra) |
| **Recall** | Found / Tagged |

Adrian Q4 (18 shots) reported SEPARATELY (blind test — never used to design).

2.5 Output Directory

`Liberty_Shot_Outputs/find_shots/` — script MUST refuse if directory already exists.

Outputs:
- `results.json` — full per-shot matching detail
- `summary.md` — short markdown table (per film × kind)

No DB writes.

3. NEW CODE

One script: `.team/shot_detectors/find_shots_measure.py`

Pure matching functions + CLI. Imports:
- `measure_net_moved.load_shot_tags` (tags)
- `event_generator.generate_precision_events_from_segments` (precision shots)
- `event_generator.generate_expanded_events_from_segments` (expanded shots)
- `scoreboard_pair_rises.find_rises` (scoreboard rises)
- `event_generator.rim_arc_shots` (arc shots, if hoop samples available)

Matching function (reusable, tested):

```python
def match_shots(tag_times: list[int], finder_times: list[int], window_ms: int) -> dict:
    """Greedy nearest-neighbor matching within window_ms.
    Returns: {matches: [(tag_t, finder_t, delta_ms)], unmatched_tags: [...], unmatched_finder: [...]}"""
```

Tests (hand-made times, no video):
- Exact match (delta=0)
- Inside window (delta < window)
- Outside window (delta > window)
- Two finder shots near one tag (closer wins)
- One finder shot near two tags (closer tag wins)
- Empty lists

4. ROLES & GATES

- Cursor codes the script + tests.
- Claude Code vets the plan and code (checks: no core edits, matching logic correct, window fixed before run, Q4 separate, output dir refusal).
- Muse checks the Vetter: AGREE or DISAGREE with each VETTED/PASS. A DISAGREE stops the loop for Scott.
- Scott reviews the summary table before any next step.

5. FACT SOURCES

Every fact above comes from a file read this session or the lines in the prompt. Otherwise: "NOT FOUND - Claude Code to check".

Key lines read:
- `event_generator.py:572-692` (`detect_shot_from_segment` primary/secondary)
- `event_generator.py:701-731` (`PRECISION_DEFAULTS`)
- `event_generator.py:790-1069` (`generate_precision_events_from_segments`)
- `event_generator.py:1125-1155` (`generate_expanded_events_from_segments`)
- `event_generator.py:1071-1122` (`rim_arc_shots` — "Not used to write shots")
- `ai_bridge.py:908-958` (`run_saved_v6_rule` docstring — make/miss classifier)
- `net_detector.py:514-523` (`net_moved_after_shot` — requires peak_frame)
- `scoreboard_pair_rises.py:46-74` (`find_rises` — scoreboard rise finder)
- `measure_net_moved.py:73-97` (`load_shot_tags`)
- `TEAM_RECOVERY.md:16,123,125` (scoreboard 43/43, Stage C/D1, make/miss coach review)
- `BRAD.md:20,44,52,65,81,83,97` (run_saved_v6_rule scores, rim_arc_shots not called, Q3 hoop track)
- `ACTIVE.md:35,45,55` (run_saved_v6_rule proven scores, Q4 blind test)
- `TEACH_ISSUE_ANALYSIS.txt:36` (8-second teach window)