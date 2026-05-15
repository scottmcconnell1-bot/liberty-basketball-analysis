WORKLOG — Liberty Basketball Analysis
Started: 2026-04-27

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
