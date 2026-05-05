# Liberty Basketball Analysis

Flask-based basketball operations app for Liberty that combines scheduling, games, sources, video upload/review, manual tagging, AI-assisted event generation, practice planning, debugging, and lightweight local resource monitoring.

## What the project does

- **Schedule and season management** with CRUD flows for seasons and scheduled games.
- **Games and source tracking** for manual sources and NFHS matches.
- **Film workflow** with upload, manual tagging, bookmarks, AI-generated events, and run-status tracking.
- **Practice workflows** with plans, coach notes, AI notes, and summaries.
- **Debug and issue reporting** with an in-page report drawer, saved issue log, app logs, and AI failure visibility.
- **Runtime telemetry** that shows CPU, memory, GPU, and live power data when the host exposes those metrics.

## Repository map

| Path | Purpose |
| --- | --- |
| `app.py` | Main Flask application, routes, DB bootstrap, resource-status API |
| `config.py` | Feature flags and runtime environment configuration |
| `schema.sql` | SQLite schema source of truth |
| `templates/` | Server-rendered UI templates |
| `ai_analyzer.py` | Background analysis runner |
| `event_generator.py` | Event heuristics and generation |
| `stats.py` | Stats aggregation helpers |
| `docs/` | Project, deployment, and handoff documentation |
| `scripts/setup_project.py` | Text UI installer for standalone or container installs |
| `scripts/build_transfer_bundle.sh` | Creates a server-transfer tarball |
| `deploy/liberty-basketball-analysis.service` | Systemd service template for standalone installs |

## Quick start

### Recommended: use the setup TUI

```bash
python3 scripts/setup_project.py
```

The setup script can:

1. Install the app as a **standalone Python service**
2. Start the app as a **Docker container**
3. Use the **GPU Docker override** when an NVIDIA GPU is available
4. Build a **transfer tarball** for moving the project to another server

## Standalone run

### Manual install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -c "from app import app, init_db; ctx = app.app_context(); ctx.push(); init_db(); ctx.pop()"
python app.py
```

### Standalone runtime environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `LIBERTY_DATABASE` | `film_analysis.db` | SQLite DB path |
| `LIBERTY_UPLOAD_FOLDER` | `uploads` | Upload/media directory |
| `PORT` | `8080` | HTTP port |
| `LIBERTY_DEBUG` | `1` | Enables Flask debug mode when running `python app.py` |

### Production-style standalone launch

```bash
LIBERTY_DEBUG=0 PORT=8080 .venv/bin/python app.py
```

For a long-running server install, use the systemd template at `deploy/liberty-basketball-analysis.service`.

## Docker and container run

### CPU container

```bash
docker compose up -d --build
```

### GPU-capable container

Use the GPU override on hosts with:

- NVIDIA drivers installed
- NVIDIA Container Toolkit configured for Docker
- `nvidia-smi` working on the host

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

The default `docker-compose.yml` builds a CPU image. The `docker-compose.gpu.yml` override switches the PyTorch wheel index to CUDA and requests `gpus: all`.

## Data and persistent files

The app keeps its mutable state in:

- `film_analysis.db`
- `uploads/`
- optional local model weights such as `yolov8n.pt`, `yolov8m.pt`, `yolo11m.pt`

These are included in the transfer bundle script so another server can receive both the code and the current working state.

## Documentation map

- `docs/DEPLOYMENT.md` — standalone install, Docker, GPU containers, server transfer, restore flow
- `docs/AI_AGENT_HANDOFF.md` — concise handoff brief for another AI agent
- `docs/IMPLEMENTATION_PLAN.md` — current implementation snapshot and forward roadmap
- `docs/FILM_TOOL_AI_EVENTS.md` — film tool event panel behavior and related UI notes

## AI handoff

If another AI agent needs to take over the project, start with:

1. `README.md`
2. `docs/DEPLOYMENT.md`
3. `docs/AI_AGENT_HANDOFF.md`
4. `schema.sql`
5. `app.py`

The handoff doc includes a suggested prompt, key commands, persistent data locations, and the highest-value code surfaces to read first.

## Transfer bundle

Create a server-migration archive with:

```bash
bash scripts/build_transfer_bundle.sh
```

The archive is written to `transfer-bundles/` and includes the app code, docs, templates, tests, Docker assets, setup scripts, DB, uploads, and local `.pt` model files.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```
