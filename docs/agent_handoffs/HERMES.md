# Hermes handoff

Updated: 2026-09-29 evening. Paste this into a new Hermes window. Chat memory is not the record.

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

A make on the film is `ball_through_rim` or `net_moved_after_shot`. Code inside `ai_bridge.py` is an experiment, not a make. Do not change `models/ball_detector.pt` or `ball_confidence`. Do not restart Flask.

## Where the Adrian count stands

Game: Liberty vs Adrian, video 73, `uploads/nfhs_gam0a66d85e12.mp4`.

Rerun: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027`.

Book: Liberty 51, Adrian 26. Tags stop at about 32:15, the end of Q2. Halftime note: Liberty 27, Adrian 15.

Teach matched 67 tags, rejected 154 nearby AI events, and left 79 tags unmatched. Those 79 are not inserted as makes. The 8-second window stays. Corrected makes in the database: 17 rows, 31 points, Liberty 21 and Adrian 10.

Flask on port 8080 has been up since 09:19 local and does not have today's code. Do not open `/api/analysis` for this game. That route stamps cluster names. Do not restart Flask.

Fuller notes: `docs/agent_handoffs/ACTIVE.md`. Rules Cursor already loads: `.cursorrules`.
