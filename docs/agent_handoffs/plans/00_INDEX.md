# Phase plans — one file per step

Created: 2026-10-11. Source of truth for scope: `docs/agent_handoffs/PROGRAM_FOR_JASON_2026-10-10.md` (PR #168).
If a number in a plan file disagrees with that program file, the program file wins and the plan file is wrong — fix the plan.

**Where the source docs are.** `PROGRAM_FOR_JASON_2026-10-10.md`, `COUNT_FIXES_2026-10-10.md`, and `COUNT_ROADMAP_2026-10-10.md` are on branch `cursor/count-roadmap-2026-10-10` (PR #168), **not on `main`**. Until that PR merges, read them with `git show origin/cursor/count-roadmap-2026-10-10:docs/agent_handoffs/<file>` or from the PR. `ACTIVE.md`, `HERMES.md`, `AUTHORITY.md`, and `AGENT_PROTOCOL.md` are on `main`.

**Read `JASON.md` in the repo root too.** It is on `main`, it is 286 lines, and it is more specific than the PR #168 docs on what is actually wrong with run 12 — it names the individual shots, gives the per-stat baseline table, and carries operational do-nots the program file leaves out. Where it disagrees with `PROGRAM_FOR_JASON_2026-10-10.md`, the program file is newer and wins, but the detail in `JASON.md` is not repeated there and is not optional.

These files exist so one step can be handed to one agent without that agent reading the whole program.
Each plan is self-contained: it restates the do-nots that matter for that step, because an agent may read only its own file.

## The order

Steps 1–6 are the current job: count Adrian from the film and check it against Liberty 51, Adrian 26. Due 1 Nov 2026.
Steps 7–10 are the rest of the program. They wait on a ledger that matches a book. Do not start them early.

| Step | File | Depends on | Writes to the database? |
| --- | --- | --- | --- |
| 1 | `STEP_01_HOOP_ON_ORANGE_RIM.md` | — | No. Offline only. |
| 2 | `STEP_02_BALL_BOX_STAYS_ON_BALL.md` | — (parallel with 1) | No. Offline only. |
| 3 | `STEP_03_SCORE_THE_111_TAGS.md` | 1 and 2 | No. Offline only. |
| 4 | `STEP_04_WRITE_MISSING_TAGGED_SHOTS.md` | 3 must pass its bar | Yes. First step that does. |
| 5 | `STEP_05_COMPARE_CARD_TO_BOOK.md` | 4 | Read-only on run 12 |
| 6 | `STEP_06_NO_TIMESTAMP_LIST.md` | 5 | Yes, on a new run |
| 7 | `STEP_07_SHOOTER_TEAM_POINTS.md` | 6 | Yes |
| 8 | `STEP_08_REST_OF_BOX_SCORE.md` | 7 | Yes |
| 9 | `STEP_09_MINUTES_LINEUPS_POSSESSION.md` | 8 | Yes, plus schema (Scott gate) |
| 10 | `STEP_10_ASSISTANT_SECOND_GYM_PACKAGES.md` | 9 | Yes |

Steps 1 and 2 are independent of each other and can run as two agents at the same time.
Step 3 cannot start until both land, because it scores the rule that uses both.
Everything from 4 on is a single file of work at a time.

## Rules that apply to every step

These are from `AUTHORITY.md`, `AGENT_PROTOCOL.md`, and the program file. They are not optional and they are not restated in full in each plan.

**Roles.** Scott decides. Cursor implements and pushes. Hermes edits `ai_bridge.py` only, never the core, and nothing in the core calls `ai_bridge.py`. A Hermes proposal leaves as JSON with `applied_to_core` false until Scott accepts it.

**If the agent is Hermes** (`HERMES.md`, through the Architecture section — stop before "Where the Adrian count stands", which is the September 30 rerun and not the counting run):
- Stay in `ai_bridge.py`. Do not edit `ai_analyzer.py`, `event_generator.py`, `court_memory.py`, `net_detector.py`, `manual_tag_teach.py`, `game_boxscore.py`, or `scoreboard_clock.py`, and do not call `ai_bridge.py` from any of them.
- Data leaves the sandbox through `validated_stats()` as JSON. **Do not pass model objects across that boundary.**
- Do not run git, change git config, or delete `.git/hooks`. Do not claim a commit you did not make.
- Do not load `yolov8n.pt`. Do not call `validated_stats` on the game film. Do not restart Flask to load the adapter.
- A report lists what was run and what the output was.

**Stop and ask Scott** before: a `schema.sql` change, flipping a feature flag False to True, touching `models/ball_detector.pt` or `ball_confidence`, unpausing teach or auto-accept, deleting data or features, mass-deleting branches, or treating a close spelling as a known name.

**The core sequence is sequential. Do not reorganize it.** `ai_analyzer.py` → `event_generator.py` → `court_memory.py` / `net_detector.py` → `manual_tag_teach.py` → `game_boxscore.py` / `scoreboard_clock.py`.

**Data location.** Home owns `film_analysis.db` and the films. School uses Funnel only (`https://liberty-coach.tail368a37.ts.net`). Do not overwrite the home database from school. The database, the films, and the offline weights are **not in git**. A pull does not bring them.

**A manual tag is truth.** `MATCH_TOLERANCE_MS = 8000` (`manual_tag_teach.py:18`). A tag within 8 seconds grades a machine row and the tag wins. An unmatched tag is **not** inserted as a make. Do not widen the window. Do not ask Scott to accept or reject his own tags.

**Make/miss contract.** A make is `ball_through_rim` or `net_moved_after_shot`. Both false is stored as a **miss**. There is no "unknown". Scott kept this on 2026-10-07. Points: made two 2, made three 3, made free throw 1, a shot row by itself 0. Counted review statuses: accepted, corrected, pending. Rejected drops off the card.

**The NFHS counting rules (Scott, 2026-09-15)** live in the **Standing facts** section of `ACTIVE.md`, not in a separate document. They are the spec for step 8 and are quoted in full there.

**Names.** Dayley, Daley, and Daly are one Liberty player, number 40, roster name Daly. Liberty has no 2 and no 6. Foster number 22 is Adrian. Liberty number 3 is Kariuki. **A cluster id of 3 is not Kariuki.** Ask Scott before treating any other close spelling as the same person.

**Colors on this camera.** The rim is orange. The ball is brown-orange. The net is white and cone-shaped. The exit sign above the door is the only red object. Older notes that say "red" mean an OpenCV hue bin on this camera, not the paint.

**Do not resume these finished agents.** A resume puts the chip back on "Starting up".
`a4e6aae5-7ad7-48e0-a657-0faf69984c15`, `5cb51e6b-92f6-4927-8332-2bbc4dae58c3`, `666207e1-46d2-4d32-89b7-39d86bd2de44`, `62491ff3-e01c-42dd-b52e-9238c4113df3`.

**Never do these, at any step.**
- Copy Scott's tags or the book onto detector rows. Nine tag-copy rows were already added for shots with no detector row. Those are not detector results. Do not add more.
- Turn on `rim_arc_shots` (`event_generator.py:1071`). It is written and deliberately not called.
- Change `models/ball_detector.pt` or `ball_confidence`.
- Train another ball-weights file of the same kind and call it the fix. v1 through v6 were tried. v6 put more boxes on the ball in the net and the count did not move.
- Merge `Scott_Hermes` commit `6143e83`, or treat `cbeb0ed` on PR #168 as step 1 or step 3. Both are analysed in `COUNT_FIXES_2026-10-10.md` section 4.
- Treat the bottom of `HERMES.md` ("Where the Adrian count stands") as the counting run. That is the September 30 rerun.
- **Open `GET /api/analysis/<game_id>` for this game** (`blueprints/ai.py:809`). **That request rewrites identity rows.** Read the `events` table directly, or the HTML results page. This is the easiest way for an agent to silently corrupt the run it is measuring.
- Merge **pull request 147** ("Re-enable auto-accept (0.85) for full-stack bring-up", open as of 2026-10-11). It turns auto-accept on at 0.85 and Scott has not approved that.
- Start the **teach loop**.
- Use **video 64**. The film is **video id 73**, `uploads/nfhs_gam0a66d85e12.mp4`.
- Commit the untracked GitHub credential file in the repo root, or paste it into a note.

## The run under test

| Thing | Value |
| --- | --- |
| Game id | `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334` |
| Counting run | `...__rerun_20261006_033941` ("run 12"), home database only |
| Film | `uploads/nfhs_gam0a66d85e12.mp4` |
| Book | Liberty 51, Adrian 26 (77 points) |
| Scott's tags | 111 shot tags: 38 makes, 73 misses |
| Tags through Q3 | Liberty 43, Adrian 24 — matches the book |
| Q4 | Not tagged (one Start QTR at 56:26.7 is the inbound). Remainder is Liberty 8, Adrian 2. |
| Quarter ends | Q1 16:00.7, Q2 32:15.0, Q3 55:17.1 |
| Video id | **73**. Not 64. |
| Tag file | `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` — 378 rows, of which 111 are shot tags. **Not in git** (`data/film_tags/` holds only a `.gitkeep`). Home machine only. |
| History copies | `data/film_tags/_history` — one every 2 min while tags change, newest 120 in full, then hourly for 72 h |
| Confirmed book | `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` — **this one is in git** |
| Review exports | `tag-exports/` — Q1 and Q2 shot reviews, before-states, hoop probe images. **In git.** The test set for steps 4 and 7. |
| Tags with no AI row | **22 of 111** (6 makes, 16 misses); 9 of them in Q3; 17 of the 22 are within 280px of the median rim |
| Hoop track | runs to 64:56, 1,949 raw samples, ±3-sample median |
| Run 12 shot rows | 206 |
| Run 12 event count | 1,452 (2026-10-06), 1,509 (2026-10-08 night) |

### Run 12 point totals move — know which number you are looking at

`JASON.md` contains several non-rejected make-point totals from different nights. They are a sequence, not a contradiction. Quoting the wrong one makes a step look passed or failed when it is neither.

| Points | When | What changed |
| --- | --- | --- |
| 64 | 2026-10-06 snapshot | the original run 12 count |
| 76 | 2026-10-07 | seven tagged makes restored when `reconcile_makes_with_shots` stopped rejecting corrected rows |
| 59 → 43 | 2026-10-08 | Q2 review rejected all 27 extra AI shots, and between-quarters shots were rejected |
| **49** | **2026-10-08 night** | **current.** The locked-hoop ball-box change wrote six misses; his tags graded five of them, three were makes (43 → 49). 14 twos, 5 threes, 6 free throws. |

**49 is the number to re-measure against.** It is not an accuracy claim. The book is 77.

Two more small discrepancies, neither load-bearing — just do not treat either as a regression:
- **Run 12 event count**: `ACTIVE.md` says 1,503 after the 2026-10-08 steal and foul write (was 1,452); `JASON.md` says 1,509. Re-query rather than quoting.
- **"The 79 unmatched tags stay unmatched"** is a standing decision in `ACTIVE.md`. That 79 is all unmatched manual tags of every type, **not** the 22 shot tags with no AI row. Do not conflate them.
| Best offline make/miss | 85 right, 20 makes missed, 6 misses called makes. **Not turned on. No rows written from it.** |

## Before you run the test suite

Known baseline from the last full run (`JASON.md`, 2026-10-07 night), which took **26 minutes**:

**1,046 passed, 9 failed, 1 skipped, 25 errors.**

Almost all the failures are `tests/test_transfer_bundle.py`, which builds a bundle with `bash`. On Scott's Windows machine that build does not succeed, so the whole group fails together. **Those failures are environmental and are not yours.** Do not spend a session chasing them, and do not report them as a regression.

An earlier report of a test-suite hang was incomplete — a second copy of the run was stopped and has no result. **It is not established that a test deadlocked.**

## An open task that is not one of the ten steps

Scott asked for the **self-check to be run again**. `JASON.md`: "It is not finished." That is a live request, outside the step 1–10 roadmap, and it is not covered by any plan in this directory. Do not let it fall off the list — raise it with Scott rather than assuming the roadmap replaced it.

## What the author of these plans could not check

These plans were written on 2026-10-11 from `PROGRAM_FOR_JASON_2026-10-10.md` (PR #168), `JASON.md`, `ACTIVE.md`, `HERMES.md`, and the source code. **Every number in them is quoted from those documents. None was re-measured**, because the things that would measure it are not in git.

**Not in the repo — so nothing depending on them is Proven here:**

| Missing | What that makes unverified |
| --- | --- |
| `film_analysis.db` (home PC, ~379 MB) — no `.db` file anywhere in the tree | Every run-12 figure: 1,452 / 1,503 / 1,509 events, 206 shot rows, 49 make points, the per-player lines, the 22 tags with no AI row, the per-quarter make counts, the 132-of-170 rebounds, the steal and foul counts |
| The film — `uploads/` is empty, `nfhs_gam0a66d85e12.mp4` (video 73) is absent | **Every frame claim.** 896600, 1776500, 1515700, 2455600, 755400, 856200, 280200, and the whole Q3 stretch. No frame in these plans was opened. |
| `data/film_tags/<game id>.json` — the directory holds only `.gitkeep` | The 378 tag rows and the **111 shot tags themselves**. The grader for steps 3, 4, 7 and 8 is not here. |
| `data/film_tags/_history` | The dated tag copies |
| v6 weights (`ball_net_runs\v6\weights\best.pt`, Windows Temp), `v6_tracks.json`, the BODD public model | Every row of the try table, including the 85 / 20 / 6 best score |
| `tag-exports/rejected_makes_before_restore_20261007.json` | Cited in `ACTIVE.md`; **checked and not present.** Probably home-machine-only. |
| The passphrase for `encrypted-archive/liberty_adrian_detections_20261007.enc` | The archived detections |
| HUDL teach state | — |

**Present and usable, which is more than the handoffs imply:**

- All source, tests, and `scripts/`.
- `models/ball_detector.pt` — **165 MB of real weights via LFS, not a pointer.** The production detector is here. It is still a Scott gate; do not change it.
- `models/court_keypoint_detector.pt` (399 MB), `court_fp_classifier.pt`, `_v2`.
- `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` — **the confirmed book is in git.**
- `models/film_tool_jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` — a teach calibrator derived from the tags: 44 `shot_label_anchors` with `shot_type` and `shot_result`, 92 `positive_windows`, 92 `supervised_templates`. **`window_end_ms` is 960700 — 16:00.7, the Q1 end, so this is Q1 only.** It is a useful slice, not a substitute for the 111 tags.
- `tag-exports/` — the Q1 and Q2 shot-review CSVs, both before-state JSONs, `jrhigh_adrian_q1_manual_tags.json`, and the hoop probe images.
- `data/hoopsalytics/` — `full_film_panel_latest.json`, `full_film_panel_history.jsonl`, `full_film_panel_targets.json`, and a `TEACH_LOOP_PAUSED` marker.
- `data/jersey_shades/` — 6 files including the run-12 sidecar.

**What this means for an agent picking up a step:** the plans are a map, not a measurement. Treat every quoted number as the last recorded value and re-measure it on the home machine before you act on it. The first task of each step is to confirm its own starting numbers are still true.

## Report format — every step, every agent

From `AUTHORITY.md`. Chat memory is not repository truth.

```markdown
### Proven
(a command, a query, a file, or a frame was checked in this session — say which)

### Inferred
(reasonable conclusions)

### Unknown
(not yet verified)
```

A fix is **not Proven** until it was run against the real thing it fixes — the live film, the live page, the real database read-only. A passing unit test alone is not verification.

When a step completes, replace the paragraph it changes in `ACTIVE.md`. Do not stack a new Proven paragraph on top of one it contradicts. Move old text to `ARCHIVE/`.

## One open discrepancy, found 2026-10-11

The program file and the roadmap both say "the 170-pixel rise". There are **two** rise gates in `event_generator.py`, not one:

- `shot_min_ball_rise: 80.0` (line 707), applied in the primary shot pass at line 832
- `live_shot_min_ball_rise: 170.0` (line 710), applied to live field goals at line 946

A tagged shot that never becomes a row may be dropped at the 80px primary gate, before the 170px live gate is ever reached. Any step-4 work that reasons only about "the 170" is reasoning about the second gate of two. `adrian_quality.py:45` has a third, separate `MIN_SHOT_BALL_RISE = 120.0` on the quality-pass path.

This is a documentation gap, not a decision. Confirm with Scott which gate he means before changing either.
