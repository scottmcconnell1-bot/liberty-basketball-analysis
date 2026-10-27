# Hermes handoff

Updated: 2026-10-20. Paste this into a new Hermes window. Chat memory is not the record. If this file and an older note disagree, this file wins. The Adrian count record is `docs/agent_handoffs/ACTIVE.md`. The September 30 rerun at the bottom of this file is not the counting run. `origin/Scott_Hermes` at `87afd11` does not contain the rule below. Gemini cannot see GitHub. Its note is `docs/agent_handoffs/GEMINI.md` and its upload folder is `gemini-upload/`. Claude Code (auditor, replaced Muse 2026-10-26) reads `CLAUDE.md`. Ollama reads `OLLAMA.md`. Jason reads `JASON.md`. Brad reads `BRAD.md`.

## Court size and the moving camera (2026-10-26)

**Proven:** Half court is now measured, not assumed. `resolve_half_court_limit` in `ai_bridge.py` uses a measured `half_court_y_ft`, then `court_length_ft`, then the 94 ft NFHS maximum, and says which one it used. `pick_court_points.py --halfcourt` adds two center-line clicks to `manual_calibration.json` and prints the court length they imply. Scott (2026-10-26): Liberty's gym is full size, so 94 ft is right for Liberty home games (Notus A1 was played there). Other gyms' lengths are unknown and use the 94 ft default. Court length changes only the transition/backcourt split near half court. Rim, paint, three-point, and perimeter come from the lane, which is the same in every gym.

**Proven:** The NFHS camera follows the play. It pans and zooms. In the Notus A1 film (frames every 15 s, first 10 minutes) no frame shows both the lane corners and the half-court line. The four clicks in `manual_calibration.json` describe one camera position only. A homography from them is correct only on frames where the camera points the same way. Do not apply one calibration to a whole game, and do not build more on the single-frame bird's-eye until the court lines are found and the homography rebuilt per frame. `run_saved_v6_rule` scores in pixels near the hoop and is not affected. Nothing calls `classify_court_zone` yet.

## Pickup (2026-10-20)

Work from `main`. From 2026-10-10 through the morning of 2026-10-20 the checkout was `cursor/count-roadmap-2026-10-10`. That branch was fast-forwarded onto `main` at `3eea117`. `jason-5-may-updates` and `Brad/Claude` are the same commit.

This section wins over the 2026-10-13 score line where they disagree. The Q1–Q3 file is still 99 of 111, 12 makes missed, 0 misses called makes. The whole Adrian film, after Scott tagged Q4, is 113 of 129. Notus A1 Q1 is 24 of 31, 7 makes missed, 0 misses called makes. A longer window, a straight-line fill, ByteTrack, and DeepSORT all scored worse than 24 of 31. Do not loosen a cutoff to chase those seven. Interpolation and a wider column were rejected in `DETECTOR_PROPOSAL_REJECTION.md`. Do not write `inspect_rule_logic.py`. Scott did not accept the contract on 2026-10-20. `applied_to_core` stays false. A future weights file is scored by `C:\Users\scott\AppData\Local\Temp\validate_ball_weights.py` and is not copied onto `models/ball_detector.pt`.

## Pickup (2026-10-13)

Counting run is `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20261006_033941` (run 12) on the home database. The book is Liberty 51, Adrian 26. The count is not solved. The adapter experiment is solved at the best score these tracks can hold.

The working rule is `run_saved_v6_rule` in `ai_bridge.py` on `main`. The file still has `validated_stats` and `BasketballStatsAdapter`. The scored rule has no tag-time lists. Scored on the saved v6 tracks: **99 of 111 right, 12 makes missed, 0 misses called makes.** `applied_to_core` is false. A make on the film is still `ball_through_rim` or `net_moved_after_shot`. Do not merge `Scott_Hermes`.

A ball that goes wide below 80 px and then returns at least 0.40 hoop-widths, ending within 0.70, keeps the make. That recovers 2486900 and 2914500. The ball at 180 px may sit out to 0.85 hoop-widths. Sideways drift vetoes above 0.43 hoop-widths. Do not move the hoop center onto the ball. 896600 and 3256200 walk off the rim and never return.

These proposals were scored on all 111 tags and are not in the file. Do not bring them back:

- A wider column, a depth-gated column, or a hoop recenter. Each one called at least one miss a make.
- Raising the box-jump limit from 60 px to 85 px. The two missed jumps are 97 px and 110 px. The change called 530600 and 1776500 makes.
- A pre-drift check on the points above 80 px. It recovered 3 makes and called 8 misses makes, including 3256200.
- Replacing the grouped hoop with the detector hoop from `bodd_shots.json`. Score 95 right, 15 makes missed, 1 miss called a make.
- Box width and confidence. On 1231400 and 2870400 the box stays ball-sized and the confidence stays high while the center walks off.

The 12 the rule still misses are 342800 (bounce, then the box leaves the net), 638300 (starts well below), 717000, 801800, 2479100, 3095700 (no crossing), 1231400 and 2870400 (the box walks off), 1792900 (short net), 1836700 and 3045900 (box jumps), and 2962500 (sideways drift). Another cutoff on these centers will call a miss a make.

## Where the files are

Hermes does not have these in git. They are on the home PC.

| What | Path |
|---|---|
| The rule to edit | `ai_bridge.py` in the repo root, function `run_saved_v6_rule` |
| The 111 saved tracks | `C:\Users\scott\AppData\Local\Temp\v6_tracks.json` |
| Detector boxes (width, height, confidence) | `C:\Users\scott\AppData\Local\Temp\bodd_shots.json` |
| Score the rule | `C:\Users\scott\AppData\Local\Programs\Python\Python312\python.exe C:\Users\scott\AppData\Local\Temp\score_hermes_now.py` |
| Scott's 111 shot tags | `data\film_tags\jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` |
| Home database | `film_analysis.db` in the repo root |

Each track row has `t`, `result`, `hoop` (`x`, `y`, `w`, `area`), `ball`, and `bodd`. A point is `[frame, x, y]`. There is no box width on the track. The tag file stores shots in `rows`. The clock is `start` (`20:31.4`). The type is `eventtype` (`2PT`, `3PT`, `FT`). `map_manual_row` in `manual_tag_teach.py` already turns those into `made_two`, `missed_three`, and the free-throw types. Hermes does not edit that file.

## How Hermes can contribute

Stay in `ai_bridge.py`. A change counts only when `score_hermes_now.py` prints a better line than 99 right, 12 makes missed, 0 misses called makes. Report those three numbers and `applied_to_core`. If the false-make count is not 0, take the change back out.

Do not write `film_analysis.db`. Do not copy tags onto AI rows. The card gap is not an adapter cutoff. A `shot` row scores 0 points. The card scores the made or missed row at the same timestamp. Ten of the sixteen shots within 2 seconds of a disagreeing tag already have that scoring row on the tag's side. Six scoring rows still disagree and are Cursor's to correct: 31364, 31457, 31479, 31498, 31547, and 31624. Thirteen tags sit 2 to 8 seconds from a shot and stay untouched. Fifteen tags have no shot within 8 seconds. Hermes does not insert those rows.

Do not edit `event_generator.py`, `net_detector.py`, `manual_tag_teach.py`, or `models/ball_detector.pt`. Do not change `ball_confidence`. Scott (2026-10-20) allowed a candidate weights file. Do not copy it over `models/ball_detector.pt`. Keep it only when the validator passes. Do not resume the four finished agents named in `ACTIVE.md`. The rim is orange. The net is white and cone-shaped. The exit sign is the only red object.

## How Cursor and Hermes work

Scott decides. Cursor changes the film pipeline and is the only one who commits and pushes. Hermes writes experiments in `ai_bridge.py` and stops there.

Hermes does not run git, does not change git config, and does not delete `.git/hooks`. Hermes does not claim a commit it did not make. A report lists what was run and what the output was.

The job is the Adrian count, not a new detector. Do not load `yolov8n.pt`. Do not call `validated_stats` on the game film. A proposal comes back as JSON with `applied_to_core` false. Cursor checks it against the database before Scott is asked to accept it.

## Architecture

This project has a strict, sequential pipeline. Do not structurally alter it.

Hermes edits `ai_bridge.py` only. Do not rewrite, refactor, or reorganize:

- `ai_analyzer.py`
- `event_generator.py`
- `court_memory.py`
- `net_detector.py`
- `manual_tag_teach.py`
- `game_boxscore.py`
- `scoreboard_clock.py`

Do not call `ai_bridge.py` from those files. Data leaves the sandbox through `validated_stats()` as JSON. `applied_to_core` stays false until Scott accepts the contract. Do not pass model objects across that boundary.

A make on the film is `ball_through_rim` or `net_moved_after_shot`. Code inside `ai_bridge.py` is an experiment, not a make. Do not change `models/ball_detector.pt` or `ball_confidence`. Do not restart Flask to load the adapter.

## Where the Adrian count stands

Game: Liberty vs Adrian, video 73, `uploads/nfhs_gam0a66d85e12.mp4`.

Rerun: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546`. Completed 2026-09-30 at 11:21 AM local. 1,452 events. No error. This was a new detection pass. The September 28 rerun is the previous one.

Book: Liberty 51, Adrian 26. Tags stop at about 32:15, the end of Q2. Halftime note: Liberty 27, Adrian 15.

Teach rejects an AI row only when a tag of that same family is within 8 seconds. A make in an open stretch stays pending. An unmatched tag is not inserted as a make.

Makes on this run: 40 rows, 80 points (26 twos, 7 threes, 7 free throws).

- Corrected: 29 makes, 59 points. These matched a tag.
- Pending: 9 makes, 17 points. These did not match a tag inside 8 seconds.
- Rejected: 2 made twos, 4 points. Dayley at 12:16 and cluster 8 at 26:05. The note is "extra AI event in tagged window."

The results box counts accepted, corrected, and pending. The scorebook total stays Liberty 51, Adrian 26. A later shot-chart step logged 0% makes on 206 shots. The event list is the count.

Flask was restarted on 2026-09-30 after Jason and Claude's review was merged, so port 8080 is running that code. The worker applied 7 jersey mappings at the end of this run.

Review branch: `cursor/playbook-jason-clean-slate-ac1f`, pull request 151. `main` and `jason-5-may-updates` are the last merged line (pull request 150). They do not have this run's teach rule or the review fixes.

Jason and Claude's fixes are already on the review branch: a named rerun stays that rerun, a new run with no coach decisions does not replace a reviewed copy, highlights use that same copy, games without a scoreboard track use equal video slices, an unreadable clock digit is not a clock, and imported FastDraw sheets do not get automatic defenders. Adrian has a scoreboard track, so a moment without a legal clock and a period stays out of the line score.

Not decided, and not a reason to edit the core: pass only from the ball handler, undo, screen coverage, zones, saving a dragged defender x, and the unread checks on net movement, defender jump, jersey mapping, and results speed.

`TEACH_ISSUE_ANALYSIS.txt` on the home machine describes the September 28 rerun. The span-reject bug it names is already fixed in `manual_tag_teach.py` and was used on the September 30 run. Do not apply that note to this run.

The database is `film_analysis.db` in the repo root on the home machine. The film is `uploads\nfhs_gam0a66d85e12.mp4`. Neither is in Git. Jersey shades for this run are `data/jersey_shades/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546.json`.

Fuller notes: `docs/agent_handoffs/ACTIVE.md`. Rules Cursor already loads: `.cursorrules`.
