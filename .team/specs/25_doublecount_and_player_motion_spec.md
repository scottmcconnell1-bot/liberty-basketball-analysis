DOUBLE-COUNT FIX + PLAYER MOTION SPEC v2 - run once 2026-11-02: part 1 v6+D1 29/0 (unchanged, pass), d2v1+D1 29/5 (39400 still a false make: its make moment is offset 60, before the cut at 62); part 2 measured, makes and misses overlap - stopped for Scott
VETTED by Claude Code, 2026-11-02: v1 reasons fixed; count 5/140 (all misses) and 0/18 Q4 measured by Claude Code (repo venv, load_build_shot_list + load_shot_tags); baselines checked against BASELINE_MAKES_RIGHT=28, d1_results 29/0, d2_results 29/5, q4_results 2/5 + 1; no tracking (per-frame only), only existing number 3.0; Q4 not run for part 1 (cannot change). Claude Code removed 3 leftover Q4 lines while stamping.

# PART 1 — Double-count fix (test-copy only, default-OFF switch)

## 1.1 Problem in plain words
The saved track for a shot contains up to 80 frames of ball/bodd points starting at the shot's tag time (collect_q4_bodd.py `v6_ball`, `range(80)`). When the NEXT tagged shot (2PT/3PT/FT, either team) occurs within those 80 frames, the current shot's track borrows the next shot's make frames. The miss at `t=39400` (0:39.4, 2PT Miss, 21 Colman) has D1 `anchor_frame=1045` (41.8 s, `anchor_reason="crossing"`); the next shot at `t=41900` (0:41.9, 2PT Make, 40 Dayley) has `anchor_frame=1048`. The 2.5 s gap (62.5 frames at 25 fps) means the miss's 80-frame window reaches into the next shot's make — the rule sees the next shot's ball falling through the rim and calls the miss a make.

## 1.2 Fix rule — exact definition
For each tagged shot in a film, compute the **cut frame offset**:

```
cut_offset = round((t_next - t) / 1000.0 * fps)
```

where:
- `t` = this shot's tag time (ms)
- `t_next` = tag time (ms) of the next shot in the **same film** whose `eventtype` ∈ {2PT, 3PT, FT} (any team), sorted by `t`
- `fps` = video FPS for this film (from `cv2.CAP_PROP_FPS`, fallback 25.0)

If no next shot exists in the film, `cut_offset = None` (no cut).

**Action**: before any decision logic runs, drop every ball/bodd point whose `frame_offset >= cut_offset`. This applies to:
- `decide_shot` (small_fixes_v6_copy.py) — the `ball` and `bodd` lists passed in
- `peak_from_track` (measure_net_moved.py) — the `track["ball"]` and `track["bodd"]` used to build `combined`
- Any future detector that reads the saved track

The fix **only removes frames**; it never adds or interpolates.

## 1.3 Where it plugs in (function names)
| Location | Function | What changes |
|---|---|---|
| `.team/shot_detectors/double_count_fix.py` | `apply_double_count_cut(track, cut_offset)` | Drops ball/bodd points with `frame_offset >= cut_offset`. Called from `keep_ball_detections.py` right after the result is stripped, in BOTH `step_extract` (before `peak_from_track` and `frames_to_extract`) and `step_arc_rule_report` / `run_arc_and_rule_on_shot`. |
| `.team/shot_detectors/keep_ball_detections.py` | `run_arc_and_rule_on_shot(...)` | Additive flag `--double-count-cut` (default off) applies the cut to the track right after result strip. Uses v6 weights and d2v1 best_basketball.pt. Re-extracts candidates into new folders under `C:/Users/scott/Documents/Liberty_Shot_Outputs/double_count/` — never over old files. |
| `.team/shot_detectors/small_fixes_v6_copy.py` | `decide_shot(track, ...)` | The cut is applied through the track passed in (no new `decide_shot` switch needed). |

**Mapping check**: use `--mapping-proof-json` with D1's `ball_arc/candidates.json` as before.

No edit to `pixel_miss/measure_net_moved.py`.

## 1.4 Switch / flag names
- `--double-count-cut` (bool, default `False`) — added to `keep_ball_detections.py` command line; when ON, applies `apply_double_count_cut` to the track right after result strip in both step_extract and step_arc_rule_report.

## 1.5 Tests (switch OFF = today's results exactly)
1. **Identity test**: `--double-count-cut=False` on all 140 build shots must produce byte-identical verdicts and reasons to today's runs (v6 plain, D1, fall-through guard).
2. **Hand-made pair**: synthetic two shots 2.5 s apart (62 frames at 25 fps) where the first is a miss with a long track that would reach the second's make frames. With `--double-count-cut=True`, the first shot's track is cut at frame 62; verify the false make disappears.
3. **Shot with no next shot**: a shot at the end of a film; `cut_offset=None`; track unchanged; verdict unchanged.

## 1.6 Count — how many of the 140 build shots have a next shot within 80 frames
**5 of 140 build shots have a next shot tag within 80 frames, ALL misses:**
- `notus_a1` 693500 (70 frames)
- `adrian` 39400 (62 frames)
- `adrian` 1600900 (75 frames)
- `adrian` 2417100 (52 frames)
- `adrian` 2753100 (2 frames)

Adrian Q4: **0 of 18** shots have a next shot within 80 frames.

## 1.7 One run — 140 build shots + Adrian Q4, current model (v6, D1) and d2v1
- **Current model (v6 + D1)**: run with `--double-count-cut=True` on the 140 build shots (re-extract with the flag ON).
- **d2v1** (`d2_train/runs/d2v1/weights/best_basketball.pt`): same run on the 140 build shots.
- **Pass criteria** (fixed now, no tuning after):
  - Build set, each model (v6+D1 and d2v1+D1): `misses_called_makes` must not rise and `makes_right` must not fall vs its baseline below.
  - For d2v1: report whether the 39400 false make is gone.
  - **Adrian Q4: NOT run for this fix**, because 0 of 18 Q4 shots have a next shot within 80 frames, so the fix cannot change any Q4 call.

**Baselines (measured):**
| Set | Model | makes_right | misses_called_makes |
|---|---|---|---|
| Build set | v6 plain rule | 28 | 0 |
| Build set | D1 (v6 + arc) | 29 | 0 |
| Build set | d2v1 + D1 | 29 | 5 |
| Adrian Q4 | v6 plain | 2 of 5 makes right | 1 (56:33.6) |

Source files: `keep_ball_detections.py` BASELINE_MAKES_RIGHT = 28; `ball_arc/d1_results.json`; `d2_train/test2/d2_results.json`; `q4_guard/q4_blind/q4_results.json`.

## 1.8 Untagged games (out of scope)
An untagged game has no tag file, so `t_next` cannot be computed from tags. Later, when a detector runs on untagged video, the **next DETECTED shot** will play the role of `t_next`. This is out of scope for this spec.

---

# PART 2 — Player motion measurement (measure only, changes no call)

## 2.1 Scope
- **140 build shots only** (Q1–Q3 from notus_a1 and adrian films, same as `net_moved_build_results.json`).
- Adrian Q4 is **NOT measured** in this step.
- Output **only** under `C:/Users/scott/Documents/Liberty_Shot_Outputs/player_motion/` — script refuses to overwrite if the directory exists and is non-empty.

## 2.2 Input per shot
- Shot moment = D1 `anchor_frame` from `keep_ball_detections.py` output (`d1_results.json` → `shots[i].anchor_frame`). If no D1 result exists for a shot, fall back to `tag_frame = round(t/1000*fps)`.
- Window = `[anchor_frame, anchor_frame + 3.0*s]` inclusive (i.e., `anchor_frame` to `anchor_frame + round(3.0*fps)`).
- Video: `film["video_rel"]` from `measure_net_moved.py` FILMS list.
- Hoop: `track["hoop"]` = `[hoop_x, hoop_y, hoop_w, hoop_area]`.
- FPS: from video `cv2.CAP_PROP_FPS` (fallback 25.0).

## 2.3 Per-frame processing
For each frame `fr` in the window:
1. Decode frame.
2. Run BODD model (`BODD_yolov8n_0001.pt`) on full frame, `conf=0.12`, `imgsz=960` (same as `collect_samples` in collect_q4_bodd.py).
3. Extract **player boxes** (class 2) and **hoop box** (class 1). Referees (class 3) excluded.
4. If **no hoop box** in this frame → skip frame, increment `hoop_missing_count`.
5. Hoop per frame = BODD hoop box nearest the previous frame's hoop, starting from `track["hoop"]`; none within 2 hoop widths of the previous → frame skipped and counted.
6. Use the **hoop center (hx, hy)** and **hoop width hw** from the detected hoop box **in this frame** (cancels camera pan).
7. For each player box: compute player center `(px, py)`, then distance to hoop `dist = sqrt((px-hx)^2 + (py-hy)^2)`.
8. Convert to **hoop-width units**: `dist_hw = dist / hw`.

**Players are NOT matched across frames** (that would be tracking; ByteTrack/DeepSORT are banned). Per frame only: distances of all player boxes to that frame's hoop, in hoop widths.

## 2.4 Measures (fixed now — no others)
`ZONE_HOOP_WIDTHS_H = 3.0` (from `keep_ball_detections.py`).

| Measure | Definition | Distance source |
|---|---|---|
| (a) `players_within_3hw` | Count of players with `dist_hw <= 3.0` in each frame; report **median** over the first 1.0 s and over the last 1.0 s of the 3.0 s window, and the **change** (last minus first). | `ZONE_HOOP_WIDTHS_H = 3.0` from `keep_ball_detections.py` |
| (b) `median_player_distance_hw` | Median player distance to hoop (in hoop widths) over all players in each frame; report median over the first 1.0 s and over the last 1.0 s of the 3.0 s window, and the **change** (last minus first). | Uses hoop-width units from frame's own hoop detection. |

**Per-shot output**: one JSON + one markdown table with:
- `shot_key`: `{film, t, quarter, label, player, gt_make}`
- `window_frames`: `anchor_frame` to `anchor_frame + round(3*fps)`
- `hoop_missing_frames`: count
- `frames_with_hoop`: count
- `players_within_3hw`: per-frame list + median_first1s, median_last1s, change
- `median_player_distance_hw`: median_first1s, median_last1s, change
- NO 2.0 number. NO threshold, NO rule.

## 2.5 Makes-vs-misses summary
After all 140 shots, write one JSON + one markdown table:

| Metric | Makes (median, min, max) | Misses (median, min, max) |
|---|---|---|
| players_within_3hw (first 1s) | | |
| players_within_3hw (last 1s) | | |
| players_within_3hw (change) | | |
| median_player_distance_hw (first 1s) | | |
| median_player_distance_hw (last 1s) | | |
| median_player_distance_hw (change) | | |

**NO threshold, NO rule, NO call change** — this is measurement only.

## 2.6 Output paths
```
C:/Users/scott/Documents/Liberty_Shot_Outputs/player_motion/
  {film}_t{t}_player_motion.json
  {film}_t{t}_player_motion.md
  summary_player_motion.json
  summary_player_motion.md
```
Script **refuses to run** if `player_motion/` exists and contains any file.

---

# PART 3 — Files, tests, who

## 3.1 New files (only under `.team/shot_detectors/`)
| File | Purpose |
|---|---|
| `double_count_fix.py` | Computes `cut_offset` per shot, provides `apply_double_count_cut(track, cut_offset)` helper. Tests: identity, hand-made pair, no-next-shot. |
| `measure_player_motion.py` | Runs BODD on 140 build shots' 3-second windows, computes measures, writes per-shot + summary JSON/MD. Tests: hoop-missing handling, known synthetic track, output directory refusal. |
| `test_double_count.py` | Pytest: identity (OFF == baseline), hand-made 2.5s pair, end-of-film shot. |
| `test_player_motion.py` | Pytest: hoop-missing frame skip, distance calc relative to per-frame hoop, summary stats. |

## 3.2 Test commands
```bash
# Double-count fix tests
python -m pytest .team/shot_detectors/test_double_count.py -v

# Player motion tests
python -m pytest .team/shot_detectors/test_player_motion.py -v
```

## 3.3 Review chain
1. **Claude Code** vets the plan and the code (does not plan or code).
2. **Muse (OpenRouter free models via `run_muse_or.sh`)** checks the Vetter: AGREE or DISAGREE with each VETTED/PASS; a DISAGREE stops the loop for Scott.
3. **Coder = Hermes** (Scott had Hermes code spec 24).
4. **Hermes and Muse** check the diff after coding.
5. **Claude Code** runs tests and the one run.

## 3.4 Branch
All team work goes on `team/auto` branch. Scott says when to push or merge.

---

# VERIFICATION CHECKLIST (Claude Code to fill)

| Item | Status | Value / Note |
|---|---|---|
| 1.6 Count of build shots with next shot < 80 frames | DONE | 5 (all misses); Adrian Q4: 0 of 18 |
| 1.7 Baseline makes_right (v6 plain, build) | DONE | 28 (0 misses called makes) |
| 1.7 Baseline makes_right (D1, build) | DONE | 29 (0 misses called makes) |
| 1.7 Baseline makes_right (v6 plain, Adrian Q4) | DONE | 2 of 5 makes right, 1 miss called make (56:33.6) |
| All file paths exist | PENDING | |
| BODD model classes confirmed {0:basketball,1:hoop,2:player,3:referee} | CONFIRMED | from prompt |
| Adrian video FPS | 25 | from prompt |
| Output directory refusal logic specified | YES | in 2.6 |

**Every fact above from a file read or the prompt; otherwise marked NOT FOUND - Claude Code to check.**