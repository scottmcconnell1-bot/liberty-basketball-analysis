# Jason — start here

Updated: 2026-10-06. This file is on `main` once this note is merged. Branch `jason-5-may-updates` is kept even with `main`. Open that branch, then read this file. The same words are on `Brad/Claude` in `BRAD.md`.

The job is Liberty at Adrian. The official book is Liberty 51, Adrian 26 (77 points). The program is counting that game from the film. It is not the book yet. Do not copy the book totals onto the AI rows to make them match.

## The new run is not a better count

Results now open run 12, because it finished with corrected rows. It is not a better count than run 11.

Run 12, finished 2026-10-06 04:59:04 UTC, 1,452 events, no error:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941`

Film: `uploads\nfhs_gam0a66d85e12.mp4` (video id 73). Do not use video 64.

Run 11, the September 30 comparison, is:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_191418`

Live points are pending plus corrected. A `shot` row scores 0.

| | Truth | Run 11 live | Run 12 live |
| --- | --- | --- | --- |
| First half, through video 32:15 | 42 (Scott's tags) | 56 | 50 |
| Second half, after 32:15 | 35 (book minus those 42) | 14 | 14 |
| Full game | 77 | 70 | 64 |

Run 12 live makes are 64 points. Corrected makes are 10 rows / 19 points, all in the first half. Pending makes are 21 rows / 45 points (31 in the first half, 14 in the second). Rejected makes are 9 rows / 16 points, all in the first half.

The two runs have the same 206 shot rows. Same timestamps, same peak frames, same make-or-miss call, same `through_rim`, same `net_moved`. Run 12 filled in a name, jersey, or side on 52 of those shots, 25 of them in the second half. It did not find a new shot. Another detection pass of this same film will reprint these baskets until the rim and net read changes.

Run 12 also rejected three first-half makes that run 11 had kept as corrected: Alvarez's free throw at 20:10, Dayley's three at 24:19, and Dayley's two at 29:54. That is 6 points. It is the whole drop in corrected points, from 25 to 19. The shot under each one did not change.

Scott's rule for this game is still not in the events. First-half tags were not written in as the ledger. The second-half book was not written in either. The 64 points are the program's count.

## First half against the tags

The tags through 32:15 are 24 makes and 42 points. Liberty 27, Adrian 15. True halftime in the book is the same 27–15. The scorekeeper had listed Liberty 25.

Run 12 found a scoring row within 8 seconds for 17 of those 24 makes (31 points). Seven of those rows were then rejected, so they are not on the live card. Seven tag makes, 11 points, have no scoring row at all.

The live first half is 50 points: 19 of Scott's tag points, kept as corrected, plus 31 pending points that have no tag. Every corrected point in the first half is one of his tags. The 31 extras are why 50 can sit nearer to 42 than the old 56 and still be the wrong game.

Tag makes with no scoring row:

| Video time | Team | Player | Shot | Points | What is nearby |
| --- | --- | --- | --- | --- | --- |
| 8:21.9 | Adrian | Rodus | Free throw | 1 | No shot. A Mendoza rebound about 10 seconds earlier |
| 9:50.9 | Adrian | Mendoza | Free throw | 1 | No shot. Possession changes only |
| 19:41.7 | Liberty | Colman | Free throw | 1 | No shot. Possession changes only |
| 20:31.4 | Adrian | Alvarez | Free throw | 1 | No shot. A turnover by cluster 7 |
| 26:22.0 | Adrian | Mendoza | Two | 2 | No shot. A Foster rebound about 12 seconds earlier |
| 26:43.9 | Liberty | Dayley | Two | 2 | No shot. Possession changes only |
| 30:36.7 | Liberty | Colman | Three | 3 | A miss by player 3 at 30:26 and a Dayley miss at 30:47. Both have rim and net false |

Six of those seven were never stored as a shot. Four of the six are free throws. The Colman three was seen and stored as a miss.

Tag makes that were found and then rejected. The note on each one is "Shot did not go in." The shot used as that proof is often a different player, and that shot is a miss with `through_rim` false and `net_moved` false.

| Tag | Tag player | Points | Shot used as proof |
| --- | --- | --- | --- |
| 0:41.9 two | Dayley | 2 | No separate shot. The rejected make itself has rim and net false |
| 9:26.9 free throw | Mendoza | 1 | Dayley miss at 9:28 |
| 13:21.8 two | Dayley | 2 | Dayley miss at 13:17 |
| 15:36.2 free throw | Alvarez | 1 | Mendoza miss at 15:37 |
| 20:17.3 free throw | Alvarez | 1 | Foster miss at 20:10 |
| 24:21.0 three | Dayley | 3 | Foster miss at 24:19 |
| 29:52.9 two | Dayley | 2 | Foster miss at 29:54 |

A tag must not be rejected because a different player's nearby miss says the ball did not go in.

## Second half against the book

After 32:15 the book still has 35 points. Liberty 24: Dayley 9, Colman 7, Sullivan 4, Peterson 2, Flores 2. Adrian 11: Mendoza 6, Alvarez 1, Rodus 2, Allison 2, Foster 0.

Run 12 scored 14 points there, the same 14 as run 11, all pending. Tags stop at 32:15, so nothing in the second half was taught. Zero second-half scoring rows have `film_tool_teach`.

The film was watched. After 32:15 there are 123 shot rows: 6 called a make, 117 called a miss. The first half saw 83 shots and called 33 of them makes. A make is stored only when `through_rim` or `net_moved` is true (`generate_precision_events_from_segments`). All 117 second-half misses have both flags false. None of them still carries a make signal. The six makes are through the rim. The net flag is false on every one of them.

| Player | Book, 2nd half | Run 12 live | What the row is |
| --- | --- | --- | --- |
| Dayley | 9 | 5 | A three at 44:53 and a two at 56:21 |
| Colman | 7 | 0 | No second-half scoring row |
| Sullivan | 4 | 0 | No second-half scoring row |
| Peterson | 2 | 0 | No second-half scoring row |
| Flores | 2 | 0 | No second-half scoring row |
| Mendoza | 6 | 3 | One three at 44:58. The book second half is one two and four free throws |
| Alvarez | 1 | 2 | A two at 58:32. The book second half is one free throw |
| Rodus | 2 | 0 | No second-half scoring row |
| Allison | 2 | 0 | No second-half scoring row |
| Foster | 0 | 2 | A two at 57:42. His two in the book is already in the first-half tags |
| Unnamed 7 | 0 | 2 | A two at 59:55 |

The only second-half name changes from run 11 are the 44:58 three (cluster 5 to Mendoza) and the 56:21 two (cluster 8 to Dayley).

## Full-game lines on run 12

Pending plus corrected:

| Player | Run 12 | Book |
| --- | --- | --- |
| Dayley | 14 | 26 |
| Colman | 4 | 15 |
| Peterson | 2 | 4 |
| Sullivan | 0 | 4 |
| Flores | 0 | 2 |
| Mendoza | 15 | 13 |
| Alvarez | 7 | 5 |
| Foster | 9 | 2 |
| Rodus | 3 | 4 |
| Allison | 0 | 2 |
| Unnamed cluster `7` | 7 | — |
| Unnamed cluster `0` | 3 | — |

Dayley, Daley, and Daly are the same Liberty player. Foster #22 is Adrian. Do not move him to Liberty. Scott said Liberty has no 2 and no 6. Cluster `7` stays unnamed. Do not assign those points to a Liberty player.

## Where to work

1. Second-half rim and net read. 117 shots are misses because both `through_rim` and `net_moved` are false. The September run read those same frames the same way.
2. A nearby miss rejects a real tag. 12 real first-half points were found and then removed. The proof shot is often a different player.
3. Shots the detector never saw. 11 tag points have no scoring row. Six of those seven makes have no shot within 12 seconds. Four of the six are free throws.
4. Pending points with no tag. 31 first-half points are on the live card and are not in the tags.
5. Names on the six second-half baskets. Foster's second-half two and Alvarez's two do not match the book. Naming did not create the missing Colman, Sullivan, Peterson, Flores, Rodus, or Allison points.

## Do not

- Merge pull request 147. It turns auto-accept on at 0.85. Scott has not approved that.
- Change `schema.sql`, `models/ball_detector.pt`, or `ball_confidence`.
- Start the teach loop.
- Call `ai_bridge.py` from the core. A make is `ball_through_rim` or `net_moved_after_shot` in the core.
- Open `GET /api/analysis` for this game. That request rewrites identity rows. Read `events`, or the HTML results page.
- Treat two close name spellings as the same player unless Scott has said so.
- Copy the book totals onto the AI rows to make the card say 77.

Code that writes these rows: `event_generator.py`, `manual_tag_teach.py`, `track_identity.py`, `court_slot_mapping.py`, `game_boxscore.py`. The database `film_analysis.db` is on Scott's home machine only. It is not in git.

Tags: `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`. Confirmed book: `data/stat_books/confirmed/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`.
