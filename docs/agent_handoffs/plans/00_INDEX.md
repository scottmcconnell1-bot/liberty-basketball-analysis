# Phase plans — one file per step

Created: 2026-10-11. Source of truth for scope: `docs/agent_handoffs/PROGRAM_FOR_JASON_2026-10-10.md` (PR #168).
If a number in a plan file disagrees with that program file, the program file wins and the plan file is wrong — fix the plan.

**Where the source docs are.** `PROGRAM_FOR_JASON_2026-10-10.md`, `COUNT_FIXES_2026-10-10.md`, `COUNT_ROADMAP_2026-10-10.md` and `HERMES_EXPERIMENT_2026-10-09.md` sit in `docs/agent_handoffs/` **on this branch**, copied from PR #168 because every plan below cites them and that pull request cannot merge (see the do-not). `ACTIVE.md`, `HERMES.md`, `AUTHORITY.md`, and `AGENT_PROTOCOL.md` are on `main`.

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

**Auto-accept is on, at 0.85, and that is deliberate.** Scott confirmed it on 2026-10-11 evening. Two things follow for every step below. First, a run you measure may contain rows that were promoted from `pending` to `accepted` with no human looking at them, so "accepted" does not mean "Scott saw it". Second, the comment at `review_actions.py:197` still reads "Threshold 0 (default) fully disables auto-accept" — the default in `settings_store.py:30` is `0.85`, not `0`. Believe the stored setting, not the comment. Changing the number in either direction is a Scott gate, and `scripts/check_scott_gates.py` blocks it unless the pull request body names it.

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
- Merge `Scott_Hermes`. Not the branch and not commit `6143e83`. Six of its rules were scored on the 111 tags and all six lost: 71/32/8, 66/37/8, 73/38/0, 73/38/0, 72/34/5, 75/36/0 (`HERMES.md`, 2026-10-11). Three of those six score at or below the 73 you get by calling every shot a miss. Do not resubmit any of them: the column under the rim, a frame-to-frame jump called 0.45, drift used as the whole make, a farthest-point substitute for 180 px, or a last-box depth check. Also do not treat `cbeb0ed` on PR #168 as step 1 or step 3 — both are analysed in `COUNT_FIXES_2026-10-10.md` section 4.
- Merge **pull request 168** (`cursor/count-roadmap-2026-10-10`). Its four handoff documents are worth having and are already copied onto the phase-plans branch; the branch itself must not land. It is an **orphan**: seven commits, no commit in common with `main`'s 695, so GitHub's file list is a whole-tree comparison and not a change set. Merging it reverts work that is already on `main` — it conflicts on eight files, including both e2e tests fixed on 2026-10-12 (`#175`) and `scoreboard_clock.py` from the seven-segment fix (`#173`), and its `ACTIVE.md` is the 2026-10-10 copy, so it would delete the scoreboard section. Its `ai_bridge.py` is a different 438-line file that **drops `validated_stats()`**, the sandbox boundary Hermes is required to pass data through, and drops the `sqlite3` import that `check_adrian_rerun_score` still calls (`ruff` reports `F821` there and `F811` at line 89). Its CI has never run a test: the lint step fails first. Take documents out of it with `git show`; do not press merge.
- Treat the bottom of `HERMES.md` ("Where the Adrian count stands") as the counting run. That is the September 30 rerun.
- **Open `GET /api/analysis/<game_id>` for this game** (`blueprints/ai.py:809`). **That request rewrites identity rows.** Read the `events` table directly, or the HTML results page. This is the easiest way for an agent to silently corrupt the run it is measuring.
- Merge **pull request 147** ("Re-enable auto-accept (0.85) for full-stack bring-up", open as of 2026-10-11). Scott settled this on the evening of 2026-10-11 (`JASON.md`, `BRAD.md`): **auto-accept stays at 0.85**, the home database already stores `ai.auto_accept_event_confidence` as `0.85`, and `event_generator.py:1554` calls `auto_accept_high_confidence_events` after a counting run, so a pending AI row at or above 0.85 is accepted. The pull request is therefore not needed, and it is not the place to change the value either way. **Do not turn auto-accept off either** — that is the same gate in the other direction.
- Start the **teach loop**.
- Use **video 64**. The film is **video id 73**, `uploads/nfhs_gam0a66d85e12.mp4`.
- Commit the untracked GitHub credential file in the repo root, or paste it into a note.
- Commit **anything out of the home-laptop share** (`http://100.107.224.49:8091/`, `HOME_TAILSCALE_SHARE.md`). It contains `.env` (the coach portal password), the database snapshot, the film and the tag files. `scripts/check_scott_gates.py` refuses the obvious ones, but it is not a substitute for not trying.
- Copy the share's `film_analysis.db` **back over** the home laptop's database. The snapshot is read-only and sanitised; the home copy is the real one.

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
| Run 12 shot rows | **229**, of which **155** are not rejected (measured 2026-10-11). 206 is an older count. |
| Run 12 event count | **1,555** (measured 2026-10-11). 1,452, 1,503 and 1,509 are older nights. |

### Run 12 point totals move — know which number you are looking at

`JASON.md` contains several non-rejected make-point totals from different nights. They are a sequence, not a contradiction. Quoting the wrong one makes a step look passed or failed when it is neither.

| Points | When | What changed |
| --- | --- | --- |
| 64 | 2026-10-06 snapshot | the original run 12 count |
| 76 | 2026-10-07 | seven tagged makes restored when `reconcile_makes_with_shots` stopped rejecting corrected rows |
| 59 → 43 | 2026-10-08 | Q2 review rejected all 27 extra AI shots, and between-quarters shots were rejected |
| 49 | 2026-10-08 night | The locked-hoop ball-box change wrote six misses; his tags graded five of them, three were makes (43 → 49). 14 twos, 5 threes, 6 free throws. |
| **55** | **2026-10-11, measured** | **current.** Non-rejected makes: 15 twos, 5 threes, 10 free throws. |
| **53** | **2026-10-11, measured** | **distinct baskets.** One `made_two` at 0:48.2 is **stored twice**, both taught Dayley rows. |

**55 and 53 are the numbers to work from.** The book is 77.

**The duplicate at 0:48.2 is a defect, not a rounding difference.** Two stored rows for one basket put two points on the card that the film only shows once, with no detector error involved. Step 5 names it; find out whether it is one row written twice or two rows taught from the same tag before changing anything.

One more discrepancy, not load-bearing — just do not treat it as a regression:
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

These plans were written on 2026-10-11 from `PROGRAM_FOR_JASON_2026-10-10.md` (PR #168), `JASON.md`, `ACTIVE.md`, `HERMES.md`, and the source code. **No frame of film was opened and no database row was read while writing them.** Every figure below that is not marked "measured" is quoted from those documents.

Scott then re-measured the run on the home laptop on 2026-10-11 and answered the open questions; those answers are in `JASON.md`, `BRAD.md` and `HERMES.md`, and the numbers in this index now carry them.

One item was still unreadable from here after that: the stored `ai.auto_accept_event_confidence` in the home database, which decides whether the 0.85 default actually promotes rows. Scott answered it on the evening of 2026-10-11 — it is stored as `0.85`, and it stays. Nothing in these plans now rests on an unanswered question about a setting.

**Not in git, but reachable from the home laptop over Tailscale.** Google Drive was the plan on the afternoon of 2026-10-11 and is **not** the handoff any more: the personal account filled up and the work account cannot share the folder (`HOME_TAILSCALE_SHARE.md`, pull request 171). The files stay on the home laptop and are served on its tailnet address only, at `http://100.107.224.49:8091/`, while that laptop is on and `scripts/serve_home_share.ps1` is running. Clone the repo, `git lfs pull`, then copy that folder over the clone so the paths line up. A Tailscale invite to this network is what grants access; it is not a public link, and **Funnel must not be turned on for port 8091**. Two consequences: the files are reachable only while the laptop is awake, so plan a step around copying once rather than reading live; and the share is an unauthenticated directory listing to every device on the tailnet, so treat tailnet membership as the only thing protecting it.

| Not in git | What it unlocks |
| --- | --- |
| `film_analysis.db` — read-only snapshot, 2026-10-11. Password hashes, phone numbers, session tokens, the NFHS login and share tokens were removed first. | Every run-12 figure: the event count, the shot rows, the make points, the per-player lines, the 22 tags with no AI row, the per-quarter make counts, the rebounds, the steals and fouls |
| `uploads/nfhs_gam0a66d85e12.mp4` — the Adrian film only (video 73) | **Every frame claim.** 896600, 1776500, 1515700, 2455600, 755400, 856200, 280200, and the Q3 stretch |
| `data/film_tags/`, including the history copies | The 378 tag rows and the **111 shot tags** — the grader for steps 3, 4, 7 and 8 |
| `data/hoop_tracks/`, `data/lineups/`, `data/hoopsalytics/` (state files; logs left off) | The locked hoop track, the lineup work, the panel state |
| `tag-exports/` — the review exports, including `rejected_makes_before_restore_20261007.json`, which is **not** in git | The step 4 and step 7 test set |
| `offline/v6/weights/best.pt`, `offline/v6_tracks.json`, `offline/bodd_shots.json`, `offline/hermes_suggestion_tracks.json` | **Every row of the try table, including the 85 / 20 / 6 best score.** These are not a replacement for `models/ball_detector.pt`. |
| `.env` — the coach portal password only | Running the app against the snapshot |

**Still nowhere, on purpose:**

| Missing | What stays unverified |
| --- | --- |
| The passphrase for `encrypted-archive/liberty_adrian_detections_20261007.enc` | The archived detections. Scott has it off-repo. |
| The NFHS login | Fetching film |
| The other eight game films | Step 10b's second gym |
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

**What this means for an agent picking up a step:** the plans are a map, not a measurement. Treat every quoted number as the last recorded value and re-measure it before you act on it. The first task of each step is to confirm its own starting numbers are still true. Since 2026-10-11 that is a real possibility rather than a formality — the home-laptop share makes the database, the film, the tags and the v6 tracks openable off that laptop.

## How a change proves it did not break the count

Three numbers decide it, and they are the same three everywhere: **right**, **makes missed**, **misses called makes**, on the coach's shot tags. Each tag lands in exactly one bucket, so the three always add up to the tag count — which is why the recorded best reads 85 + 20 + 6 = 111, and why calling every shot a miss reads 73 + 38 + 0.

| Tool | Where it runs | What it holds |
| --- | --- | --- |
| `scripts/shot_tag_score.py` | Home laptop, or a clone with the served folder copied over | Scores a run against the real tag file. Floor in `benchmarks/shot_tags/baseline.json`: **85 / 20 / 6** on `adrian_111`. Exit status 1 when the score is below it. |
| `scripts/accuracy_benchmark.py` | **CI, every pull request** | Runs the event generator on frozen detections and scores it, now including the three shot numbers. Floors in `benchmarks/accuracy/baseline.json`. |
| `tests/test_shot_tag_gate.py` | CI, plus the real film where the data is | Pins the arithmetic, the 8-second tolerance and what counts as the program's own claim. The 111-tag test skips where the data is absent and says so. |
| `scripts/check_scott_gates.py` | **CI, every pull request** (`.github/workflows/guardrails.yml`) | Refuses a change that crosses a Scott gate without naming it, and a change to how a shot is read that carries no score. |

Two things that follow from this, for any agent proposing a rule:

- **A note that says a rule is implemented is not a result.** Paste the line: `right=N makes_missed=N misses_called_makes=N`. The guardrail job blocks a pull request that changes `net_detector.py`, `event_generator.py`, `ai_bridge.py`, `stat_rules.py`, `manual_tag_teach.py`, `ai_analyzer.py` or `court_memory.py` without one.
- **A taught row is not the program's work.** `shot_tag_gate.stored_makes` ignores rejected rows, manual rows, and rows the teach pass corrected from a tag inside the tolerance. Counting a corrected row would grade the tags against themselves. `--count-taught` exists to answer "what does the card say now" and cannot be used to claim a gate score.

**One sample is not a measurement.** The event generator is nondeterministic: the same commit on the same frozen detections lands in one of two modes, 1,269 or 1,271 possession segments, and the scores differ between them — on the CI fixture, 10.1/28.3/14.9 with shot tags 12/8/3, or 9.9/26.4/14.4 with shot tags 13/8/2. Both interpreters in CI have produced both. So **run a scoring job twice before you believe it moved**, and read a single run as one sample. `benchmarks/accuracy/README.md` records the observations. Seeding the clustering would fix it and is a Scott gate.

`benchmarks/accuracy/adrian_q1/` holds the coach's 134 Q1 tags (44 shot tags) ready to go, built from a file that **is** in git. It has no frozen detections, so the benchmark prints `WAITING: adrian_q1` and scores nothing. Building them needs the film — see that folder's README. Until then the make/miss gate in CI runs on a different gym's film, which is better than nothing and is not the Adrian count.

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

## The two rise gates — raised 2026-10-11, answered the same day

The program file and the roadmap both say "the 170-pixel rise". There are **two** rise gates in `event_generator.py`, not one:

- `shot_min_ball_rise: 80.0` (line 707), applied in the primary shot pass at line 832
- `live_shot_min_ball_rise: 170.0` (line 710), applied to live field goals at line 946

A tagged shot that never becomes a row may be dropped at the 80px primary gate, before the 170px live gate is ever reached. Any step-4 work that reasons only about "the 170" is reasoning about the second gate of two. `adrian_quality.py:45` has a third, separate `MIN_SHOT_BALL_RISE = 120.0` on the quality-pass path.

**Scott's answer (2026-10-11): both stay, and change neither number.** The 80 is the primary pass. The 170 is the live field-goal pass and is the one he refused to drop. **Lane free throws skip the 170 and keep the 80** — which matters for step 4, where 4 of the 6 never-stored makes are free throws, so those four never met the 170 in the first place. Neither number moves until a tested rule beats 85 right with no more than 6 misses called makes *and* the same test shows the missing tagged rows appearing without new untagged shots. Both numbers are watched by `scripts/check_scott_gates.py`.
