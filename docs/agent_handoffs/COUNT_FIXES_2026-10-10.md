# What needs done and what needs fixed

Updated: 2026-10-10. This file is the current Adrian count only. The whole program is `PROGRAM_FOR_JASON_2026-10-10.md`. Read this with `COUNT_ROADMAP_2026-10-10.md`. If this file and `ACTIVE.md` disagree on a number from 2026-10-09, this file wins for the make/miss count. `ACTIVE.md` still wins for steals, fouls, tags, and the teach rules.

## What the program is for

Liberty is a coach-facing ledger. From a film, write the game: shots, makes, misses, who shot, which team, then minutes, lineups, and the rest. The same path has to work on the next gym, not only on one tagged list.

Adrian is the first film that ledger has to get right. Book: Liberty 51, Adrian 26. Due 1 Nov 2026. Accuracy over speed.

## Read first

1. This file
2. `docs/agent_handoffs/COUNT_ROADMAP_2026-10-10.md`
3. The 2026-10-09 pickup bullet in `docs/agent_handoffs/ACTIVE.md`
4. `docs/agent_handoffs/HERMES.md` through the Architecture section only. Stop before "Where the Adrian count stands." That section is the September 30 rerun and is not the counting run.

Do not resume these finished agents. A resume puts the chip back on "Starting up."

- `a4e6aae5-7ad7-48e0-a657-0faf69984c15` — Explore Adrian timestamp sync
- `5cb51e6b-92f6-4927-8332-2bbc4dae58c3` — Write steals and fouls
- `666207e1-46d2-4d32-89b7-39d86bd2de44` — Shot detection literature
- `62491ff3-e01c-42dd-b52e-9238c4113df3` — Raw boxes on nine shots

## Proven

Counting run, home database only (not in git): `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941` (run 12). Film: `uploads/nfhs_gam0a66d85e12.mp4`.

Scott's tags through three quarters score Liberty 43, Adrian 24. That matches the book. Q4 is not tagged except Start QTR at 56:26.7. The Q4 remainder is Liberty 8, Adrian 2.

111 shot tags: 38 makes, 73 misses. Best offline score, not written to the database: 85 right, 20 makes still missed, 6 misses called makes. The rule that got there throws out a ball that slides sideways by more than 0.45 rim-widths between 80 and 180 pixels below the hoop. Requiring the ball to stay under the rim was worse: 74 right, 22 misses called makes.

The v6 weights at `C:\Users\scott\AppData\Local\Temp\ball_net_runs\v6\weights\best.pt` have one class: `basketball`. Loaded and checked 2026-10-10. They are not in git. They are not `models/ball_detector.pt`.

A public model that really does detect basketball and hoop as different classes was already run (BODD, not in git). It keeps both boxes. On this camera the line through the opening still cannot tell a ball through the white net from a ball off the front of the orange rim.

The rim is orange. The ball is brown-orange. The net is white and cone-shaped. The exit sign above the door is the only red object. Do not call the rim red paint. Hue bins in older notes are camera numbers, not the paint color.

## What needs fixed

### 1. The hoop box is not always the rim

On the film, some hoop boxes sit on the glass or the backboard, above the orange rim. A ball at the real rim is then already "below" that box, so a miss looks like a make.

Opened frames:

- 14:56.6 (896600): hoop box on the backboard, above the rim.
- 29:36.5 (1776500): hoop box on the top corner of the glass. A later box is a ball in a player's hands.

`detect_hoop_cv` now rejects a round blob, so the ball is not chosen as the rim. It does not yet reject a box on the glass.

### 2. The ball box leaves the ball

- 25:15.7 (1515700): the box leaves the ball and sits on the wall left of the backboard.
- 40:55.6 (2455600): the hoop is on the rim, then the box is on a ball in a player's hands well below the rim, then a box is back at the rim.
- 12:35.4 (755400): the ball hits short and falls in the lane in front of the basket. Image-down from this camera is the floor in front, not "through the net."

`build_ball_track` drops a ball box that sits on a player who is present just before and just after, when another box on that frame is in the air. It does not stop a box from jumping to the wall.

### 3. Make/miss is not solved

Both-false (`ball_through_rim` and `net_moved` both false) is still stored as a miss. Scott kept that. Do not change it until a tested rule beats 85 right without calling more misses makes.

Do not train another ball-weights file of the same kind. v6 put more boxes on the ball in the net. The make/miss count did not move past the line rule (80 of 111) until the sideways check, and that check is not shipped.

Do not drop the 170-pixel rise or widen the 8-second teach window until a test shows the missing tagged shots appear and new untagged shots do not.

Do not copy Scott's tags onto AI rows to force 51–26. A tag is truth when a row exists. An unmatched tag is not inserted as a make.

### 4. `Scott_Hermes` does not fix this

Branch `Scott_Hermes`, commit `6143e83`, adds `BallHoopExperiment` in `ai_bridge.py` and `docs/agent_handoffs/HERMES_EXPERIMENT_2026-10-09.md`. Do not merge that commit as the fix.

Checked against the code and the weights file:

- The note says v6 detects basketball and hoop as two classes. The file has one class, `basketball`. The code looks for `hoop`, `rim`, or `basket`, so every window has no hoop and is called a miss.
- `hoop_on_rim` is set to true in the source. It never looks at the picture, so a box on the glass is not rejected.
- The make test is "ball at the rim, then a later ball in the column under it," already scored at 74 of 111.
- `run_ball_hoop_experiment` only grades timestamps you hand it. It does not watch a film and write the ledger. It does not name the shooter, the team, or 1, 2, or 3 points.
- The debug query uses the September 28 rerun key. That is not run 12.

The direction in the note (hoop on the orange rim, ball stays on the ball) is the next check. This commit does not do that check. Leave it in `ai_bridge.py` with `applied_to_core: false` until a score against the 111 tags beats 85 right and does not add misses.

### 5. Rows still missing, and extras still exist

He can reject a false row. He cannot correct a row that was never written. Tagged shots with no row within 8 seconds are still part of the gap between the card and the book. Nine tags were copied onto corrected rows earlier. That was not a detector result. Do not do it again.

`rim_arc_shots` is in `event_generator.py` and is not called from the shot pass. On this film the same rise appears on tagged shots and on moments with no tag. Do not turn it on.

## Do not

- Change `models/ball_detector.pt` or `ball_confidence`.
- Write database rows from an offline rule that has not beaten 85 right without more false makes.
- Start another production detection pass of this film expecting new baskets.
- Resume the four agents above.
- Ask Scott to accept or reject his own tags.
- Treat the September 30 rerun in the bottom of `HERMES.md` as the counting run.

## Done when

A rule, run on the 111 shot tags, is right on more than 85, and the number of misses called makes is not higher than 6. The hoop box on the checked frames sits on the orange rim. The ball box stays on the ball. Then, and only then, a write of the missing tagged shots adds those rows and does not add shots he did not tag. The card can then be compared to 51–26. Q4 still needs tags or a method that does not depend on a hand-built list.
