# What Scott expects

Effective 2026-10-20. Paste this whole note into a new chat. Files on `main` win if this note and a chat disagree. Scott's latest instruction wins over this note.

The job is one NFHS game counted from the film and checked against the book. The book for Liberty at Adrian is Liberty 51, Adrian 26. Accuracy matters more than speed. The date is 1 November 2026. Notus A1 first quarter is the second measurement. It is 24 of 31 make or miss. That is not 100 percent, and it is not the whole job.

## Who decides

Scott decides. He may talk to any agent directly. No agent sits between him and the agent he is talking to. Ollama does not assign Cursor's work. Muse does not have to stamp a task Scott already gave.

Cursor implements on this PC, updates `docs/agent_handoffs/ACTIVE.md` when the task is done, and pushes `main`. `jason-5-may-updates` and `Brad/Claude` stay even with `main`. Jason reads `JASON.md`. Brad reads `BRAD.md`.

## What each agent does

**Cursor.** Build the smallest change that can be checked against the real file or the real score. Commit and push when Scott has asked for the work to be saved. Do not wait for a Muse stamp when Scott has already said to do the job. Do not call `ai_bridge.py` from the core. A make on the film is `ball_through_rim` or `net_moved_after_shot`.

**Hermes.** Edit `ai_bridge.py` only. Do not rewrite `ai_analyzer.py`, `event_generator.py`, `court_memory.py`, `net_detector.py`, `manual_tag_teach.py`, `game_boxscore.py`, or `scoreboard_clock.py`. Do not integrate an experiment into those files. A change in `ai_bridge.py` counts only when `run_saved_v6_rule` is better than 99 of 111 on the Adrian Q1–Q3 tracks with 0 misses called makes, or better than 24 of 31 on Notus Q1 with 0 misses called makes. Read `docs/agent_handoffs/HERMES.md`.

**Gemini.** Propose from the files in `gemini-upload/`. Gemini cannot see GitHub. A pull does not reach Gemini. Do not suggest a looser cutoff or a trial listed below. Read `docs/agent_handoffs/GEMINI.md`.

**Muse.** Check a proposal against `OLLAMA.md`, `MUSE.md`, and this note. Reject a looser cutoff. Reject a banned trial. Reject a script that prints a hard-coded score. Muse reads `main` and has no separate branch. Muse does not block a job Scott has already given to Cursor.

**Ollama.** Run on this PC as `gemma4:cloud` at `http://127.0.0.1:11434`. Keep `SESSION_STATE.md` short and current. Read `OLLAMA.md` before trusting `SESSION_STATE.md`. If they disagree, `OLLAMA.md` wins. Translate a measured result into plain English. Do not edit the core. Do not delegate Scott's instructions. Start a reply with WORKING while a tool is running, and IDLE when the task is finished.

**Jason and Brad.** Pull `main` before starting. Their branches are mirrors. They follow this same note.

## The score that is already measured

`run_saved_v6_rule` is make or miss only.

- Adrian Q1–Q3 tracks: 99 right, 12 makes missed, 0 misses called makes.
- Whole Adrian film, all four quarters tagged (458 rows, 129 shots): 113 of 129.
- Notus A1 Q1, 31 shots, tag points Liberty 3, Notus 11: 24 right, 7 makes missed, 0 misses called makes.

The seven Notus misses and the trial scores are in `OLLAMA.md`. The live detector matched 0 of those 31 tags on player, shot type, and make or miss together. Player, 2, 3, and free throw are unsolved. They are not part of the 24 or the 113.

The card that reads Liberty 51, Adrian 26 is Scott's tags written onto the card. It is not the live detector. `applied_to_core` is false. Scott has not accepted the JSON contract. `emit_fouls` stays false.

Work from `main`. The side branch `cursor/count-roadmap-2026-10-10` was merged on 2026-10-20.

## New rule: a candidate weights file may be written

Scott allowed this on the evening of 2026-10-20. The 9 October ban on training is lifted.

Write the new file beside the run. Do not copy it over `models/ball_detector.pt`. Do not change `ball_confidence`. Score it with `C:\Users\scott\AppData\Local\Temp\validate_ball_weights.py`. Keep it only when that script reports Adrian with 0 misses called makes, no more than 12 makes missed, and Notus with fewer than 7 makes missed. No candidate has been written yet.

Another file of the same kind as v1 through v6 is not, by itself, the fix. v6 is `C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt`. It is the file behind the scores above.

## Closed trials

Do not suggest these again. Do not rerun them.

- A window that starts 2 seconds earlier on the seven Notus makes: 0 of 7.
- Dropping jumps over 60 pixels: Adrian 86 of 111, 3 misses called makes.
- Drawing a jumped segment through the hoop: Adrian 93 of 111, 1 miss called a make.
- A straight line between neighboring points: Adrian 98 of 111.
- ByteTrack: 21 of 31, 1 miss called a make.
- DeepSORT: 22 of 31.
- A wider column. The record is `DETECTOR_PROPOSAL_REJECTION.md`.

Do not loosen `live_shot_min_ball_rise` (170), `shot_min_ball_rise` (80), or `MATCH_TOLERANCE_MS` (8000). Do not move a cutoff in `run_saved_v6_rule` to pick up a Notus make. On Adrian that calls a miss a make.

## Claims

A score is a number returned by `run_saved_v6_rule` on a real track file. The Adrian tracks in the upload folder are `gemini-upload/v6_tracks.json`. The Notus tracks are `gemini-upload/notus_q1_v6_tracks.json`. The printed line `SCORE: n/111` is a fixed string. Use the returned counts. Do not write `inspect_rule_logic.py`. Do not ship a script that prints a made-up total. Do not write `film_analysis.db` unless Scott says to write the live card. Do not commit the GitHub credential file in the repo root.

## Names that are already settled

Dayley, Daley, and Daly are one Liberty player, number 40, roster name Daly. Foster number 22 is Adrian. Notus roster names win where a tag spelling differs: Donamus, and Jake Alvarez and Liam Alvarez. Shared jersey numbers 0, 3, 5, and 11 need a team. Ask Scott before treating any other close spelling as the same person.
