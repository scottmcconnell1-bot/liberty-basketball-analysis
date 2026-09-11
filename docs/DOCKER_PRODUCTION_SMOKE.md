# Docker Production Smoke (Stage 9C)

Updated: 2026-07-05  
Status: Operator checklist — run on a clean Linux VM with Docker before public production.

## Purpose

Validate the **production-shaped** container path end-to-end:

1. Image builds from `Dockerfile` + `requirements.docker.txt`
2. `docker compose up` serves coach surfaces on port 8080
3. HTTP smoke tests pass (`scripts/smoke_test.sh`)
4. Optional in-container secrets audit runs without crashing

Auth middleware remains disabled; this is a deploy-shape check, not a go-live flip.

## Prerequisites

- Linux host (Hermes/OWL machine or fresh VM)
- Docker Engine + Compose plugin
- `curl`
- Ports `8080` free
- No committed secrets required for smoke (VAPID/SMTP may be unset)

## One-command smoke

```bash
bash scripts/docker_production_smoke.sh
```

Keep the container running after success:

```bash
KEEP_RUNNING=1 bash scripts/docker_production_smoke.sh
```

## Manual steps (equivalent)

```bash
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
curl -sf http://127.0.0.1:8080/status
bash scripts/smoke_test.sh http://127.0.0.1:8080 standalone
docker compose exec web python scripts/audit_secrets.py
docker compose down
```

## GPU path (optional)

After CPU smoke passes:

```bash
nvidia-smi
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec web nvidia-smi
```

## Expected results

| Check | Expected |
| --- | --- |
| `docker compose build` | succeeds |
| `/status` | HTTP 200 |
| `smoke_test.sh` | all HTTP checks pass; 0 failures |
| `audit_secrets.py` | runs; may report dev SECRET_KEY / missing VAPID (documented in `docs/SECRETS_AUDIT.md`) |
| Host pytest (optional) | `python3 -m pytest tests/ -q` — 631 passed, 29 skipped (Python 3.13, 2026-09-09; was 331/1 on 2026-07-05) |

## Scott gate

- Passing this smoke on Hermes/Linux is required before public production deploy.
- Re-enabling auth (`docs/AUTH_REENABLE_PLAN.md`) is a separate Scott approval.

## Troubleshooting

- **Build fails on torch**: confirm network access to `download.pytorch.org` or use pre-built image cache.
- **Container exits immediately**: `docker compose logs web` — often missing volume paths or import errors.
- **Smoke 000 / connection refused**: wait longer or increase `WAIT_SECONDS=120`.
