# Active Task

Updated: 2026-10-04. If an older paragraph below disagrees with this section, this section wins.

Working branch: `main`. `jason-5-may-updates` and `Brad/Claude` stay even with `main`. GitHub's default branch is `main`. Jason's note is `JASON.md`. Brad's note is `BRAD.md`. Whenever a pull request is opened for Jason/Claude, push those same commits to `Brad/Claude` and open the same pull request there. Auto-accept pull request 147 is still open and is not on `main`.

When a roster name and a scorebook name are close but not the same spelling, ask Scott. Dayley, Daley, and Daly are already confirmed as one player. Do not invent the next alias.

A tag does not rename a shot that already belongs to a different player. A make is rejected when that same shot says the ball did not go in. On run `...191418` that removed the extra Dayley make at 48.2 seconds and the other makes whose own shot missed.

**Proven (2026-10-04):** Run `...191418` still has 1,452 events. Pending plus corrected makes are 70 points (book 77). Corrected makes are 13 rows / 25 points. Pending makes are 21 rows / 45 points. Rejected makes are 6 rows / 10 points. Combined lines: Dayley 16 (book 26), Colman 4 (15), Peterson 2 (4), Mendoza 8 (13), Alvarez 8 (5), Foster 9 (2), Rodus 3 (4). Sullivan, Flores, and Allison are 0. Unnamed: cluster 5 is 7, cluster 7 is 7, cluster 8 is 3, `#6` is 3. Scott said Liberty has no 2 and no 6, so those stay unnamed. A make is named only when the jersey read and the shirt shade agree with one scorebook person. Liberty makes for Dayley, Colman, and Peterson have team id 1. Colman has player id 1. Dayley uses the Daly roster row. Adrian named makes have side `home`. There is no Adrian team row. Opening the film does not ask to restore tags or import an old roster. The graphics-card check no longer opens a black Windows window.

**Proven (2026-09-30 afternoon):** The Adrian count to review is `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546`. It finished at 11:21 AM local, 1,452 events, no error, on `uploads\nfhs_gam0a66d85e12.mp4`. Book: Liberty 51, Adrian 26. Makes: 40 rows, 80 points. Corrected 29 / 59 points, pending 9 / 17 points, rejected 2 made twos / 4 points (Dayley at 12:16, cluster 8 at 26:05). Tags stop at 32:15. Teach rejects a play only when a tag of that same kind is within 8 seconds. A make in an open stretch stays pending. The database and the film stay on this machine. The new run's jersey shades are `data/jersey_shades/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546.json`.

**Proven (2026-09-30 afternoon):** Jason and Claude's review (`632b0ad`) is merged here. An older rerun opens by its own key. A newer run with no accepted or corrected events does not hide a coach-reviewed copy. This Adrian run has corrected events, so the game key opens it. Games with no scoreboard track use four equal slices of the video for the line score. Adrian has a track, so a moment without a legal clock and a period stays out of the line score. An unreadable clock digit does not become a shorter clock. Imported FastDraw sheets do not get automatic defenders. Flask on port 8080 was restarted after that merge.

**Proven (2026-10-01):** The review branch now includes the jersey rule and Claude's shared-number shade fix (pull request 163), plus the accuracy benchmark (pull request 162). Auto-accept pull request 147 is not merged. The 2:11 PM Adrian run already finished before the shade fix, so that card was not rebuilt.

**Proven (2026-09-30 afternoon):** The Adrian run `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_191418` finished at 2:11 PM local, 1,452 events, no error. It posted, and Results opens it. Corrected makes are 17 / 31 points. Pending makes are 21 / 45 points. Naming a jersey did not mark those pending rows corrected. Claude's shared-number shade fix was not in this run.

**Proven (2026-09-30 afternoon):** A jersey name comes from OCR on that same analysis. A saved court slot with no read is not stamped onto events, and naming a jersey does not mark the event corrected. When the same number is on both teams, the jersey shade picks the side. A shared number with no shade stays a number. That code is for Claude to review; the finished Adrian run was named by the previous apply and has not been rewritten.

**Not decided:** Only the ball handler can pass, undo, screen coverage, matchups, zones, curved cuts, lead passes, formations, and keyboard shortcuts. A defender x dragged in the draw tool is still not saved. Whether the original run should also open from the game key is still open. Their unread checks on net movement, defender jump, and results speed are not fixes yet.

**Proven:** Coaches edit a saved play at `/playbook/draw/<id>` (Edit play). Existing pictures load with the players where they stand. Next picture saves the picture just finished. Save and watch opens `/playbook/play/<id>`. The editor code and Scott's saved plays (1-Game `98`, `99`, `101`, and copies `146`–`148`) are on this same branch.

**Proven:** This branch now includes `origin/main` (`59577bd`, public signup closed). GitHub's default branch is `main`.

**Proven:** Build a picture at `/playbook/draw`. Click the player (that spot is the start), then Cut, Pass, Dribble, or Screen, then where he goes. A pass ends on the catcher. Next picture starts where this one finished. Save and watch opens the full play with the players moving and no arrows.

**Inferred:** A coach save of arrows and spots is stored with the path, and Play on that sheet uses the saved list instead of the original 1-Game script. The save round-trip is unit-tested. It was not replayed on 1-Game in the browser in this pass.

**Proven:** A cut, screen, run, or dribble is a spot on the floor. Add movement drops an arrow. Drag the white ends to the start and the spot. Pass still clicks the passer and the catcher. A defender x you drag stays where you put it. The other x's keep standard man-defense spots.

**Proven:** [PR #149](https://github.com/scottmcconnell1-bot/liberty-basketball-analysis/pull/149) (`claude/speed-up-analysis`, merge `cf58c9d`) is on this branch. Scott said not to protect the Adrian pass. The rerun `...__rerun_20260927_042234` (started 2026-09-26 22:22, before that merge) was stopped on 2026-09-27. `idx_detections_game_frame` was built in 11 seconds on about 7.8M detection rows. Liberty vs Adrian video 73 (`uploads/nfhs_gam0a66d85e12.mp4`) restarted as `...__rerun_20260928_031027` (PID started 2026-09-27 21:10 local, label "Indexed rerun"). Video 64 is the screen capture and stays unused. Flask may still have `LIBERTY_SKIP_DETECTION_INDEX=1`; this worker was started without it.

## This session

**Proven:** Signed-in parents and players can open Game Film (`/videos`, `/film`, `/highlights`, and the uploaded video file) for every game. Tag saves stay refused. Their stat board is still only their own player.

**Proven:** On 1-Game (`/playbook/play/98`), clicking a player during Play All stops the play and it stays stopped. Play All then continues on the same sheet (step 5, next beat) instead of restarting at sheet 1. Back stops playback and returns to the start of the current action. Players, defenders, and the ball can be dragged while paused. Save choreography still stores offense spacing.

**Proven:** Liberty vs Adrian (`jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`) events were rebuilt from the existing 866,471 detections. Film Tool tags are 146 manual rows. Foul is the category (`foul`); subcategories are Shooting (`foul_shooting`), Personal (`foul_personal`), and Technical (`foul_technical`). The 18 existing Foul tags count as the category. Teach runs before auto-accept. Q1 shot tags match 45/60 within 8s, Q2 23/38. Q3/Q4 are still untagged. Teach Watchdog stays disabled.

**Proven:** Play All order for a FastDraw sheet is PDF paint order (`ink.actions`, one stroke one beat). Dashed = pass, solid = cut, squiggle = dribble. Coach-saved movement lists still win. The handwritten 1-Game / Triangle / Pitt 5 lists apply only when a sheet has no draw-order strokes. See `docs/playbook_pipeline.md`.

Branch: `cursor/playbook-jason-clean-slate-ac1f`  
Base: `cursor/dashboard-maxpreps-results-ac1f`

## How review results land

Review output is code on **this** branch. A side branch such as `claude/review-fixes` is only the review workspace. It is not done until those commits are fast-forwarded here and pushed. Docs under `docs/validation/` record the proof. They do not replace the code.

**Proven:** `origin/claude/review-fixes` (`3d9aee9`, PR #148) is contained in this branch. Jason’s stats, film, access, schedule, playbook, and ops fixes are the files on this branch, not a parked copy.

## Security / correctness (Scott 2026-09-26)

**Proven fixes on this branch:**
1. **Nightly leak:** untracked Chrome LevelDB / flask logs / transfer bundles; `.gitignore` + `daily_git_save.ps1` blocklist expanded. *(Git history may still contain old blobs — rotate any exposed cookies/tokens.)*
2. **Messaging:** signed-in only; membership-scoped list/poll/send; client `sender_id` ignored.
3. **Settings:** admin-only; logout deletes `user_sessions` and production requests require a live token (copied cookie stops working).
4. **Rebuild dupes:** `persist_events` deletes prior AI rows (including auto-accepted), keeps manual/corrected.
5. **Stats:** FT no longer counts as FG; Film Tool add/correct set `event_type_id` + refresh stats; ledger skips shot+make pairs and counts O/D rebounds.
6. **Teach loop:** hung fail won’t leave dual GPU; young runs not zombie-killed; broken games skip after 3 start failures.
7. **Schedule:** re-import skips duplicates; delete scored game/season clears `games` first; archive copies results via `scheduled_game_id`.
8. **Paths/XSS:** upload_id / team photos / scorebook contained; HTML uploads forced download; category names sanitized; playbook chip HTML escaped.

## Dual-machine roles (locked)

Home owns data. School uses Funnel only.

Funnel: https://liberty-coach.tail368a37.ts.net

## Coaches site / nightly (Scott 2026-09-18)

**Proven:** Nightly `Liberty Daily Git Save` (11:00 PM) is running. Last success 2026-09-17 23:00 (commit `81ff752`, `docs/LEARNING_STATUS.md` generated, pushed). Server watchdog healthy on `:8080`. Funnel `/coach` is up.

**Proven:** `Liberty Teach Watchdog` was **Disabled** since 2026-08-09 (3,799 missed 15-min runs). Teach loop was not running, so `/coach/progress` HUDL % and panel gates looked frozen. Re-registered Ready; teach loop pid 33872 started; Nyssa `analysis_launcher` running. Nightly panel still shows FAIL 0% until those games have events again (clean-slate wipe).

## Product priority (Scott 2026-09-15)

**AI’s job is counting stats.** Film clip review is coach work later.

North star: a Liberty vs opponent box (PTS, FGM/A, 2PM/A, 3PM/A, FTM/A, REB O/D, AST, STL, BLK, TO) that can be checked against a confirmed scorebook — without Scott walking every AI event. +/− is parked.

**NFHS definitions locked (Scott 2026-09-15, camera notes 2026-09-15 evening):**
- **FT:** lane lined up around the key; technical = one shooter, empty lane. Camera is locked on the key (no pan) during the FT.
- **Assist:** last pass that directly leads to a made field goal; 1–2 dribbles max; no FT assists.
- **TO:** offense loses the ball before a shot. Hudl/Synergy credit whistle TOs by watching the referee (human). Liberty first split: live-ball TO vs dead-ball TO (zoom-out / stoppage). Do not name travel vs charge vs 5-second from vision yet.
- **Steal:** defender’s active play causes that TO (intercept, strip, deflection, held-ball arrow). Not a loose-ball pickup or charge.
- **OREB/DREB:** shooter jersey color vs rebounder jersey color (same = offensive).
- **Block:** ball deflected on the way up / at the peak, near the shooter’s hand; if it still goes in, it is a FG not a block. HS goaltending ignored (almost never called).
- **Paint:** shot from inside the key outline. Camera zooms in during live play, out on dead balls, otherwise pans left–right. Plan: lock the key on zoom-out frames and track that polygon through pan/zoom.
- **Second chance:** same-color rebound after a miss, then a make before the defense possesses.
- **Starters:** coach picks five per team per game; tip-off five is the later fallback. Subs after dead balls.

**Proven:** Starting five is coach-saved per game (`data/lineups/<game_id>.json`, Film Tool + Analysis Results). Box splits STARTERS/BENCH and shows bench points. No schema change.

**Proven (2026-09-15 evening):** NFHS counting rules are now in `stat_rules.py` / `court_memory.py` and wired into the precision event generator + official box.
- FT: lane lined up (or technical = empty lane), camera not panning.
- Assist: made FG, last pass, 1–2 dribble hold, never on FT.
- TO: live vs dead (zoom-out). Steal only if the next player is close to the ball, not a dead-ball pickup.
- OREB/DREB: same team/color when known; else possession touch-chain fallback.
- Block: deflection near the shooter; makes are FGs. HS goaltending ignored.
- Paint / 2nd chance / points off TO: team extras on the box.
These apply to **new** analyses (or a rebuild). The live Adrian run keeps the generator it started with.

**Line score limfac (plain language):** If the spiral book has no Q1–Q4 cells (Adrian), the app cuts the video file into four equal time slices. That is not when the referee ended the period; timeouts and halftime on the tape sit inside those slices. Enter quarter scores in the book to replace the estimate.

**Proven:** One Jr High game emitted 2,699 precision events. Event-level review is not a one-coach workflow across Varsity/JV/boys/girls/Jr High.

**How stats are produced now:** YOLO detections → precision events → Program Mode ledger (Adrian: `adrian_quality` drops high-pass fakes, caps team totals to the book). Scorebook remains the check. Per-player jerseys stay wrong until IDs map.

## Playbook (item 3)

Optimum = imported FastDraw/PDF sheets auto-animate. Scott does **not** trace, rebuild, or write descriptions.

**Proven:** Play All was throwing away extracted polylines (straight digit→digit passes, OCR endpoint snaps) and ignoring Stage-1 session ink until Save. Playback now prefers extract ink, keeps pass/cut midpoints, auto-saves sticky as `auto_extract`.

**Proven (2026-09-15):** Vector extract mapped digits through FastDraw’s white title panel, so 1-Game opening parked 4/5 on the 3-point line. Court crop is the painted outline; Y is piecewise (FT→160, 3pt→235) so elbows sit in the lane. Sheet plays no longer auto-spawn man defenders (looked like every player had the ball). `auto_extract` sticky does not block a fresh extract.

**Proven (2026-09-17 night, pause-to-fix Play All):** Pause stays on the current sheet (does not reset). In View or Edit (not a shared link) you can change run/screen/dribble/pass, reorder or delete actions, add/remove steps, then Play All continues from the paused spots. Save choreography stores that action order so Play All does not re-guess sequence.

## Jason film stack (item 4)

| Item | Status |
| --- | --- |
| Precision generator + auto-accept 0.85 | Already on |
| E2E suite, migrate/stale scripts, quality docs | Checked out from `origin/main` |
| `src/tracker_wrapper.py` wired into `ai_analyzer.py` | ON by default |
| Undo | Settings → Vision Runtime → uncheck **Jason tracker wrapper** (`ai.tracker_enabled`) |

Ball detector / `ball_confidence` unchanged.

## Clean slate

Wiped analysis outputs from `film_analysis.db` (detections ~55.6M, events ~670k, runs 59, review/provenance/possessions). **Kept** videos, schedule scores, playbook, users.

Re-analyze film from Videos when ready.

## Roster matching (Jr High vs Varsity)

**Proven:** Film Tool defaulted to Varsity, and analysis roster matching fell back across levels. A Jr High game (`jrhigh_adrian_…`) with no `games` row was therefore shown the Varsity film roster. Matching now infers Jr High from the game id, links Adrian to the Jr High schedule, and will not use a Varsity list for a Jr High game.

**Proven:** Confirmed Adrian spiral scorebook now seeds Jr High **Liberty** and a selectable **Adrian** opponent roster (not Home/Away). Analysis roster prefers that confirmed book over a Varsity film list.

## Analysis Results empty after Adrian (Scott 2026-09-16 morning)

**Proven:** The PDF subtitle `jrhigh_adrian%2C_or_…` is a URL-encoding miss, not a missing analysis. The decoded key has ~866k detections and 2,699 events. Videos → Results encodes the comma; Flask left `%2C` in `GAME_ID`; JS encoded again (`%252C`); APIs looked up a key with 0 detections. Starters are coach-picked (not auto-detected); the picker said “No roster yet” because the official box loaded the encoded key.

**Fix:** `normalize_analysis_game_id` unquotes up to 3 times; Analysis Results page + `/api/analysis` + status + starters use it; JS decodes `GAME_ID` on load. Hard refresh after Flask restart.

## Inflated Pos# stats (Scott 2026-09-16)

**Proven:** The 168-shot / 194-point rows were the raw detector tables (Pos # = camera track, not a player). The scorebook named-player helper had been dropping PTS/FG cells, so the official box was filling blanks from 2,699 events. Official box now keeps book PTS/makes as the check. Duplicate jerseys (#11 both teams) use Home = light / Away = dark. Empty REB/AST/STL/BLK/TO/PF and misses come from the 168 accepted film events.

## Live AI progress (all games)

**Proven:** Video Library hid the whole table every poll while a run was going (blink) and only showed a confirm popup. `/api/analysis_jobs` now feeds a site-wide bar (percent, frame n/N, elapsed). Frame text updates about every 500 frames; the bar stays animated so a long game is not mistaken for stuck. Completed stays on the banner ~3 minutes.

## Manual tagging layout (Scott 2026-09-16)

**Proven:** Film Tool tagging is a slim **Tag** strip on the **right edge of the video**. **Off / Def / More** tabs show one group at a time. **Vs** (this game’s opponent) and **5s** (starting fives) stay on the strip while tagging so Game info can stay hidden. Dropdowns sit above the film. The running score sits immediately above the video (visible while tagging) so it can be checked against the gym board and the book. Skip / speed controls stay under the film.

**Pickup (work computer):** School uses **Funnel only** — https://liberty-coach.tail368a37.ts.net. Scott’s Jr High Q1 tags were in **home Chrome localStorage for the Funnel origin** (not localhost, not Wilder). Recovered 2026-09-17: **134 tags**, last at **16:00.7**, names Sullivan / Colman / Dayley / Musgrave / Peterson (no Taylor/Blacker). Stored at `data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` and `tag-exports/jrhigh_adrian_q1_manual_tags.json`. Funnel Film Tool **↩ Resume** / open this film loads that sidecar. **Save** / **Teach AI** updates it. Gym Q1: Liberty 16, Adrian 10. Do not Restore Varsity names.

**Proven (2026-09-16 night):** Running score is **only tagged makes** (2PT/3PT/FT Make). It is not the gym board or the book. And-1 is 2 until the FT is tagged. Opponent points count even if the Vs name drifted. Made FG asks Assist? Yes → passer (not the shooter); No → close. BLOB/SLOB are team-only. Player pills are the five currently in the game (5s + SUB); missing name means a sub happened. Team names like Liberty/Adrian are stored on each tag (the old team dropdown only had Our Team/Opponent, which dropped the name and froze the score at 0).

**Proven (2026-09-16 night, teach):** Film Tool Save and **Teach AI** POST tags to `/api/film/<game_id>/teach-manual`. Those rows land as `source_type=manual`, `human_verified=1`, plus `human_corrections`. Nearby AI plays in the tagged window are corrected or rejected. `persist_events` keeps them on the next pass and re-grades new AI. Adrian quality will not park Film Tool teach rows. This still does not retrain `ball_detector.pt`.

**Proven (2026-09-17, FT rule vs copy):** Q1 tags were used as a **test**, not stamped onto AI. Ball is already on every tagged shot (15/15 FT, 22/22 2PT, 7/7 3PT) — do not retrain `ball_detector.pt`. The old `n<=3 + ball = technical` rule was why live ISO became FTs. New rule: two walls of the key + shooter at the line, ignore x=1919 edge boxes, require the floor to be still or a dead ball. Technical is coded (1 shooter, empty space) but not applied to shot type yet — zoom-in 1–2 person frames false-trigger it.

**Proven (2026-09-17, extra-shot rule):** Q1 tags trained a live-shot floor (170px rise, 4s gap, arc must come down). Lane FTs keep the lower 80px floor. Scored on Q1 without photocopying: **181 → 113** AI shots vs 44 tagged (73 extras, 40/44 still found). Q2 film 16:00–32:00 is the holdout: **99 AI shots** before Scott tags. Events rebuilt and persisted for this Adrian game. Technical FT still not counted. Ball detector unchanged.

**Proven (2026-09-17 night, rim/net rule):** Arc is the approach, not the make. Attempt = ball close to the hoop (top of the locked key). Make = ball drops through that same column (net), not a dead-ball gap. Q2 after rebuild: you 16 pts 5/19, AI **8 pts 3/58** (was 9/86 then 181). Through-the-nylon is the right rule; YOLO person+ball cannot see the net on this sideline camera (sparse boxes, pan). Did not copy tags. Ball detector unchanged.

**Proven (2026-09-17 night, net detector):** New module `net_detector.py` finds the **red rim + hanging white net** in the video (not a YOLO “net class”). Sidecar `data/hoop_tracks/<game_id>.json`. Precision generator uses it as the hoop. Locked on this Adrian film at FT, Q1 end, Q2, and HT. Events rebuilt against that track. Extra FTs that were a false lane at the far end are gone: a FT now has to be at **this** hoop, and two shots cannot be 1 second apart.

## Next session — tags → better counting

**Done:** Q1 extra-shot floor; Q2 make/TO/hoop-aim rewrite; hoop/net track rebuild; FT must be at this hoop + 4s gap.

**Proven (2026-09-29):** Net motion is in effect on the indexed Adrian rerun `...__rerun_20260928_031027`. A make is `ball_through_rim` or `net_moved_after_shot`. Of 212 shots, 18 makes are the ball through the rim and 23 are the locked net moving. Teach (`manual_tag_teach.py`, `MATCH_TOLERANCE_MS = 8000`) then graded that rerun from the 146 base-film tags: 67 corrected, 154 rejected, 79 tags with no AI event inside 8 seconds. Those 79 are not inserted as makes, and the window stays 8 seconds. The Results AI card counts 17 makes, 31 points: Liberty 21 (Dayley 15, Colman 4, Peterson 2) and Adrian 10 (Mendoza 4, Alvarez 3, Foster 2, Rodus 1). The book is Liberty 51, Adrian 26. Tags stop at about 32:15 (end of Q2). The halftime note is Liberty 27, Adrian 15, so the tagged stretch is short 6 and 5. The earlier Liberty 9 / opponent 48 card was cluster names and is not the count. Foster #22 is Adrian. The scoreboard reader is `scoreboard_clock.py` plus `data/scoreboard_tracks/` (3,897 samples). A quarter is set only from a sample with a legal clock and a period. Period alone, a partial clock, or seconds past 59 do not set a quarter. Digit 9 has no template. Do not restart Flask to load that track until this gate is the code the process is running.

**Proven (2026-09-29 evening):** Flask on port 8080 is still the process started 09:19 local. It does not have the quarter gate, the teach-window fix, or the OCR identity guard. `GET /analysis/<id>` returns 200 and the AI card shell. The numbers come from `GET /api/analysis`, which also runs `ensure_identity_applied` in that old process. That API was last called at 14:58 local, before teach. It was not called in this check: 1,285 AI events on the rerun are still a single digit, and the loaded code stamps every saved slot onto those rows.

**Proven (2026-09-30 afternoon):** Jason and Claude's review fixes (`632b0ad`, on `claude/pr151-fixes`) are merged onto this branch. An older rerun opens by its own key. A newer run with no accepted or corrected events does not replace a coach-reviewed copy. The finished Adrian run has corrected events, so the game key still opens it. A game with no scoreboard track uses four equal slices of the video for the line score. Adrian has a track, so a moment without a legal clock and a period stays out of the line score. An unreadable clock digit does not become a shorter clock. Imported FastDraw sheets do not get automatic defenders. The editor ideas in the review (only the ball handler passes, undo, screen coverage, zones, and the rest) are not built. A defender x dragged in the draw tool is still not saved.

**Proven (2026-09-30):** The full Adrian analysis finished: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260930_160546` on `uploads\nfhs_gam0a66d85e12.mp4` (97,475 frames). Completed 11:21 AM local, 1,452 events, no error. Precision events, net-move makes, jersey reads, and teach that only rejects a play within 8 seconds of a tag of the same kind. Ball detector and `ball_confidence` are unchanged. Flask was restarted with that same code so the results page uses the scoreboard quarter rule (legal clock plus period; no equal film slices) and the OCR identity guard. Makes on this run: 40 rows, 80 points. Corrected 29 makes / 59 points, pending 9 makes / 17 points, rejected 2 made twos / 4 points (Dayley at 12:16, cluster 8 at 26:05). The book is still Liberty 51, Adrian 26. A later shot-chart step logged 0% makes; the event list is the count. The worker applied 7 jersey mappings at the end.

**Proven (2026-09-30, previous rerun):** On `...__rerun_20260928_031027`, the 17 rejected makes (35 points) were not extras sitting on a tag. None is within 8 seconds of a make tag. Fifteen (31 points) are more than 8 seconds from every shot tag. Teach rejected them because they sit between the first tag and the last tag. Two (4 points, 12:16 and 26:05) are within 8 seconds of a miss tag. Do not put those 31 points back on the card automatically. The reject rule should not drop a make that is more than 8 seconds from every tag. That rule is what the 2026-09-30 run used.

**Decision:** The 79 unmatched tags stay unmatched. Do not insert them as makes, and do not widen the 8-second window. A nearest-neighbor pass (not the one-to-one teach match) puts 70 tags within 8 seconds, 18 between 8 and 15 seconds (4 of those are makes), 11 between 15 and 30 seconds, 21 farther than 30 seconds, and 26 with no AI event of that family at all. One make tag is farther than 30 seconds. Manual triage only.

**Decision:** Identity for a rerun reads that rerun's own rows. `apply_lookaround_to_accepted` uses `detections.jersey_read` where `game_id` is the rerun, plus `data/jersey_shades/<rerun>.json` (9 tracks load for this rerun). It does not copy `track_identity_labels` from the base id. That pass already named 214 events, 4 of them made twos. The 17 makes on the card are the tag names. Leftover single-digit players are not named by jersey number.

**Proven:** Corrected and accepted makes in the database are 17 rows, 31 points: Liberty 21, Adrian 10. Six pending makes are still cluster ids 2, 4, 5, 6, and 8 (14 points). `build_official_box(..., event_counts=True)` on current code also counts those pending rows and returned Liberty 25, opponent 8, with 12 points unassigned (Kariuki and Bradshaw appeared from cluster ids). That is not the card to publish. Do not restart Flask.

**Proven (2026-09-16 afternoon):** The tag card is a compact centered dialog (not full-bleed). Every tag except Start/End QTR uses the same flow: Liberty vs this game’s opponent, then that team’s roster. Jump Ball asks who won. Steal still adds the matching turnover from the other roster. Add-player is an inline field (no nested `prompt()`), so Cancel / Esc / backdrop still close the card. Opponent roster keys off the team you are playing (Adrian on this game), not a generic Opponent list.

## Hermes (Scott 2026-09-29)

**Decision:** Hermes may edit `ai_bridge.py` only. The core sequence stays `ai_analyzer.py` → `event_generator.py` → `court_memory.py` / `net_detector.py`, then teach and the box. Hermes does not rewrite those files, does not get called from them, and does not change the ball detector. Paste `docs/agent_handoffs/HERMES.md` into a new Hermes window. Adapter output is JSON from `validated_stats` and is not applied to the film count.

## Do not

- Change production `ball_detector.pt` / `ball_confidence` without Scott
- Overwrite home DB from school
- Ask Scott to film-check every AI event
