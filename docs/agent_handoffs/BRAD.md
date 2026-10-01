# Brad / Claude

Updated: 2026-10-01. Branch: `Brad/Claude`. This branch matches `main`. Read this file first.

You are looking at the database behind one junior-high film: Liberty at Adrian. The official book is Liberty 51, Adrian 26. The program is trying to count the same game from the film. It is not close enough yet. Do not copy the book totals onto the AI rows to make them match.

## Where the data is

The database is `film_analysis.db` in the repo root on Scott's home machine. It is about 15 GB. It is not in git. School does not have this file. Do not overwrite it from another machine.

Film file: `uploads\nfhs_gam0a66d85e12.mp4` (video id 73, 1920x1080, 25 fps, 97,475 frames). Do not use video 64.

Schema: `schema.sql`. The tables that matter first are `analysis_runs`, `events`, `detections`, `track_identity_labels`, `players`, `roster_memberships`, and `stats`.

`events.game_id` is a text key, not `games.id`. The Adrian base key is:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`

The comma is required. A rerun appends `__rerun_YYYYMMDD_HHMMSS`.

## Which run is on the results page

Newest completed run, id 11:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_191418`

Finished 2026-09-30 20:11:42 UTC. 1,452 events. No error. Results opens this run from the base key.

| review_status | events | made shots | points |
| --- | --- | --- | --- |
| accepted | 242 |  |  |
| corrected | 67 | 17 | 31 |
| pending | 1,125 | 21 | 45 |
| rejected | 18 | 2 made twos | 4 |

Corrected makes plus pending makes are 38 rows and 76 points. The book is 77 points. The corrected-only card is 31 points. That drop is why the latest card looks worse than the run before it. Naming a jersey no longer sets `review_status` to `corrected`.

The run before that, id 10, `...__rerun_20260930_160546`, had 749 corrected events and 29 corrected makes / 59 points, because naming a player used to flip `pending` to `corrected`. Do not treat that flip as the right count.

## How a point is stored

Only `event_type` in `made_two`, `made_three`, `made_free_throw` adds points. `event_type = 'shot'` adds 0 even when `shot_result = 'make'`. There is no points column on `events`. `stats.py` trusts only `review_status IN ('accepted', 'corrected')`. The AI card on the results page also includes `pending`.

`primary_player_id` is set only when the saved name matches the roster person. A cluster id in `events.player` (`5`, `7`, `8`) is a tracker, not a roster jersey. Jersey labels look like `#40` or `40 - Dayley`.

Book individuals: Liberty Dayley 26, Colman 15, Sullivan 4, Peterson 4, Flores 2. Adrian Mendoza 13, Alvarez 5, Rodus 4, Foster 2, Allison 2. Foster #22 is Adrian in the book and in the tags. Do not move him to Liberty.

## Where to look for bugs

1. `events` for run 11. Split makes by `review_status`, `event_type`, `player`, and `team_id`. Pending named makes still in that run include `#13 Mendoza`, `#22 Foster`, `#23 Rodus`, `#25 Alvarez`, `#40 Dayley`, `#6` with no name, and clusters `5`, `7`, and `8`.
2. `review_status`. A bug is any path that sets `pending` to `corrected` just because a name was filled in. Coach accept/correct may set it. Jersey naming must not.
3. `primary_player_id` and `team_id` on those makes. A shared jersey (11 and 24 are on both teams) must not attach the wrong roster row. No shade and two players with that number should leave the name empty.
4. `track_identity_labels` for this analysis key only. Do not copy tracker ids or names from an older `__rerun_` key onto this one.
5. `analysis_runs`. `game_id` there is the integer `games.id`. `events.game_id` is the text key. Do not join them as the same type.
6. `detections`. One row per object per frame. The index is `idx_detections_game_frame` on `(game_id, frame_number)`. A query without that filter will scan a huge table.
7. Quarters. Manual tags exist for Q1 and Q2 only, through 32:15, in `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`. Q3 and Q4 were never tagged, so the AI total will not equal 51–26 from tags alone. The scoreboard track has no readable period 3. A missing clock must stay out of the line score. Do not invent quarters by splitting the video into four equal parts for this game.
8. `stats` rows versus a fresh sum of `events`. If those disagree, the card is stale.

Confirmed book file: `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`.

## What not to change

Do not change `schema.sql` without Scott. Do not turn auto-accept on (open pull request 147). Do not change `models/ball_detector.pt` or `ball_confidence`. Do not start the teach loop. Opening `GET /api/analysis` for this game rewrites identity rows. Use the events table, or the HTML results page, to look.

Code that writes these rows: `event_generator.py`, `manual_tag_teach.py`, `track_identity.py`, `court_slot_mapping.py`, `game_boxscore.py`. `ai_bridge.py` is an experiment file. It does not count a make.
