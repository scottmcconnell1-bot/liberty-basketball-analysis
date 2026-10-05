# Jason — start here

Updated: 2026-10-04. This file is on `main`. Branch `jason-5-may-updates` is kept even with `main`. Open that branch, then read this file. The same words are on `Brad/Claude` in `BRAD.md`.

The job is Liberty at Adrian. The official book is Liberty 51, Adrian 26. The program is counting that game from the film. It is not the book yet. Do not copy the book totals onto the AI rows to make them match.

## Where the count stands

Results open this run (run 11, finished 2026-09-30 20:11:42 UTC, 1,452 events, no error):

`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_191418`

Film: `uploads\nfhs_gam0a66d85e12.mp4` (video id 73). Do not use video 64.

Pending plus corrected makes are **70 points**. The book is **77**. Corrected makes are 13 rows / 25 points. Pending makes are 21 rows / 45 points. Rejected makes are 6 rows / 10 points. Naming a jersey does not set `review_status` to `corrected`. The corrected-only card is 25 points, so it looks worse than the 70.

| Player | AI points (pending + corrected) | Book |
| --- | --- | --- |
| Dayley | 16 (`#40 Dayley` 12 + `40 - Dayley` 4) | 26 |
| Colman | 4 | 15 |
| Peterson | 2 | 4 |
| Sullivan | 0 | 4 |
| Flores | 0 | 2 |
| Mendoza | 8 (`#13 Mendoza` 5 + `13 - Mendoza` 3) | 13 |
| Alvarez | 8 (`#25 Alvarez` 6 + `25 - Alvarez` 2) | 5 |
| Foster | 9 | 2 |
| Rodus | 3 (`#23 Rodus` 2 + `23 - Rodus` 1) | 4 |
| Allison | 0 | 2 |
| Unnamed cluster `5` | 7 | — |
| Unnamed cluster `7` | 7 | — |
| Unnamed cluster `8` | 3 | — |
| Unnamed `#6` | 3 | — |

Dayley, Daley, and Daly are the same Liberty player. Foster #22 is Adrian. Do not move him to Liberty. Scott said Liberty has no 2 and no 6, so cluster `7` and `#6` stay unnamed. Do not assign those 10 points to a Liberty player.

A tag does not rename a shot that already belongs to a different player. A make is rejected when that same shot says the ball did not go in (`through_rim` false and `net_moved` false). A different player's shot at the same timestamp is not that proof.

Tags cover Q1 and Q2 only, through 32:15. Q3 and Q4 were never tagged. Adrian has a scoreboard track, so do not invent quarters by splitting the video into four equal parts. The track has no readable period 3.

## What is already in the code

- A jersey is named from OCR on this analysis only. A shared number uses the shirt shade. A unique number whose shirt is the other team is not named.
- Opening the film does not ask to restore tags or import an old browser roster.
- The graphics-card check no longer opens a black Windows window. That window was `nvidia-smi` every two seconds while the film page was open.

## Do not

- Merge pull request 147. It turns auto-accept on at 0.85. Scott has not approved that.
- Change `schema.sql`, `models/ball_detector.pt`, or `ball_confidence`.
- Start the teach loop.
- Call `ai_bridge.py` from the core. A make is `ball_through_rim` or `net_moved_after_shot` in the core.
- Open `GET /api/analysis` for this game. That request rewrites identity rows. Read `events`, or the HTML results page.
- Treat two close name spellings as the same player unless Scott has said so.

Code that writes these rows: `event_generator.py`, `manual_tag_teach.py`, `track_identity.py`, `court_slot_mapping.py`, `game_boxscore.py`. The database `film_analysis.db` is on Scott's home machine only. It is not in git.
