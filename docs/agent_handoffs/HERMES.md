# Hermes handoff

Updated: 2026-10-11. Paste this into a new Hermes window. Chat memory is not the record. If this file and an older note disagree, this file wins. The Adrian count record is `docs/agent_handoffs/ACTIVE.md`. Stop reading at the Architecture section. The section "Where the Adrian count stands" is the September 30 rerun, not the counting run.

## Pickup (2026-10-11)

This section wins over the 2026-10-09 night section where a number disagrees. The count is not solved. Jason's plans are pull request 169. Brad's copy is pull request 170. One file per roadmap step, under `docs/agent_handoffs/plans/`. Docs only. Steps 1 and 2 stay offline. Step 3 is the gate: more than 85 right, no more than 6 misses called makes. Nothing is turned on until that gate passes.

Stay in `ai_bridge.py`. Do not edit the core pipeline, do not write database rows, and do not widen this file so it can. `applied_to_core` stays false. Do not train another ball-weights file. Do not change `models/ball_detector.pt` or `ball_confidence`. A manual tag is truth. The answer key is Scott's 111 shot tags (38 makes, 73 misses), not the AI rows in the database.

The best offline score is still 85 right, 20 makes missed, 6 misses called makes. That score was two steps on a ball track that actually falls through the net: the ball goes through the opening and keeps falling, then a make is thrown out only when the ball slides more than 0.45 rim-widths between 80px and 180px below the rim. It is not turned on.

These `Scott_Hermes` commits were scored on those 111 tags and lost. Do not resubmit them:

| Commit | What it did | Right | Makes missed | Misses called makes |
| --- | --- | --- | --- | --- |
| column under the rim | ball in the column under the hoop | 71 | 32 | 8 |
| `70516e2` | frame-to-frame slide called 0.45 | 66 | 37 | 8 |
| `1bf7e45` | drift of 0.45 treated as the whole make | 73 | 38 | 0 |
| `168beb8` | required 180px below a hoop the track had already cut off | 73 | 38 | 0 |
| `2e73ebe` | drift measured to the lowest box in the window | 72 | 34 | 5 |
| `69439fd` | threw out a shot whose highest ball was more than 2 rim-radii from the hoop | 75 | 36 | 0 |

Calling every shot a miss scores 73. A note that says the 85 rule is implemented is not a result. Cursor scores the code. If the score is not above 85 right with no more than 6 misses called makes, nothing is turned on.

Re-measured on the home machine 2026-10-11, counting run `...__rerun_20261006_033941`:

- **Two rise gates, and both stay.** `shot_min_ball_rise` 80 is the primary shot pass. `live_shot_min_ball_rise` 170 is the live field-goal pass. The 170 is the one Scott refused to drop. Lane free throws skip the 170 and keep the 80. Change neither number.
- **Events: 1,555.** 1,503 and 1,509 are older nights.
- **Points: 55** from non-rejected makes (15 twos, 5 threes, 10 free throws). One `made_two` at 0:48.2 is stored twice, both taught Dayley rows, so distinct baskets are 53 points. 49 is the 2026-10-08 night snapshot. The book is Liberty 51, Adrian 26.
- **Shot rows: 229**, 155 not rejected.
- **Steals are written.** 14 tags, 14 accepted film-tool rows. Through Q3 that is Liberty 8 and Adrian 6.
- **Assists do not match.** 10 tags. 10 rows: 8 pending, 2 rejected, none within 8 seconds of a tag. Leave them. That is step 8, after the shot count.
- **Possessions already have a table.** The film shot pass still builds segments in memory. Do not create a second table.
- **`tag-exports/rejected_makes_before_restore_20261007.json`** stays out of git.
- **The self-check is not this assignment.** Do not fold it into `ai_bridge.py`.

The next experiment, still inside `ai_bridge.py`, scores all 111 tags as right, makes missed, and misses called makes. Do not grade a shorter list and print "/111". Do not resubmit the column rule, a frame-to-frame jump called 0.45, drift used as the whole make, a farthest-point substitute for 180px, or a last-box depth check. The five misses that still look like makes are 755400, 896600, 1515700, 1776500, and 2455600. The hoop box has to sit on the orange rim. The ball box has to stay on the ball. The rim is orange. The net is white and cone-shaped. The exit sign is the only red object.

## Pickup (2026-10-09 night)

Counting run is `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941` (run 12) on the home database. The book is Liberty 51, Adrian 26. The count is not solved.

Stay in `ai_bridge.py`. Do not edit `event_generator.py`, `net_detector.py`, or `models/ball_detector.pt`. Do not change `ball_confidence`. Do not write database rows. Do not train another ball-weights file. Do not copy Scott's tags onto AI rows. Do not resume the four finished agents named in `ACTIVE.md`.

The best offline score on his 111 shot tags is 85 right, with 20 makes still missed and 6 misses called makes. Five of those misses still look like makes because the hoop box is on the glass or the backboard, or the ball box jumps off the ball. The next check is a hoop box on the orange rim and a ball box that stays on the ball. The rim is orange. The net is white and cone-shaped. The exit sign is the only red object. Read the 2026-10-09 pickup bullet in `ACTIVE.md` before proposing anything.

## How Cursor and Hermes work

Scott decides. Cursor changes the film pipeline and is the only one who commits and pushes. Hermes writes experiments in `ai_bridge.py` and stops there.

Hermes does not run git, does not change git config, and does not delete `.git/hooks`. Hermes does not claim a commit it did not make. A report lists what was run and what the output was.

The job is the Adrian count, not a new detector. Do not load `yolov8n.pt`. Do not call `validated_stats` on the game film. A proposal comes back as JSON with `applied_to_core` false. Cursor checks it against the database before Scott is asked to accept it.

## Architecture

This project has a strict, sequential pipeline. Do not structurally alter it.

Hermes edits `ai_bridge.py` only. Do not rewrite, refactor, or reorganize:

- `ai_analyzer.py`
- `event_generator.py`
- `court_memory.py`
- `net_detector.py`
- `manual_tag_teach.py`
- `game_boxscore.py`
- `scoreboard_clock.py`

Do not call `ai_bridge.py` from those files. Data leaves the sandbox through `validated_stats()` as JSON. `applied_to_core` stays false until Scott accepts the contract. Do not pass model objects across that boundary.

A make on the film is `ball_through_rim` or `net_moved_after_shot`. Code inside `ai_bridge.py` is an experiment, not a make. Do not change `models/ball_detector.pt` or `ball_confidence`. Do not restart Flask to load the adapter.

## Where the Adrian count stands

Game: Liberty vs Adrian, video 73, `uploads/nfhs_gam0a66d85e12.mp4`.

Rerun: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546`. Completed 2026-09-30 at 11:21 AM local. 1,452 events. No error. This was a new detection pass. The September 28 rerun is the previous one.

Book: Liberty 51, Adrian 26. Tags stop at about 32:15, the end of Q2. Halftime note: Liberty 27, Adrian 15.

Teach rejects an AI row only when a tag of that same family is within 8 seconds. A make in an open stretch stays pending. An unmatched tag is not inserted as a make.

Makes on this run: 40 rows, 80 points (26 twos, 7 threes, 7 free throws).

- Corrected: 29 makes, 59 points. These matched a tag.
- Pending: 9 makes, 17 points. These did not match a tag inside 8 seconds.
- Rejected: 2 made twos, 4 points. Dayley at 12:16 and cluster 8 at 26:05. The note is "extra AI event in tagged window."

The results box counts accepted, corrected, and pending. The scorebook total stays Liberty 51, Adrian 26. A later shot-chart step logged 0% makes on 206 shots. The event list is the count.

Flask was restarted on 2026-09-30 after Jason and Claude's review was merged, so port 8080 is running that code. The worker applied 7 jersey mappings at the end of this run.

Review branch: `cursor/playbook-jason-clean-slate-ac1f`, pull request 151. `main` and `jason-5-may-updates` are the last merged line (pull request 150). They do not have this run's teach rule or the review fixes.

Jason and Claude's fixes are already on the review branch: a named rerun stays that rerun, a new run with no coach decisions does not replace a reviewed copy, highlights use that same copy, games without a scoreboard track use equal video slices, an unreadable clock digit is not a clock, and imported FastDraw sheets do not get automatic defenders. Adrian has a scoreboard track, so a moment without a legal clock and a period stays out of the line score.

Not decided, and not a reason to edit the core: pass only from the ball handler, undo, screen coverage, zones, saving a dragged defender x, and the unread checks on net movement, defender jump, jersey mapping, and results speed.

`TEACH_ISSUE_ANALYSIS.txt` on the home machine describes the September 28 rerun. The span-reject bug it names is already fixed in `manual_tag_teach.py` and was used on the September 30 run. Do not apply that note to this run.

The database is `film_analysis.db` in the repo root on the home machine. The film is `uploads\nfhs_gam0a66d85e12.mp4`. Neither is in Git. Jersey shades for this run are `data/jersey_shades/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546.json`.

Fuller notes: `docs/agent_handoffs/ACTIVE.md`. Rules Cursor already loads: `.cursorrules`.
