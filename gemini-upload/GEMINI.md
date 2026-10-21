# Gemini handoff

Updated: 2026-10-20. Gemini cannot see GitHub. Chat memory is not the record. If this file and an older note disagree, this file wins. The upload folder is `gemini-upload/` at the repo root. Upload that whole folder again after 2026-10-20. A pull does not reach Gemini. Hermes reads `docs/agent_handoffs/HERMES.md`. Muse reads `MUSE.md`. Ollama reads `OLLAMA.md`. Jason reads `JASON.md`. Brad reads `BRAD.md`. The Adrian count record is `docs/agent_handoffs/ACTIVE.md`.

## Pickup (2026-10-20)

The program is on `main` at `3eea117`. From 2026-10-10 through the morning of 2026-10-20 the checkout was `cursor/count-roadmap-2026-10-10`. That branch was fast-forwarded onto `main`. `jason-5-may-updates` and `Brad/Claude` are the same commit.

Scott tagged all four Adrian quarters: 458 rows, 129 shots. `run_saved_v6_rule` is 99 of 111 on the Q1–Q3 tracks (12 makes missed, 0 misses called makes) and 113 of 129 on the whole film. Notus A1 Q1 is 24 of 31, 7 makes missed, 0 misses called makes. A longer window, a straight-line fill, ByteTrack, and DeepSORT all scored worse. Do not propose those again. A later proposal to interpolate sparse frames and widen the column was rejected in `DETECTOR_PROPOSAL_REJECTION.md`. Do not write `inspect_rule_logic.py`. `applied_to_core` is false. Scott did not accept the contract on 2026-10-20. A make on the film is still `ball_through_rim` or `net_moved_after_shot`. Do not change `models/ball_detector.pt` or `ball_confidence`.

`main`, `jason-5-may-updates`, and `Brad/Claude` carry this same folder. `Scott_Hermes` does not. When the rule, the tags, the schema, the teach mapping, or the card scoring changes, refresh every file in `gemini-upload/` from `main` and push that commit to `main`, Jason, and Brad together.

## What is in the folder

| File | What it is |
|---|---|
| `GEMINI.md` | This note |
| `MUSE.md` | Muse's note. Muse reads `main` and does not get a separate branch |
| `OLLAMA.md` | Ollama's note. Ollama runs on this PC and does not get a separate branch |
| `DETECTOR_PROPOSAL_REJECTION.md` | Interpolation and a wider column were rejected. The next step is a new weights file |
| `ai_bridge.py` | The published adapter. The scored rule is `run_saved_v6_rule`. `validated_stats` and `BasketballStatsAdapter` stay in the file |
| `HERMES.md` | Hermes's note. Hermes may edit `ai_bridge.py` only |
| `ACTIVE.md` | The count record |
| `manual_tag_teach.py` | `map_manual_row` and `_scoring_code` |
| `game_boxscore.py` | `apply_ai_event`. A `shot` row scores 0 |
| `schema.sql` | `events` and `event_types` |
| `adrian_film_tags.json` | Scott's Adrian film tags. Shots are in `rows`. The clock is `start` (`20:31.4`). The type is `eventtype` (`2PT`, `3PT`, `FT`) |
| `notus_a1_film_tags.json` | Scott's Notus A1 tags. Same shape. Q1 ends at the `EndQTR` row, clock `14:43.4` |
| `v6_tracks.json` | The 111 Adrian tracks. A point is `[frame, x, y]`. There is no box width on a track |
| `notus_q1_v6_tracks.json` | The 31 Notus A1 first-quarter tracks, copied from the home PC. Same shape as `v6_tracks.json` |
| `score_hermes_now.py` | Scores `run_saved_v6_rule` in the `ai_bridge.py` next to it |

Do not ask for `film_analysis.db`, `bodd_shots.json`, `.env`, or the GitHub credential file. Box width and confidence do not separate the last makes. The database is about 380 MB and stays on the home PC.

## The score

`run_saved_v6_rule` is **99 of 111 right, 12 makes missed, 0 misses called makes.** `applied_to_core` is false. A make on the film is `ball_through_rim` or `net_moved_after_shot`. A proposal that calls a miss a make is not a contribution. Do not put tag times or tag results inside a detection rule.

These were already scored and are not in the file: a wider column, a hoop recenter, an 85-pixel jump, a pre-drift check on the points above 80 px, and swapping the grouped hoop for the detector hoop.

## How the card scores

`apply_ai_event` gives a `shot` row 0 points. The card scores `made_two`, `missed_two`, `made_three`, `missed_three`, `made_free_throw`, and `missed_free_throw`.

`map_manual_row` reads one film row. `_scoring_code` turns it into the event the card counts. A `2PT` make is `made_two`. A `3PT` miss is `missed_three`. An `FT` make is `made_free_throw`. `shot_result` is `make` or `miss`. The player column is `player`, not `player_name`. `event_types` has `code` and `label`, not `name`. `human_verified` is an integer column. `review_status` is `pending`, `accepted`, `corrected`, or `rejected`.

The six scoring rows that still disagree with a tag are 31364 (`made_two`, `40 - Dayley`), 31457 (`made_three`, `21 - Colman`), 31479 (`made_three`, `40 - Dayley`), 31498 (`made_two`, `21 - Colman`), 31547 (`made_free_throw`, `13 - Mendoza`), and 31624 (`made_free_throw`, `13 - Mendoza`). Each also needs `review_status` `corrected` and `human_verified` 1. Those rows have not been written. Thirteen tags sit 2 to 8 seconds from a shot and stay untouched. Fifteen tags have no shot within 8 seconds. A new row for one of those has to be a scoring type. A new `shot` row adds 0 points.

## What Gemini can contribute

Read the files in `gemini-upload/`. Propose a change to `run_saved_v6_rule` only when it can be scored on all 111 tracks and the false-make count stays 0. Propose a database change only with the column names in `schema.sql` and the scoring types in `game_boxscore.py`. Do not invent `player_name`, `timestamp_ms` on a film row, or `event_types.name`.

Gemini does not edit the core pipeline, does not write the live database, and does not merge `Scott_Hermes`. Cursor commits and pushes.

## Notus A1 first quarter, measured 2026-10-18

Scott tagged the first quarter. The hoop and ball for those 31 shots were read from the Notus film on the home PC. The track file in this folder is `notus_q1_v6_tracks.json`. Gemini’s own machine does not have `C:\Users\scott\AppData\Local\Temp`. Read the copy in this folder.

| What | Exact path or value |
|---|---|
| Game id | `jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334` |
| Film tags in the repo | `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` |
| Copy in this folder | `notus_a1_film_tags.json` |
| Tracks in this folder | `notus_q1_v6_tracks.json` (31 rows). The home PC original is `C:\Users\scott\AppData\Local\Temp\v6_tracks_notus_q1.json` |
| Make or miss score | `run_saved_v6_rule` returned 24 right, 7 makes missed, 0 misses called makes, `applied_to_core` false. The printed `24/111` line is a fixed string |
| Live database | `film_analysis.db` at the repo root. It stays on the home PC |
| Scorebook the page reads | `data/stat_books/confirmed/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` |
| Q1 end | `EndQTR` at `14:43.4` |
| Q1 shot tags | 31 (`2PT`, `3PT`, `FT`) |
| Tag points | Liberty 3, Notus 11 |

These files are not in the repo: `game2_tracks.json`, `data/notus_raw_tracks.json`, `notus_game_tags.json`, `evaluate_new_game.py`.

The pairing used `MATCH_TOLERANCE_MS = 8000` in `manual_tag_teach.py`. Zero of the 31 tags match an AI row on player, shot type, and make or miss together. Five agree on type and make or miss, and the AI player is a track number. Seven tagged shots have no AI row within 8 seconds: `1:04.2` Camden Linkhart 2 make, `5:57.5` Camden Linkhart free-throw make, `7:02.7` Miguel Rodus 2 miss, `8:03.4` Carson Linkhart 2 make, `9:51.1` Camden Linkhart 2 miss, `9:58.3` Price 2 miss, `12:54.6` Price free-throw make.

### Functions and columns that exist

`run_saved_v6_rule(tag_timestamps, v6_tracks_path)` is at line 906 of `ai_bridge.py`. The default path in the signature is the Adrian file. It scores only the timestamps present in the track file. A track row is `{t, result, hoop, ball, bodd}`. `ball` points are `[frame, x, y]`. The return dict is `total_tags`, `right`, `makes_missed`, `misses_called_makes`, `results`, `applied_to_core`. Each result is `tag_ts`, `true`, `pred`, `details`. The printed line `SCORE: n/111` is a fixed string. Use the return dict. `applied_to_core` stays false.

`map_manual_row(row)` in `manual_tag_teach.py` reads `eventtype`, `result`, `player`, `team`, and `start`. A shot returns `event_type` `shot` and `shot_type` `2pt`, `3pt`, or `ft`. `_scoring_code` turns that into `made_two`, `missed_two`, `made_three`, `missed_three`, `made_free_throw`, or `missed_free_throw`. A `shot` row scores 0.

`events` columns: `id`, `game_id`, `player`, `event_type`, `shot_result`, `timestamp_ms`, `details_json`, `review_status`, `human_verified`, `source_type`. `shot_result` is `make` or `miss`. `review_status` is `pending`, `accepted`, `corrected`, or `rejected`. Jersey, when the detector stored one, is `jersey_number` inside `details_json`. There is no `events.jersey_number` column and no `events.team` column.

### What a useful Notus change is

The make or miss score on `notus_q1_v6_tracks.json` is already 24 of 31. The seven missed makes are 64200, 142600, 159300, 212300, 357500, 483400, and 774600. Their ball tracks are long enough. A wider cutoff is not a contribution. A script that writes jersey numbers onto `events`, or that writes a scorebook of zeros, does not score this quarter.
