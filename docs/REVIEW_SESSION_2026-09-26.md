# Review session summary (2026-09-25 → 2026-09-26)

This is the index for the review work on branch `claude/review-fixes` (PR #148, into
`cursor/playbook-jason-clean-slate-ac1f`). It records what was found, what was
fixed, how each fix was proven, and what still needs the owner.

## Documents

| Document | What it holds |
| --- | --- |
| [REVIEW_FIXES_2026-09-26.md](REVIEW_FIXES_2026-09-26.md) | First review pass: 15 bugs and the security baseline, what was fixed, and which owner decisions are open |
| [REVIEW_FINDINGS_2026-09-26.md](REVIEW_FINDINGS_2026-09-26.md) | Full review: 94 findings by area, with file:line and severity |
| [validation/README.md](validation/README.md) | How every finding was validated, fixed and revalidated, and how to reproduce the proof |
| validation/{stats,film,schedule_roster,access,playbook,scouting_practice,ops}.md | One row per finding: failure before, fix, result after, test name |
| [validation/open_items.md](validation/open_items.md) | Leftovers found while fixing, and the merge of 8853d38 |

## Where the project stood at the start (2026-09-25, commit 2652e5e)

- **Test suite:** `pytest tests/` gave **703 passed, 23 failed, 12 skipped**, with 55% line
  coverage (Python 3.14, `requirements.txt` only). Running the suite also modified
  tracked files: `data/stat_books/confirmed/sample-hsb-liberty.json`, a transfer
  bundle, and new files in `data/play_matches/`.
- **Weakest coverage:** the code that produces stats had the least.

  | Module | Coverage |
  | --- | --- |
  | `ai_analyzer.py` | 7% |
  | `boxscore_constraints.py` | 12% |
  | `net_detector.py` | 16% |
  | `adrian_quality.py` | 33% |
  | `program_mode.py` | 42% |
  | `playbook_sheet_align.py` | 0% without OpenCV |
- **Stale tests:** 6 tests still required auto-accept = 0. The default had been changed to
  0.85, and precision mode made the default, inside the automated commit e46883c
  ("chore: daily learning status 2026-09-14"). The nightly job commits real code
  changes, some of them 60+ files.
- **Product state:** AI stat counting is far from its goal. The nightly panel was failing
  every gate (precision 3.4%, recall 7.4%, target 90%). Player identity was
  Unknown.
- **Branches:** this branch was 45 commits ahead of `jason-5-may-updates` and 20 behind
  `origin/main`. It is now 20 behind and 70 ahead of `main`. `main` has CI
  (`.github/workflows/tests.yml`: Python 3.12/3.13, no OpenCV, ruff F821/F811/F823/E9)
  and this branch does not. Deciding which line is the real one is still open.

## Earlier Claude PRs #139 → #140 → #141 (closed unmerged 2026-09-14)

The owner closed them because they targeted `jason-5-may-updates`. Some parts were
ported to `main` (#142/#143): the E2E suite and seeder, the precision generator,
`migrate_paths`, `mark_stale`, CI, the highlight/trim fixes and the share-link fix.
The rest was never ported. This branch now carries it:

- The `conftest.py` isolation fixtures (tests no longer write into the repo, and
  cannot start `analysis_launcher.py`).
- Transfer bundles that include `static/` and `stat_book/`.
- Same-second trim collisions and cross-worker trim status.
- `.env` values for `LIBERTY_DATABASE` / `LIBERTY_UPLOAD_FOLDER` being honoured.
- The dev `SECRET_KEY` warning.
- The service-worker precache fix.

Still only in the closed PRs (refs `pull/139..141/head`): `CLAUDE.md`,
`docs/agent_handoffs/TODO.md`, the session/resume handoff notes, the branch audit,
and that PR's version of `scripts/score_manual_q1_regression.py` with its test.

## What was found and fixed

| Round | Bugs | Proof |
| --- | ---: | --- |
| First pass: security baseline and 10 correctness bugs | 15 | Each test fails on 2652e5e and passes after |
| Full review of 7 areas (stats, film, schedule/roster, access, playbook, scouting/practice, ops scripts) | 94 | 95 strict-xfail tests, all failing under `--runxfail`; after the fixes, the final tests fail 134 times on the pre-fix code (28e6053) |
| Open items found while fixing | 7 | 10 tests fail on 8b5c670 |
| Merge of the owner's 8853d38: ported fixes plus the adopted Settings rule | 4 | 4 tests fail on b511af7 |
| Branch check before hand-off: net-detector tests failed without OpenCV (first-pass finding, fixed at the end), plus 4 pre-existing CI lint errors (one was an undefined `fail_` in `tests/test_ui_comprehensive.py`) | 5 | Suite without OpenCV: 3 failed before, 0 after; `ruff` (CI rules): 4 errors before, 0 after |

**Final state of the branch:**
- 988 passed, 31 skipped, 0 failed, 0 xfailed (with OpenCV).
- 977 passed, 16 skipped without OpenCV (the CI setup).
- `ruff check --select F821,F811,F823,E9` is clean.
- The suite writes nothing outside temp dirs.

## Needs the owner

1. **Chrome browser data in git history.** `tag-exports/_chrome_ls_q2/` (commit 81ff752,
   pushed by the nightly save) holds Local Storage for banking, id.me, Google and
   AI/dev sites. 8853d38 removed it from the tip, but it is still in history.
   - Sign out of or reset those sessions.
   - Purge the folder from history.
   - Collaborators' clones also hold it.
2. **Turn on sign-in.** `ENABLE_AUTH_MIDDLEWARE` is off. Create an admin, then enable it.
   The Funnel URL is public until then.
3. **Set `SECRET_KEY`** in the home PC `.env`.
4. **Run the nightly save once by hand.** `scripts/daily_git_save.ps1` and
   `scripts/watchdog_teach_loop.ps1` were not executed (no `pwsh` here). Their
   selection logic is Python and tested.
5. **Pick the integration line.** Either this branch or `main` should carry CI and
   receive merges. They have diverged.

## Not verified in this session

- **YOLO worker:** the real YOLO/ultralytics worker was not run (not installed). Tests
  replay its DB writes.
- **Browser JavaScript:** checked only where a test runs the page's own functions under node.
- **Push and email notifications:** live delivery was not checked.
