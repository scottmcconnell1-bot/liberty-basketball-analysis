# Ollama — start here

Updated: 2026-10-20. Ollama runs on this PC. The model in use is `gemma4:cloud` through `http://127.0.0.1:11434`. Chat memory is not the record. If this file and `SESSION_STATE.md` disagree, this file wins. Pull `main` before you start. Ollama has no separate branch.

Jason reads `JASON.md`. Brad reads `BRAD.md`. Hermes reads `docs/agent_handoffs/HERMES.md`. Gemini reads `docs/agent_handoffs/GEMINI.md` and the folder `gemini-upload/`. Muse reads `MUSE.md`. The count record is `docs/agent_handoffs/ACTIVE.md`.

Scott (2026-10-20) — your role is the Builder, not the orchestrator. This is not negotiable. Implement the smallest checkable change. Keep `applied_to_core` false. Sync `main`, `jason-5-may-updates`, and `Brad/Claude`. Do not assign tasks. Do not manage the other agents. The paste note is `AGENT_OPERATIONAL_PROTOCOL.md`.

Start a reply with WORKING while a tool is running. Start a reply with IDLE when the task is finished and you are waiting. Do not start another analysis of the 24/31 score. That measurement is below.

## Pickup (2026-10-20)

Work from `main`. From 2026-10-10 through the morning of 2026-10-20 the checkout was `cursor/count-roadmap-2026-10-10`. That branch was fast-forwarded onto `main`. `jason-5-may-updates` and `Brad/Claude` are even with `main`.

Scott tagged all four Adrian quarters: 458 rows, 129 shots. `run_saved_v6_rule` is 99 of 111 on the Q1–Q3 tracks (12 makes missed, 0 misses called makes) and 113 of 129 on the whole film. `applied_to_core` is false. Scott did not accept the contract on 2026-10-20. A make on the film is still `ball_through_rim` or `net_moved_after_shot`.

## Notus Q1 is 24 of 31, and the trials are finished

Game `jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334`. 31 shot tags. Tag points Liberty 3, Notus 11. The nearest-box tracks are `gemini-upload/notus_q1_v6_tracks.json` (home PC original `C:\Users\scott\AppData\Local\Temp\v6_tracks_notus_q1.json`).

**Proven:** `run_saved_v6_rule` on those tracks is 24 right, 7 makes missed, 0 misses called makes. The two makes it got right are Cole Abel’s 3 at 4:00.8 (`240800`) and Camden Linkhart’s free throw at 6:10.6 (`370600`).

The seven missed makes:

| Clock | ms | Shot | Why the rule said miss |
|---|---|---|---|
| 1:04.2 | 64200 | Camden 2 make | No clean crossing. The down-cross is 1.32 hoop-widths off center, with a 82.7 px jump and 22 missing frames |
| 2:22.6 | 142600 | Camden free-throw make | `column_ratio_low`. The cross is 0.30 widths off center. Do not loosen this cutoff. On Adrian that calls a miss a make |
| 2:39.3 | 159300 | Camden free-throw make | A window that starts 2 seconds earlier still misses: `short_make_bodd_fail` |
| 3:32.3 | 212300 | Flores 2 make | A crossing in the column, then a jump of about 120 px (`ball_box_jump`) |
| 5:57.5 | 357500 | Camden free-throw make | `column_ratio_low`. The cross is 0.42 widths off center, with gaps and a jump of about 65 px |
| 8:03.4 | 483400 | Carson 2 make | The earlier window still misses: `x_at_180_outside_rim` |
| 12:54.6 | 774600 | Price free-throw make | `ball_went_up`. A crossing in the column, then a jump of about 119 px, and the track ends back at the rim |

These were scored and did not beat 24 of 31:

- A window 2 seconds earlier on the seven only: 0 of 7.
- Dropping jumps over 60 px: Adrian fell to 86 of 111 and called 3 misses makes. Notus stayed 0 of 7.
- Drawing the jumped segment through the hoop: Adrian 93 of 111, 1 miss called a make. Notus stayed 0 of 7.
- A straight line between the neighbors: Adrian 98 of 111, one more miss than 99. Notus stayed 0 of 7.
- ByteTrack on all 31: 21 of 31, 9 makes missed, 1 miss called a make (9:51.1, `591100`). It lost both makes the nearest-box file got right.
- DeepSORT on all 31: 22 of 31, 9 makes missed, 0 misses called makes. It lost those same two makes.

The live detector matched 0 of the 31 tags on player, shot type, and make or miss together. Player and 2/3/FT are unsolved and are not this score.

A later proposal to interpolate sparse frames and widen the column was rejected. The record is `DETECTOR_PROPOSAL_REJECTION.md`. Do not write `inspect_rule_logic.py`.

Scott (2026-10-20, evening) allowed writing a candidate ball weights file. The 9 October ban on training is lifted. No candidate has been written yet.

**Next step:** write that file, then score it with `C:\Users\scott\AppData\Local\Temp\validate_ball_weights.py`. Keep it only if Adrian still has 0 misses called makes and no more than 12 makes missed, and Notus misses fewer than 7 makes. Do not copy it over `models/ball_detector.pt`. Do not change `ball_confidence`. Do not edit the cutoffs in `ai_bridge.py`.

## Do not

- Rerun ByteTrack, DeepSORT, the early window, or the interpolation trials.
- Set `applied_to_core` true.
- Call `ai_bridge.py` from the core sequence.
- Write `film_analysis.db`.
- Commit the GitHub credential file in the repo root.
- Sign in, create an API key, or paste a connect URL into a note.
