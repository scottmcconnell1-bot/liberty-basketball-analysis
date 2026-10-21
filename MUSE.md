# Muse — start here

Updated: 2026-10-20. Muse reads `main` and `AGENT_OPERATIONAL_PROTOCOL.md`. Muse has no separate branch. Pull `main` before you start. Reject a looser cutoff and a banned trial. Do not block a job Scott has already given to Cursor. Jason's note is `JASON.md`. Brad's note is `BRAD.md`. Hermes reads `docs/agent_handoffs/HERMES.md`. Gemini reads `docs/agent_handoffs/GEMINI.md` and the folder `gemini-upload/`. Ollama reads `OLLAMA.md`. The count record is `docs/agent_handoffs/ACTIVE.md`.

## Pickup (2026-10-20) — you are on main

From 2026-10-10 through the morning of 2026-10-20 the working checkout was `cursor/count-roadmap-2026-10-10`, not `main`. On 2026-10-20 that branch was fast-forwarded onto `main`. Pull `main` before you start. `jason-5-may-updates` and `Brad/Claude` stay even with `main`. Do not keep working from the side branch.

Older notes that say the fourth quarter is untagged, or that the best make/miss score is 85 of 111, are history. This file wins on those two points.

**Proven:** Scott tagged all four Adrian quarters. The tag file on the home PC has 458 rows and 129 shots (111 in Q1–Q3, 18 in Q4). `data/film_tags/*.json` is gitignored. `run_saved_v6_rule` in `ai_bridge.py` is make or miss only: 99 of 111 on the Q1–Q3 tracks (12 makes missed, 0 misses called makes), and 113 of 129 on the whole Adrian film. Notus A1 first quarter (`jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334`, 31 shots) is 24 right, 7 makes missed, 0 misses called makes. The live detector matched 0 of those 31 on player, shot type, and make or miss together. `applied_to_core` is false. Scott did not accept the JSON contract on 2026-10-20. A make on the film is still `ball_through_rim` or `net_moved_after_shot`.

The card that reads Liberty 51, Adrian 26 is the tags written onto the card. It is not the live detector. Rebounds, assists, steals, turnovers, and fouls are in the tags. They were not part of the 113. `emit_fouls` stays false.

The two Notus makes the rule got right are Cole Abel’s 3 at 4:00.8 (`240800`) and Camden Linkhart’s free throw at 6:10.6 (`370600`). Tag points for that quarter are Liberty 3, Notus 11. The tracks are `gemini-upload/notus_q1_v6_tracks.json`.

The seven missed makes are 1:04.2 Camden 2 (`64200`, no clean crossing), 2:22.6 Camden free throw (`142600`, `column_ratio_low`), 2:39.3 Camden free throw (`159300`, `short_make_bodd_fail` even with an earlier window), 3:32.3 Flores 2 (`212300`, `ball_box_jump`), 5:57.5 Camden free throw (`357500`, `column_ratio_low`), 8:03.4 Carson 2 (`483400`, `x_at_180_outside_rim`), and 12:54.6 Price free throw (`774600`, `ball_went_up`). The same table is in `OLLAMA.md`.

These trials did not beat 24 of 31. Do not rerun them.

- A window 2 seconds earlier on the seven only: 0 of 7.
- Dropping jumps over 60 px: Adrian 86 of 111, 3 misses called makes. Notus 0 of 7.
- Drawing the jumped segment through the hoop: Adrian 93 of 111, 1 miss called a make. Notus 0 of 7.
- A straight line between the neighbors: Adrian 98 of 111. Notus 0 of 7.
- ByteTrack: 21 of 31, 1 miss called a make (9:51.1, `591100`). It lost both makes the nearest-box file got right.
- DeepSORT: 22 of 31, 0 misses called makes. It lost those same two makes.

`SESSION_STATE.md` is Ollama’s short status. It says Idle. If it still says the detector trials are pending, `OLLAMA.md` wins.

A proposal to interpolate sparse frames and widen the column was rejected. The record is `DETECTOR_PROPOSAL_REJECTION.md`. Do not write `inspect_rule_logic.py`.

A future weights file is scored by `C:\Users\scott\AppData\Local\Temp\validate_ball_weights.py`. It does not replace `models/ball_detector.pt`. It is kept only if Adrian still has 0 misses called makes and no more than 12 makes missed, and Notus misses fewer than 7 makes.

The extended `results` shape (shooter and shot value beside make or miss) was drafted for review and was not written into `ai_bridge.py`. The current track has no shooter and no shot type.

**Unknown:** a weights file that holds the ball through the net on the seven Notus misses without a false make on Adrian. Player and 2/3/FT are a separate unsolved count.

## Do not

- Copy a new weights file over `models/ball_detector.pt`, or change `ball_confidence`. Writing a candidate file is allowed as of 2026-10-20. It stays only when `validate_ball_weights.py` passes.
- Set `applied_to_core` true. Scott connects the adapter only after he accepts the contract.
- Call `ai_bridge.py` from the core sequence.
- Rewrite `ai_analyzer.py`, `event_generator.py`, `court_memory.py`, `net_detector.py`, `manual_tag_teach.py`, `game_boxscore.py`, or `scoreboard_clock.py`.
- Loosen `live_shot_min_ball_rise` (170), `shot_min_ball_rise` (80), or `MATCH_TOLERANCE_MS` (8000).
- Commit the GitHub credential file in the repo root.
- Resume the four finished agents named in `ACTIVE.md`.
- Rerun ByteTrack, DeepSORT, the early window, or the interpolation trials.
