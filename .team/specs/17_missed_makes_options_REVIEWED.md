OPTIONS v1 REVIEWED - Hermes wrote, Muse reviewed and added, Claude Code reviewed and added - nothing built

# Makes and misses: options for the 19 missed makes

Flow (Scott, 2026-10-29): Hermes wrote the list (.team/specs/17_missed_makes_options.md), Muse reviewed it and added M1-M4 (.team/muse_options17_run.txt), and Claude Code reviewed both and added C1-C5. Muse voted DISAGREE ("send it back to Hermes") because of A1, A3, A6 and B7. Those corrections are applied below instead of another Hermes round. Scott can still send it back.

## Where we stand (Proven = checked by a command this session)

- Build set 140 shots = Notus A1 Q1 31 + Adrian Q1-Q3 109. The v6 rule gets 28 of 47 makes, misses 19 makes, and calls 0 of 93 misses makes. Proven: reason tally file; makes column sums to 19 (Muse said 20; that is wrong).
- Of the 19: 12 had a rim crossing that a later test vetoed; 7 had no crossing.
- Proven (check17b.py on the saved tracks): in the 7 no-crossing makes, the tracked object starts 1 to 2.6 hoop widths off center or well below the rim; 2 of them (801800, 3095700) have NO point near the hoop at all. **The ball was never detected near the rim on these shots. No change to the rule's steps can recover them; only better detection can.**
- Proven: 4 column_ratio_low makes have ratios 0.25, 0.0, 0.0, 0.0. A ratio of 0.0 means every deep point is off to the side, so the track is on another object or the hoop spot is off (plan 16 crops showed the saved hoop sits below the real rim).
- Proven: 7 of the 19 are free throws (159300, 3095700 no crossing; 142600, 357500, 774600, 1231400, 3045900 vetoed).
- Proven: both films have stereo sound (ffprobe: AAC 48 kHz). Notus 1280x720, Adrian 1920x1080, both 25 frames a second.
- Proven: the scoreboard reader found 43 of 43 Adrian makes, final 51-26 (TEAM_RECOVERY.md, spec 05). Only the Notus board failed (gate 9 of 20). Scott shelved the scoreboard.

## Dropped (cannot work or breaks a rule)

| Option | Why dropped | Found by |
|---|---|---|
| A1 reorder jump before column | Two vetoes in a row give the same answer in any order; changes no verdict | Muse, Claude agrees |
| A3 came_back 0.70 -> 0.85 | Looser cutoff | Muse |
| A6 accept a first point below the rim | Wrong fact: the fallback already accepts a first point ANY distance below the rim (ai_bridge.py detect_dynamic_entry_crossing: `first_y >= hoop_y - 10`) | Muse; Claude: it is looser than Muse said |
| A9 sustained exit for short_track_left_net | A veto that fires less often is looser, not "stricter"; 0 makes affected, so only risk | Claude (Hermes and Muse both called it stricter) |
| A10 bounce 5 px -> 10 px + 2 frames | Same: looser cutoff, not stricter | Claude (Hermes and Muse both called it stricter) |
| B2 court-space interpolation | Interpolation is a banned trial; moving it to court space is the same method. Also needs court keypoints (Stage 1b did not pass) | Claude (Muse flagged it) |
| B5 tracker ensemble with ByteTrack/DeepSORT | Rerunning ByteTrack or DeepSORT is a banned trial whatever it is called | Claude (Muse said OK) |
| B6 three zones (up / rim / down in net column) | The "down" zone is the net region; Scott closed net measurements | Claude (Muse said "Scott should confirm") |
| B9 opponent basket | Wrong premise: each saved track already carries the hoop it was shot at (hoop x from 370 to 1400 across shots) | Claude |

Corrections to the rest: Hermes said 1 make fails x_at_180_outside_rim; the tally says 0 makes, 1 miss. Hermes's B7 said all 7 no-crossing makes are free throws; it is 2 of 7 (Muse).

## Options that stay

Gain = how many of the 19 it could recover at best. Every option must keep 0 misses called makes on the 140.

### Group 1: small fixes inside the rule (no cutoff change). Together: up to about 4 of 19.

- **A7 bodd points count for net depth**: 1 make (short_net_depth). Low risk. About 1 hour.
- **A8 ignore an "upward" move that is a box jump**: 2 makes (ball_went_up). Low risk. About 1 hour.
- **A4 measure drift from the crossing point**: 1 make (sideways_drift). It can make the veto stronger OR weaker for a given shot, so it must be measured. About 1 hour.
- **C4 (Claude) two bugs in the rule's own steps, not cutoffs**: (a) ai_bridge.py, LINE TEST: `ball[cross_idx:]` uses a position counted along the combined track (ball then bodd) on the ball-only track, so a crossing found in the bodd part is thrown away as short_net_depth; (b) the jump check finds its own "true crossing" with no hoop-width test, so it can measure from a different crossing than the one that passed. Gain unknown until measured; a quick count first.
- A5 bodd crossing / A2 bodd column: about 0-1 make. The no-crossing makes have no bodd points near the rim either (proven above). Low value.

### Group 2: see the ball near the rim (the real cause for at least 7 of 19)

- **B1 new candidate ball weights** trained on Liberty film, kept as a separate file, scored by validate_ball_weights.py. Goes at the cause: the ball is not detected near the rim. Up to all 19. Cost: high (labelled frames, training). Scott's gate already allows a candidate file (2026-10-20). Muse's note: the pass bar should be tighter than today's baseline.
- **C3 (Claude) + M1 (Muse) keep every ball detection near the hoop and build one real arc**: today each frame keeps only the nearest box, so other detections are thrown away. Pick, among REAL detections only (no made-up points), the ones that fit a falling arc. Not ByteTrack, DeepSORT or interpolation. Medium risk; a no-op on shots already right. About 2 days.
- **C5 (Claude) check where the hoop is**: plan 16 crops show the saved hoop below the real rim, and 3 column makes read 0.0. "Hoop recenter" is a banned trial, so this only goes ahead if Scott says so. First step would be a count only: on how many of the 140 is the saved hoop off the real rim in the pictures.

### Group 3: other evidence that a basket was made (does not depend on the ball track)

- **B3 scoreboard** (shelved by Scott): already 43 of 43 makes on Adrian. Would cover all 12 Adrian missed makes; fails on Notus because that board could not be read. The scoreboard says that a team scored within 25 s, not which shot, so it is paired with the rule's shots. Strongest single option for gyms with a readable board.
- **C1 (Claude) sound**: a swish, a rim clang, the whistle, the crowd and bench. Both films have sound. Independent of the tracker. Risk: gym noise, and the crowd cheers for both teams. First step is a measurement only on the 140. About 1-2 days.
- **C2 (Claude) what players do next**: after a made field goal the other team takes the ball out under the basket and everyone runs the other way; after a miss there is a rebound scramble. Uses the people detector, not the ball. About 2-3 days.
- **B8 rim contact (angle change at the crossing)**: for the 12 shots with a crossing. Low-medium risk. About 2 days.
- **B7 + M4 free throws**: 7 of the 19 are free throws; a free throw has a fixed spot, no defenders and a set routine. A separate check for free throws only. About 2-3 days.

### Group 4: let Scott check only the hard ones

- **B4 review queue, corrected**: Hermes's version used the tag file to pick the 19, which a new game will not have. Working version: the rule's MAKES are trusted (0 false makes); the rule's MISSES are sorted by a "maybe a make" score (from B10, the sound, the scoreboard or C2), and Scott looks only at the top of that list. Saves most tagging even before 100%.
- **B10 classifier on the rule's own numbers**: flags only, never flips a verdict. 140 shots is small; must be tested game by game.
- M2 shot window from the ball rising, M3 jerk/acceleration instead of jump size: Muse's ideas; low expected gain because the problem shots have no detections near the rim.

## Claude Code's recommendation, in order

1. **Scoreboard (B3)**: proven 43 of 43 on Adrian, independent of the ball. Needs Scott to reopen it. For gyms with an unreadable board, it does not help.
2. **Sound probe (C1)**: cheap, measurement only, independent of the ball. Tells us within a day or two whether sound separates makes from misses on the 140.
3. **Group 1 together (A7, A8, A4, C4)**: an afternoon, at most about 4 of 19, 0 false makes required.
4. **Ball near the rim (C3, then B1)**: the real fix for the shots where the ball was never seen; bigger job.
5. The review queue (B4 corrected) as the safety net while the count is below 100%.
