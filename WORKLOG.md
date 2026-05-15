WORKLOG — Liberty Basketball Analysis
Started: 2026-04-27

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
