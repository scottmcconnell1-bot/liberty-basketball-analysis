# Liberty Basketball Analysis — Implementation Snapshot

Last updated: 2026-05-10

## Current state

The project is running as a Flask application with SQLite persistence and server-rendered templates. All phases through Phase 7 are complete, plus extensive UI/dashboard work:

- **Phase 1:** Data model & schema (all tables)
- **Phase 2:** Season & scheduled game management + /schedule UI
- **Phase 3:** Games & film sources CRUD + NFHS matching
- **Phase 4:** NFHS matching (manual candidate add/confirm/reject)
- **Phase 5:** Stats aggregation from events
- **Phase 6:** Practices & practice reports (AI notes, combined summaries, date-range summaries)
- **Phase 7:** Player development clips, practice playlists, practice plan items
- **Dashboard (COMPLETE):** Full dashboard overhaul — team cards, schedule, rankings, photos, UI audit

## Dashboard — Complete ✅

The dashboard (`/`) is the main landing page and includes:

### Team Cards (1.1)
- 2-column responsive grid of team cards
- Each card shows: team name, MaxPreps ranking (varsity only), overall + conference record, last game result, upcoming schedule
- Schedule rows use a clean 3-column grid layout: `Date | Opponent | H/A`
- Dates right-aligned with vertical border separator for clear column appearance
- Rankings include "↻ Update" button for live MaxPreps refresh

### Team Photos (1.2)
- Full-width section below team cards
- Team selector dropdown to filter by team (Varsity Boys/Girls, JV Boys/Girls, Jr High Boys/Girls)
- Photos displayed full-width, one per row, with `object-fit: contain` and max-height 400px
- Upload button uses selected team from dropdown
- Download and delete actions per photo
- Photo upload/serve via `/api/photos/upload` and `/uploads/team_photos/`

### UI Overflow Audit
- Automated Playwright-based audit (`tests/test_ui_overflow.py`) checks all 17 pages for:
  - Text overflow (horizontal + vertical)
  - Ellipsis truncation
  - Table column breakage
  - Zero-size elements
  - Off-screen elements
  - Overlapping cards
  - Page viewport overflow
- **Result: 17/17 pages passing, 0 HIGH severity issues**
- Run via `python tests/test_ui_overflow.py` or `pytest tests/test_ui_overflow.py -v`

### Technical Details
- 10 Flask Blueprints: core, games, clips, stats, practice, player_dev, ai, playbook, messaging, users
- SQLite with WAL mode + busy_timeout for concurrent request safety
- DB connection teardown via `teardown_appcontext`
- 188 tests passing (187 unit/integration + 1 UI overflow audit)
- Cloudflare tunnel: free tier, URL changes on restart

## Architecture summary

### Application layer

- `app.py` owns the Flask app, blueprint registration, teardown, and entry point
- `helpers.py` contains all shared utilities: `get_db()`, `init_db()`, settings, resource status, etc.
- `config.py` contains feature flags and runtime environment configuration
- `blueprints/` — 10 blueprint modules organizing all routes
- `templates/` — Jinja2 templates for all pages

### Analysis pipeline

- `ai_analyzer.py` runs background analysis jobs.
- `event_generator.py` turns detections into persisted events.
- `stats.py` aggregates event data into stats structures.
- `tracker_assigner.py` provides lightweight centroid-based tracking.

### Persistence

- `schema.sql` is the schema source of truth.
- `film_analysis.db` is the default runtime database (WAL mode).
- `uploads/` stores uploaded media (team photos, videos).

## Deployment modes

### Production (gunicorn + nginx)

- `deploy/liberty-basketball-analysis.service` — systemd service using gunicorn
- `deploy/nginx-liberty-basketball-analysis.conf` — nginx reverse proxy config
- `deploy/deploy_production.sh` — automated install/start/stop/restart script
- `scripts/backup.sh` — backup/restore for DB and uploads
- `scripts/smoke_test.sh` — deployment smoke tests

### Standalone Python install

- Uses `.venv`, `requirements.txt`, and `python app.py`
- Can be managed with systemd using `deploy/liberty-basketball-analysis.service`

### Container install

- Uses `Dockerfile` and `docker-compose.yml`
- GPU hosts can opt into `docker-compose.gpu.yml`

## Test suite

188 tests passing:
- `test_api.py` — Integration tests for all Flask API endpoints
- `test_season_management.py` — Unit tests for season/scheduled game helpers
- `test_schema.py` — Schema verification (all tables and columns)
- `test_event_pipeline.py` — Tracker and event pipeline tests
- `test_player_development.py` — Phase 7 tests (clips, playlists, plan items)
- `test_team_photos.py` — Team photos CRUD tests
- `test_ui_overflow.py` — Playwright-based UI overflow audit (17 pages)
- Plus comprehensive UI, visual regression, and other test files

## Next likely engineering work

1. ~~Harden production serving~~ — gunicorn + nginx config done
2. ~~Dashboard overhaul~~ — team cards, schedule, rankings, photos — DONE ✅
3. Expand AI event quality and tracking accuracy (ByteTrack/DeepSort)
4. ~~Add backup/restore tooling~~ — done
5. ~~Add deployment smoke tests~~ — done
6. Mobile-responsive / PWA (bottom nav, hamburger menu, touch controls, manifest + service worker)

## Notes

- The historical project-outline documents in `docs/liberty_outline.txt` and `docs/Master Project Outline 05-04-2026.txt` are still useful for product intent, but the current operational source of truth is now `README.md` plus the deployment and AI handoff docs.
- Cloudflare tunnel URL changes on restart (free tier). Current URL provided separately.
