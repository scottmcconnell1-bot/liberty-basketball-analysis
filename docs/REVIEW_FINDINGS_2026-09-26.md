# Full code review findings (2026-09-26)

Branch: `claude/review-fixes`. This review covers the code the first pass
(docs/REVIEW_FIXES_2026-09-26.md) did not: stats, film pipeline,
schedule/roster, access control, playbook, scouting/practice/assistant,
and the unattended ops scripts.

**Evidence.** Every finding has a regression test marked
`xfail(strict=True, reason="BUG: ...")` that asserts the correct behaviour.
`pytest tests/ --runxfail` shows all 95 failing on the bug they name, with no
setup errors. When a bug is fixed, its test starts passing and strict xfail
turns it red, so remove the marker in the same change.

**Suite:** `pytest tests/` → 846 passed, 31 skipped, 95 xfailed (~27 s). The
run writes nothing outside temp dirs.

**Status (later on 2026-09-26): all findings are fixed.** Each one was
validated, fixed and revalidated, and its test is now a normal regression
test. See docs/validation/README.md. The suite is 975 passed, 0 xfailed.

## Act on these first

1. **Personal browser data is on GitHub.** The nightly save
   (`scripts/daily_git_save.ps1:88-133`) runs `git add -A` and then unstages a
   short fixed list. Commit 81ff752 pushed `tag-exports/_chrome_ls_q2/`: a copy
   of a Chrome profile's Local Storage, with entries for banking, id.me, Google,
   AI and developer sites. It also pushed server logs, scratch images and test
   output such as `models/film_tool_jrhigh_adrian,_or_TEACH.json`.
   Steps: sign out of or reset those sessions, purge the folder from history,
   and switch the job to an allowlist.
   Test: `test_daily_save_does_not_stage_runtime_junk`.
2. **Messaging is readable and writable by anyone** (`blueprints/messaging.py`).
   - Any user can poll or read any conversation (297, 125-139).
   - Any user can post into any conversation (243).
   - With sign-in off (the default, on a public URL), an anonymous request can
     post as any `sender_id`, including the admin (32).
   - The conversation list shows everyone's conversations (111).
   - Read receipts come from the payload (315).
   Tests: `test_journey_access.py::test_messaging_*`.
3. **Any signed-in user can change Settings** (`blueprints/core.py:1883`),
   including turning the sign-in gate off; the same goes for `/settings/ollama/pull`.
   A stale coach-portal cookie gets full access once the portal is disabled
   (`app.py:200`). Logout does not invalidate a copied cookie (`users.py:57`).
4. **Rebuilding events duplicates trusted events** (`event_generator.py:1138`).
   `persist_events` deletes only `human_verified=0` rows, while auto-accept
   (0.85 since 2026-09-14) marks drafts human-verified. Every rebuild therefore
   adds another accepted copy (4 → 8 → 12), and box scores and highlights
   inflate. On NFHS videos a rerun also deletes the primary run's drafts (1139)
   and loads the primary's detections (20).
5. **Stats are wrong in common cases.**
   - `stats.py:228` counts free throws as FGM/FGA.
   - Coach corrections and edits change `event_type` but not `event_type_id`,
     so the stats ignore them (`blueprints/clips.py:806`, `268`).
   - Events added with the Film Tool "+ add" never reach `/api/stats`
     (`clips.py:549`).
   - The program ledger double-counts AI shot+make pairs (`program_mode.py:386`)
     and ignores OREB/DREB (406).
6. **Teach loop can kill a live analysis** (`scripts/hoops_teach_loop.py:275-334`).
   When the process probe fails or times out, the loop reads that as "no
   worker", marks the running run failed, and starts a second GPU job. A failed
   teach is still marked taught using stale scores (676-719). One broken game
   blocks the queue forever (592-615). A truncated state file crashes the loop
   on every restart (162-170).
7. **The schedule re-import duplicates every game** (`blueprints/core.py:1240`),
   which double-counts W-L. Deleting a scored game, a season, or a game that has
   sources returns 500 on the FK (`core.py:554`, `446`; `games.py:142`, `238`).
   The season archive leaves out all game results (`scripts/archive_season.py:150`).

## All findings by area

Severity: H = high, M = medium, L = low. The test is in the file named in each
section header.

### Stats, review, scorebook — `tests/e2e/test_journey_stats.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | stats.py:228 | Free throws are counted as field goals |
| H | blueprints/clips.py:806 | Review "correct" leaves `event_type_id` stale, so stats ignore the correction |
| H | blueprints/clips.py:549 | Film Tool "+ add event" rows lack `event_type_id`/`relational_game_id` and are never counted |
| H | program_mode.py:386 | Ledger double-counts AI `shot` + `make` pairs |
| M | blueprints/clips.py:268 | Event edit (PUT) leaves `event_type_id` stale |
| M | stats.py:590,594,690 | Team stats and four factors need `shot_result=='made'` and ignore AI `make`/`miss` |
| M | program_mode.py:406 | Ledger ignores offensive and defensive rebounds |
| M | blueprints/clips.py:293 | Deleting a tag after viewing stats returns 500 (possessions FK) |
| M | program_mode.py:57 | Path traversal: `/api/program/<path>` reads any `.json` scorebook |
| L | blueprints/clips.py:179 | `reviewed_at` stores 'accepted'/'pending' text |
| L | stat_book/demo.py:69 | The sample book stores running quarter totals, so the line score sums to 122 when the final is 48 |

### Film, analysis, clips, NFHS — `tests/e2e/test_journey_film.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | event_generator.py:1138 | Rebuild duplicates accepted and auto-accepted events |
| H | nfhs.py:448 | A partial NFHS download overwrites the full-game file |
| M | event_generator.py:20 | Rerun rebuild on NFHS videos also loads the primary run's detections |
| M | event_generator.py:1139 | Rerun generation deletes the primary run's drafts |
| M | blueprints/ai.py:1352 | The compare page subquery uses a non-existent `games.game_id`, so detection counts are wrong |
| M | manual_tag_teach.py:154 | Re-saving Film Tool tags after a highlight clip returns 500 (FK) |
| M | blueprints/ai.py:1895,1095,2019 | Same-second uploads overwrite the first file, then 500 |
| M | helpers.py:1527 | An interrupted rebuild stays "running" forever |
| M | blueprints/ai.py:1155 | Chunked upload without the AI runtime leaves the run pending forever |
| M | blueprints/ai.py:1082 | Path traversal: `upload_id` writes chunks anywhere |
| M | blueprints/scouting.py:121 | NFHS login with a new password keeps the old stored password |
| M | blueprints/scouting.py:124 | A failed NFHS login replaces the working saved credentials |
| L | helpers.py:800 | Same-second reruns share one analysis key |
| L | blueprints/ai.py:395 | Double-encoded game ids are never reconciled |

### Schedule, seasons, roster — `tests/e2e/test_journey_schedule_roster.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | blueprints/core.py:1240 | Schedule PDF re-import duplicates every game |
| H | blueprints/core.py:554; games.py:142 | Deleting a scored scheduled game returns 500 |
| H | blueprints/core.py:446; stats.py:86 | Deleting a season with results returns 500 |
| H | blueprints/core.py:1835 | Path traversal: team photo `team_key` |
| H | scripts/archive_season.py:150 | The archive leaves out game results (`games.season_id` does not exist) |
| M | blueprints/games.py:71 | API-created girls and jr-high games count for the boys card |
| M | blueprints/core.py:2287 | The dashboard counts a game once per linked `games` row |
| M | blueprints/core.py:1248 | Import ignores the per-row team selection |
| M | blueprints/core.py:855 | Legacy PDF rows like "TUES, DEC 4" merge into one game |
| M | roster_import.py:239 | The CSV maps columns by position and ignores the header, and blank cells shift columns |
| M | blueprints/core.py:1835 | Same-second team photos overwrite each other |
| M | blueprints/games.py:238 | `DELETE /api/games/<id>` with sources returns 500 |
| L | blueprints/core.py:2310 | Upcoming/recent use the UTC date |
| L | film_roster.py:199 | A merge re-import duplicates a player when the grade changes |

### Access control, messaging, settings — `tests/e2e/test_journey_access.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | blueprints/messaging.py:297 | Anyone can read any conversation |
| H | blueprints/messaging.py:243 | Anyone can post into any conversation |
| H | blueprints/messaging.py:32 | An anonymous request can send as any user |
| H | app.py:200 | A stale coach cookie bypasses the gate once the portal is disabled |
| H | blueprints/core.py:1883 | Any signed-in user can change all settings, including the gate |
| M | blueprints/messaging.py:111 | The conversation list is not scoped to the user |
| M | blueprints/messaging.py:315 | Read receipts use the user_id from the payload |
| M | services/notifications.py:181 | Message notifications never fire (missing columns) |
| M | blueprints/users.py:57 | Logout does not invalidate the session |
| M | blueprints/coach.py:216 | Open redirect on coach login `next` |
| M | helpers.py:1674 | `safe_return_path` fallback raises BuildError (500) |
| M | blueprints/core.py:2559 | User delete always returns 500 and has no auth check |
| M | module_entitlements.py:33 | A negative-UTC-offset entitlement date crashes scouting and playbook |
| L | blueprints/messaging.py:203 | A numeric `recipient_id` returns 500 |

### Playbook — `tests/e2e/test_journey_playbook.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | blueprints/bulk_import.py:156 | Each bulk import overwrites earlier imports' sheet images |
| M | playbook_vector_extract.py:104 | Stored sheet URLs never resolve to their PDF, so the vector path is dead |
| M | playbook_vector_extract.py:104 | Path traversal: an absolute `image_url` opens any `<dir>.pdf` (shown by a direct probe only) |
| M | blueprints/playbook.py:1677 | Import accepts `.html` and serves it same-origin (stored XSS) |
| M | templates/playbook.html:1916 | Dragging sheets to a new order saves the choreography onto the wrong sheets |
| M | playbook_taxonomy.py:547 | Moving a category under its own child makes both vanish |
| M | playbook_taxonomy.py:541 | Rename or move leaves descendant slug paths stale |
| M | static/js/playbook-dnd.js:135 | Category name goes into innerHTML (stored XSS) |
| M | blueprints/playbook.py:399 | Duplicate and copy-to-team drop the saved choreography |
| M | blueprints/bulk_import.py:446 | Bulk-imported plays always land in HS Boys |
| M | app.py:182 | With sign-in on, a shared play's images and choreography are blocked |
| L | playbook_taxonomy.py:556 | A category cannot be moved to the top level |
| L | playbook_play_match.py:47 | Play-match cache collides for game keys that differ only in punctuation |
| L | blueprints/playbook.py:1261 | A share link cannot be revoked |

### Scouting, practice, player development, assistant — `tests/e2e/test_journey_scouting_practice.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | blueprints/scouting.py:590 | Auto-generate uses pending and rejected AI events |
| H | blueprints/scouting.py:593 | Joins `events.player` to `players.id`, which lists Liberty players as opponent personnel |
| M | blueprints/scouting.py:594 | Auto-generate never finds AI events (legacy vs relational game id) |
| M | templates/scouting_report_print.html:39 | Stored XSS on the print page and dashboard |
| M | helpers.py:543 | Practice LLM notes return 500 whenever Ollama is configured |
| M | player_development.py:321 | Deleting a playlist used by a plan returns 500 |
| M | player_development.py:218 | A moved dev clip keeps the old `relational_game_id` |
| M | assistant_query.py:86 | Name match returns "Al" for "Alice" |
| L | blueprints/scouting.py:462 | Child POST to a missing report returns 500 instead of 404 |
| L | player_development.py:347 | Adding a missing clip to a playlist returns 500 |

### Ops scripts — `tests/test_ops_scripts_regression.py`
| Sev | Where | Bug |
| --- | --- | --- |
| H | scripts/daily_git_save.ps1:88-133 | Stages everything, so personal browser data, logs and test output get pushed |
| H | scripts/hoops_teach_loop.py:275-334 | A probe failure reclaims a live run and starts a second job |
| M | scripts/hoops_teach_loop.py:676-719 | A failed teach is marked taught with a stale score |
| M | scripts/hoops_teach_loop.py:592-615 | No retry cap: one broken game blocks the queue |
| M | scripts/hoops_teach_loop.py:162-170 | A truncated state file crashes the loop permanently |
| M | scripts/teach_from_boxscore.py:75 | `--write-model` erases the merged HUDL caps |
| M | scripts/teach_from_hoops_pbp.py:166 | Trains on the primary run instead of the newer full rerun |
| M | scripts/score_full_film_panel.py:449 | Gates average only games with data and can PASS when most are missing (proof tests are in the session scratchpad, not the repo) |
| M | scripts/compare_ai_to_hoops_pbp.py:126 | Matching ignores event type, which deflates P/R (proof test is in the session scratchpad, not the repo) |
| M | liberty_data_paths.py and scripts | The scripts ignore `LIBERTY_DATABASE` and may back up or wipe the wrong DB |
| M | scripts/wipe_film_analysis.py:20,49 | No backup; drops coach corrections, playlists and dev clips |
| L | scripts/backup_db.py:74 | A `#` in the path produces an empty backup, then good backups are pruned |
| L | scripts/score_full_film_panel.py:601 | The panel JSON is written non-atomically (no repo test; proof is in the session scratchpad) |
| L | scripts/import_hudl.py:313 | Slugged filenames collide on re-import |
| L | scripts/materialize_lfs_models.py:296 | Crashes once weights are materialized |
| L | hoops_teach_loop.py + watchdog_teach_loop.ps1 | Pause marker is never read, and the watchdog restarts a finished loop (found by reading the code; no test) |

## Not covered

- The real YOLO worker: the tests replay its DB writes because there is no
  ultralytics or torch here.
- PowerShell scripts: `pwsh` was not available, so the git-save logic was
  replayed in a temp repo instead.
- Browser JS beyond functions run in node.
- Live push and email delivery.
