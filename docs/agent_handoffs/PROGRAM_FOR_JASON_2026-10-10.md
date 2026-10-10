# Liberty for Jason — the whole program, then the current job

Updated: 2026-10-10. This is the document to read first.

`COUNT_FIXES_2026-10-10.md` and `COUNT_ROADMAP_2026-10-10.md` are only the current film-count job. They are not the whole program. This file is both: what Liberty is, what is already built, what the whole product still needs, and then the Adrian count in detail (what works, what does not, why, what was tried, and the order to finish).

If a number here disagrees with the bottom of `docs/agent_handoffs/HERMES.md`, this file wins. That bottom section is the September 30 rerun. If a number here disagrees with the 2026-10-09 pickup bullet in `ACTIVE.md`, the pickup bullet is the measurement and this file is the map.

## 1. What the program is

Liberty is a coach-facing basketball operations platform. One trusted event ledger feeds every module. An assistant coach is supposed to answer questions from that ledger later, not from a second database and not from guesses.

The coach should be able to:

- Keep a season, a roster, and a schedule
- Upload game film and tag it by hand
- Have the program write the game from the film: shots, makes, misses, who shot, which team, rebounds, turnovers, steals, fouls, then minutes and lineups
- Review the film, accept or reject a machine row, and keep a clip
- Run practice, a playbook, and scouting from the same players and games
- Ask a question and get an answer that cites reviewed rows

The film count is the hard part. Schedule, roster, playbook, scouting, practice, clips, and messaging already exist as pages. They are not the thing stuck on 10 October 2026. The ledger is. If the film writes the wrong shot, or writes no shot, every stat, lineup, scouting note, and assistant answer built on that game is wrong.

Adrian (Liberty at Adrian, book Liberty 51, Adrian 26, due 1 Nov 2026) is the first game that ledger has to get right against a book Scott has confirmed. It is not a separate product. The same path has to work on the next gym, on a film that has not been tagged shot by shot.

Home owns the database and the films. School uses Funnel only: https://liberty-coach.tail368a37.ts.net. Do not overwrite the home database from school. The database, the films, and the offline weights are not in git. A pull does not bring them.

## 2. What is already in the app

Flask app. `app.py` registers these blueprints: messaging, users, core, games, clips, stats, practice, player development, AI, playbook, scouting, bulk import, coach portal, and stat books. Schema is `schema.sql`. Default database is `film_analysis.db`. The app listens on port 8080. Debug stays off unless Scott asks.

The film pipeline is sequential. Do not reorganize it.

`ai_analyzer.py` runs detection. `event_generator.py` writes events from possessions and the ball track. `court_memory.py` and `net_detector.py` judge the rim and the net. `manual_tag_teach.py` applies Scott's tags. `game_boxscore.py` and `scoreboard_clock.py` are part of that same core. Hermes may edit `ai_bridge.py` only. Nothing in the core calls `ai_bridge.py`. A proposal leaves as JSON with `applied_to_core` false until Scott accepts it.

A make in the live writer is `ball_through_rim` or `net_moved_after_shot`. If both are false, the row is stored as a miss. There is no "unknown." Scott kept that on 2026-10-07. Points: made two is 2, made three is 3, made free throw is 1. A shot row by itself is 0. Counted review statuses are accepted, corrected, and pending. Rejected drops off the card.

Roles: Scott decides. Cursor implements and pushes. Jason's note is `JASON.md` on `jason-5-may-updates`. Brad's note is `BRAD.md` on `Brad/Claude`. Those two branches stay even with `main` when a pull request is merged. Hermes reads `docs/agent_handoffs/HERMES.md` and does not run git.

Names: Dayley, Daley, and Daly are one Liberty player, number 40, roster name Daly. Liberty has no 2 and no 6. Foster number 22 is Adrian. Liberty number 3 is Kariuki. A cluster id of 3 is not Kariuki. Ask Scott before treating any other close spelling as the same person.

## 3. What has been done

### The platform around the film

These are in the repo and had a validation pass on 2026-09-26 (`docs/validation/README.md`). That pass recorded 975 passed, then 988 after the open items. It is a bug-fix pass on the pages, not a claim that film stats match a book.

- Season, schedule, roster, games, NFHS source matching
- Video upload that does not overwrite a file of the same name
- Manual tagging in the film tool, clips, review
- Stats pages, scorebook upload, playbook and choreography, scouting, practice, player development
- Users, messaging, settings (admins change settings; a signed-in non-admin is refused)
- Assistant lookups that prefer an exact player name
- A coach portal
- A nightly full-film panel with Scott's gates: final score 100 percent, player points 100 percent, event precision at least 90 percent, event recall at least 90 percent

A June 2026 gap audit (`docs/BASE_PLATFORM_GAP_AUDIT.md`) said auth was disabled, there was no assistant query, and there was no possession table. Treat that audit as history. Later code added auth checks, messaging sessions, and an assistant query. The possession-table gap and the "one ledger" gap are still real. Do not start paid-package work from the June audit.

The nightly panel on 2026-10-09 (`docs/LEARNING_STATUS.md`) still fails every gate: final score 0 percent, player points 0 percent, event precision 4.9 percent, event recall 9.5 percent, on the fixed panel (Harper and Nyssa are the games that actually score). That is the same disease as Adrian, measured on other films: the machine events are not the game. HUDL teach state has keys stored. That is not a box score.

### The film tool and Scott's tags

Tags typed in the film tool used to live only in the browser. On 2026-10-07 the page loaded an older 246-row server file over his 378-row list. The rows were recovered. Now every add, edit, or delete is sent to the server about 0.8 seconds later, again every 30 seconds, and when the tab hides, but only if the rows changed. A save built on an older version is refused with 409. History copies sit in `data/film_tags/_history`. Typing in the 378-row table went from 4.7 seconds to 0.07 seconds. Proven on the live Adrian film, then the real tag file was put back.

A manual tag is truth. `reconcile_makes_with_shots` no longer rejects a make he already corrected. The 8-second match window stays (`MATCH_TOLERANCE_MS = 8000`). An unmatched tag is not inserted as a make. A shot after his EndQTR tag and before the next StartQTR is rejected, unless one of his shot tags is within 8 seconds. A film tag that says this team is on defense rejects an AI shot for that team within 8 seconds.

His Q1 review rejected 16 extra AI shots. His Q2 review rejected all 27 extra AI shots. Notes are on those rows. Several were a pass, an inbound, a foul, a timeout, or a player who was on defense. The 2:55.8 row stays a pending miss labeled tracker 7 until he says to change the tag. His note says that player was number 21 Colman.

Steals and fouls were written from his film-tool tags onto run 12 (14 accepted manual steals, 18 fouls, 5 personal fouls, 14 steal-linked turnovers). `emit_fouls` stays false. That heuristic credits the shooter after a long dead ball. It is not a foul. `credit_steal` stays the defender's active takeaway.

Five older reruns were removed from the home database on 2026-10-08 after an encrypted archive (`encrypted-archive/liberty_adrian_detections_20261007.enc`, commit `df83b66`). The passphrase is not in the repo. Do not commit `scottmcconnell1-bot-liberty-basketball-analysis-*.txt`.

### The Adrian count, as far as it has gone

Game id `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`. Film `uploads/nfhs_gam0a66d85e12.mp4`. Counting run `...__rerun_20261006_033941` (run 12) on the home database only.

Through three quarters his tags score Liberty 43, Adrian 24 (Q3 is Liberty 16, Adrian 9). That matches the book. Quarter ends: Q1 16:00.7, Q2 32:15.0, Q3 55:17.1. One Q4 Start QTR at 56:26.7 is the inbound. Q4 is not tagged. The fourth-quarter remainder is Liberty 8, Adrian 2. Full book 77 points.

On the night of 2026-10-08 the non-rejected make points on run 12 were 49 (14 twos, 5 threes, 6 free throws). The book is 77. 49 is not an accuracy claim. Later tag-copy rows were added for nine shots that had no detector row. Those copies are not detector results. Do not add more of them.

Code already on `main` from this work, and not a new detection pass:

- `load_hoop_track` uses the median of the surrounding samples, so one orange blob (the ball, or the exit sign) does not move the rim. A rim that stays put at the other end of the court is followed.
- `detect_hoop_cv` rejects a round blob. The rim is a wide band, about 65 by 30. The ball is about 44 by 46. The ball is not chosen as the rim.
- `build_ball_track` keeps a ball at the hoop when another box on that frame has higher confidence, and it drops a ball box that sits on a player who is in that spot just before and just after when another box is off the player.
- `rim_arc_shots` exists and is not called. On this film the same rise appears on tagged shots and on moments with no tag.

The rim is orange. The ball is brown-orange. The net is white and cone-shaped. The exit sign above the door is the only red object. Older notes that say "red" mean an OpenCV hue bin on this camera, not the paint.

## 4. What the whole program still needs

In this order. The film ledger is first because everything else reads it.

1. **A game the book agrees with.** Adrian, then one other film, without copying the book onto the rows. The panel gates (100 / 100 / 90 / 90) are the same requirement stated as numbers. They are failing.
2. **The writer has to notice a shot without a hand-built list of times.** Tag windows are how we grade a rule. They are not how a future game gets counted. Q4 of Adrian is the first untagged stretch.
3. **Who shot, which team, and 1, 2, or 3 points,** from the film, checked against his tags where he has them. Cluster id 3 is not Kariuki. Jersey identity is still wrong often enough that he rejected rows for the wrong player and for players on defense.
4. **Rebounds, turnovers, steals, fouls, and blocks** from the film under the rules he already set (2026-09-15). Steals and fouls on Adrian were written from his tags, not from the dead-ball heuristic. The heuristic stays off.
5. **Minutes and lineups** from substitutions he trusts. Do not build plus/minus on a ledger that has the wrong shots.
6. **One possession record** the film room, the box score, and scouting all read. The June audit is right about this gap even though it is wrong about auth.
7. **The assistant answers only from reviewed rows,** with the clip or the event id. It does not paper over a missing make.
8. **A second gym.** A rule that only works on this NFHS corner camera is not the product. Harper and Nyssa are already on the panel and are not close.
9. **Package boundaries** (who paid for stats, film room, scouting) come after the ledger is trustworthy. Do not start there.

## 5. The current job

Count Adrian from the film and check it against Liberty 51, Adrian 26. Accuracy over speed. Due 1 Nov 2026.

He was clear about the shape of a fix. A shot he tagged is correct. If the program never writes a row, the counting stats are wrong. He can reject a false row. He cannot correct a row that was never written. On the shots he tagged, the ball went through the hoop and the net moved. Arc height varies, so one rise number cannot be the reason to write nothing. A rule that adds shots he did not tag is also not the answer. Both problems stand: write the missing shots, and do not create extras he must reject.

Do not train another ball-weights file of the same kind. Do not change `models/ball_detector.pt` or `ball_confidence`. Do not drop the 170-pixel live rise until a test shows the missing rows appear and new untagged shots do not. Do not widen the 8-second window. Do not resume these finished agents (a resume puts the chip back on "Starting up"):

- `a4e6aae5-7ad7-48e0-a657-0faf69984c15` — Explore Adrian timestamp sync
- `5cb51e6b-92f6-4927-8332-2bbc4dae58c3` — Write steals and fouls
- `666207e1-46d2-4d32-89b7-39d86bd2de44` — Shot detection literature
- `62491ff3-e01c-42dd-b52e-9238c4113df3` — Raw boxes on nine shots

### What is working

- His tags save, and an old tab cannot overwrite them.
- A tag grades a machine row within 8 seconds. The tag wins.
- Between-quarters shots are rejected. Shots by the team that does not have the ball are rejected.
- Steals and fouls he tagged are on run 12. The dead-ball foul heuristic is off.
- The hoop track now runs to the end of the film (64:56), median-stabilized, so Q3 is not stuck on the first-half rim.
- A round blob is not chosen as the rim. A ball on a player's body loses to a ball in the air when both boxes exist.
- Separate ball and hoop classes do keep a ball box at the rim. A public model (BODD, not in git, not `ball_detector.pt`) does that. The v6 ball file also puts a box on the ball at the rim and sometimes inside the net, and it mostly leaves an empty net alone.
- Offline, the best make/miss score on his 111 shot tags is 85 right: 20 makes still missed, 6 misses called makes. The rule throws out a ball that slides sideways by more than 0.45 rim-widths between 80 and 180 pixels below the hoop. It is not turned on. No rows were written from it.

### What is not working, and why

The card is not the book. Run 12 does not contain the game.

The live make rule only runs after an arc has already been accepted. A live shot must also rise 170 pixels. Both-false is then a miss. On this film a lot of real shots never become a row, because the stored ball never reaches the rim the program locked, or the arc gate drops them. Copying his tag onto a corrected row fills the card and does not detect the shot. That was done for nine tags. Do not do it again.

When a ball box and a hoop box both exist, the line from the last point above the rim to the first point below it still cannot tell a make from a miss on this camera. The camera looks down from the side. A ball through the white net and a ball off the front of the orange rim draw the same line, and both can fall to the floor in front of the basket. Image-down is not "through the net."

The hoop box is sometimes not the rim. On 14:56.6 (896600) it sits on the backboard, above the rim, so the ball at the real rim is already "below" the box. On 29:36.5 (1776500) it sits on the top corner of the glass, and a later box is a ball in a player's hands.

The ball box leaves the ball. On 25:15.7 (1515700) it jumps to the wall left of the backboard. On 40:55.6 (2455600) the hoop is on the rim, then the box is in a player's hands, then a box is back at the rim. On 12:35.4 (755400) the ball hits short and falls in the lane. That is a miss. From this camera it looks like a make if "below the rim" is the test.

The white net cords knock the ball box out for a run of frames. The ball is still in the picture. The box returns when the ball is a clean circle again. Lowering the confidence cutoff does not mark the frames where the cords cross the ball. Production detection at image size 320 makes a ball in a 1920-wide frame about 7 pixels, so a clean ball in the air also blinks for a frame or two. That blink is a separate problem from the net.

v6 (`C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt`) has one class: `basketball`. Loaded and checked 2026-10-10. It is not a hoop detector. It is not in git.

`Scott_Hermes` commit `6143e83` does not fix any of this. The note says those weights detect basketball and hoop as two classes. They do not. The new function looks for a box named `hoop`, `rim`, or `basket`, finds none, and calls every window a miss. `hoop_on_rim` is set to true in the source. It never looks at the picture. The make test is "the ball was at the rim, then a later ball is in the column under it," which already scored 74 of 111 with 22 misses called makes. The function only grades timestamps you hand it. It does not watch a film, name the shooter, or write the ledger. Do not merge it as the fix. The direction in the note (hoop on the orange rim, ball stays on the ball) is still the next check. This commit does not do that check.

A later commit on this same pull request, `cbeb0ed`, rewrites the note. The note now says v6 is basketball only and the hoop comes from `detect_hoop_cv`. The code in that commit does not match the note. `find_hoop_on_orange_rim` still looks for a box named `hoop`, `rim`, or `basket`. `hoop_on_rim` is still set to true in the source. The make test is still the column-under-the-rim rule that scored 74 of 111. It has not been run on the 111 tags. Do not treat `cbeb0ed` as step 1 or step 3 of the roadmap.

### What was tried, and the result

All of these were offline. None were written into run 12 as the make rule. "Right" means the call matched his tag. There are 111 shot tags and 38 makes.

| Try | Right | Makes missed | Misses called makes |
| --- | --- | --- | --- |
| Color tracker, line through the opening | 74 | 37 (found 1 make) | 0 |
| Gap bridge | 75 | 19 | 17 |
| Orange patch tracked through the rim | 58 | 34 | 19 |
| Orange pixels inside the net cone | about 58 | makes and misses overlap | not a separator |
| Public ball+hoop model, line through the opening | 73 | 13 | 25 |
| Ball falls in one motion to the floor | 80 | 28 (found 10 makes) | 3 |
| Line from last ball into the rim to the next ball away | 67 | 15 | 29 |
| Slight arc, same idea | worse | found up to 29 makes | up to 45 |
| Incoming speed and arc, reject a next spot that arc cannot reach | 78 | 25 | 8 |
| Rim-scaled gravity, only on shots where the ball disappears | 78 | recovered 0 of the gap makes | added 2 |
| Search every missing frame along the path | 79 | 28 | 1 new |
| "Directly under the basket" with no floor required | — | 7 | 31 |
| v6 ball track, line through the opening, fall 180px | 80 | 20 | 11 |
| v6, one-frame fill between two real boxes | 80 | 20 | 11 |
| v6, ball must stay under the rim for the length of the net | 74 | 15 | 22 |
| v6, reject a sideways slide over 0.45 rim-widths from 80px to 180px below the hoop | 85 | 20 | 6 |

Loosening the pair window, the fall gap, or the drop each added more false makes than makes. Starting 1.6 seconds before the tag picked up the previous play. Template-matching the ball across the white net gained nothing. The net changes the ball's look.

Physics from the incoming arc rejects some front-rim misses and also rejects real makes that rattle, because the rim changes the speed. Gravity in inches, using the 18-inch rim and the camera tilt, was off by feet. This camera mixes height and depth. Dividing by the cosine of the tilt does not separate them.

Weight files v1 through v6 were trained off to the side. v1 learned to call the white net a basketball, because automatic orange labels sat on jerseys, faces, and the rim. Later files were taught on real ball boxes, empty nets, and balls placed under the rim with cords drawn across them. Held-out, a box landed on the path under the rim on 16 of 19 frames (was 6 of 19). Quiet empty nets stayed mostly quiet (7 or 8 of 305). That did not move the count past 80 until the sideways check, and the sideways check is still not good enough to ship. Another weights file of that kind will not fix the count on this camera.

`Scott_Hermes` was not scored on the 111 tags. From the code and the weights file, it would call the makes misses, because it never gets a hoop box.

### What still has to be accomplished on this job

- A hoop box on the orange rim on the frames where it currently sits on the glass or the backboard (896600, 1776500).
- A ball box that stays on the ball, and is rejected when it jumps to the wall or to a player's hands (1515700, 2455600, 1776500).
- A make/miss rule that beats 85 right on the 111 tags and does not call more than 6 misses makes. Then write it. Not before.
- Detector rows for the tagged shots that still have none, without a pile of untagged shots.
- The card compared to 51–26, shot by shot. Q4 is still untagged, so the last 8 and 2 points are not in his tags.
- The same rule running on a stretch with no hand-built timestamp list.

### What still has to be fixed, and must not be "fixed" the wrong way

- Do not copy his tags or the book onto the rows.
- Do not turn on `rim_arc_shots`.
- Do not change `ball_detector.pt` or `ball_confidence`.
- Do not train v7 of the same ball file and call it the fix.
- Do not merge `Scott_Hermes` `6143e83`.
- Do not drop both-false-is-a-miss until he says so, and not until a tested rule is better than 85 / 6.
- Do not ask him to accept or reject his own tags.
- Do not rename the 2:55.8 row to Colman until he says to change the tag.

## 6. Roadmap, in order

Do not skip a step because a note sounds confident. A step is done when its test was run on the film or the tags.

**Step 1. Hoop on the orange rim.** Offline. On 896600 and 1776500 the box sits on the rim band, not the glass and not the backboard. Use a model that actually emits a hoop, or the orange-band finder in `net_detector.py`. v6 does not emit a hoop. `test_a_round_ball_does_not_become_the_rim` and `test_a_one_sample_jump_does_not_move_the_rim` still pass.

**Step 2. Ball box stays on the ball.** Offline. On 1515700, 2455600, and 1776500 the box is on the ball, or the jump is rejected and the shot is not called a make. This is not another weights file of the same kind.

**Step 3. Score the 111 tags again.** Report right, makes missed, and misses called makes. The bar is more than 85 right, and misses called makes not higher than 6. A printout that only says "how many windows were called makes" is not a score. If the trade is worse, write the numbers in `ACTIVE.md` and do not ship.

**Step 4. Write the missing tagged shots.** Only after step 3. His tag within 8 seconds grades the row. Unmatched tags stay unmatched. The 170-pixel rise stays unless this same test shows the missing rows appear and new untagged shots do not.

**Step 5. Compare run 12 to the book.** Explain the gap shot by shot. Tags through three quarters are 43–24. Q4 remainder is 8–2 and is not tagged. Do not close the gap by copying 51–26 onto the rows.

**Step 6. Run the same rule with no timestamp list.** Q4, or one other Liberty film. Extra shots must be ones a person can see. The grader in `run_ball_hoop_experiment` cannot do this step.

**Step 7. Shooter, team, and points.** Check jersey and team against his tags. Fix the cases he already marked (wrong player, player on defense). Cluster 3 is not Kariuki.

**Step 8. The rest of the box score from the film.** Rebounds, turnovers, steals, fouls, blocks, under the 2026-09-15 rules. `emit_fouls` stays false.

**Step 9. Minutes and lineups,** then one possession record shared by the box score, the film room, and scouting.

**Step 10. The assistant, only on reviewed rows.** Then a second gym against the panel gates. Package boundaries after that.

Steps 1 through 6 are the current job. Steps 7 through 10 are the rest of the program, and they wait on a ledger that matches a book.
