# Full session context — Claude, 2026-09-09 → 2026-09-11

This is the complete working memory of the agent session that produced PRs #139–#141, written
so a new session (cloud or local) can operate at parity without the conversation. It is
organised as: people and goals → what happened → how the codebase actually works → contracts
and quirks learned the hard way → what was measured → what was built → what is open.
No personal data appears here (the repo contains minors' names in rosters and tags; never copy
them into docs, fixtures or chat).

---

## 1. People, accounts, goals

- **Scott** (`scottmcconnell1-bot`, "Scott McConnell") — project owner, coach, decides
  scope/schema/flags/merges (`AUTHORITY.md`). Works on a **Windows** box
  (`C:\Users\scott\Documents\liberty-basketball-analysis`, Python 3.12, site on :8080 behind
  Tailscale). Has hand-tagged one quarter of film (Wilder Q1) — the only ground truth.
- **The operator I worked with** — GitHub account `wakeboardtsi`, email `boiseaiteam@gmail.com`
  (used only for commit attribution). Has repo access; is not Scott. Decisions they made:
  1. All work on new branches; **no push until locally tested**, then push (they said so each time).
  2. "Fully local" = self-hosted, no third-party services at runtime; internet allowed at install.
  3. CPU-only is acceptable (no NVIDIA on their box).
  4. They intend to mirror **Scott's real data** onto their machine (not done — no path to his box).
  5. "Do it all" is their usual response to a prioritized plan; they value momentum and honesty
     about what was and wasn't verified.
- Legacy agent process (ALPHA/OWL GitHub labels) is retired per `docs/agent_handoffs/README.md`;
  `AGENT_PROTOCOL.md` rules (preflight, Proven/Inferred/Unknown, no destructive git without
  Scott, no private memory writes unless "update memory") still apply and I followed them:
  **no memory files were written**; the repo docs are the memory.

## 2. What happened, in order (condensed)

1. Access: `gh auth login` as wakeboardtsi; cloned; stale `~/.git-credentials` entry removed.
2. Read `AGENT_PROTOCOL.md`/`AUTHORITY.md`; wrote `CLAUDE.md` (pointer file).
3. **Branch audit** (`docs/BRANCH_AUDIT_2026-09-09.md`): 73 branches → 14 plan; discovered the
   public GitHub Pages exposure; found the newest work (`cursor/film-tool-review-layout-ac1f`,
   0 behind / 21 ahead of default) is not on the default branch; `main` is an unrelated
   orphan history. Corrected later: Pages serves only LFS *pointers* for weights/film.
4. **Local standup** on a Linux workstation (fish shell; Python 3.14 system → uv-managed 3.13
   venv; CPU torch/opencv/ultralytics; LFS weights hydrated; gunicorn on 127.0.0.1:8080).
   Full CPU analysis of the 5-min snippet: 1,038 s. Reversed the initial Docker plan (no
   ollama in image; `.dockerignore` drops `*.mp4`; single-file SQLite bind mount vs WAL).
5. **Issue sweep** (PR #139): 7 failing tests → 0, six runtime bugs, hermetic test suite,
   transfer-bundle fix, stale docs; then a manual E2E that exposed two trim bugs (fixed).
6. **Quality measurement** (PR #140): rescued the manual-vs-AI scorer + ground truth, measured
   precision 1.4 %; built opt-in precision mode → 8.7 %; migration tool; watchdog; CI.
7. **E2E suite** (PR #141): 15 blueprints, 3 run modes, demo seeder; found 2 more bugs.
8. Workstation wiped 2026-09-11; `RESUME_2026-09-11.md` + this file written.

## 3. How the codebase actually works (mental model)

**Stack**: Flask 3 + Jinja + vanilla JS, SQLite (WAL) via `sqlite3` (no ORM), 15 blueprints
registered in `app.py`. ~250 routes. Python 3.12/3.13 pinned by the scientific stack.

**Startup**: `app.py` loads `.env` (`_load_dotenv`, does not override real env) **before**
`from config import Config` (fixed in #139 — previously `LIBERTY_DATABASE`/`UPLOAD_FOLDER`/
`COACH_PASSWORD` from `.env` were ignored). `SECRET_KEY` falls back to a committed dev key
with a WARNING (Scott gate to remove). `python app.py` binds `0.0.0.0` and runs `ensure_db()`;
gunicorn (`deploy/*.service`, `--bind 127.0.0.1:8080 --workers 2`) imports `app:app` and does
**not** run `ensure_db()` — do it out of band.

**Config layers**: `config.py::Features` (13 `ENABLE_*` flags; 3 default False) are
*defaults*; the `app_settings` table overrides them (`settings_store.load_all_settings`,
keys `feature.<NAME>` and `ai.<key>`). `settings_store.AI_DEFAULTS` holds detector paths
(`models/ball_detector.pt`, class 0, conf 0.25 — pinned by `AGENT_PROTOCOL` "Production
Safety"), `event_generator_mode` (`legacy`|`expanded`|`precision`), stride, tracker,
`llm_provider`. `auto_accept_event_confidence` is force-set to 0.0 in code. The `/settings`
form posts **everything**; an omitted `feature_<NAME>` checkbox turns that flag **off** —
tests must post the full set (`tests/e2e/scenarios.py::feature_form_fields`).
`module_entitlements` (per-team DB rows) are a separate, softer gate from feature flags.

**Analysis data flow**: upload (`/upload` XHR or `/api/upload_chunk` 3-chunk protocol) →
`videos` row (`file_path` = absolute UPLOAD_FOLDER path, stored verbatim) → `analysis_runs`
row (`analysis_key` = `<opponent>_<stem>_<ts>`; `game_id` = relational `games.id` or NULL)
→ `helpers.start_analysis_subprocess` spawns `python analysis_launcher.py <db> <video> <key>`
detached → `ai_analyzer.run_ai_analysis`: YOLO person detector (`yolov8n.pt`, auto-download)
+ fine-tuned ball detector; **ByteTrack via `model.track(persist=True)`** (`ai_analyzer.py:167`)
— `tracker_assigner.assign_trackers_bytetrack` is a dead stub; writes `detections` every
frame at stride; optional EasyOCR jersey reads (absent → 0); then `event_generator.main`
(clusters players spatially into 10 slots → `find_ball_possession` → `build_possession_segments`
→ generator by mode → `persist_events` which DELETEs unverified events for the game and
INSERTs with `event_type_id` + review items) → `film_analysis.run_enhanced_analysis`
(`shot_classifications` keyed by `event_id`, `player_minutes`, `player_effect`, play recognition)
→ `analysis_runs.status='completed'`. Progress: `/api/analysis_progress/<key>`.
"Rebuild events" (`/api/videos/<id>/regenerate-events`) re-runs the generator in the web
worker with `force_expanded=True` (precision mode wins when set) then enhanced analysis.

**Event generators** (`event_generator.py`): `legacy` emits nothing; `expanded`
(`generate_expanded_events_from_segments`) emits possession_change on every segment
boundary, shots from a primary arc detector plus a low-threshold secondary pass, derived
make/miss rows, rebound (+block if next player ≠ and gap ≤ 12) after misses, assist after
makes, dead-ball fouls — with **constant confidences**. `precision` (mine, #140) merges
segments < `min_hold_frames`(12), primary-pass shots only with `shot_min_ball_rise`(80), one
shot per possessor per 6 s, no blocks/fouls, computed confidences. `stats.py` counts
`shot` rows by `shot_result`, and `make`/`miss` rows — keep the derived rows.

**Review**: `events.review_status` pending/accepted/rejected/corrected, `human_verified`,
`review_notes`, `reviewed_at`; `review_items` mirror; `human_corrections` provenance.
`/api/review/events?game_id=&review_status=` list; `POST .../{id}/accept|reject|correct`
(correct takes `event_type`, `player`, `timestamp_ms`, `notes`). Highlights
(`highlight_clips.py`) use only accepted/corrected; `/api/highlights/games` lists **games-table
rows only** (plain uploads invisible); `generate` saves canonical clips + dev clips and starts
ffmpeg trims via `video_trim.start_trim_job` (threads in the worker; job registry now mirrored
to `<UPLOAD_FOLDER>/.trim_jobs/`; output names `stem_trim_<ts>_<job8>`).

**Manual events**: `/api/save_event` requires `game_id` to be an **integer `games.id`**
(`int()`), not the analysis key. Film-tool manual tags live elsewhere (July branch persisted
them to `film_tool_games`; on default they are browser-side + backup JSON).

**Stat books** (`stat_book/`): upload scan → align (identity/homography) → OCR chain
EasyOCR → pytesseract → `none` (manual entry) → draft JSON under
`<UPLOAD_FOLDER>/stat_books/<gid>/` (meta has absolute paths) → confirm writes
`data/stat_books/confirmed/<gid>.json` **inside the repo tree** (`stat_book.paths.CONFIRMED_ROOT`).

**Playbook**: `plays`/`play_steps`/`play_categories`/`playbooks`(opponent books);
`/playbook/save` form; share tokens → `/play/share/<token>` (fixed `sqlite3.Row.get` 500);
import parse (PDF → page images under `uploads/play_imports/`), bulk parse/split/save;
choreography JSON; FastDraw vector extract; play-match ranking writes
`data/play_matches/<game>.json` (gitignored now).

**Users/coach**: local users table (salted SHA-256), `login_required` only on profile/
notifications/push/api-users; **global auth middleware is `pass`**; `/register` accepts any
role. Coach portal: shared password from **env `LIBERTY_COACH_PASSWORD`** (not app.config),
session becomes read-only — ops routes 403 via `coach_portal_ops_gate`.

**Scouting**: reports + 8 section tables; NFHS Network login/lookup/download (yt-dlp) are the
only inherently-online features besides MaxPreps rankings scrape (Playwright, not installed).

**Storage/paths**: SQLite `film_analysis.db` (gitignored); `uploads/` (gitignored; on my
box `LIBERTY_UPLOAD_FOLDER=~/LibertyData/uploads`); `logs/ai-<key>.log` under repo root;
`data/` has tracked JSON caches (89 `sheet_align_cache` files embed Scott's Windows paths —
keys are content hashes, harmless).

## 4. Contracts and quirks (each cost me a cycle)

- Route payloads: `/api/film-rosters*` want `level ∈ {jrhigh, jv, varsity}` (not `jr_high`),
  `side ∈ {home, away, our, opp}`, players need `label`; `/api/rosters/import` **only parses**;
  `/api/messages/send|read` and `/playbook/import/save` `.strip()` ids → send **strings**;
  `/api/messages/poll` needs `conversation_id`; `/api/court-slots/<g>` PUT takes
  `mappings=[{tracker_id, jersey_number, player_name}]`; `/api/scouting/reports/<id>/generate`
  400s "No AI events" unless the relational game has AI events; NFHS download cancel on an
  unknown job → 409; `/games` deliberately 302s to `/schedule`; `/coach` 302s to
  `/coach/progress` when logged in; `/api/admin/reset` 403 in a coach session.
- `save_event` → integer `games.id`. `videos.game_id` is the TEXT analysis key. Many tables
  carry both `game_id` (TEXT) and `relational_game_id` (INTEGER) — Stage 5 migration.
- Tests: root `tests/conftest.py` gives each test a temp DB + upload dir and (mine) redirects
  play-match JSON and analysis logs to tmp, and **raises if any test spawns
  `analysis_launcher.py`**. Check hermeticity as `git status --porcelain | grep -E '^(\?\?| M) (data/|logs/)'`
  and live-DB row counts — tracked-file checks alone missed two leaks. `test_ui_audit.py` is a
  live-server script (skips at collection unless `LIBERTY_RUN_LIVE_UI_TESTS=1`). Real
  detector in tests must run **after** the request returns (see `tests/e2e/conftest.py`).
- Docs contradicted each other on the pytest baseline (360 vs 331) — both stale; measure.
- `scripts/score_manual_q1_regression.py` had moved from `tag-exports/` and broke three
  relative references; `--no-fail` printed PASS on failure. Fixed.
- `scripts/build_transfer_bundle.sh` omitted `stat_book/`, `static/`, `models/` — a restored
  bundle could not import. Fixed.
- Git LFS: `models/*.pt`, `*.mp4` under `videos/`, `data/videos/` are pointers until
  `git lfs pull --include=…`; `materialize_lfs_models.py` falls back to `fetch --all` (70+
  branches) — pre-pull. Pages serves pointers, not payloads.
- `videos/Q1.mp4` (906 s) **is** the Wilder Q1 that Scott tagged; `data/videos/Q1_snippet.mp4`
  is its first 300 s (frame hash verified). Tags: `tag-exports/liberty-manual-tags-backup.json`
  (`savedGames[0].id == game-1784304093435`, rows with `start` as `m:ss.s`).
- Operating the agent tooling: the Bash tool's shell is **zsh** here (user shell is fish):
  unquoted `$VAR` does **not** word-split in `for` loops; `pkill -f 'pattern'` matches its own
  shell — use `pkill -f 'gunicor[n]'`; the in-app browser pane can be hidden (viewport 0×0) →
  clicks/scroll fail, `find`/`read_page`/`form_input` still work; Claude Code's auto-mode
  permission classifier declined installing systemd user units (not a sandbox).
- AGENT_PROTOCOL forbids `git checkout -- <path>`/stash/reset during verification without
  approval; the operator explicitly granted local ops later, and I only reverted test
  side-effects.

## 5. Measurements (Proven, this machine, CPU)

- Test suite: as cloned 606 passed / 7 failed / 11 skipped → now 663 / 0 / 29 (on 3.13;
  622/12 on 3.12 web-only). Smoke: 20/20. E2E: 18/18, 18/18 (real detector), 17/18+1 skipped
  (live server); endpoint coverage 219/251.
- Analysis speed: ~3.5× realtime (5 min film → 17 min; full quarter 906 s → 49 min solo,
  slower under contention). A 32-min game ≈ 2 h here.
- Pipeline quality vs Scott's tags (±10 s, strict type+result), full quarter:
  `expanded` precision 0.014 / recall 0.660 / 35 TP / 2,415 FP; `precision` mode 0.087 /
  0.623 / 33 / 346 (gates pass). 300 s window: 0.011 → 0.103. Recall is chance-dominated at
  2.5 AI rows/s (~50 same-family candidates within ±10 s). All 7 3PT typed 2PT; all 7 fouls
  missed; 528/578 `shot_classifications` say 3pt (implausible). Scott's own July baseline:
  0.008 / 0.415. Detection: ~5 of 11 people boxed at t=60; ball ≥0.25 in 12.4 % of frames;
  1,036 tracker IDs for ~13 people / 5 min.

## 6. What I built (where, how to run)

- `scripts/score_manual_q1_regression.py --analysis-key K [--window-end-sec 300] --no-fail --per-tag`
- `event_generator.py` precision mode; `main(mode_override=, precision_params=)`; tune on a
  DB copy (`cp film_analysis.db /tmp/tune.db`) — the scratch tuner script was not committed;
  recreate by looping `main(key, db, mode_override="precision", precision_params={...})` then scoring.
- `scripts/migrate_paths.py --db … --audit | --from-prefix … --to-prefix … [--stat-books-dir …] [--apply]`
- `scripts/mark_stale_analysis_runs.py --db … [--minutes 45] [--apply]`
- `tests/e2e/` (`data.py` generators, `conftest.py` dual target, `scenarios.py` steps,
  `test_e2e_flow.py`); `scripts/run_e2e_live.sh`; `scripts/seed_e2e_data.py --db --uploads`
- `.github/workflows/tests.yml` (PRs; 3.12 + 3.13; ruff; pytest; secrets audit)
- Loopback launcher (not in repo; content in LOCAL_STANDUP §2): gunicorn `--bind 127.0.0.1:8080
  --timeout 300`, exports `LIBERTY_UPLOAD_FOLDER`/`LIBERTY_DATABASE`, runs `ensure_db()` first.

## 7. Findings not changed (need Scott or are product decisions)

Pages exposure · auth no-op · `/register` admin · dev `SECRET_KEY` fallback · SHA-256 passwords
· XOR NFHS creds · `default-src *` CSP · 4 GB unauth uploads · schema/migrations versioning ·
repo size / `_tmp_*` / node_modules / `pose_landmarker.task` · branch cleanup · Review queue
pagination · `/status` message · Highlights dropdown · confirmed books in repo tree ·
`ENABLE_RECRUITING` dead nav · chart.js CDN · int-id 500s · docs sprawl · ALPHA/OWL legacy docs.
Full list with priorities: `docs/agent_handoffs/TODO.md`.

## 8. Open questions

1. Which copy of the DB is authoritative once Scott's data is mirrored elsewhere?
2. Does Scott keep the July branch's teach/calibrator loop or the new precision mode (or both)?
3. Is the manual-tags JSON acceptable on the main line (it names minors; already in history)?
4. CI on his Actions minutes — keep?
5. What is the coach's tolerance for queue size — is 346 drafts per quarter reviewable?

## 9. Assumptions I made (state them if they turn out wrong)

- The operator has authority to direct local work and to push branches/open PRs (they did).
- `jason-5-may-updates` is the mainline (GitHub default; `AGENT_PROTOCOL` agrees).
- `expanded` is the production generator today (default in `AI_DEFAULTS` is `legacy`, but every
  analyzed game on this box produced expanded output via `force_expanded` / settings; verify
  Scott's `app_settings`).
- Scott's DB stores Windows absolute upload paths (inferred from `blueprints/ai.py:882` +
  `launch_liberty.py:211`; not yet seen).
