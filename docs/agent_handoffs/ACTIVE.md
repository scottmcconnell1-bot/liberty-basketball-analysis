# Active Task

Updated: 2026-10-07 (evening). The full text of the previous, much longer version is `ARCHIVE/ACTIVE-snapshot-2026-10-07.md`. If this file and the archive disagree, this file wins. Read the archive only when you need a date or a number from an old run.

## Goal

Count stats for one game (Liberty at Adrian, NFHS video 73, `uploads\nfhs_gam0a66d85e12.mp4`, game id `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`) and check them against Scott's confirmed scorebook (Liberty 51, Adrian 26). Accuracy matters more than speed. It must work by 1 Nov 2026.

## Adrian count today (2026-10-07)

**Proven:**
- Scott's hand tags are saved on the server: 378 rows in `data/film_tags/<game id>.json`. Quarter ends: Q1 16:00.7, Q2 32:15.0, Q3 55:17.1 (last play is Jenkins' 3PT miss at 55:14.2). The tags score Liberty 43, Adrian 24 after three quarters (Q3 16-9). That matches the book. The fourth quarter remainder is Liberty 8, Adrian 2. The last tag is a Q4 Start QTR at 56:26.7 (the ball handed in); it belongs. Q4 is not tagged yet.
- Newest run is `...__rerun_20261006_033941` (run 12): 1,452 events, 206 shot rows. The 2026-10-06 card was 64 live points. After the seven tagged makes were restored it is 76 non-rejected make points (31 corrected, 45 pending). Book 77. The 45 are not film-checked. Run 11 was removed from the database on 2026-10-08.
- Shot rows where a make was seen (ball through rim or net moved): Q1 19 of 46, Q2 14 of 37, Q3 2 of 86, Q4 4 of 37. Every other row has `through_rim` false and `net_moved` false and is written as a miss. There is no "unknown" result. Q3 has 86 shot rows against about 42 real attempts Scott tagged (32 field goals, 10 free throws).
- 132 of the 170 rebounds are written within 6 seconds after one of those both-false misses. 804 of the 1,452 events are `possession_change`, which the box score ignores.
- Steals and fouls are not written (8 steal tags and 18 foul tags, zero events). Fouls are off by design (`emit_fouls` is False).
- Seven makes your tags had corrected in run 12 (12 points) had been rejected by `reconcile_makes_with_shots`, six of them by another shot's miss at the same moment. Restored on 2026-10-07 (before-state saved in `tag-exports/rejected_makes_before_restore_20261007.json`). Run 12 non-rejected make points are now 76 (book 77): 17 corrected rows (31 points) plus 21 pending AI rows (45 points). The pending rows are not checked against the film, so 76 is not an accuracy figure.

**Inferred:** The second-half collapse (about 40% of shots show a make in Q1 and Q2, 2% in Q3) looks like the hoop or net lock failing on the second-half camera view. The same code finds makes in the first half. Not yet checked against second-half frames.

**Unknown:** Why the lock fails in Q3 and Q4. Whether the fix is a setting, a rule, or the detector.

**Self-check (why):** Scott started it because the assistant had been wrong (the book does have a third quarter; his Q3 tags vanished; Jenkins was left as a free throw; typed tags were not saved). He asked whether the code, tools, and rules were what the AI was obeying. Results are in `JASON.md` and `BRAD.md`. The test run first called a hang did finish: 1,046 passed, 9 failed, 25 errors, almost all `tests/test_transfer_bundle.py` because the `bash` bundle build failed on Windows. A second copy was stopped and has no result. He asked on 2026-10-08 for the check to be run again.

Full first-run write-ups are in `JASON.md` and `BRAD.md`. Do not copy the book onto the rows. Do not start another detection pass expecting new baskets.

## Decisions (Scott, 2026-10-07)

1. **Both-false shot is written as a miss: keep for now, may need refining.** (`event_generator.py` about lines 806-846.) No code change.
2. **Steals:** `credit_steal` (`stat_rules.py` line 69) wrote no steals on this film (8 steal tags). Scott asked for a plain explanation; not changed.
3. **A manual tag is always truth.** `reconcile_makes_with_shots` (`manual_tag_teach.py` line 344) no longer rejects a make that is `corrected` or `human_verified`. Test: `test_a_tagged_make_is_never_rejected_by_the_ai_shot`. The seven wrongly rejected makes in run 12 were restored. The four in `...191418` went away when that rerun was removed.
4. **Indexes on `events`: approved.** `idx_events_game_ts` and `idx_events_game_type` are in `schema.sql` and created for existing databases by `ensure_event_indexes` in `helpers.py`. Proven present on the live database; the plan for `WHERE game_id=? ORDER BY timestamp_ms` uses the index.
5. **Archive, encrypt, VACUUM, then remove the five reruns (Scott, 2026-10-08): done.** Encrypted archive `encrypted-archive/liberty_adrian_detections_20261007.enc` is on `main` (commit `df83b66`). The passphrase is not in the repo. On 2026-10-08 the five reruns were deleted from the live database (4,139,840 detections, 7,055 events, plus their review, correction, classification, and provenance rows) and the file was compacted again. Integrity check passed. Kept: the base game (866,471 detections) and run 12 (883,276 detections, 1,452 events, corrected makes 31 points, pending 45, rejected 4). `film_analysis.db` is about 379 MB. Flask was restarted on it and the home page returned 200. The 378 tag rows were still served.
6. **Autosave: done** (see below).
## Film tool tags (fixed 2026-10-07, hardened evening)

**Proven:** Tags typed in the film tool lived only in the browser. `queueAutosave()` existed since 2026-09-16 and nothing called it, so tags reached the server only through the old Resume button, Save, or Teach AI. The 2026-10-06 commit `664a129` removed Resume and opened the server copy first, which replaced Scott's newer 378-row list with the 246-row server file. The 378 rows came back from Chrome's older storage (copies in `tag-exports/`). Now every add, edit, or delete is sent to the server 0.8 seconds later, the film opens the newer copy, and a saved game from another film is never sent to this film's file. `film_tool_tags.py` keeps dated copies in `data/film_tags/_history` before a shorter list replaces a longer one. Typing in the table took 4.7 seconds with 378 rows and now takes 0.07 seconds. The editable table is under the Reports tab. Hardening (Scott's item 6): the page also saves every 30 seconds and when the tab is hidden, but only if the tags changed. Every save carries the server version it was built on (baseUpdatedAt). The server refuses a save built on an older version, or one with no version (a tab opened before this fix), with a 409 and keeps its copy. A tab that is refused sets its own list aside in the browser (key ending :set-aside) and shows the server copy. History copies are made every 2 minutes while tags change: the newest 120, then one per hour for 72 hours. Proven on the live film: an edit reached the server by itself; a simulated second tab's newer save was not overwritten; a reload with no change writes nothing; an old-style save was refused. The real tag file was restored byte for byte after the test.

## Standing facts

- Working branch is `main`. `jason-5-may-updates` and `Brad/Claude` stay even with `main`. Jason's note is `JASON.md`, Brad's is `BRAD.md`. Push the same commits to `Brad/Claude` when a pull request is opened for Jason. Auto-accept pull request 147 is still open and is not on `main`.
- Home owns data. School uses Funnel only: https://liberty-coach.tail368a37.ts.net.
- Names: Dayley, Daley, and Daly are one Liberty player (#40, roster name Daly). Liberty has no 2 and no 6. Foster #22 is Adrian. Ask Scott before treating any other close spelling as the same person.
- A make is `ball_through_rim` or `net_moved_after_shot`. Only the core sequence writes one. Hermes may edit `ai_bridge.py` only; it is never called from the core. Its notes are `HERMES.md`.
- NFHS counting rules (Scott, 2026-09-15): FT is the lane lined up around the key with the camera locked on it. Assist is the last pass before a made field goal, 1-2 dribbles, no FT assists. Turnover is the offense losing the ball before a shot. Steal is the defender's active play causing that turnover. OREB or DREB comes from shooter and rebounder shirt color. Block is a deflection near the shooter's hand; if it still goes in, it is a field goal. Starters are the five the coach picks per game.
- Decisions still in force: the 79 unmatched tags stay unmatched (do not insert them as makes and do not widen the 8-second window). A rerun reads its own rows for identity and does not copy labels from the base game id.

## Do not

- Change production `ball_detector.pt` or `ball_confidence` without Scott.
- Overwrite the home database from school.
- Ask Scott to film-check every AI event.
- Copy the book onto the rows, or start another detection pass of this film expecting new baskets, fouls, or steals.
- Commit the GitHub credential file (`scottmcconnell1-bot-liberty-basketball-analysis-*.txt`).
