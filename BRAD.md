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

## The rest of the box score

Match rule: one live row (`pending`, `corrected`, or `accepted`) of the same stat within 8,000 ms of a first-half tag. Tags are truth through 32:15.0. Book fields `fga`, `tpa`, `reb`, `ast`, `stl`, `blk`, `to`, and `fouls` are null on all 28 players. Second half can be checked only on points and on `ftm` / `fta`.

Event types present on this run include `shot`, `made_two`, `missed_two`, `made_three`, `missed_three`, `made_free_throw`, `missed_free_throw`, `rebound_offensive`, `rebound_defensive`, `turnover`, `assist`, and `block`. There is no `steal` row and no `foul`, `foul_personal`, `foul_shooting`, or `foul_technical` row.

| Stat | Verdict | Tags matched | Tags missed | Extra live |
| --- | --- | --- | --- | --- |
| Field-goal attempts | Partly | 31 of 48 | 17 | 46 |
| Free throws | Fails | 11 of 21 | 10 | 4 |
| Rebounds | Fails | 13 of 29 | 16 | 39 |
| Turnovers | Fails | 3 of 16 | 13 | 17 |
| Assists | Fails | 0 of 6 | 6 | 8 |
| Steals | Not written | 0 of 8 | 8 | 0 |
| Fouls | Not written | 0 of 18 | 18 | 0 |
| Blocks | Unchecked | No `Block` tag | — | 4, all `timestamp_ms` > 1,935,000 |

Field goals: tag `2PT` 31 and `3PT` 17, all at or before 32:15. Count one live attempt per timestamp. A second row with `derived_from` `shot` is the same attempt. A `shot` with `shot_kind` `ft` is a free throw and is not in the 48. Live first half is 77 attempts. 29 of the 31 time matches have the same two or three on the classified event (`made_two`, `missed_two`, `made_three`, `missed_three`). Second half is 119 live attempts: 58 twos and 61 threes. `fga` and `tpa` are null, so there is no remainder.

Free throws: tag `FT` is 9 Make and 12 Miss. The 11 live matches are all `corrected`. Live makes that match are Rodus and one Alvarez. Rejected `made_free_throw` rows sit on three tags the live set missed: Mendoza near 9:26.9, Alvarez near 15:36.2, Alvarez near 20:17.3. After 1,935,000 ms the live free throws are 4 pending Dayley `missed_free_throw` rows and no makes.

Book `ftm`/`fta` minus first-half tags:

| Player | Book | Tags | Remainder | Run 12 after 32:15 |
| --- | --- | --- | --- | --- |
| Dayley | 1/2 | 0 | 1 make, 1 miss | 0 makes, 4 misses |
| Flores | 0/2 | 0 | 2 misses | 0 |
| Colman | 1/3 | 1/3 | 0 | 0 |
| Mendoza | 6/10 | 2/4 | 4 makes, 2 misses | 0 |
| Alvarez | 5/8 | 4/6 | 1 make, 1 miss | 0 |
| Foster | 0/2 | 0 | 2 misses | 0 |
| Adrian 32 | 0/2 | 0 | 2 misses | 0 |
| Linkhart 12 | 0/2 | 0/2 | 0 | 0 |
| Rodus | 2/4 | 2/6 | Tags already exceed the book | 0 |

Liberty remainder is 1 make and 3 misses. Adrian remainder is 5 makes and 7 misses.

Rebounds: tag `OffRebound` 14, `DefRebound` 15. AI is `rebound_offensive` 89 (79 pending, 9 corrected, 1 rejected) and `rebound_defensive` 81 (76 pending, 4 corrected, 1 rejected). Same-type matches within 8 seconds: 9 offensive and 4 defensive. All 13 are `corrected` and have `film_tool_teach`. Pending matches: 0. The closer pair at about 5:41 names the tag Peterson and the row Dayley. On 9 of the 13 corrected rows, `details_json.rebound_kind` is the opposite of `event_type` (7 offensive rows still say `dreb`; 2 defensive rows still say `oreb`). After 1,935,000 ms: 116 pending rows, 64 offensive and 52 defensive.

Turnovers: tag `Turnover` 16. AI `turnover` is 40 rows: 37 pending, 3 corrected, 0 rejected. The 3 corrected rows are the only matches, and the player agrees: Kariuki at 7:23.5 and 18:07.8, Foster at 13:17.4. First-half live is 20 rows, so 17 are extra. After 1,935,000 ms: 20 pending. Book `to` is null.

Assists: tag `Assist` 6 (Peterson 1, Sullivan 2, Colman 2, Foster 1). AI `assist` is 10 rows, all pending, 8 at or before 1,935,000 ms and 2 after. Matched: 0. Nearest gap is 34.5 seconds. Book `ast` is null.

Steals: tag `Steal` 8. Liberty Colman 2, Sullivan 1, Dayley 1. Adrian Foster 2, Linkhart 12 one, Mendoza 1. No event type and no `details_json` text contains steal. Book `stl` is null.

Fouls: tag `Foul` 18, all `category` Defense, all at or before 31:47.2. Liberty Price 3, Musgrave 2, Colman 2, Peterson 2, Flores 1, Sullivan 1, Leach 1, Dayley 1. Adrian Linkhart 12 three, Linkhart 11 one, Alvarez 1. AI foul count is 0. Book `fouls` is null. Do not count a free throw or a `possession_change` as a foul.

Blocks: no tag `eventtype` Block. Book `blk` is null. AI `block` is 4 rows, all pending, all after 1,935,000 ms: event 31266 Dayley #40 at 2,356,480 ms, event 31509 player `3` at 3,008,400 ms (no jersey, no team; do not assign to Liberty), event 31536 Foster #22 at 3,055,320 ms, event 31816 Alvarez #25 at 3,711,400 ms.

## Where to look

1. Second-half `shot` rows after 1,935,000 ms. All 117 misses have `through_rim` false and `net_moved` false. The September run has the same flags on the same frames. Do not expect a new YOLO pass of this film to add baskets until that read changes.
2. `review_notes` "Shot did not go in" on the seven rejected tag makes above. The companion `shot` is often a different player.
3. The six tag times with no `shot` within 12 seconds. Four are free throws.
4. The 15 pending first-half scoring rows with no tag make within 8 seconds. They are the 31 extra points.
5. The six second-half scoring rows. Foster's two and Alvarez's two do not match the book remainder. Naming did not create Colman, Sullivan, Peterson, Flores, Rodus, or Allison.
6. Fouls and steals. Tag counts are 18 and 8. This run has zero rows. The event types exist in `helpers.py` (`FOUL_EVENT_CODES`) and in `game_boxscore.py`. A new detection pass will not fill them until something writes the rows.
7. `rebound_offensive`, `rebound_defensive`, `turnover`, and `assist`. The tag matches are the `corrected` rows that already have `film_tool_teach`. Pending rebounds and every `assist` miss the tags. Nine corrected rebounds have `rebound_kind` opposite `event_type`.
8. Extra field-goal attempts. 31 of 48 tagged attempts are within 8 seconds of a live timestamp, and 46 other first-half timestamps match no tag.

## How a point is stored

Only `event_type` of `made_two`, `made_three`, or `made_free_throw` adds points. There is no points column. `stats.py` trusts only `accepted` and `corrected`. The AI card also includes `pending`.

A cluster id in `events.player` (`7`, `0`) is a tracker, not a roster jersey. Labels look like `#40` or `40 - Dayley`.

Confirmed book: `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`. The `halftime` block is the true 27–15.

Do not change `schema.sql` without Scott. Do not turn auto-accept on (pull request 147). Do not change `models/ball_detector.pt` or `ball_confidence`. Do not start the teach loop. Opening `GET /api/analysis` for this game rewrites identity rows. Read `events`, or the HTML results page. Do not copy the book onto the rows to force 77.

Code that writes these rows: `event_generator.py`, `manual_tag_teach.py`, `track_identity.py`, `court_slot_mapping.py`, `game_boxscore.py`. `ai_bridge.py` does not count a make.
