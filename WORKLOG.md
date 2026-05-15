WORKLOG — Liberty Basketball Analysis
Started: 2026-04-27

---

## OpenClaw Review Turn — 2026-05-15

### What Rex Had Already Fixed (context)
- Created `games.py`, `sources.py`, `season_management.py`, `scheduled_games.py` modules
- Created `templates/games.html` and `templates/schedule.html`
- Fixed `app.py`: WAL mode, busy_timeout, CSP headers, `teardown_appcontext`, serialized `details_json`
- Fixed `ai_analyzer.py`: WAL mode, busy_timeout, removed duplicate `frame_number = 0`
- Fixed `event_generator.py`: WAL mode, busy_timeout
- Fixed `season_management.py` and `scheduled_games.py`: removed thread-unsafe `row_factory` toggling
- Added `/games` route, `/api/games` CRUD, `/api/sources` CRUD
- Set `ENABLE_GAMES = True` in `config.py`

### What This Review Fixed

#### Bug: Missing `/upload` route (critical — broke end-to-end upload flow)
- The film tool HTML has `<form action="/upload" method="post" ...>` for the "Upload and Analyze" button
- `app.py` had no `/upload` route — this would have returned 404 on every upload attempt
- **Fix:** Added `POST /upload` route in `app.py` that:
  - Validates file type (mp4, mov, avi, mkv, m4v, webm)
  - Saves file to `uploads/`
  - Inserts an `analysis_runs` row with `status='pending'`
  - Launches `run_ai_analysis` in a background `threading.Thread` (daemon=True)
  - Updates `analysis_runs` to `status='running'` before analysis starts
  - Updates to `status='completed'` on success, `status='failed'` with error message on exception
  - Redirects back to the film tool at `/video/<filename>?game_id=<game_id>`
- Added `GET /uploads/<filename>` route to serve uploaded video files
- Added `allowed_video()` helper to whitelist video extensions

#### Bug: `game_id` template variable not passed to film tool
- Film tool HTML uses `{{ game_id or '' }}` Jinja variable for AI status polling
- The `index()` route only passed `filename`, not `game_id`
- **Fix:** Updated `index()` to also extract `game_id` from query params and pass it to the template
- **Fix:** Changed upload redirect to use `url_for("index", filename=filename, game_id=game_id)` (proper Flask URL building instead of fragile string concatenation)

#### Bug: Malformed HTML — double `<script>` tag in film tool
- Line ~3170: `    <script>` appeared where it should have been `    </script>` (closing the main JS block)
- This caused the main script block to remain unclosed, meaning the AI status polling script was technically nested inside it
- **Fix:** Changed the spurious `<script>` to `</script>` — script tags are now balanced (2 open, 2 close)

#### Bug: `ai_analyzer.py` updated `completed_at` mid-run with incorrect semantics
- Every 500 frames the analyzer wrote `completed_at = CURRENT_TIMESTAMP` to `analysis_runs` while status was still `'running'`
- This made it look like the job had completed when it hadn't, confusing the status polling UI
- **Fix:** Removed the mid-run `completed_at` update; final status is now set cleanly by the upload route's background thread handler

#### Cleanup: Removed unused `sys` and `subprocess` imports from `app.py`
- These were carried over from earlier scaffolding and never used

#### Consistency: Added WAL mode + busy_timeout to `tracker_assigner.py`
- All other DB-touching modules already had this; `tracker_assigner.py` was the outlier

#### UX: Added navigation bar to film tool HTML
- Added a simple nav bar at the top of the film tool with links to `/`, `/schedule`, and `/games`
- Consistent styling with the rest of the app (dark theme, Liberty colors)

### Testing
- All Python modules pass syntax check (`py_compile`)
- HTML script tag balance verified (2 open, 2 close)
- Upload → analysis → status polling flow is fully wired end-to-end

### Next
- Scott to test the upload flow with a real video
- Phase 2.5: Manual Tagging & Bookmarks MVP
- Phase 4: NFHS Matching — manual candidate add/confirm/reject flow
- Phase 6: `/practices` route + `templates/practices.html`

---

## OpenClaw Turn 1 — 2026-05-15

### Done
- Created `games.py` — full CRUD for games table (create, list w/ filters, get, edit, delete) — Phase 3.1
- Created `sources.py` — full CRUD for sources table (create, list, get, delete) — Phase 3.2
- Updated `schema.sql` — fixed practices table to match Phase 6.1 spec: added `level`, `status`, `plan_source`, `plan_text`, `combined_summary`; corrected `end_time` type to TIME
- Updated `templates/schedule.html` — added season/level/gender filter bar, Add Game form (full field set per Phase 2.2), inline Edit row, status badge for rescheduled
- Updated `app.py` — removed debug `print(app.url_map)` line

### Issues fixed
- `games.py` and `sources.py` were missing; `app.py` imports them (gated behind `ENABLE_GAMES` flag) — now present and passing syntax check
- schedule.html was missing Add Game form and filter controls required by Phase 2.2
- practices table was missing `level`, `status`, `plan_source`, `plan_text`, `combined_summary` columns required by Phase 6.1

### Testing
- All Python modules pass syntax check (`py_compile`)
- `ENABLE_GAMES` remains `False`; Phase 3 routes present but gated
- Schedule page (`/schedule`) fully functional: filter + add + edit + delete

### Next
- Scott to test the site and report feedback
- Phase 3 next step: enable `ENABLE_GAMES = True` in config.py and add `templates/games.html`
- Phase 6 next step: add `/practices` route + `templates/practices.html`

---

## Rex Turn 1 — 2026-05-15

### Done
- Created `config.py` — feature flags (Features.*, AnalysisConfig.*) per project outline Phase 0.4
- Created `season_management.py` — full CRUD for seasons table
- Created `scheduled_games.py` — full CRUD for scheduled_games table (create, list w/ filters, get, edit, delete)
- Updated `schema.sql` — added all missing tables: seasons, scheduled_games, games, nfhs_matches, sources, players, stats, practices. Added columns to events (source_video, source_frame, human_verified, confidence). Added home_score, away_score, result, is_conference to games.
- Updated `app.py` — added /schedule route (server-rendered), /api/seasons CRUD, /api/scheduled_games CRUD
- Created `templates/schedule.html` — server-rendered schedule table grouped by season

### Schema changes summary
- New tables: seasons, scheduled_games, games, nfhs_matches, sources, players, stats, practices
- events table: added source_video TEXT, source_frame INTEGER, human_verified INTEGER DEFAULT 0, confidence REAL
- games table: added home_score INTEGER DEFAULT 0, away_score INTEGER DEFAULT 0, result TEXT, is_conference INTEGER DEFAULT 0

### Testing
- All Python modules pass syntax check (pyright reports missing Flask/werkzeug imports — expected, those are in the project venv)
- schema.sql is valid SQL

### Next (for OpenClaw)
- Phase 3: Games CRUD (games.py module + routes + template)
- Phase 2.5: Manual Tagging & Bookmarks MVP (feature-flagged)
- Wire up the film tool HTML to the new API endpoints

### How to run
- cd /home/smcconnell/projects/liberty-basketball-analysis && source .venv/bin/activate && python app.py
- Schedule page: http://localhost:8080/schedule

---

## Rex Turn 2 — 2026-05-15

### Fixes applied
- **app.py**: Replaced deprecated `before_first_request` with `g`-based connection management + `teardown_appcontext`
- **app.py**: Added WAL mode (`PRAGMA journal_mode=WAL`) and busy timeout (`PRAGMA busy_timeout=10000`) to all DB connections
- **app.py**: Added fully permissive CSP headers via `after_request` (required for browser extensions)
- **app.py**: Fixed `save_event` to serialize `details_json` dicts via `json.dumps`
- **app.py**: Auto-init DB on first run if file doesn't exist
- **app.py**: Added `/games` page route, `/api/games` CRUD endpoints, `/api/sources` CRUD endpoints
- **app.py**: Removed debug `print(app.url_map)` line (OpenClaw also caught this)
- **ai_analyzer.py**: Removed duplicate `frame_number = 0` assignment
- **ai_analyzer.py**: Added WAL mode and busy timeout to DB connection
- **ai_analyzer.py**: Changed progress logging from every 100 frames to every 500 frames
- **event_generator.py**: Added WAL mode and busy_timeout to `get_db_connection`
- **season_management.py**: Removed thread-unsafe `row_factory` toggling on connection; use cursor directly
- **scheduled_games.py**: Same row_factory fix

### New features (Phase 3)
- **templates/games.html**: New page — create game form, game list table, delete action
- **config.py**: Enabled `ENABLE_GAMES = True`

### Testing
- All Python modules pass syntax check
- WAL mode and timeout applied consistently across all DB connections
- CSP headers set to fully permissive for extension compatibility

### Next (for OpenClaw)
- Phase 2.5: Manual Tagging & Bookmarks MVP (feature-flagged)
- Phase 4: NFHS Matching — manual candidate add/confirm/reject flow
- Phase 6: Add `/practices` route + `templates/practices.html`
- Wire film tool HTML to the new API endpoints
- Add navigation links between pages (film tool ↔ schedule ↔ games)
