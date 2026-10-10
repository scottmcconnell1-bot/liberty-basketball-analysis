# Brad — start here

Updated: 2026-10-09 night. This is the note on branch `Brad/Claude`. That branch stays even with `main`. Jason's copy is `JASON.md`. Hermes reads `docs/agent_handoffs/HERMES.md` and `docs/agent_handoffs/ACTIVE.md`.

## Pickup (2026-10-09 night)

This section wins over the 2026-10-08 night section where a number disagrees. The count is not solved. The measurement list is the 2026-10-09 pickup bullet in `docs/agent_handoffs/ACTIVE.md`.

Do not train another ball-weights file. Do not change `models/ball_detector.pt` or `ball_confidence`. Do not write `events` from the offline tests. Do not insert Scott's tags as makes. Do not resume the four finished agents listed in `ACTIVE.md`.

Best offline score on 111 shot tags: 85 right, 20 makes missed, 6 misses called makes (sideways slide under the rim greater than 0.45 rim-widths, from 80px below the hoop to 180px). Not shipped. The five remaining false makes, opened on the film: 755400 short and in the lane; 896600 hoop box on the backboard; 1515700 ball box jumps to the wall; 1776500 hoop box on the glass, later box in a player's hands; 2455600 hoop is on the rim, then the box is in someone's hands, then back at the rim. Next: hoop box on the orange rim, ball box stays on the ball. Rim is orange. Net is white. Exit sign is the only red object.

Code now in the repo, still not a new detection pass: `stabilize_hoop_track` (median of surrounding samples) inside `load_hoop_track`; round-blob rejection in `detect_hoop_cv`; player-carry filter in `build_ball_track`; `rim_arc_shots` is defined and not called. Tests: `test_a_round_ball_does_not_become_the_rim`, `test_a_one_sample_jump_does_not_move_the_rim`, `test_a_ball_on_a_player_loses_to_the_ball_in_the_air`, `test_the_possession_pass_does_not_write_a_bare_rim_arc`. Offline weights are on the home PC Temp folder only (`ball_net_runs\v6`), not in git.

## What Scott is having us do (2026-10-08 night)

This section wins where a number below disagrees. He asked for an accurate answer, not a fast one.

His film tags are truth. Do not ask him to grade his own tags. A tagged shot with no `events` row makes the count wrong. He can reject a false row. He cannot repair a missing one. He says the ball went through the hoop and the net moved on those shots, and that arc height varies too widely for a single rise threshold to decide that no shot occurred.

The open job is to find a detection method, from other basketball-film programs, that writes that row, then test it on run 12 before any gate is loosened. Do not insert his tags as AI makes to force the total. Do not remove `live_shot_min_ball_rise` (170) until that test says the missing rows appear and new untagged shots do not. Do not start another ball-detector pass. `ball_through_rim` / `net_moved` still run only after an arc is accepted (`event_generator.py`, the precision shot loop). Both-false remains a miss.

**Home database only** (`film_analysis.db` is not in git). Run 12 `...__rerun_20261006_033941`, queried 2026-10-08 night:

- `events` for that `game_id`: 1,509 rows.
- Non-rejected makes (`review_status` in accepted, corrected, pending): `made_two` 14 (28 pts), `made_three` 5 (15), `made_free_throw` 6 (6). Total 49. Book 77. Do not publish 49 as accuracy.

Code now in the repo, not yet a new detection pass:

- `shot_is_between_quarters` in `stat_rules.py`. `reject_shots_when_the_ball_is_not_in_play` in `manual_tag_teach.py`. An AI shot strictly after his EndQTR and before the next StartQTR is rejected. A shot tag within 8 seconds (`MATCH_TOLERANCE_MS`) protects it. His Q2 sheet plus this rule took non-rejected make points from 59 to 43.
- `build_ball_track(..., hoop_samples=)` keeps the ball within 280px above an on-court hoop when another box on that frame has higher confidence. `_shot_peak_index` uses that ball as the peak. Test: `test_a_lower_confidence_ball_at_the_hoop_is_the_shot`.
- Those six new `missed_two` rows exist only in the home database. Five were then `_correct_ai_from_manual` from the base game id’s `source_type='manual'` shot tags: Mendoza 2 miss at 6:13.7 (374800 ms graded from 373700), Colman FT make at 19:41.7, Dayley 2 make at 26:43.9, Rodus 3 miss at 28:28.1, Colman 3 make at 30:36.7. That is +6 points, 43 to 49. Foster `missed_two` at 773200 ms (12:53.2) stayed `pending`. No tag within 8 seconds.

Still no AI shot within 8 seconds, and still no row: Rodus FT 501900 (8:21.9), Mendoza FT 590900 (9:50.9), Alvarez FT 1231400 (20:31.4), Mendoza 2 1582000 (26:22.0). Checked this night: `ball_through_rim` geometry on stored `object_class='ball'` rows finds no box within 72px of the locked hoop (at the iron). `net_kicked` on `uploads/nfhs_gam0a66d85e12.mp4` under that same lock, including frames around the tag, is false for all four. Hoop samples for Mendoza’s free throw swing off the court (x as low as 16). He says the net he watched did move, so the lock is not that rim.

Looked at, not shipped: HoopCut scores a make when the segment from the last ball above the rim to the first ball below it intersects the hoop. NBAction scores when the ball is inside a small radius of a stabilized hoop. A 2020 basket-appearance method uses the picture around the basket, not arc height. None of those, pointed at the current lock, add these four rows. The unfinished work is to locate that rim, then test again.

You are a database analyst. The job is Liberty at Adrian. The official book is Liberty 51, Adrian 26 (77 points). The program is trying to count that game from the film. It is not close enough. Do not copy the book totals onto the AI rows to make them match.

The database is `film_analysis.db` in the repo root on Scott's home machine. It is about 379 MB after the 2026-10-08 prune (it was about 14.5 GB, almost all empty pages). It is not in git. School does not have this file. Do not overwrite it from another machine.

## 2026-10-07 and 2026-10-08 (read this first)

The sections under "Man defense" are the 2026-10-06 snapshot. Where a number disagrees, this section wins.

**Tags.** 378 rows in `data/film_tags/<base game id>.json`. Through three quarters they score Liberty 43, Adrian 24 (Q3 Liberty 16, Adrian 9), matching the book. Q3 ends 55:17.1. Jenkins at 55:14.2 is a 3PT miss, corrected from a free throw. One Q4 Start QTR at 56:26.7 is the inbound that starts the quarter. Q4 is not tagged. The fourth-quarter book remainder is Liberty 8, Adrian 2.

**The lost tags.** On 2026-10-07 the page replaced those 378 rows with a 246-row server file. `queueAutosave()` had existed since 2026-09-16 and had no caller, so the browser list was ahead of the server. Commit `664a129` then loaded the server copy first. The 378 rows were recovered from Chrome. Now every edit posts to `/api/film/<game_id>/manual-tags` (about 0.8 seconds, plus every 30 seconds, plus when the tab hides). The body includes `baseUpdatedAt`. `film_tool_tags.check_not_stale` returns 409 `stale` when that stamp is missing or older than the file, and the file is not written. History copies go to `data/film_tags/_history` at most every 2 minutes unless the list shrinks, which copies immediately. Newest 120, then one per hour for 72 hours.

**Tag is truth.** `reconcile_makes_with_shots` (`manual_tag_teach.py`) no longer selects rows with `review_status` `corrected` or `human_verified` 1. It was rejecting a tagged make when `through_rim` and `net_moved` were both false, including on a different player's shot at the same `timestamp_ms`. Seven run-12 makes were updated back to `review_status='corrected'`, `human_verified=1`, `review_notes='Film Tool teach'` (12 points). Before-state is local only, `tag-exports/rejected_makes_before_restore_20261007.json`, not in git. Run 12 make points where `review_status != 'rejected'`: corrected 31, pending 45, rejected 4. Sum of the first two is 76. Book is 77. Do not publish 76 as accuracy. The pending 45 are unchecked.

**Run 12 shot rows, makes actually seen** (`through_rim` or `net_moved`): Q1 19/46, Q2 14/37, Q3 2/86, Q4 4/37. The rest are stored as misses. Scott said keep that rule for now (`event_generator.py` around 806-846). 132 of 170 rebounds fall within 6 seconds after a both-false miss. 804 of 1,452 events are `possession_change`. `credit_steal` (`stat_rules.py`) returned false for every candidate (8 steal tags, 0 events). `emit_fouls` is false (18 foul tags, 0 events).

**Rows removed 2026-10-08.** These `analysis_key` / `game_id` values are gone from `analysis_runs`, `detections`, `events`, `review_items`, `human_corrections`, `shot_classifications`, `play_recognitions`, `track_identity_labels`, `player_minutes`, `player_effect`, `stats`, and event `provenance_records`:

- `...__rerun_20260915_193718` (failed)
- `...__rerun_20260927_042234` (failed)
- `...__rerun_20260928_031027`
- `...__rerun_20260930_160546`
- `...__rerun_20260930_191418` (run 11)

That was 4,139,840 `detections` rows and 7,055 `events` rows. Still present: the base id (866,471 detections) and run 12 `...__rerun_20261006_033941` (883,276 detections, 1,452 events). The detection rows are in `encrypted-archive/liberty_adrian_detections_20261007.enc` (AES-256-GCM). Every archived row was compared to the live table before encryption. The passphrase is not in the repo. `restore_detections.py` is inside the archive and skips ids that are already present. `events` indexes: `idx_events_game_ts (game_id, timestamp_ms)`, `idx_events_game_type (game_id, event_type)`.

**Self-check.** Scott started it on 2026-10-07 because the assistant had been wrong in ways that were not the film model: it said the book had no third quarter (the book is Adrian 9, Liberty 16 that quarter, running 24–43); the third-quarter tags vanished; Jenkins at 55:14.2 stayed a free throw; typed tags never reached the server. He asked for a check of the code, tools, and rules, in case the AI was only following those.

Checked and changed: `queueAutosave` had no caller (tags now post, and a stale `baseUpdatedAt` is a 409); the tag table was 4.7 seconds per keystroke and is 0.07 seconds; `reconcile_makes_with_shots` no longer rejects `corrected` or `human_verified` makes; `events` indexes added; `ACTIVE.md` cut from 35 KB and the branch/Hermes lines in `AUTHORITY.md` corrected; database compacted from 14.5 GB to about 379 MB after the five reruns above were removed. Not changed, by Scott's decision: a shot with both `through_rim` and `net_moved` false is still stored as a miss. `credit_steal` was explained and not loosened.

Test suite: first called an unknown hang. The run that finished took 26 minutes and reported 1,046 passed, 9 failed, 1 skipped, 25 errors, almost all `tests/test_transfer_bundle.py` (the fixture runs `bash scripts/build_transfer_bundle.sh`, which did not succeed on this Windows PC, so every test using that fixture errored). A second copy was killed and recorded nothing. No deadlock was shown. He has asked for the check to be run again.

## Where the film and the schema are

Film file: `uploads\nfhs_gam0a66d85e12.mp4` (video id 73). Do not use video 64.

Schema: `schema.sql`. Start with `analysis_runs`, `events`, `detections`, `track_identity_labels`, `players`, `roster_memberships`, and `stats`.

`events.game_id` is text. `analysis_runs.game_id` is an integer. Do not join them as the same type. The Adrian base key, comma included, is:

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`

## Man defense on the play court

This commit is the Liberty man shell. It does not change `events` or the Adrian count.

Open a play. **Add defense** and **Move them** are in the row with Play All. On a defense play the five X's are already on the floor. Each X is the color of the offensive player he guards. A click gives that player the ball and the shell shifts: high shoulder on the ball, on the line one pass away, half-deny on a high post while the ball is above the free-throw line, and a front when the ball is at the free-throw line or below. **Move them** makes a drag a cut. A post exchange hedges, goes over, and switches if the cutter beats the screen. Drag one X and the other four stay.

Build a picture is `/playbook/draw`. Add defense sets category Defense / Man.

Code: `static/js/man_defense.js`, `templates/playbook.html`, `templates/play_draw.html`, `blueprints/playbook.py`. A defender nudge is stored as `_defense_tune` on the step `_meta` object. It is not a new table. `schema.sql` did not change.

A new message while a job is running is added instruction. It does not replace the job. That rule is in `.cursor/rules/liberty-orchestration.mdc`.

## The run on the results page

The counts in this section are the 2026-10-06 snapshot. As of 2026-10-08, run 12 non-rejected make points are 76 (corrected 31, pending 45, rejected 4), not the 64 in the table. Run 11's rows are deleted. The 206-shot comparison is still valid as a description of what run 12 contains.

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

## Left off commit 664a129, included now

The film-library commit left these on the home machine. They are in this commit. They do not change the Adrian event rows.

- `data/hoopsalytics/full_film_panel_latest.json` and `data/hoopsalytics/full_film_panel_history.jsonl` are the learning-panel snapshot.
- `data/jersey_shades/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941.json` is the run 12 shirt-shade sidecar.
- `data/playbook/choreography/97.json`, `102.json`, `103.json`, `149.json`, and `150.json` are saved play movements. `85.json` only changed its saved time.

Still out:

- `adrian_quality.py`, `pytest.ini`, and `tests/test_ui_comprehensive.py` showed as modified, and the diff was only line endings. There is no code change to review.
- A GitHub credential file is untracked in the repo root. It stays out. Do not commit it and do not paste it into a note.
