# Roadmap — film count

Updated: 2026-10-10. The fixes are in `COUNT_FIXES_2026-10-10.md`. Do that file's "Do not" list at every step. Do not skip a step because a note sounds confident. A step is done only when its exit test was run on the film or the tags, not only when the code compiles.

The product is one ledger for every module: stats, minutes, lineups, film room, scouting, playbook, and the assistant. Adrian is the first game. The path has to work on a film that has not been tagged shot by shot, then on a second gym.

## Step 1 — Hoop on the orange rim

Offline only. No database writes. No change to `models/ball_detector.pt` or `ball_confidence`.

On the frames already opened (896600, 1776500, and the makes that were right), the hoop box has to sit on the orange rim band, not on the glass and not on the backboard. Shape already rejects a round blob. This step rejects a box whose center is on the glass above the rim.

Use a model that actually emits a hoop class, or the orange-band finder in `net_detector.py`. The v6 file does not emit a hoop. `Scott_Hermes` commit `6143e83` does not do this step.

Exit: on those opened frames the box is on the rim. A one-sample jump onto the glass does not move the rim. Existing tests `test_a_round_ball_does_not_become_the_rim` and `test_a_one_sample_jump_does_not_move_the_rim` still pass.

## Step 2 — Ball box stays on the ball

Offline only.

The box stays on the ball through the white net, and it does not jump to the wall (1515700) or to a ball in a player's hands (2455600, 1776500) when the ball in the air is still visible.

Another weights file of the same kind is not this step. v6 already improved boxes in the net and the count did not move.

Exit: on the five misses listed in `COUNT_FIXES_2026-10-10.md`, say where the box sits on the opened frames. It is on the ball, or the jump is rejected and the shot is not called a make.

## Step 3 — Score make/miss again

Still offline. Compare to Scott's make and miss tags. Report right, makes missed, and misses called makes.

The current bar is 85 right, 20 makes missed, 6 misses called makes. A result that only prints "how many windows were called makes" is not a score.

Exit: more than 85 right, and misses called makes not higher than 6. If the new rule loses that trade, do not ship it. Write the numbers into `ACTIVE.md` and stop this step.

## Step 4 — Write missing tagged shots

Only after step 3 passes.

Write the shot row the detector found. His tag within 8 seconds grades it. Do not insert an unmatched tag as a make. Do not turn on `rim_arc_shots`. Do not drop the 170-pixel rise unless this same test shows the missing rows appear and new untagged shots do not.

Exit: tagged shots that had no row within 8 seconds now have one, and a pass over the film does not add a pile of shots with no tag. Both-false stays a miss until Scott changes that.

## Step 5 — Compare the card to the book

Home database, run 12. Non-rejected makes against Liberty 51, Adrian 26 (77 points). Tags through three quarters are Liberty 43, Adrian 24. Q4 remainder is Liberty 8, Adrian 2, and Q4 is not tagged.

Exit: the gap is explained shot by shot. What is still missing is either an untagged Q4 possession or a row the detector still did not write. Do not close the gap by copying the book onto the rows.

## Step 6 — A film with no shot-by-shot list

The grader in `run_ball_hoop_experiment` cannot do this. It only scores timestamps you hand it.

The ledger has to notice the shot, the shooter, the team, and 1, 2, or 3 points from the film. Run that on Q4, or on one other Liberty film, without a hand-built list of 111 times.

Exit: the same make/miss rule from step 3 runs without a tag list, and the extra shots are ones a person can see on the film. Then the other modules read those events. They do not grow a second database.

## Standing rules that do not wait

- Hermes edits `ai_bridge.py` only. `applied_to_core` stays false until Scott accepts the JSON contract.
- Cursor may fix a bug Scott has asked to fix in the core. Do not reorganize the core sequence.
- Home owns `film_analysis.db` and the film. School uses Funnel only.
- `jason-5-may-updates` and `Brad/Claude` stay even with `main` when a pull request is merged.
- Names: Dayley, Daley, and Daly are Liberty #40, roster name Daly. Liberty has no 2 and no 6. Foster #22 is Adrian. Liberty #3 is Kariuki. A cluster id of 3 is not Kariuki. Ask Scott before treating any other close spelling as the same person.
