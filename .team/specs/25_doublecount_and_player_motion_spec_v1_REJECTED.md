REJECTED by Claude Code, 2026-11-02 (v1): wrong baselines (1.7), Q4 pass test meaningless, plug-in edits a pixel_miss file and skips re-extract, player measures (b)/(c) need player identity across frames = tracking (ByteTrack/DeepSORT banned), new 2.0 number. Fixes in prompt_hermes_doublecount_players_v2.txt.
DOUBLE-COUNT FIX + PLAYER MOTION SPEC v1 - not run

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
| `.team/shot_detectors/small_fixes_v6_copy.py` | `decide_shot(track, ..., switch_double_count=False)` | At line 193–194, after `ball = track.get("ball", [])` and `bodd = track.get("bodd", [])`, filter both lists by `pt[0] < cut_offset` if `switch_double_count` and `cut_offset` is not None. |
| `.team/shot_detectors/pixel_miss/measure_net_moved.py` | `peak_from_track(track, t_ms, fps)` | At line 162–163, after `ball = list(track.get("ball") or [])`, filter `ball` and `bodd` before building `combined`. |
| `.team/shot_detectors/keep_ball_detections.py` | `run_arc_and_rule_on_shot(...)` | At line 695, after `track_no_truth = {...}`, filter `track_no_truth["ball"]` and `track_no_truth["bodd"]` before `peak_from_track` and before `decide_shot`. |

The `cut_offset` is computed **once per shot** from the film's ordered shot list and passed in (or looked up by `(film, t)`).

## 1.4 Switch / flag names
- `switch_double_count` (bool, default `False`) — added to `decide_shot` signature and to the `run_copy_on_shots` call chain in small_fixes_v6_copy.py
- `double_count_cut` (dict mapping `(film, t)` → `int` or `None`) — precomputed once per run, passed to the three functions above

## 1.5 Tests (switch OFF = today's results exactly)
1. **Identity test**: `switch_double_count=False` on all 140 build shots + Adrian Q4 must produce byte-identical verdicts and reasons to today's runs (v6 plain, D1, fall-through guard).
2. **Hand-made pair**: synthetic two shots 2.5 s apart (62 frames at 25 fps) where the first is a miss with a long track that would reach the second's make frames. With `switch_double_count=True`, the first shot's track is cut at frame 62; verify the false make disappears.
3. **Shot with no next shot**: a shot at the end of a film; `cut_offset=None`; track unchanged; verdict unchanged.

## 1.6 Count — how many of the 140 build shots have a next shot within 80 frames
**NOT FOUND - Claude Code to check**. Compute by: for each of the 140 build shots (from `net_moved_build_results.json`), find `t_next` in the same film's tag list; if `round((t_next - t)/1000*fps) < 80`, count it. Report the number in the spec after verification.

## 1.7 One run — 140 build shots + Adrian Q4, current model (v6, D1) and d2v1
- **Current model (v6 + D1)**: run with `switch_double_count=True` on the 140 build shots and Adrian Q4 (18 shots).
- **d2v1**: when the d2 detector exists, same run.
- **Pass criteria** (fixed now, no tuning after):
  - `misses_called_makes == 0` (hard gate)
  - `makes_right >= today's makes_right` for that model on that set
    - Build set today (v6 plain): 20 makes right (from q4_guard summary: v6_plain makes_right=2 on 18 Q4 shots; build set from small_fixes_v6_copy baseline: need to read — **NOT FOUND - Claude Code to check**; use the actual measured baseline from the identity run)
    - Adrian Q4 today (v6 plain): 1 make right (from q4_results.json)
    - Build set today (D1): **NOT FOUND - Claude Code to check** (run keep_ball_detections.py step arc-rule-report without fall-through guard)
    - Adrian Q4 today (D1): **NOT FOUND - Claude Code to check**

Record the exact baseline numbers here after the identity run; the pass line uses those fixed numbers.

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
3. Extract **player boxes** (class 2) and **hoop box** (class 1).
4. If **no hoop box** in this frame → skip frame, increment `hoop_missing_count`.
5. Use the **hoop center (hx, hy)** and **hoop width hw** from the detected hoop box **in this frame** (cancels camera pan).
6. For each player box: compute player center `(px, py)`, then distance to hoop `dist = sqrt((px-hx)^2 + (py-hy)^2)`.
7. Convert to **hoop-width units**: `dist_hw = dist / hw`.

## 2.4 Measures (fixed now — no others)
Choose distances **only from numbers already in the code** (name the line) or state as **Scott-decided-in-advance**:

| Measure | Definition | Distance source |
|---|---|---|
| (a) `players_within_2hw` | Count of players with `dist_hw <= 2.0` in each frame; report **median** over window. | `2.0` — **Scott-decided-in-advance** (no existing constant at exactly 2.0; `ZONE_HOOP_WIDTHS_H=3.0` in keep_ball_detections.py:29 is 3.0; `0.55` crossing tolerance in small_fixes_v6_copy.py:218; `0.6` column in :303; `0.85` rim in :467). |
| (b) `avg_distance_change_hw` | For each player present in ≥2 frames: compute `dist_hw` at first and last frame they appear; `change = last - first` (negative = toward, positive = away). Average over all such players in the window. | Uses hoop-width units from frame's own hoop detection. |
| (c) `players_away_count` / `players_toward_count` | Count of players with `change > 0` (away) vs `change < 0` (toward). Players with `change == 0` ignored. | Same as (b). |

**Per-shot output**: one JSON + one markdown table with:
- `shot_key`: `{film, t, quarter, label, player, gt_make}`
- `window_frames`: `anchor_frame` to `anchor_frame + round(3*fps)`
- `hoop_missing_frames`: count
- `frames_with_hoop`: count
- `players_within_2hw`: per-frame list + median/min/max
- `avg_distance_change_hw`: single number
- `players_away_count`, `players_toward_count`: integers
- `player_tracks`: list of `{first_frame, last_frame, first_dist_hw, last_dist_hw, change_hw, direction}`

## 2.5 Makes-vs-misses summary
After all 140 shots, write one JSON + one markdown table:
| Metric | Makes (median, min, max) | Misses (median, min, max) |
|---|---|---|
| players_within_2hw | | |
| avg_distance_change_hw | | |
| players_away_count | | |
| players_toward_count | | |

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
| `double_count_fix.py` | Computes `cut_offset` per shot, provides `apply_double_count_cut(track, cut_offset)` helper, adds `switch_double_count` to `decide_shot` (or wraps it). Tests: identity, hand-made pair, no-next-shot. |
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
2. **Muse (GLM via OpenCode)** checks the Vetter: AGREE or DISAGREE with each VETTED/PASS; a DISAGREE stops the loop for Scott.
3. **Scott** names the coder (OpenCode / DeepSeek).
4. **Hermes and Muse** check the diff after coding.

## 3.4 Branch
All team work goes on `team/auto` branch. Scott says when to push or merge.

---

# VERIFICATION CHECKLIST (Claude Code to fill)

| Item | Status | Value / Note |
|---|---|---|
| 1.6 Count of build shots with next shot < 80 frames | PENDING | |
| 1.7 Baseline makes_right (v6 plain, build) | PENDING | |
| 1.7 Baseline makes_right (D1, build) | PENDING | |
| 1.7 Baseline makes_right (v6 plain, Adrian Q4) | 1 | from q4_results.json |
| 1.7 Baseline makes_right (D1, Adrian Q4) | PENDING | |
| All file paths exist | PENDING | |
| BODD model classes confirmed {0:basketball,1:hoop,2:player,3:referee} | CONFIRMED | from prompt |
| Adrian video FPS | 25 | from prompt |
| Output directory refusal logic specified | YES | in 2.6 |

**Every fact above from a file read or the prompt; otherwise marked NOT FOUND - Claude Code to check.**