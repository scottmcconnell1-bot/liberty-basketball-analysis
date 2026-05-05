# Liberty Basketball Analysis — Implementation Snapshot

Last updated: 2026-05-05

## Current state

The project is running as a single Flask application with SQLite persistence and server-rendered templates. The codebase already supports:

- season and scheduled game management
- games and sources
- NFHS match linking
- video upload and AI-analysis run tracking
- film review/manual tagging workflows
- practice planning and reporting
- debug/issue reporting with saved reports and application logs
- local runtime telemetry for CPU, memory, GPU, and live power when the host exposes those metrics

## Architecture summary

### Application layer

- `app.py` owns the Flask routes, database bootstrap, feature-flag injection, resource-status API, and page rendering.
- `config.py` contains feature flags and runtime path configuration via environment variables.
- `templates/` contains the UI for dashboard, film tool, schedule, settings, debug/issues, practices, and supporting pages.

### Analysis pipeline

- `ai_analyzer.py` runs background analysis jobs.
- `event_generator.py` turns detections into persisted events.
- `stats.py` aggregates event data into stats structures.
- `tracker_assigner.py` and supporting helpers provide tracking-related logic.

### Persistence

- `schema.sql` is the schema source of truth.
- `film_analysis.db` is the default runtime database.
- `uploads/` stores uploaded media.

## Deployment modes

The project is now documented and supported in two primary modes:

1. **Standalone Python install**
   - Uses `.venv`, `requirements.txt`, and `python app.py`
   - Can be managed with systemd using `deploy/liberty-basketball-analysis.service`

2. **Container install**
   - Uses `Dockerfile` and `docker-compose.yml`
   - GPU hosts can opt into `docker-compose.gpu.yml`

## Operational assets

- `scripts/setup_project.py` — text UI installer for standalone or container setup
- `scripts/build_transfer_bundle.sh` — creates a migration tarball for another server
- `docs/DEPLOYMENT.md` — operational runbook
- `docs/AI_AGENT_HANDOFF.md` — AI handoff brief

## Next likely engineering work

These are the most natural follow-on tasks after the current deployment and handoff refresh:

1. Harden production serving for standalone installs (for example gunicorn + reverse proxy if needed)
2. Expand AI event quality and tracking accuracy
3. Add more explicit backup/restore tooling for uploads and SQLite snapshots
4. Add deployment smoke tests for standalone and container flows
5. Split large templates or route groups if future work increases complexity further

## Notes

- The historical project-outline documents in `docs/liberty_outline.txt` and `docs/Master Project Outline 05-04-2026.txt` are still useful for product intent, but the current operational source of truth is now `README.md` plus the deployment and AI handoff docs.
