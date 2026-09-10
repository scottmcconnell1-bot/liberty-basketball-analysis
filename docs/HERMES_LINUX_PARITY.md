# Hermes / Linux Parity (Stage 9D)

Updated: 2026-07-05  
Audience: Hermes (OWL), Cursor Cloud Agent, Scott

## Why this doc exists

Liberty development spans multiple agents and machines. **Parity** means the same verification commands produce the same pass/fail signal on:

- Cursor Cloud Agent (Linux, Python 3.12)
- Hermes/OWL executor (Scott's Linux host)
- A restored transfer bundle on a fresh server

## Agent roles

| Agent | Role |
| --- | --- |
| **Cursor Cloud Agent** | Implements roadmap slices, runs pytest, opens/merges PRs |
| **Hermes (OWL)** | Git/deploy executor on Scott's machine; Linux verification witness |
| **Scott** | Product owner; gates schema, auth, production deploy |

## Parity baseline (2026-07-05)

| Check | Command | Expected |
| --- | --- | --- |
| Unit/integration tests | `python3 -m pytest tests/ -q` | **631 passed, 29 skipped** (2026-09-09; was 331/1 on 2026-07-05) |
| Secrets audit | `python3 scripts/audit_secrets.py` | exits 0; findings documented in `docs/SECRETS_AUDIT.md` |
| Module entitlements audit | `python3 scripts/audit_module_entitlements.py` | exits 0 |
| Transfer bundle build | `bash scripts/build_transfer_bundle.sh` | creates `transfer-bundles/*.tar.gz` (gitignored; now includes `stat_book/`, `static/`, `data/stat_books/`, `models/`) |
| Docker production smoke | `bash scripts/docker_production_smoke.sh` | **Hermes/Linux only** (requires Docker) |

## Transfer bundle workflow

### Build (source machine)

```bash
bash scripts/build_transfer_bundle.sh
```

Output: `transfer-bundles/liberty-basketball-analysis-transfer-<timestamp>.tar.gz`

The bundle includes application code (`blueprints/`, root `*.py` except `benchmark_*`), templates, tests, docs, scripts, Docker files, `.env.example`, `film_analysis.db`, `uploads/`, and root `*.pt` models.

### Restore (target machine)

```bash
mkdir -p ~/liberty-restore && cd ~/liberty-restore
tar -xzf /path/to/liberty-basketball-analysis-transfer-<timestamp>.tar.gz
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -c "from app import app, init_db; ctx = app.app_context(); ctx.push(); init_db(); ctx.pop()"
python3 -m pytest tests/ -q
LIBERTY_DEBUG=0 PORT=8080 python app.py
```

Or use `python3 scripts/setup_project.py` for guided standalone/container install.

### Parity proof Hermes should record

After restore on Linux, capture in the GitHub issue or handoff note:

1. `python3 -m pytest tests/ -q` line (pass/skip counts)
2. `python3 scripts/audit_secrets.py` summary line
3. Optional: `bash scripts/docker_production_smoke.sh` result

## Differences that are OK

| Topic | Cloud Agent | Hermes host |
| --- | --- | --- |
| Docker smoke | May skip if Docker not installed | Should run full 9C smoke |
| GPU | CPU-only typical | May run `docker-compose.gpu.yml` |
| `film_analysis.db` | Bundled demo data | Same file restores 1:1 |
| Secrets | Dev `SECRET_KEY` fallback | Set `SECRET_KEY` via env before production |

## Differences that are NOT OK

- Pytest pass count regression without explanation
- Missing modules in transfer bundle (import errors on restore)
- Committed private keys (run `scripts/audit_secrets.py`; `repo_pattern_hits` should be 0)
- Auth middleware enabled without Scott approval

## Related

- `docs/DEPLOYMENT.md` — install and restore details
- `docs/DOCKER_PRODUCTION_SMOKE.md` — Stage 9C checklist
- `docs/AI_AGENT_HANDOFF.md` — file map for new agents
- `docs/agent_handoffs/ACTIVE.md` — current slice
