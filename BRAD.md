# Brad — start here

Updated: 2026-10-06. This is the note on branch `Brad/Claude`. That branch stays even with `main`. Scott is texting you to open this branch. Jason's copy of this status is `JASON.md`.

You are a database analyst. The job is Liberty at Adrian. The official book is Liberty 51, Adrian 26 (77 points). The program is trying to count that game from the film. It is not close enough. Do not copy the book totals onto the AI rows to make them match.

The database is `film_analysis.db` in the repo root on Scott's home machine. It is about 15 GB. It is not in git. School does not have this file. Do not overwrite it from another machine.

Film file: `uploads\nfhs_gam0a66d85e12.mp4` (video id 73). Do not use video 64.

Schema: `schema.sql`. Start with `analysis_runs`, `events`, `detections`, `track_identity_labels`, `players`, `roster_memberships`, and `stats`.

`events.game_id` is text. `analysis_runs.game_id` is an integer. Do not join them as the same type. The Adrian base key, comma included, is:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`

## The run on the results page

Run 12 is what results open. It finished 2026-10-06 04:59:04 UTC, 1,452 events, no error, and it has corrected rows:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941`

It is not a better count than run 11 (finished 2026-09-30 20:11:42 UTC):

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_191418`

Live points are pending plus corrected. Only `made_two` (2), `made_three` (3), and `made_free_throw` (1) score. `event_type = 'shot'` scores 0 even when `shot_result = 'make'`.

| | Truth | Run 11 live | Run 12 live |
| --- | --- | --- | --- |
| First half, `timestamp_ms` <= 1,935,000 (video 32:15) | 42, from the tags | 56 | 50 |
| Second half, after that | 35, book 77 minus those 42 | 14 | 14 |
| Full game | 77 | 70 | 64 |

Run 12 makes: corrected 10 rows / 19 points, all first half. Pending 21 rows / 45 points (31 first half, 14 second half). Rejected 9 rows / 16 points, all first half.

Both runs have 206 `shot` rows. The 206 timestamps match. `peak_frame`, `shot_result`, `through_rim`, `net_moved`, and `shot_kind` match on all 206. `source_frame` is null on every shot in both runs. 52 shots differ only in `player_name`, `jersey_number`, and `team_side` (25 of those are in the second half). Run 11 is null on those fields. Run 12 filled them in. Scoring rows are 40 in each run, 39 unique timestamps (48,200 ms appears twice in both). All 39 timestamps are shared. No scoring timestamp exists in only one run.

Three first-half scoring rows are `corrected` on run 11 and `rejected` on run 12: `made_free_throw` at 1,210,000 ms, `made_three` at 1,459,200 ms, `made_two` at 1,793,800 ms. That is 6 points, the whole drop in corrected points from 25 to 19. The shot under each one did not change. The other 37 scoring rows have the same `review_status`.

Scott's half rule is not in the events. Tags were not written as the first-half ledger. The book remainder was not written as the second-half ledger.

## First half against the tags

Tags file `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`. `lastTaggedTime` is `32:15.0`. 24 rows with `result` Make, 42 points. Liberty 27, Adrian 15. The confirmed book `halftime` block is the same 27–15. The scorekeeper had listed Liberty 25.

Within 8 seconds, run 12 has a scoring row for 17 of the 24 makes (31 points). Seven of those rows are `rejected`, so they are off the live card. Seven tag makes, 11 points, have no scoring row within 8 seconds.

Live first half is 50 points: 19 tag points kept as `corrected`, plus 31 pending points with no tag make within 8 seconds (15 scoring rows). Every corrected first-half point is one of those tags.

Six of the seven missing tag makes have no `shot` row within 12 seconds. The events in those windows are `possession_change`, plus one rebound or one turnover. Four of the six are free throws:

| Video time | Who | Shot | Nearby |
| --- | --- | --- | --- |
| 8:21.9 | Adrian Rodus | Free throw, 1 | No shot. Mendoza defensive rebound at 8:11.40 |
| 9:50.9 | Adrian Mendoza | Free throw, 1 | No shot |
| 19:41.7 | Liberty Colman | Free throw, 1 | No shot |
| 20:31.4 | Adrian Alvarez | Free throw, 1 | No shot. Turnover by player `7` at 20:38.84 |
| 26:22.0 | Adrian Mendoza | Two, 2 | No shot. Foster defensive rebound at 26:10.40 |
| 26:43.9 | Liberty Dayley | Two, 2 | No shot |
| 30:36.7 | Liberty Colman | Three, 3 | Misses, both rim and net false: player `3` `missed_three` at 30:25.80, Dayley `missed_two` at 30:47.40 |

The seven rejected tag matches all have `review_notes` "Shot did not go in." The shot used as proof:

| Tag | Tag player | Points | Proof shot |
| --- | --- | --- | --- |
| 0:41.9 two | Dayley | 2 | No separate `shot` row at 48,200 ms. The rejected `made_two` itself has `through_rim` false and `net_moved` false |
| 9:26.9 free throw | Mendoza | 1 | Dayley miss at 9:28.000 |
| 13:21.8 two | Dayley | 2 | Dayley miss at 13:17.400 |
| 15:36.2 free throw | Alvarez | 1 | Mendoza miss at 15:37.400 |
| 20:17.3 free throw | Alvarez | 1 | Foster miss at 20:10.000 |
| 24:21.0 three | Dayley | 3 | Foster miss at 24:19.200 |
| 29:52.9 two | Dayley | 2 | Foster miss at 29:53.800 |

Each proof shot that exists is `shot_result` miss with `through_rim` false and `net_moved` false. Several are a different player than the tag. A different player's miss is not proof that the tagged make did not go in.

## Second half against the book

Book second half is 35 points. Liberty 24: Dayley 9 (one two, two threes, one free throw), Colman 7 (two twos, one three), Sullivan 4 (two twos), Peterson 2 (one two), Flores 2 (one two). Adrian 11: Mendoza 6 (one two, four free throws), Alvarez 1 (one free throw), Rodus 2 (one two), Allison 2 (one two), Foster 0.

After 1,935,000 ms, run 12 has 123 shots: 6 `shot_result` make and 117 `shot_result` miss. The six makes are the only second-half points, 14, all `pending`. Same six timestamps as run 11. Zero second-half scoring rows have `film_tool_teach`. The tag file has no row after 32:15.0.

`generate_precision_events_from_segments` sets `shot_result` to make when `through_rim` or `net_moved` is true, and miss when both are false. All 117 second-half misses have both flags false. Misses that still have either flag true: 0. The six makes are `through_rim` true and `net_moved` false. Whether the net stayed false because no hoop was locked is unknown. Hoop lock is not on the shot row.

| Player | Book 2nd half | Run 12 | Row |
| --- | --- | --- | --- |
| Dayley | 9 | 5 | `made_three` 44.88 min, `made_two` 56.35 min |
| Colman | 7 | 0 | None |
| Sullivan | 4 | 0 | None |
| Peterson | 2 | 0 | None |
| Flores | 2 | 0 | None |
| Mendoza | 6 | 3 | `made_three` 44.97 min. Book second half is one two and four free throws |
| Alvarez | 1 | 2 | `made_two` 58.54 min. Book second half is one free throw |
| Rodus | 2 | 0 | None |
| Allison | 2 | 0 | None |
| Foster | 0 | 2 | `made_two` 57.70 min. His book two is already in the first-half tags |
| Player `7` | 0 | 2 | `made_two` 59.92 min |

Run 11 had cluster `5` on the 44.97 three and cluster `8` on the 56.35 two. Run 12 named those Mendoza and Dayley. The make call did not change.

## Full-game lines, run 12, pending plus corrected

Dayley 14 (book 26), Colman 4 (15), Peterson 2 (4), Mendoza 15 (13), Alvarez 7 (5), Foster 9 (2), Rodus 3 (4). Sullivan, Flores, and Allison are 0. Unnamed cluster `7` is 7. Unnamed cluster `0` is 3. Sum is 64.

Dayley, Daley, and Daly are the same Liberty player (player id 4, roster name `Daly`). Foster #22 is Adrian. Do not move him to Liberty. Liberty has no 2 and no 6. Do not assign cluster `7` to a Liberty player.

Book individuals: Liberty Dayley 26, Colman 15, Sullivan 4, Peterson 4, Flores 2. Adrian Mendoza 13, Alvarez 5, Rodus 4, Foster 2, Allison 2.

## Where to look

1. Second-half `shot` rows after 1,935,000 ms. All 117 misses have `through_rim` false and `net_moved` false. The September run has the same flags on the same frames. Do not expect a new YOLO pass of this film to add baskets until that read changes.
2. `review_notes` "Shot did not go in" on the seven rejected tag makes above. The companion `shot` is often a different player.
3. The six tag times with no `shot` within 12 seconds. Four are free throws.
4. The 15 pending first-half scoring rows with no tag make within 8 seconds. They are the 31 extra points.
5. The six second-half scoring rows. Foster's two and Alvarez's two do not match the book remainder. Naming did not create Colman, Sullivan, Peterson, Flores, Rodus, or Allison.

## How a point is stored

Only `event_type` of `made_two`, `made_three`, or `made_free_throw` adds points. There is no points column. `stats.py` trusts only `accepted` and `corrected`. The AI card also includes `pending`.

A cluster id in `events.player` (`7`, `0`) is a tracker, not a roster jersey. Labels look like `#40` or `40 - Dayley`.

Confirmed book: `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`. The `halftime` block is the true 27–15.

Do not change `schema.sql` without Scott. Do not turn auto-accept on (pull request 147). Do not change `models/ball_detector.pt` or `ball_confidence`. Do not start the teach loop. Opening `GET /api/analysis` for this game rewrites identity rows. Read `events`, or the HTML results page. Do not copy the book onto the rows to force 77.

Code that writes these rows: `event_generator.py`, `manual_tag_teach.py`, `track_identity.py`, `court_slot_mapping.py`, `game_boxscore.py`. `ai_bridge.py` does not count a make.
