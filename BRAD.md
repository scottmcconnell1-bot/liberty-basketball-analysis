# Brad — start here

Updated: 2026-10-04. This is the note on branch `Brad/Claude`. That branch stays even with `main`. Scott is texting you to open this branch. Jason's copy of this status is `JASON.md`.

You are a database analyst. The job is Liberty at Adrian. The official book is Liberty 51, Adrian 26. The program is trying to count that game from the film. It is not close enough. Do not copy the book totals onto the AI rows to make them match.

The database is `film_analysis.db` in the repo root on Scott's home machine. It is about 15 GB. It is not in git. School does not have this file. Do not overwrite it from another machine.

Film file: `uploads\nfhs_gam0a66d85e12.mp4` (video id 73). Do not use video 64.

Schema: `schema.sql`. Start with `analysis_runs`, `events`, `detections`, `track_identity_labels`, `players`, `roster_memberships`, and `stats`.

`events.game_id` is text. `analysis_runs.game_id` is an integer. Do not join them as the same type. The Adrian base key, comma included, is:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`

## The run on the results page

Run 11, finished 2026-09-30 20:11:42 UTC, 1,452 events, no error:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_191418`

| review_status | events | made shots | points |
| --- | --- | --- | --- |
| accepted | 242 |  |  |
| corrected | 63 | 13 | 25 |
| pending | 1,125 | 21 | 45 |
| rejected | 22 | 6 | 10 |

Corrected makes plus pending makes are 34 rows and 70 points. The book is 77. The corrected-only card is 25 points. That is why the latest card looks worse. Naming a jersey no longer sets `review_status` to `corrected`.

Combined lines (both label styles, pending + corrected): Dayley 16 (book 26), Colman 4 (15), Peterson 2 (4), Mendoza 8 (13), Alvarez 8 (5), Foster 9 (2), Rodus 3 (4). Sullivan, Flores, and Allison are 0. Unnamed: cluster `5` is 7, cluster `7` is 7, cluster `8` is 3, `#6` is 3. Scott said Liberty has no 2 and no 6, so cluster `7` and `#6` stay unnamed. Do not assign those 10 points to a Liberty player.

The previous run, id 10 (`...__rerun_20260930_160546`), had 29 corrected makes and 59 points because naming a player used to flip `pending` to `corrected`. Do not treat that flip as the right count.

## How a point is stored

Only `event_type` of `made_two`, `made_three`, or `made_free_throw` adds points. `event_type = 'shot'` adds 0 even when `shot_result = 'make'`. There is no points column. `stats.py` trusts only `accepted` and `corrected`. The AI card also includes `pending`.

A cluster id in `events.player` (`5`, `7`, `8`) is a tracker, not a roster jersey. Labels look like `#40` or `40 - Dayley`.

Book individuals: Liberty Dayley 26, Colman 15, Sullivan 4, Peterson 4, Flores 2. Adrian Mendoza 13, Alvarez 5, Rodus 4, Foster 2, Allison 2. Foster #22 is Adrian. Do not move him to Liberty.

## Where to look for bugs

1. `events` for run 11. Split makes by `review_status`, `event_type`, `player`, and `team_id`. Pending named makes include `#13 Mendoza`, `#22 Foster`, `#23 Rodus`, `#25 Alvarez`, `#40 Dayley`, `#6` with no name, and clusters `5`, `7`, and `8`.
2. Any path that sets `pending` to `corrected` only because a name was filled in. Jersey naming must not do that.
3. `primary_player_id` and `team_id` on shared jerseys. Numbers 11 and 24 are on both teams. No shade and two players with that number should leave the name empty.
4. `track_identity_labels` for this analysis key only. Do not copy tracker ids from an older rerun.
5. `detections` is one row per object per frame. Filter on `game_id` and `frame_number` (`idx_detections_game_frame`). An unfiltered query scans the whole table.
6. Tags cover Q1 and Q2 only, through 32:15 (`data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`). Q3 and Q4 were never tagged, so the AI total will not equal 51–26 from tags. The scoreboard track has no readable period 3. Do not invent quarters by splitting this video into four equal parts.
7. Compare `stats` to a fresh sum of `events`. If they disagree, the card is stale.

Confirmed book: `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`.

Do not change `schema.sql` without Scott. Do not turn auto-accept on (pull request 147). Do not change `models/ball_detector.pt` or `ball_confidence`. Do not start the teach loop. Opening `GET /api/analysis` for this game rewrites identity rows. Read `events`, or the HTML results page.

Code that writes these rows: `event_generator.py`, `manual_tag_teach.py`, `track_identity.py`, `court_slot_mapping.py`, `game_boxscore.py`. `ai_bridge.py` does not count a make.
