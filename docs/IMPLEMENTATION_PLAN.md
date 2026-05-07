# Liberty Basketball Analysis — Implementation Snapshot

Last updated: 2026-05-07

## Current state

The project is running as a single Flask application with SQLite persistence and server-rendered templates. All phases through Phase 7 are complete:

- **Phase 1:** Data model & schema (all tables)
- **Phase 2:** Season & scheduled game management + /schedule UI
- **Phase 3:** Games & film sources CRUD + NFHS matching
- **Phase 4:** NFHS matching (manual candidate add/confirm/reject)
- **Phase 5:** Stats aggregation from events
- **Phase 6:** Practices & practice reports (AI notes, combined summaries, date-range summaries)
- **Phase 7:** Player development clips, practice playlists, practice plan items

## Architecture summary

### Application layer

- `app.py` owns the Flask routes, database bootstrap, feature-flag injection, resource-status API, and page rendering.
- `config.py` contains feature flags and runtime environment configuration.
- `templates/` contains the UI for all pages.
- `player_development.py` — Phase 7 helper module for clips, playlists, and plan items.

### Analysis pipeline

- `ai_analyzer.py` runs background analysis jobs.
- `event_generator.py` turns detections into persisted events.
- `stats.py` aggregates event data into stats structures.
- `tracker_assigner.py` provides lightweight centroid-based tracking.

### Persistence

- `schema.sql` is the schema source of truth.
- `film_analysis.db` is the default runtime database.
- `uploads/` stores uploaded media.

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

## Operational assets

- `scripts/setup_project.py` — text UI installer for standalone or container setup
- `scripts/build_transfer_bundle.sh` — creates a migration tarball for another server
- `scripts/backup.sh` — backup/restore tooling
- `scripts/smoke_test.sh` — deployment smoke tests
- `docs/DEPLOYMENT.md` — operational runbook
- `docs/AI_AGENT_HANDOFF.md` — AI handoff brief

## Test suite

112 tests passing:
- `test_api.py` — Integration tests for all Flask API endpoints
- `test_season_management.py` — Unit tests for season/scheduled game helpers
- `test_schema.py` — Schema verification (all tables and columns)
- `test_event_pipeline.py` — Tracker and event pipeline tests
- `test_player_development.py` — Phase 7 tests (clips, playlists, plan items)

## Next likely engineering work

1. ~~Harden production serving~~ — gunicorn + nginx config done
2. Expand AI event quality and tracking accuracy (ByteTrack/DeepSort)
3. ~~Add backup/restore tooling~~ — done
4. ~~Add deployment smoke tests~~ — done
5. Split large templates or route groups if future work increases complexity further

## Notes

- The historical project-outline documents in `docs/liberty_outline.txt` and `docs/Master Project Outline 05-04-2026.txt` are still useful for product intent, but the current operational source of truth is now `README.md` plus the deployment and AI handoff docs.
