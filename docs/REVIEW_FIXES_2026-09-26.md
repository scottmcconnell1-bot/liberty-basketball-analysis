# Code review fixes (2026-09-26)

Branch: `claude/review-fixes` (from `cursor/playbook-jason-clean-slate-ac1f` @ 2652e5e).
Each fix has a regression test that fails on 2652e5e and passes here. Now part of PR #148
(see docs/REVIEW_SESSION_2026-09-26.md for the full picture).

Test run (Python 3.14, `requirements.txt` + `opencv-python-headless`):
`pytest tests/` after this first pass → **770 passed, 31 skipped**. Before: 703 passed, 23 failed.
Final state of the branch: 988 passed, 31 skipped, 0 xfailed.
The suite no longer writes into tracked files.

## Scott decisions still open

| Item | State on this branch | Scott action |
| --- | --- | --- |
| Global sign-in | Built behind `ENABLE_AUTH_MIDDLEWARE`, **off** by default | Create an admin account, then flip the flag in Settings. Until then the Funnel URL is open to anyone. |
| `SECRET_KEY` | App logs a warning when the committed dev key is used | Set `SECRET_KEY` in the home PC `.env` |
| Admin reset | Now requires a signed-in **admin**, even with the flag off (behavior change) | Needs an admin account to use Videos → Clear All Videos |
| Auto-accept 0.85 + precision mode | Kept (set 2026-09-14); tests updated to match | Confirm, or set 0 in Settings to turn it off |

## Security

- `/api/admin/reset` (`blueprints/core.py`): was an unauthenticated POST that deletes every video file and all analysis rows. Now admin-only. It also used to fail the foreign-key check once any review/possession/clip rows existed; it now clears dependent tables in the same order as `scripts/wipe_film_analysis.py`.
- Sign-in gate (`app.py`, `config.py`): implements `docs/AUTH_REENABLE_PLAN.md` B2/B3 behind the flag. APIs get 401 JSON, pages redirect to `/login`. `/login`, `/static/`, `/sw.js`, `/coach*` and `/play/share/` stay public; coach-portal sessions pass through (still read-only).
- `/register` closed to the public (ported from `main` f707535 + 96af858).
- Passwords (`blueprints/users.py`): new hashes use Werkzeug's KDF. Old salted-SHA-256 hashes still log in and are upgraded on that login. Comparison is constant-time. The `next` redirect after login only accepts local paths.
- `.env` values for `LIBERTY_DATABASE` / `LIBERTY_UPLOAD_FOLDER` are now honored when running `python app.py` (config was read before `.env` loaded).

## Bugs fixed

| File | Bug |
| --- | --- |
| `adrian_quality.py` | Refine rejected coach-corrected events whose note was not the default text |
| `static/js/film-tool.js` | Add-at-playhead and the play lists used review time, not analysis time (ignored film sync offset) |
| `game_boxscore.py` | Liberty PTS came from the away score when neither team name contains "liberty" |
| `game_boxscore.py` | Book `fgm`/`fga` totals were ignored, so 2PT showed 0-0 |
| `event_generator.py` | A dropped pump-fake candidate blocked the same player's real shot for 6 s |
| `event_generator.py` | Removed ~108 unreachable lines after `return events` |
| `maxpreps_web.py`, `scripts/backfill_maxpreps_results.py` | Results matched by date only; doubleheaders could get the other team's score |
| `blueprints/core.py`, `maxpreps_web.py` | Failed ranking scrape overwrote the cached ranking with NULL; JS-rendered pages never tried the browser fallback |
| `scripts/watchdog_liberty_server.py` | A hung server holding :8080 was never restarted |
| `templates/playbook.html` | View mode allowed sheet edits with no way to save; now says so, links to Edit, and warns before leaving |
| `blueprints/playbook.py` | Share links crashed (`sqlite3.Row.get`) |
| `blueprints/users.py` | Saving notification preferences crashed (8 values for 9 columns) |
| `static/sw.js` | Service worker pre-cached a stylesheet that does not exist, so it never installed |
| `video_trim.py` | Two trims in the same second collided; status polls failed across workers (port of the closed PR #139/#141 fix) |
| `scripts/build_transfer_bundle.sh` | Bundles left out `static/` and `stat_book/`, so a restored copy could not import (port of closed PR #139) |

## Test suite

- `tests/conftest.py`: play-match JSON, analysis logs and confirmed scorebooks go to temp dirs. Any test that tries to start `analysis_launcher.py` for real now fails.
- Outdated tests updated where the product changed on purpose: auto-accept 0.85, Film Tool panels moved to Analysis Results, Preview nav hidden, rerun now validates the video and models.
- CV-only tests skip cleanly without `ultralytics`. The launcher test skips on an unsupported Python.
