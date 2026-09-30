# Hermes handoff

Updated: 2026-09-30 afternoon. Paste this into a new Hermes window. Chat memory is not the record. If this file and an older note disagree, this file wins.

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
