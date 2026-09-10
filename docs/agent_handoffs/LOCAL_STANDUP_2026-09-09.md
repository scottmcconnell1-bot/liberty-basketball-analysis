# Linux Local Standup + Issue Sweep — 2026-09-09

Branch: `claude/local-standup` (off `origin/jason-5-may-updates` @ `05c8475`)
Status: **all work local, verified, NOT pushed** (by instruction — push only after review)
Reporting: Proven / Inferred / Unknown per `AGENT_PROTOCOL.md`

This file is the single place a new agent needs to read to continue. It records
(1) how this machine is set up, (2) every change made and why, (3) how each was verified,
(4) what was deliberately NOT done because it is a Scott gate, and (5) what to do next.

---

## 1. Result in one paragraph

The app runs fully local on this Linux workstation with no external services at runtime:
Python 3.13 venv, CPU torch/opencv/ultralytics, all five LFS model weights hydrated, SQLite,
gunicorn bound to **127.0.0.1:8080 only**. A real 5-minute film clip was analysed end to end
on CPU (**1,038 s wall-clock, 77,810 detections, ~1,350 events, 578 shots classified,
`analysis_runs.status='completed'`**). The test suite went from **7 failed / 606 passed /
11 skipped** (as cloned) to **0 failed / 625 passed / 28 skipped**, and it no longer writes
into tracked files. Ruff reports zero undefined names / redefinitions / syntax errors.

---

## 2. This machine

| | |
| --- | --- |
| OS / shell | CachyOS Linux, **fish** (`VAR=x cmd` bash syntax does NOT work; use `env VAR=x cmd`) |
| CPU / RAM / disk | 20 cores, 31 GB, ~700 GB free |
| GPU | Intel Iris Xe only — **no CUDA**. CPU inference. |
| Python | system is 3.14.7 (unsupported). Venv uses **uv-managed CPython 3.13.14** (`uv python find 3.13`) |
| Venv | `.venv/` (gitignored). torch 2.14.0+cpu, opencv 5.0.0, ultralytics 8.4.146, gunicorn 23.0.0 |
| ffmpeg / docker | present (ffmpeg n9.0.1; Docker 29.7 — not used as the runtime, see §6) |
| Models | `models/*.pt` hydrated via `git lfs pull --include="models/*.pt"`; sizes match pointers byte-exact |
| Sample film | `data/videos/Q1_snippet.mp4` hydrated (65,595,180 B). `videos/Q1.mp4` still a pointer (not needed) |
| DB | `film_analysis.db` (gitignored) — empty schema + one smoke analysis (`game_id='smoke_q1_local'`) |
| Uploads | `LIBERTY_UPLOAD_FOLDER=/home/myaccount/LibertyData/uploads` — **outside the repo** so real film can never be committed |
| Secrets | `.env` (gitignored, `chmod 600`) with a real `SECRET_KEY`; VAPID/SMTP blank (features inert) |

### Run it

```bash
/home/myaccount/LibertyData/run-liberty-local.sh      # gunicorn, 127.0.0.1:8080, runs ensure_db() first
tail -f /home/myaccount/LibertyData/gunicorn.log
bash scripts/smoke_test.sh http://127.0.0.1:8080 standalone
.venv/bin/python -m pytest tests/ -q                   # expect 625 passed, 28 skipped
```

Stop: `pkill -f 'gunicor[n] --workers'` (the `[n]` keeps pkill from matching its own shell).

**Never** run `python app.py` or `scripts/launch_liberty.py` on a box holding real athlete
data: both bind `0.0.0.0`, and auth middleware is a no-op (§5). Never run
`scripts/setup_coach_tunnel.md`, `scripts/tunnel-watchdog.sh`, `scripts/check_tunnel_url.sh`,
or `deploy/deploy_production.sh` here.

---

## 3. Changes made (all Proven by tests/smoke unless marked)

### 3a. Genuine bugs fixed in application code

| File | Bug | Fix |
| --- | --- | --- |
| `app.py` | `from config import Config` ran **before** `_load_dotenv()`, and `config.py` reads `os.environ` at import time → `LIBERTY_DATABASE`, `LIBERTY_UPLOAD_FOLDER`, `LIBERTY_COACH_PASSWORD` set in `.env` were **silently ignored** (only `SECRET_KEY`/`COACH_PASSWORD` were re-read afterwards). | Load `.env` first, then import `Config`. Verified: `env -u LIBERTY_UPLOAD_FOLDER python -c 'from app import app'` now reports the `.env` value. |
| `app.py` | `coach_portal_ops_gate` defined and registered **twice** as `before_request` (ran twice per request). | Removed duplicate. `app.before_request_funcs[None]` now `['coach_portal_ops_gate','require_auth_for_api']`. |
| `app.py` | `LIBERTY_DEBUG` is documented in README/DEPLOYMENT/compose/systemd/launcher but the code only read `FLASK_DEBUG` → the documented var did nothing. | Reads `LIBERTY_DEBUG` with `FLASK_DEBUG` fallback. Launcher default changed `"1"`→`"0"` to preserve the *effective* prior behaviour (debug off) — Werkzeug debugger on a `0.0.0.0` bind would be a regression. README default corrected. |
| `app.py` | `LIBERTY_ALLOW_DEV_SECRET` documented in `.env.example` but **never read anywhere**. | Now meaningful: when the committed dev `SECRET_KEY` fallback is in use, a WARNING is logged unless `LIBERTY_ALLOW_DEV_SECRET=1`. Boot behaviour unchanged (removing the fallback is a Scott gate). |
| `blueprints/ai.py:244` | `json.loads(...)` with **no module-level `import json`** (only an unused `json as _json` inside the chunked-upload block) → `NameError` for any run whose `analysis_runs.settings_json` is set. | Added `import json`; removed the dead alias import. |
| `blueprints/playbook.py:949` | `play.get("team_key")` on a `sqlite3.Row` (no `.get()`) → **every `/play/share/<token>` link returned 500**. | `play = dict(play)` after the 404 check (matches the other play helpers). Live: `/play/share/bogus` → 404. |
| `settings_store.py` | `load_all_settings(db_path=...)` crashed with `no such table: app_settings` on a DB that predates the table. `ai_analyzer.py` calls this out-of-process before `ensure_db()` has necessarily touched that file. | Missing table ⇒ defaults (only that specific `OperationalError` is swallowed). |
| `helpers.py` (migrations) | `existing` dict built and never used; the loop relied on `ALTER TABLE` raising for missing tables. | Compute `existing_tables` and `continue` past missing tables explicitly. |
| `helpers.py:618` | Settings UI note said ball detector runs at **0.15** confidence; `AI_DEFAULTS` and `AGENT_PROTOCOL.md` say **0.25**. | Note is now rendered from `AI_DEFAULTS`. |
| `services/notifications.py` | `to_name` computed and dropped; `conv_name` dead. | `To:` header now `formataddr((to_name, to_addr))`; dead var removed. |
| `static/sw.js` | `OFFLINE_URLS` pre-cached `/static/css/style.css`, which **does not exist** → `cache.addAll()` rejected → service worker never installed. | Removed the phantom entry (base.html inlines CSS). |
| `tracker_assigner.py` | ultralytics availability probe via an unused import. | `importlib.util.find_spec("ultralytics")`. |
| `blueprints/core.py`, `event_generator.py`, `film_analysis.py` | Dead locals (`most_common`, `is_hs`, `curr_duration`, `effective_fps`); an `event_generator` comment claiming noise segments are skipped when they are not. | Removed dead code; comment now states actual behaviour. **No AI behaviour changed.** |
| `video_trim.py` | Output filename/game_id keyed on a per-second timestamp → concurrent highlight clips collided on one file. | `trim_stamp(job_id)` adds the job-id suffix. |
| `video_trim.py` | Job registry was an in-process dict → status polls fail on the non-owning gunicorn worker (`--workers 2` in the systemd unit). | State mirrored to `<UPLOAD_FOLDER>/.trim_jobs/<id>.json`; `get_trim_job` falls back to it. |
| `scripts/score_manual_q1_regression.py` | Unrunnable from a clean checkout after being moved to `scripts/` (table assumption, backup path, `sys.path`). | See `docs/ANALYSIS_QUALITY_BASELINE_2026-09-10.md` §4. |
| ~15 modules | 96 unused imports tree-wide (ruff F401). | Removed **except** re-exports other modules depend on, which are kept with explicit `# noqa: F401` notes: `helpers.jsonify` (→ `blueprints/ai.py`), `helpers.save_settings` (→ `blueprints/core.py`), `app.subprocess` + `app.{get_db,init_db,…}` (→ tests), `event_generator.AnalysisConfig` (→ `experiments/`). |

### 3b. Tests fixed (7 failing as cloned → 0)

| Test | Cause | Fix |
| --- | --- | --- |
| `test_api.py::test_film_page` | Asserted copy removed in `2925973` (review workspace MVP). | Dropped the stale line. |
| `test_api.py::test_rerun_video_analysis_*` (×2) | Route gained `validate_video_for_analysis` / `validate_ai_models_for_analysis` after the tests were written; fake `uploads/sample_N.mp4` failed validation → no second run. | Stub both validators like the other rerun tests do. |
| `test_assistant_workflow.py::…[/preview…]` | Preview nav link intentionally hidden in `66a18bf`; route still exists. | Removed the `/preview` param. |
| `test_dashboard_seasons.py` | **Time bomb**: hard-coded `2026-07-15` game became "past" (`game_date >= date('now')`) on 2026-07-16. | Dates computed relative to today. |
| `test_launch_liberty.py::test_find_system_python…` | `python3.12`/`python3.13` not on PATH here (uv-managed). | Launcher now tries `sys.executable` first (real improvement: works from any 3.12/3.13 not on PATH). |
| `test_playbook_share.py` | The real bug above. | — |
| `test_ai_analyzer.py::…video_missing` *(was skipped as cloned; cv2 absent)* | Bare DB → `app_settings` crash before the video check. | `settings_store` hardening above. |
| `test_nfhs_download.py::…requires_ai_packages` *(passed only because cv2 was absent)* | Environment-coupled: expected 503 with no stub. | Stub `ai_runtime_available → False`. |

### 3c. Test hermeticity (suite wrote into tracked files)

- `tests/test_stat_book.py::test_routes_sample_and_confirm` overwrote the **tracked**
  `data/stat_books/confirmed/sample-hsb-liberty.json` (timestamp) → now writes to `tmp_path`
  via `monkeypatch.setattr(stat_book.paths, "CONFIRMED_ROOT", …)`.
- `tests/test_transfer_bundle.py` rebuilt the bundle **19×** into the tracked
  `transfer-bundles/` dir → now builds **once** (module fixture) into a temp dir via the new
  `LIBERTY_TRANSFER_OUT_DIR` env, skips models via `LIBERTY_TRANSFER_SKIP_MODELS=1`, and asserts
  nothing in the repo tree was touched. Extra required-path assertions added for
  `stat_book/`, `static/`, `data/stat_books/`.
- Three tarballs that had been **committed by accident** (`a071737`) are now untracked
  (`git rm --cached`, files kept on disk) and `transfer-bundles/*.tar.gz` is gitignored.
- Some test (any that renders a film page or calls `/api/film/<game>/play-matches`) wrote
  `data/play_matches/<game>.json` into the **repo tree** because
  `blueprints.ai._play_match_store_base()` resolves under `current_app.root_path`. Fixed with an
  **autouse fixture in `tests/conftest.py`** that points it at `tmp_path`; `data/play_matches/`
  is also gitignored (it is runtime output for real games).
- Analysis launcher logs (`helpers.ai_analysis_log_path`) defaulted to `<repo>/logs/ai-<game>.log`
  even under pytest → redirected to `tmp_path` by the same conftest fixture.
- **Safety net:** a conftest autouse fixture wraps `subprocess.Popen` and raises if any test tries
  to spawn `analysis_launcher.py`. On this box (CV stack installed) an un-stubbed test could
  otherwise start a multi-minute CPU job against whatever DB/video it was handed.
- `tests/test_ui_audit.py` is a standalone live-server audit *script* with no test functions; pytest
  imported it and it ran ~100 live GETs at collection time. Now skips at module level unless run
  directly or `LIBERTY_RUN_LIVE_UI_TESTS=1`.
- `blueprints/coach.py` hard-coded `<repo>/film_analysis.db` for its progress snapshot instead of
  `app.config["DATABASE"]` → now uses the configured DB (falls back outside an app context).
- Verified: after a full run, `git status` shows no tracked-file modifications **and no new
  untracked files under `data/` or `logs/`**, and the live `film_analysis.db` row counts are
  unchanged (check all three — the first check alone missed two of these).
- Note: one `videos` row + failed `analysis_runs` row for `test_Q1_<stamp>` appeared in the live DB
  at 00:00 on 2026-09-10. Nothing in the repo produces it (no test/script references `Q1.mp4` or
  opponent `TEST`); it matches a manual browser upload of `videos/Q1.mp4` — which is still a
  **134-byte LFS pointer**, so analysis correctly failed with `Could not open video file`.
  Rows and the pointer file were removed. If you want that full-quarter file usable:
  `git lfs pull --include=videos/Q1.mp4` (184 MB).

### 3d. Scripts / config

| File | Change |
| --- | --- |
| `scripts/build_transfer_bundle.sh` | **Was shipping a broken app**: `stat_book/` (a package imported by blueprints → `ImportError` on restore; this is the documented "missing modules in transfer bundle" in `HERMES_LINUX_PARITY.md`), `static/` (no CSS/JS), `data/stat_books/` (scorebook templates) and `models/` were all missing; the `.pt` glob looked in repo root where weights have not lived for months. Now includes them, skips LFS pointer stubs with a message, honours `LIBERTY_TRANSFER_OUT_DIR` / `LIBERTY_TRANSFER_SKIP_MODELS`, and notes to prefer `scripts/backup_db.py` for a WAL-consistent DB. |
| `scripts/smoke_test.sh` | `/games` expected 200 but the route deliberately 302s to `/schedule` ("scores are recorded on the schedule"). Now expects 302 → **20/20**. |
| `scripts/launch_liberty.py` | `sys.executable` candidate; `LIBERTY_DEBUG` default `0` (see 3a). |
| `scripts/run_v8.py` | Hard-coded `/home/monk-admin/...` paths → repo-relative defaults with `--video/--out/--ball-model/--court-model`. |
| `requirements.txt` | `+ gunicorn>=21,<24`. `DEPLOYMENT.md`'s standalone path installs this file and then runs the systemd unit, which execs gunicorn — previously only in `requirements.docker.txt`. (Pure-Python; flagged for Scott's awareness per `CODEX_BRIEFING.md §6`.) |
| `.env.example` | Added `LIBERTY_COACH_PASSWORD` (read by 4 call sites, was undocumented) and `LIBERTY_DEBUG`; `LIBERTY_ALLOW_DEV_SECRET` comment now describes what it does. |
| `.gitignore` | `transfer-bundles/*.tar.gz`, `clips/`, `.ruff_cache/`. |
| `tests/test_ui_audit.py` | Stale `localhost:5000` → `LIBERTY_BASE_URL` (default 8080). |
| `tests/test_ui_comprehensive.py` | `fail_` → `fail` (NameError in the gated live-UI script). |

### 3e. Docs corrected

- Test baseline: `STAGE_INDEX.md` said 360/1, `DOCKER_PRODUCTION_SMOKE.md` and
  `HERMES_LINUX_PARITY.md` said 331/1. **Actual as cloned: 606 passed / 7 failed / 11 skipped.
  Now: 625 / 0 / 28** (skips = fixture files not in repo + live-UI opt-ins). All three updated.
- `docs/BRANCH_AUDIT_2026-09-09.md` overstated the Pages exposure: LFS paths serve only the
  pointer, not weights/footage. Corrected in place. Source + roster exposure stands.
- `docs/CODEX_BRIEFING.md §5` known-issues list annotated with 2026-09-09 status.
- `README.md` `LIBERTY_DEBUG` default; `CLAUDE.md` local-environment section rewritten.

---

## 4. Verification log (Proven)

```
.venv/bin/python -m pytest tests/ -q                -> 625 passed, 28 skipped
ruff --select F821,F811,F823,E9 (excl. scratch)     -> All checks passed
py_compile on every edited .py                      -> ok ; bash -n on edited .sh -> ok
import of every edited production module            -> no failures
bash scripts/smoke_test.sh http://127.0.0.1:8080    -> 20 passed, 0 failed
ss -ltn | grep 8080                                 -> 127.0.0.1:8080 (never 0.0.0.0)
GET /play/share/bogus                               -> 404 (was 500)
GET /sw.js /status /dashboard /film /review /assistant /stat-books /playbook -> 200
ai_analyzer.py film_analysis.db data/videos/Q1_snippet.mp4 smoke_q1_local
   -> 1038 s wall-clock for 300 s @30fps (9,002 frames), 77,810 detections,
      events: possession_change 332, shot 289, rebound 166, miss 166, block 134, make 123,
      assist 103, turnover 32 ; 578 shots classified ; 40 plays ; analysis_runs=completed
git status after full test run                      -> no tracked files modified
```

Skips (28) are all `fixture not present` (Rub page_0087, 1-Game page_0036, Fast Scout PDF) or
`LIBERTY_RUN_LIVE_UI_TESTS` opt-ins — none are regressions. As cloned, `test_ai_analyzer.py`
skipped wholesale because cv2 was missing; it now runs.

CPU expectation to set with Scott: **~3.5× realtime**, so a 32-minute game ≈ **2 hours** here.

---

## 5. Deliberately NOT done — Scott gates (`AUTHORITY.md`)

| Item | Where | Why it waits |
| --- | --- | --- |
| Auth middleware is a no-op (`pass`) | `app.py:require_auth_for_api` | Explicit Scott gate (`docs/AUTH_REENABLE_PLAN.md`, `QUEUE.md`). Mitigated here by loopback bind. |
| `/register` lets anyone self-register **as admin** (role from form, no invite) | `blueprints/users.py:121-165` | Changing/gating a feature. Same mitigation. |
| Committed dev `SECRET_KEY` fallback still boots | `app.py` | Refusing to boot is a behaviour change; now warns instead. |
| Public GitHub Pages serves the private repo (source + athlete roster CSV) | `gh-pages` branch, Pages settings | Outward-facing; see `docs/BRANCH_AUDIT_2026-09-09.md §6`. **Highest-priority item for Scott.** |
| `schema.sql` / feature flags (`ENABLE_*`) | — | Untouched. |
| ~100 `_tmp_*` scratch files in repo root; `pose_landmarker.task` (30 MB, nothing imports it; `mediapipe` in no requirements) | repo root | Deleting code/files is a gate. |
| `templates/base.html:857,864` reference `ENABLE_RECRUITING`, which is not in `config.py` (recruiting lives on unmerged `cursor/recruiting-station-ac1f`) → nav block permanently hidden | `base.html` | Adding a flag is a gate; harmless as-is. |
| Branch cleanup (59 deletable branches, `main` orphan, `dataset-v2` archive) | `docs/BRANCH_AUDIT_2026-09-09.md` | Needs approval. |
| Vendoring `chart.js` for offline `/dashboard` canvases (counts still render; only 2 charts blank) | `templates/dashboard.html:50` | "New library" gate. Not a blocker. |
| `scripts/materialize_lfs_models.py` fallback `git lfs fetch --all` walks 70+ branches | script | Low value; avoid by pre-pulling with `--include`. |
| `BACKLOG.md` items (email/push for bug reports, PWA) | — | Features, not bugs. |

Also left alone on purpose: the 16 remaining ruff F401/F841 hits are all in `benchmark_*.py`
(experiment scripts).

---

## 6. Why the venv and not Docker (Proven)

Docker was the first plan; four checks reversed it: the image never installs `ollama` (the
only LLM path is a `subprocess` call → permanently dead in-container); `.dockerignore`
excludes `*.mp4` globally; compose bind-mounts a single SQLite *file* while the app runs WAL
(sidecars land in the container layer); and `uv` already had 3.13 installed, which removed
Docker's only advantage. Docker remains fine for a parity smoke on an empty DB —
`docker-compose.yml` and `Dockerfile` are untouched and `tests/test_docker_config.py` still
asserts their contents.

---

## 6a. Full E2E through the app — done (2026-09-10)

The coach's definition of done (`ACTIVE.md`): scorebook photo → `/stat-books` → confirm;
film → AI events → Review Accept/Correct/Reject → official ledger → highlights. Walked end to
end on this machine against the 5-minute Wilder Q1 snippet, game
`e2e_sample_Q1_snippet_20260910_054233` (rows remain in the local DB for inspection).

| Step | How | Result (Proven) |
| --- | --- | --- |
| Upload | multipart POST to `/upload` (the film-tool form's route) | `videos` row 2, `analysis_runs` row 2 (`primary`); **gunicorn spawned** `analysis_launcher.py` (PID 818303) |
| Progress | browser: film page "Upload Video" panel | live bar "AI Analysis 44% — Detecting objects: frame 4000/9002" |
| Analysis | app-spawned, CPU | `completed`, 77,810 detections, 1,378 events — identical to the CLI run (deterministic) |
| Scorebook | POST `/stat-books/games/<g>/upload` with the sample scan, then **browser**: filled team/score fields and clicked **Confirm box** | aligned (`identity`), OCR `none` here → manual entry; confirmed JSON written, validation OK, served by `/stat-books/confirmed/<g>` |
| Review | `POST /api/review/events/<id>/{accept,reject,correct}` — the exact calls the three buttons make | accepted shot (`human_verified=1`), rejected block, corrected `possession_change`→`turnover` (#4); ledger and notes/`reviewed_at` written |
| Highlights | `GET /api/highlights/moments`, `POST /api/highlights/generate` | **only** the accepted + corrected events listed (1,375 pending excluded); 2 canonical clips + 2 dev clips saved; ffmpeg cut 2 files (6.2 s, 11.6 s) |

Honest scope note: the Review clicks were made through the endpoints rather than the buttons
because the in-app browser pane was hidden (viewport 0×0) at that point and clicks cannot
render; the Review page itself was verified rendering with its Accept/Correct/Reject controls
and 1,378-row queue while the pane was visible, and the stat-book Confirm *was* a real click.

Bugs found by the E2E and fixed (see §3a table additions):
- `video_trim.py` output name was `{stem}_trim_{YYYYmmdd_HHMMSS}` → two highlight clips cut in
  the same second wrote the **same file** (second ffmpeg overwrote the first; one 11.6 s file
  survived instead of 6.1 s + 8.0 s). Now suffixed with the job id.
- Trim job registry was a per-process dict → under the shipped `--workers 2` systemd unit a
  status poll served by the other worker returned "not found or expired". Now mirrored to
  `<UPLOAD_FOLDER>/.trim_jobs/<id>.json`; verified 12/12 polls return `complete` across both workers.

Findings not fixed (product decisions):
- The upload success message sends coaches to `/status` for progress, but `/status` is a
  product-roadmap checklist; run progress lives on the film page panel.
- `/api/highlights/games` lists only `games`-table rows, so an uploaded video with no
  relational game (this one, and any plain upload) never appears in the Highlights dropdown
  even though `/api/highlights/moments?game_id=` serves it.
- Confirmed stat books are written **into the repo tree** (`data/stat_books/confirmed/`), so a
  real coach's confirmations become untracked files in the working copy.
- OCR backend is `none` on this machine (no tesseract/EasyOCR): every scorebook cell is manual.

## 6b. AI analysis quality — measured (2026-09-10)

See **`docs/ANALYSIS_QUALITY_BASELINE_2026-09-10.md`**. Short version: on the same five minutes
of Wilder Q1 that Scott hand-tagged, the pipeline scores **precision 1.1%, recall 61.5% (mostly
chance at 2.5 AI rows/sec)** — 8 true positives vs 744 false positives. This reproduces Scott's
own full-quarter baseline (0.8% / 41.5%). The instrument is now runnable from a clean checkout:

```bash
.venv/bin/python scripts/score_manual_q1_regression.py --analysis-key <key> --window-end-sec 300 --no-fail --per-tag
```

Ground truth `tag-exports/liberty-manual-tags-backup.json` was extracted from July-branch commit
`3749831` (no code merged). `videos/Q1.mp4` is verified to be the Wilder Q1 (duration + frame
hash vs the snippet). Three latent path/table bugs in the scorer were fixed; tests added.

## 7. Next steps for whoever picks this up

1. **Review + push.** `git log` shows one commit on `claude/local-standup` with everything in
   §3. The earlier branch `claude/repo-branch-audit` (audit doc + `CLAUDE.md`) was
   cherry-picked into this one and can be deleted after merge.
2. **Scott's real data.** Not on this machine (verified: nothing under `~/LibertyData`, no
   reachable host). Plan is in `/home/myaccount/.claude/plans/…` and summarised here:
   Scott runs `py -3.12 scripts\backup_db.py --out-dir <drive>` (WAL-safe) + `certutil -hashfile`,
   copies `uploads\` with `robocopy /MIR /Z`; on arrival `sha256sum`, `PRAGMA integrity_check`,
   row counts, then audit **Windows paths stored in the DB** (`videos.file_path`,
   `analysis_runs.video_path`, `video_assets.file_path` — stored verbatim by
   `blueprints/ai.py:882`) and rewrite the prefix. Snapshot with `scripts/backup_db.py`
   before the rewrite and before first boot (`ensure_db()` migrates in place). Decide first
   which copy is authoritative if Scott keeps working on his box.
3. **Optional local extras** (no approval needed): `pacman -S tesseract tesseract-data-eng`
   restores scorebook OCR tier 2; installing `ollama` + `ollama pull llama3.1:8b` enables
   practice-note LLM (heuristic fallback otherwise).
4. **Ask Scott about §5**, Pages exposure first.
