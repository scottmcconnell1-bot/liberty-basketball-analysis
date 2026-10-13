# Gemini handoff

Updated: 2026-10-13. Gemini cannot see GitHub. Chat memory is not the record. If this file and an older note disagree, this file wins. The upload folder is `gemini-upload/` at the repo root. Upload that whole folder. Hermes reads `docs/agent_handoffs/HERMES.md`. The Adrian count record is `docs/agent_handoffs/ACTIVE.md`.

`main`, `jason-5-may-updates`, and `Brad/Claude` carry this same folder. `Scott_Hermes` does not. When the rule, the tags, the schema, the teach mapping, or the card scoring changes, refresh every file in `gemini-upload/` from `main` and push that commit to `main`, Jason, and Brad together.

## What is in the folder

| File | What it is |
|---|---|
| `GEMINI.md` | This note |
| `ai_bridge.py` | The published adapter. The scored rule is `run_saved_v6_rule`. `validated_stats` and `BasketballStatsAdapter` stay in the file |
| `HERMES.md` | Hermes's note. Hermes may edit `ai_bridge.py` only |
| `ACTIVE.md` | The count record |
| `manual_tag_teach.py` | `map_manual_row` and `_scoring_code` |
| `game_boxscore.py` | `apply_ai_event`. A `shot` row scores 0 |
| `schema.sql` | `events` and `event_types` |
| `adrian_film_tags.json` | Scott's film tags. Shots are in `rows`. The clock is `start` (`20:31.4`). The type is `eventtype` (`2PT`, `3PT`, `FT`) |
| `v6_tracks.json` | The 111 saved tracks. A point is `[frame, x, y]`. There is no box width on a track |
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
