# Finding validation log (2026-09-26)

Every finding in `docs/REVIEW_FINDINGS_2026-09-26.md` went through the same
four steps:

1. **Validate.** Run the finding's test with `--runxfail` and record the first
   failing assertion, which proves the bug.
2. **Fix** the root cause in the app or script code.
3. **Revalidate.** Remove the `xfail` marker, run the same test, and confirm it
   passes. Tests that only checked a status code or source text were rewritten
   to check the behaviour.
4. **Keep the test** in the suite as the permanent regression test.

Each file below has one row per finding: before, fix, after, and the test name.

| Area | Log | Findings | Tests that fail on the pre-fix code |
| --- | --- | ---: | ---: |
| Stats, review, scorebook | [stats.md](stats.md) | 13 | 14 |
| Film, analysis, NFHS | [film.md](film.md) | 14 | 15 |
| Schedule, seasons, roster | [schedule_roster.md](schedule_roster.md) | 16 | 17 |
| Access control, messaging, settings | [access.md](access.md) | 14 | 16 + 7 in tests/test_messaging.py |
| Playbook | [playbook.md](playbook.md) | 14 | 14 |
| Scouting, practice, assistant | [scouting_practice.md](scouting_practice.md) | 10 | 11 |
| Ops scripts | [ops.md](ops.md) | 16 | 39 + 1 in tests/test_wipe_film_analysis.py |

Some findings have more than one test, and some tests were added beyond the
original xfails. That is why the right-hand column is larger. The bulk-import
page overwrite is one finding, covered in both the playbook and schedule files.

## Evidence

- **Final suite:** `pytest tests/ -p no:cacheprovider` → **975 passed, 31
  skipped, 0 xfailed**. `--runxfail` gives the same result, so no known bug is
  hidden.
- **Tests catch the bugs:** the final `tests/` run against the pre-fix app
  code (commit 28e6053) → **134 failed, 841 passed**. Every area fails at
  least once per finding. Reproduce with:
  ```
  mkdir /tmp/old && git archive 28e6053 | tar -x -C /tmp/old
  rm -rf /tmp/old/tests && git archive HEAD tests | tar -x -C /tmp/old
  cd /tmp/old && python -m pytest tests/ -q -p no:cacheprovider
  ```
- **No writes outside temp dirs:** the suite writes nothing outside them, and
  that includes gitignored folders.

## Not verified here

- **PowerShell:** `pwsh` was not available, so `scripts/daily_git_save.ps1` and
  `scripts/watchdog_teach_loop.ps1` were not executed. Their selection logic
  was moved into Python (`scripts/git_save_select.py`) and tested against real
  git. The .ps1 text is checked by tests.
- **Real YOLO worker:** tests replay its database writes, because ultralytics
  and torch are not installed.

## Owner decisions made during the fixes

- **Settings with sign-in on:** only admins can change settings. A signed-in
  non-admin is refused in either mode. With sign-in off, the anonymous
  behaviour is unchanged.
- **Messaging:** identity comes only from the session. Anonymous callers get
  401 even with sign-in off.
- **Logout:** a session only counts if its token is still live in
  `user_sessions`.
- **Event rebuild:** anything a person decided (manual tags, accept, correct,
  reject) survives a rebuild without a duplicate. Machine output (drafts,
  auto-accepts, teach grading) is regenerated, so rebuilds are idempotent.
- **Deleting a scored scheduled game** unlinks the results and keeps them.
  **Deleting a season with results** is refused with 409.
- **Shared plays** get token-scoped routes for their own sheets and
  choreography. `/uploads` stays private. Share links can now be revoked.
- **Nightly git save** now uses an allowlist. The Chrome data already pushed
  (`tag-exports/_chrome_ls_q2/`) is now in `.gitignore` but is still tracked
  and still in history. The owner has to purge it and reset those sessions.
- **Wipe script** takes a verified backup first and deletes rows instead of
  dropping tables. Coach-authored rows are kept.

## Open items found during fixing (not yet fixed)

- `DELETE /api/events/<id>` still returns 500 when a clip or dev clip
  references the event. This needs a decision on what happens to the clip.
- The Users page reads fields `/api/users` does not return, so it shows
  "undefined". Deleting a user referenced by `created_by`/`reviewed_by` still
  hits the FK.
- The assistant's turnover and clip lookups still match names with `LIKE %x%`.
- The scouting report editor leaves a few fields unescaped (`game_time`,
  `jersey_number`).
- NFHS progress counters still sum across runs that share a relational game.
  `/api/upload_video` can still overwrite a same-named file.
