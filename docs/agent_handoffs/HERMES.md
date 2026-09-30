# Hermes handoff

Updated: 2026-09-30 evening. Paste this into a new Hermes window. Chat memory is not the record.

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

Flask was restarted on 2026-09-30 with the scoreboard quarter rule and the OCR identity guard. The worker applied 7 jersey mappings at the end of this run.

Fuller notes: `docs/agent_handoffs/ACTIVE.md`. Rules Cursor already loads: `.cursorrules`.
