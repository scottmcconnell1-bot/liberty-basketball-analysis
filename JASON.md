# Jason — start here

Updated: 2026-10-08. Branch `jason-5-may-updates` is kept even with `main`. The same note is `BRAD.md` on `Brad/Claude`.

The job is Liberty at Adrian. The official book is Liberty 51, Adrian 26 (77 points). The program is counting that game from the film. It is not the book yet. Do not copy the book totals onto the AI rows to make them match.

## 2026-10-07 and 2026-10-08 (read this first)

The sections under "Man defense" are the 2026-10-06 snapshot. Where they disagree with this section, this section wins. Run 12 is still the run to open. Run 11 is gone from the database.

### Scott's tags are the book through three quarters

378 tag rows are saved on the server in `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`. Quarter ends: Q1 16:00.7, Q2 32:15.0, Q3 55:17.1. The last Q3 play is Jenkins' 3-point miss at 55:14.2. It had been stored as a free throw and was corrected. Those tags score Liberty 43, Adrian 24 after three quarters (Q3 is Liberty 16, Adrian 9). That matches the book. The fourth-quarter remainder is Liberty 8, Adrian 2. The one Q4 row, Start QTR at 56:26.7, is the ball being handed in to start the quarter. It belongs. Q4 is not tagged yet.

On the evening of 2026-10-07 the 378 rows disappeared from the page. The server file was an older 246-row copy. The page loaded that copy and replaced the newer list, which lived only in Chrome. The rows were recovered from Chrome's older storage. The cause was in our code: `queueAutosave()` had existed since 2026-09-16 and nothing called it, so tags reached the server only from Resume, Save, or Teach AI. Commit `664a129` (2026-10-06) removed Resume and opened the server copy first.

### Tags now save, and an old tab cannot overwrite a newer one

Every add, edit, or delete is sent to the server about 0.8 seconds later, and again every 30 seconds and when the tab is hidden, but only when the rows actually changed. Each save names the server version it was built on. The server refuses a save built on an older version, or a save with no version (a tab opened before this fix), and keeps its copy. The refused tab sets its own list aside in the browser and shows the newer copy. Dated copies are kept in `data/film_tags/_history`: one every 2 minutes while tags are changing, the newest 120 in full, then one per hour for 72 hours. Typing in the 378-row table took 4.7 seconds and now takes 0.07 seconds. Checked on the live Adrian film, then the real tag file was put back byte for byte.

### A tag Scott entered is truth

`reconcile_makes_with_shots` was rejecting a tagged make because a different shot at that same moment had `through_rim` false and `net_moved` false. It no longer rejects a make that is `corrected` or `human_verified`. Seven of those makes on run 12, 12 points, were restored. Run 12's non-rejected makes are now 76 points: 17 corrected rows (31 points) plus 21 pending rows (45 points). The book is 77. The 45 pending points are not checked against the film, so 76 is not an accuracy number. The four rejected rows that were only on run 11 went away with that rerun.

### What the count still gets wrong

Run 12, `...__rerun_20261006_033941`, is still 1,452 events and the same 206 shot rows as before. Shots where a make was actually seen (ball through the rim, or the net moved): Q1 19 of 46, Q2 14 of 37, Q3 2 of 86, Q4 4 of 37. Every other shot is stored as a miss. There is no "not seen" result. Q3 has 86 shot rows against about 42 real attempts in the tags. Scott said to keep writing an unseen shot as a miss for now. It may need refining. Do not change `event_generator.py` for this until he says so.

132 of 170 rebounds are written within 6 seconds after one of those unseen misses. 804 of the 1,452 events are `possession_change`, which the box score ignores. Steals: `credit_steal` wrote none, against 8 steal tags. It only counts a steal when the turnover did not follow a shot, play was not stopped, the ball was lost abruptly, and the next touch was close. Fouls are off on purpose (`emit_fouls` is false); there are 18 foul tags and zero foul events. The second-half drop (about 40% of first-half shots show a make, 2% in Q3) looks like the hoop or net lock failing on the second-half camera. That is not yet checked on frames. Another detection pass of this film will reprint the same baskets until that read changes.

### The database

Five older Adrian reruns were removed on 2026-10-08, after their 4,139,840 detection rows had been checked one by one against an archive. The archive is `encrypted-archive/liberty_adrian_detections_20261007.enc` on `main` (AES-256-GCM, commit `df83b66`). The passphrase is not in the repo. Scott has it on the home PC, outside the repo. `encrypted-archive/README.md` says how to put the rows back.

Removed: `__rerun_20260915_193718`, `__rerun_20260927_042234`, `__rerun_20260928_031027`, `__rerun_20260930_160546`, and run 11 `__rerun_20260930_191418`. Kept: the base game id, and run 12. `film_analysis.db` on the home machine is about 379 MB. It was 14.5 GB, almost all of that empty pages. It is not in git. `events` now has indexes `idx_events_game_ts` and `idx_events_game_type`.

### Self-check (Scott, 2026-10-07 night)

Scott started this because the assistant had been making errors, and he did not want those treated as the film AI being wrong. The errors he had already caught: the assistant said the book had no third-quarter line (the book says Adrian 9, Liberty 16 for the quarter, running Adrian 24, Liberty 43); his third-quarter tags disappeared; Jenkins at 55:14.2 was left as a free throw; and tags he typed were not reaching the server. His question was whether the AI was doing exactly what the code, tools, and rules say, and those were the thing written wrong.

What the check found, and what was done:

- The tag loss was our save path. `queueAutosave()` existed and was never called. Fixed. An old tab can no longer overwrite a newer server copy.
- The tag table redrew the roster on every keystroke. Measured 4.7 seconds, then 0.07 seconds, same results.
- `reconcile_makes_with_shots` rejected Scott's tagged makes using another player's miss. He said a manual tag is always truth. That rejection is stopped, and the seven run-12 makes were restored.
- A shot with no rim and no net is stored as a miss, and most rebounds are built from those rows. Scott said keep that for now. It may need refining. Not changed.
- `credit_steal` wrote no steals. Explained. Not loosened.
- `events` had no index. Indexes added, with his OK.
- `ACTIVE.md` had grown to 35 KB of stacked, sometimes contradictory notes, and `AUTHORITY.md` still said to work on a `cursor/...` branch and that Hermes was not in the project. Slimmed and corrected. The old `ACTIVE.md` is in `docs/agent_handoffs/ARCHIVE/`.
- The database was 14.5 GB because empty pages and six copies of the Adrian detections were still in it. Archived, encrypted, compacted, then the five older reruns removed, with his OK.

The full test suite was first reported as an unknown hang. That report was incomplete. One run did finish, in 26 minutes: 1,046 passed, 9 failed, 1 skipped, 25 errors. Almost all of the failures are `tests/test_transfer_bundle.py`, which builds a bundle with `bash`. On this Windows machine that build did not succeed, so the whole group failed together. A second copy of the same run was stopped and has no result. It is not established that a test deadlocked. Scott has asked for the self-check to be run again. It is not finished.

## Man defense on the play court

This commit is the Liberty man shell. It is not a new Adrian count.

Open a play. **Add defense** and **Move them** are in the row with Play All. On a defense play the five X's are already on the floor. Each X is the color of the offensive player he guards.

Click an offensive player and he has the ball. The shell shifts.

- On the ball, the X takes the high shoulder. The middle is closed. The sideline and the baseline stay open.
- One pass away, the X is on the line between his man and the ball.
- A high post is half-denied while the ball is above the free-throw line.
- When the ball is at the free-throw line or below, the posts are fronted.
- Two passes away, one foot is in the lane. Three passes away, the X is help-side in the lane, in front of a lob.
- Drag an offensive player and the X's answer on the way. **Move them** makes that drag a cut. On a post exchange the screener's X hedges, the cutter's X goes over, and they switch if the cutter beats the screen.
- Drag one X and the other four stay. That nudge stays relative to the ball.

Build a picture (`/playbook/draw`) has the same two buttons on the court bar. Add defense sets the category to Defense / Man.

Code: `static/js/man_defense.js`, `templates/playbook.html`, `templates/play_draw.html`, `blueprints/playbook.py`.

A new message while a job is running is added instruction. It does not replace the job. That rule is in `.cursor/rules/liberty-orchestration.mdc`.

## The new run is not a better count

The point totals in this section are the 2026-10-06 snapshot. Run 12's live makes are 76 points as of 2026-10-08 (31 corrected, 45 pending), not the 64 below, because seven tagged makes were restored. Run 11 is no longer in the database. The shot-by-shot comparison is still the right diagnosis.

Results now open run 12, because it finished with corrected rows. It is not a better count than run 11 was.

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

## The rest of the box score

Made baskets were only part of the check. Each other stat was matched to Scott's first-half tags. A match is one live row of the same stat within 8 seconds. Live is pending, corrected, or accepted. The book columns for attempts, rebounds, assists, steals, blocks, turnovers, and fouls are empty on all 28 players, so the second half can be checked only for points and free throws.

| Stat | Verdict | Tags matched | Tags missed | Extra live rows |
| --- | --- | --- | --- | --- |
| Field-goal attempts | Partly | 31 of 48 | 17 | 46 |
| Free throws | Fails | 11 of 21 | 10 | 4 |
| Rebounds | Fails | 13 of 29 | 16 | 39 |
| Turnovers | Fails | 3 of 16 | 13 | 17 |
| Assists | Fails | 0 of 6 | 6 | 8 |
| Steals | Not written | 0 of 8 | 8 | 0 |
| Fouls | Not written | 0 of 18 | 18 | 0 |
| Blocks | Unchecked | No tags | — | 4, all after 32:15 |

Field-goal attempts are the only count that lands on the tags without a prior correction. The tags are 31 twos and 17 threes. 29 of the 31 time matches are the same two or three as the tag. The first half still has 46 other live attempts, so the player totals do not match. The second half has 119 live attempts, 58 twos and 61 threes, and the book has no attempt total.

Free throws fail on the makes. The tags are 9 makes and 12 misses. Only 2 of the 9 makes are on the live card: Rodus, and one Alvarez. Three more tagged makes are on the run and rejected: Mendoza at 9:26, Alvarez at 15:36, and Alvarez at 20:17. After 32:15 the run has 4 Dayley misses and no Adrian free throws. The book remainder is Liberty 1 make and 3 misses (Dayley 1-for-2, Flores 0-for-2) and Adrian 5 makes and 7 misses (Mendoza 4 makes and 2 misses, Alvarez 1 and 1, Foster 0-for-2, number 32 0-for-2). Rodus is the exception: the first-half tags already list 6 attempts, and the full book lists 4.

Rebounds fail except where Scott already corrected them. The tags are 14 offensive and 15 defensive. All 13 matches are corrected rows that already carry a film-tool teach mark. No pending rebound is within 8 seconds of a tag. One matched pair names Peterson's offensive rebound at 5:41 as Dayley. On 9 of the 13 taught rows, the detail flag says the opposite of the event type. After 32:15 the run has 116 pending rebounds, 64 offensive and 52 defensive, and no book total.

Turnovers fail the same way. 16 tags. The 3 matches are the only corrected turnovers, and the player agrees on each: Kariuki at 7:23 and 18:07, Foster at 13:17. The other 37 turnovers are pending. 17 first-half live rows match no tag. After 32:15 there are 20 more pending turnovers and no book total.

Assists fail. The 6 tags are Peterson 1, Sullivan 2, Colman 2, and Foster 1. The run has 10 pending assists. None is within 8 seconds of a tag. The closest gap is 34 seconds.

Steals are not written. 8 tags, zero steal events. Liberty: Colman 2, Sullivan 1, Dayley 1. Adrian: Foster 2, Linkhart 12 has 1, Mendoza 1.

Fouls are not written. 18 tags, zero foul events. Liberty: Price 3, Musgrave 2, Colman 2, Peterson 2, Flores 1, Sullivan 1, Leach 1, Dayley 1. Adrian: Linkhart 12 has 3, Linkhart 11 has 1, Alvarez 1. Foster has none in the tags.

Blocks cannot be scored. The tag file has no block. The book block column is empty. The run stored 4 pending blocks, all after 32:15: Dayley at 39:16, an unnamed tracker at 50:08, Foster at 50:55, and Alvarez at 61:51.

The rows that agree with the tags, other than field-goal attempts, are rows already corrected from the film tool. Another detection pass of this film will reprint the same shots. It will not create fouls or steals.

## Where to work

1. Second-half rim and net read. 117 shots are misses because both `through_rim` and `net_moved` are false. The September run read those same frames the same way.
2. A nearby miss rejects a real tag. 12 real first-half points were found and then removed. The proof shot is often a different player.
3. Shots the detector never saw. 11 tag points have no scoring row. Six of those seven makes have no shot within 12 seconds. Four of the six are free throws.
4. Pending points with no tag. 31 first-half points are on the live card and are not in the tags.
5. Names on the six second-half baskets. Foster's second-half two and Alvarez's two do not match the book. Naming did not create the missing Colman, Sullivan, Peterson, Flores, Rodus, or Allison points.
6. Fouls and steals are never written. The tags have 18 fouls and 8 steals. This run has zero events of either type. The pipeline already knows those event types.
7. Rebounds, turnovers, and assists at the wrong time. The only tag matches are rows already taught: 13 rebounds and 3 turnovers. Pending rebounds and all 10 assists miss every tag.
8. Extra field-goal attempts. 31 of 48 tagged attempts are near a live row, and 46 other live attempts in the half match no tag.

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

## Left off commit 664a129, included now

The film-library commit left these on the home machine. They are in this commit.

- `data/hoopsalytics/full_film_panel_latest.json` and `data/hoopsalytics/full_film_panel_history.jsonl` are the learning-panel snapshot. They are not the tagger or the video library.
- `data/jersey_shades/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941.json` is the run 12 shirt-shade sidecar.
- `data/playbook/choreography/97.json`, `102.json`, `103.json`, `149.json`, and `150.json` are saved play movements. `85.json` only changed its saved time.

Still out:

- `adrian_quality.py`, `pytest.ini`, and `tests/test_ui_comprehensive.py` showed as modified, and the diff was only line endings. There is no code change to review.
- A GitHub credential file is untracked in the repo root. It stays out. Do not commit it and do not paste it into a note.
