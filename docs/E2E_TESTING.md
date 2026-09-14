# End-to-End Test Suite

`tests/e2e/` drives **every feature through the application's own routes, in the order a
coach uses them, with real files** — uploads (whole-file and chunked), a real film clip,
a scorebook scan, roster CSVs, schedule and playbook PDFs, a team photo — and checks both the
HTTP result and the database after each step. It also sweeps every parameterless GET route
for crashes and prints endpoint coverage at the end.

## Three ways to run it — same tests

| Mode | Command | Analysis | Time | Use for |
| --- | --- | --- | ---: | --- |
| Test client, synthetic | `.venv/bin/python -m pytest tests/e2e -q` | stubbed; synthetic detections + AI drafts seeded | ~40 s | CI, every commit (it is part of `pytest tests/`) |
| Test client, real detector | `LIBERTY_E2E_REAL_ANALYSIS=1 .venv/bin/python -m pytest tests/e2e -q` | `ai_analyzer` runs in-process on a 12 s real clip | ~2 min | after pipeline changes (needs the CV stack) |
| **Live server** | `bash scripts/run_e2e_live.sh` | scratch gunicorn on :8090 spawns the real worker | ~2.5 min | before a release; proves the production path |

The live script boots gunicorn with its **own** SQLite file and upload folder under
`/tmp`, so the production DB is never touched, and removes the e2e stat-book confirmations
that the app writes into `data/stat_books/confirmed/`. `KEEP=1` leaves the server up.

Results on the Linux workstation, 2026-09-11: 18/18, 18/18, 17/18 + 1 skipped
(`admin reset` is only exercised against the temporary DB). Endpoint coverage 219 / 251 (87%).

## What it covers (in order)

1. **Route sweep** — every parameterless GET (49 routes) must not 500.
2. **Settings / runtime** — `/api/ai/runtime`, resource status, saving Settings with all
   feature flags (an omitted checkbox turns a flag off — the form is posted whole).
3. **Seasons + schedule** — API and HTML-form paths, result recording, MaxPreps export,
   schedule PDF parse + confirm import, deletes.
4. **Games / sources / NFHS matches** — CRUD, confirm, four-factors.
5. **Roster** — CSV parse → players created; film rosters (home/away) import + PUT; team photo
   upload/list/delete.
6. **Users / messaging / issues** — register coach + admin, login, profile, notification
   preferences, send/poll/read messages, notifications, bug report + complete, logout.
7. **Video** — `/upload` (XHR) of the real 12 s clip (or a synthetic clip), analysis to
   `completed`, chunked upload (3 chunks) of a second clip, videos API, duplicate check,
   archive/unarchive, **ffmpeg trim job to completion**, compare page, **rerun** to a second run.
8. **Analysis pages + events API** — analysis/film/review/plays pages, court-slot mapping,
   play-match run, manual `save_event` → PUT → DELETE.
9. **Review → ledger → highlights** — accept / reject / correct, ledger statuses verified in
   SQLite, highlights limited to reviewed events, **clips cut with ffmpeg**, clip CRUD,
   canonical link, playlists CRUD.
10. **Practices** — form save, plan items CRUD, AI notes generate (heuristic), report.
11. **Playbook** — categories, play save/edit/export, **share link renders** (the route that
    500'd before 2026-09-09), duplicate, reorder, move, choreography, copy-to-team, opponents
    book, PDF import parse + save, bulk parse/split/save.
12. **Scouting** — report CRUD, all eight sections, generate, print view, NFHS lookup offline
    returns a clean error (not a crash page).
13. **Stat books** — templates, sample, **scan upload → align → draft → confirm → confirmed API**.
14. **Assistant** — query + workflow endpoints.
15. **Coach portal** — login with the shared password; ops routes return **403** while the
    read-only coach session is active; logout restores them.
16. **Rebuild events in both generator modes** — `expanded` then `precision` through the
    app's regenerate endpoint (precision produces ≤ expanded), default restored.
17. **Admin reset** (temp DB only) — with dependent rows present.
18. **Coverage report** — every blueprint exercised; ≥ 60 % of endpoints hit.

## Test data

`tests/e2e/data.py` generates everything; nothing personal is embedded (player names are
invented — never copy the real rosters into fixtures):

- videos: a 6 s H.264 test pattern (ffmpeg `testsrc`), and a 12 s cut of the real Wilder Q1
  snippet when `data/videos/Q1_snippet.mp4` is hydrated from LFS
- roster CSV (12 fictional players + 5 opponents), schedule PDF, 2-page playbook PDF with
  shapes (pymupdf), team photo PNG (PIL), the repo's sample scorebook scan
- synthetic detections (10 stable "players" + a ball that arcs every ~4 s) and pending AI
  drafts via `event_generator.persist_events`, used whenever the real detector does not run

**Demo / validation database:** `python scripts/seed_e2e_data.py --db demo.db --uploads demo_uploads`
runs the same scenarios and leaves a populated DB (seasons, schedule with results, roster,
videos incl. the real clip, 6k+ detections, reviewed events, clips, plays, a practice, a
scouting report, users, a confirmed stat book). Serve it with
`LIBERTY_DATABASE=demo.db LIBERTY_UPLOAD_FOLDER=demo_uploads .venv/bin/gunicorn --bind 127.0.0.1:8091 app:app`.

## Bugs this suite found on first run (fixed in the same PR)

- `/settings/notifications` — INSERT listed 9 columns and supplied 8 values: every save of
  the page crashed. Regression test in `tests/test_messaging.py`.
- `/api/admin/reset` — deleted `events`/`videos` while `clips`, `event_participants`,
  `shot_classifications`, `possessions` … still referenced them → `FOREIGN KEY constraint
  failed` as soon as any clip existed. Now deletes dependents first. Regression test in
  `tests/test_api.py`.

Also observed, not changed: several JSON endpoints `.strip()` ids and crash (500) when a
client sends an integer instead of a string (`/api/messages/send`, `/api/messages/read`,
`/playbook/import/save`); `save_event` requires the relational `games.id`, not the analysis
key; `/api/rosters/import` only parses (players are created via `/api/players`).

## Extending

Add a step function in `tests/e2e/scenarios.py`, append it to `SCENARIO_STEPS`, and add a
one-line `test_NN_...` wrapper in `test_e2e_flow.py`. Use `e.state` to pass ids forward,
`ok(resp, *codes)` for assertions, and `e.db()` to verify what the app wrote.
