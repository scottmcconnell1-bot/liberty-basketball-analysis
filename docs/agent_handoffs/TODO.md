# TODO — everything left to work on (as of 2026-09-11)

Legend: **[SCOTT]** needs Scott's decision/approval per `AUTHORITY.md` · **[AGENT]** any agent can
do it on a branch · **[USER]** the operator's machine/account · P0–P3 priority.
Each item names where the evidence lives. Update this file when an item closes.

## P0 — safety of the data (before anything else)

- [ ] **[SCOTT] Disable or repoint GitHub Pages.** `gh-pages` publicly serves the private
      repo's application source and the athlete roster CSV (verified 200s). Only LFS pointers
      are served for weights/film. → `docs/BRANCH_AUDIT_2026-09-09.md` §6.
- [ ] **[SCOTT] Merge the stack** #139 → #140 → #141 (`claude/local-standup` →
      `claude/precision-mode` → `claude/e2e-suite`). Everything below assumes the tip.
- [ ] **[SCOTT] Auth is a no-op** (`app.py:require_auth_for_api` is `pass`) and `/register`
      grants any role incl. `admin` with no invite. Plan exists: `docs/AUTH_REENABLE_PLAN.md`.
      Until then: loopback bind only, never the tunnel scripts, never `0.0.0.0` with real data.
- [ ] **[SCOTT] Remove the committed dev `SECRET_KEY` fallback** (now warns; still boots).
- [ ] **[SCOTT] Password hashing** is salted SHA-256 (→ argon2/bcrypt); NFHS credentials are
      XOR'd with a hard-coded key (`nfhs.py`); CSP is `default-src *`. → `docs/SECRETS_AUDIT.md`.
- [ ] **[SCOTT] 4 GB `MAX_CONTENT_LENGTH` on an unauthenticated upload route** (`app.py`).

## P1 — the product's core: make AI output usable

- [ ] **[AGENT] Precision round two** (opt-in `precision` mode only; `expanded` stays default):
      - make/miss over-calls makes (88 of the remaining 346 FPs) — the "dead-ball gap ⇒ make"
        rule; changing the gap alone just moved makes into misses+rebounds.
      - shot type never reaches the event → every 3PT scores as 2PT. Carry
        `shot_classifications.shot_type` (keyed by `event_id`) into `events.details_json`
        at classification time, or join it in the scorer; then fix `film_analysis.py::
        classify_shot_type` (528/578 "3pt" on junior-high film is not real).
      - steals/turnovers 61/59 vs true 4/6; assists 51 vs 5 — tightening traded hits 1:1.
      Measure every change: `scripts/score_manual_q1_regression.py --analysis-key <key> --no-fail --per-tag`
      on a **copy** of the DB. Gates: precision ≥ 0.08, recall ≥ 0.25, exact ≥ 12, AI-only ≤ 400.
      Current: 0.087 / 0.623 / 33 / 346. Target ≥ 0.15 holding recall. → `ANALYSIS_QUALITY_BASELINE` §3b.
- [ ] **[SCOTT] Flip `ai.event_generator_mode` to `precision`** once satisfied (Settings → Runtime).
- [ ] **[AGENT] Fouls / free throws** — 0 of 7 fouls found in Q1; no whistle/ref-signal path.
      `experiments/detect_referee_signals.py` exists, unwired. Research item.
- [ ] **[AGENT/SCOTT] Detector recall** ~50 % on people, ball ≥0.25 conf in 12 % of frames on
      this fixed wide-angle camera. Ground truth for detection exists (`benchmark/`, `dataset-v2`
      branch). Camera-specific fine-tuning is the long pole; do after the event layer.
- [ ] **[AGENT] Tracking fragmentation** — ByteTrack *is* running (`ai_analyzer.py:167-178`) and
      still yields 1,036 IDs for ~13 people in 5 min; `tracker_assigner.assign_trackers_bytetrack`
      is a dead stub (returns centroid) — delete or wire it **[SCOTT: deleting code]**.
- [ ] **[USER] Jersey OCR** reads 0 numbers (EasyOCR not installed, not in requirements). Player
      identity is cluster index until this works. Adding EasyOCR = new library **[SCOTT]**.
- [ ] **[AGENT] Rescue the July learning loop**: `cursor/film-tool-reports-fix-ac1f` has
      `event_calibrator.py` + `scripts/teach_from_manual_q1.py` ("teach AI from manual Q1").
      Check out, run the scorer with the same tolerance, compare to precision mode. → BRANCH_AUDIT C2.

## P1 — Scott's real data onto a second machine

- [ ] **[SCOTT] Decide which copy is authoritative** if his Windows box keeps running.
- [ ] **[SCOTT] Export**: `py -3.12 scripts\backup_db.py --out-dir <drive>` (WAL-safe) +
      `certutil -hashfile … SHA256`; film via `robocopy /MIR /Z` (not a tarball). Send
      `LIBERTY_COACH_PASSWORD` and his `LIBERTY_UPLOAD_FOLDER` value.
- [ ] **[AGENT] On arrival**: `sha256sum`, `PRAGMA integrity_check`, row counts,
      `scripts/migrate_paths.py --db … --audit`, snapshot (`backup_db.py`), then
      `--from-prefix 'C:\…\uploads' --to-prefix … --apply --stat-books-dir …`; snapshot again
      before first boot (`ensure_db()` migrates in place, incl. `_migrate_analysis_runs_identity`).
      → LOCAL_STANDUP §7.

## P2 — engineering debt that will keep biting

- [ ] **[AGENT] Background work runs inside gunicorn workers**: trims are threads in a worker
      (restart kills them; registry now file-backed as a stopgap); analysis is a detached
      subprocess nobody supervises (`scripts/mark_stale_analysis_runs.py` is the stopgap). A
      job table + one worker process fixes both. New table ⇒ **[SCOTT]** schema.
- [ ] **[AGENT] Harden JSON endpoints that `.strip()` ids** and 500 on an integer:
      `/api/messages/send`, `/api/messages/read`, `/playbook/import/save`, `/api/court-slots`
      (list of dicts). `str()`/type-check before `.strip()`. Found by tests/e2e.
- [ ] **[SCOTT] Migrations** are ~60 ad-hoc `ALTER TABLE`s in `helpers.py:_ensure_migration_columns`
      with no version number; two divergent DBs (his + this) is where it bites.
- [ ] **[SCOTT] Repo size 727 MB**: `film_analysis.db` committed 78×, 792 `.log` objects,
      `yolov8m.pt`/`yolo11m.pt`/an `uploads/*.mp4` in history. `git filter-repo` breaks every
      clone — schedule it deliberately.
- [ ] **[SCOTT] Root clutter**: ~100 `_tmp_*.py` scratch files, `node_modules/` with no
      `package.json`, `pose_landmarker.task` (30 MB, nothing imports it, `mediapipe` in no
      requirements). Deleting = gate.
- [ ] **[SCOTT] Branch cleanup**: 59 safe deletions, tag+delete orphan `main` and
      `dataset-v2`, fast-forward default to `cursor/film-tool-review-layout-ac1f` (0 behind),
      triage July cluster. → `docs/BRANCH_AUDIT_2026-09-09.md` §9 (delete `claude/*` after merge).
- [ ] **[AGENT] Timestamps**: filenames local (now consistent), DB `CURRENT_TIMESTAMP` UTC.
      Document or unify. `datetime.utcnow()` is deprecated on 3.12+.
- [ ] **[AGENT] `materialize_lfs_models.py`** fallback `git lfs fetch --all` walks 70+ branches
      — use `--include` first (documented; low value).
- [ ] **[AGENT] `import` hub**: `helpers.py` re-exports `jsonify`/`save_settings`, `app.py`
      re-exports `subprocess`/`get_db`… (kept with noqa). Consumers should import from the source.

## P2 — product/UX findings (all **[SCOTT]** — UI/UX is his gate)

- [ ] Review Queue renders **all** pending rows in one table (1,378 for 5 min of film) — paginate.
- [ ] Upload success message sends coaches to `/status`, which is a product-roadmap checklist;
      run progress lives in the film page "Upload Video" panel.
- [ ] `/api/highlights/games` lists only `games`-table rows → plain uploads never appear in the
      Highlights dropdown though `/api/highlights/moments?game_id=` serves them.
- [ ] Confirmed stat books are written **into the repo tree** (`data/stat_books/confirmed/`).
- [ ] `templates/base.html:857,864` reference `ENABLE_RECRUITING`, which is not in `config.py`
      (recruiting lives on unmerged `cursor/recruiting-station-ac1f`) — dead nav block.
- [ ] `/dashboard` charts blank offline (`cdn.jsdelivr.net/npm/chart.js`); vendoring = new library.
- [ ] `/api/rosters/import` only parses; UI creates players one by one via `/api/players`.
- [ ] `save_event` needs the relational `games.id`; uploads without a `games` row can't take
      manual events from the API (the film tool stores them elsewhere).

## P3 — testing, CI, docs

- [ ] **[AGENT] E2E coverage** 219/251 endpoints → ~95 %: remaining are mostly `games` HTML
      form routes, `core` pages with params, `users` password/avatar flows, `scouting` NFHS
      download job endpoints (need a stub). → `docs/E2E_TESTING.md` "Extending".
- [ ] **[AGENT] Browser-level E2E** (real clicks) — the in-app browser drove the stat-book
      Confirm; Review buttons were exercised via their endpoints because the pane was hidden.
      Playwright + `tests/test_ui_overflow.py` pattern exists, opt-in.
- [ ] **[SCOTT] CI** `.github/workflows/tests.yml` runs on PRs (Actions minutes). Keep/delete.
- [ ] **[AGENT] Scorer as a CI gate** once a fixture DB with events exists (needs LFS film in CI
      or a committed small detections fixture).
- [ ] **[AGENT] Docs sprawl**: 14 root markdown files; ALPHA/OWL process docs describe a retired
      workflow (`docs/agent_handoffs/README.md` says so). Write one `docs/INDEX.md`; archive
      the rest. Reconcile `PROJECT_STATUS.md` / `DECISION_LOG.md` "main is stale" language with
      the branch audit.
- [ ] **[AGENT] `docs/DEPLOYMENT.md` §5 / `HERMES_LINUX_PARITY.md`** still describe the old
      transfer bundle in places; the bundle now includes `stat_book/`, `static/`, `models/`.
- [ ] **[AGENT] `ACTIVE.md`** still says "Unknown: whether sklearn already installed" — resolved
      on Linux; Scott's Windows box status unknown.

## P3 — local ops on whichever machine runs this next

- [ ] **[USER] Nightly backup timer** + hourly stale-run watchdog (systemd user units are in
      LOCAL_STANDUP §6c; the agent's permission classifier declines to install services).
- [ ] **[USER] Ollama** (`ollama pull llama3.1:8b`) if practice-note LLM is wanted; heuristic
      fallback otherwise. Dead inside the Docker image (no binary).
- [ ] **[USER] Docker path** is a parity check only: no ollama, `.dockerignore` drops `*.mp4`,
      single-file SQLite bind mount vs WAL. → LOCAL_STANDUP §6.

## Done this cycle (for orientation; details in WORKLOG.md)

Local standup on Linux · 7 failing tests → 0 · `.env` load order · `/play/share` 500 · `json`
NameError · service worker · duplicate before_request · `LIBERTY_DEBUG` · hermetic suite (3
leaks) · spawn guard · transfer bundle contents · trim filename collision · cross-worker trim
status · manual-vs-AI scorer rescued + bugs · quality baseline measured (1.4 %) · precision
mode (8.7 %, gates pass) · `migrate_paths.py` · stale-run watchdog · CI · pytesseract · E2E
suite (3 modes, 219/251) · notification-prefs INSERT · admin reset FK order · branch audit ·
CLAUDE.md · RESUME packet.
