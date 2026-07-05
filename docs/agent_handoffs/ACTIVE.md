# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | bootstrap-2026-07-05 |
| **status** | `done` |
| **issued_by** | orchestrator |
| **assigned_to** | cursor-cloud-agent |

## Objective

Prove the Liberty repo runs cleanly in the Cloud Agent environment and establish a baseline before Stage 6A or other product work.

## Context

- Legacy Alpha/Owl coordination is retired. See `docs/ORCHESTRATION.md`.
- Stage 5 cleanup and event lifecycle work are complete per `PROJECT_STATUS.md`.
- Leading next engineering slice: **Stage 6A module entitlement helper/audit wiring** — do **not** start until this bootstrap passes.

## Checklist

- [x] Git preflight: on `jason-5-may-updates`, fetch origin, report HEAD vs `origin/jason-5-may-updates`
- [x] Install deps if needed: `pip install -r requirements-dev.txt` (no root `requirements.txt` in repo)
- [x] Run `python -m pytest tests/ -q` — report pass/fail/skip counts
- [x] Run `python -c "from app import app; print('app import ok')"`
- [x] Note whether `models/ball_detector.pt` is present (Git LFS) — do not retrain or change detector settings
- [x] Update this file: set status to `done`, fill Report below
- [x] If bootstrap passes: set next ACTIVE task draft for Stage 6A preflight planning (issue body only — no schema changes without Scott)

## Out of scope

- `schema.sql` changes
- Production detector changes
- New features
- Devin or second-agent setup

## Report

### Proven

- HEAD `e79d421` matches `origin/jason-5-may-updates` on branch `cursor/orchestration-setup-ac1f`.
- `pip install -r requirements-dev.txt` succeeds in Cloud Agent environment.
- `python -c "from app import app"` prints `app import ok`.
- `python -m pytest tests/ -q` → **296 passed, 1 skipped** in ~10s.
- `models/ball_detector.pt` exists as a **Git LFS pointer** (134 bytes); actual weights are ~173MB via LFS.
- Root `requirements.txt` referenced in README does **not** exist; `requirements-dev.txt` is the lightweight test path.

### Inferred

- Cloud Agent environment is sufficient for Flask/schema/API unit tests without full CV stack.
- Full ML/detector runtime tests may need `requirements.docker.txt` stack or `git lfs pull` on Linux host.

### Unknown

- Whether Scott has on-demand billing disabled/$0-capped in Cursor dashboard (account-side; not verifiable from repo).
- Whether Devin subscription is active and cancellable (account-side).

### Tests

```
296 passed, 1 skipped in 10.19s
```

### Commits

- Pending: orchestration setup branch `cursor/orchestration-setup-ac1f`

---

## Next task (draft — activate when Scott approves Stage 6A)

Replace this file content when starting Stage 6A preflight:

- **id:** stage-6a-preflight
- **status:** pending
- **objective:** Plan module entitlement helper/audit wiring per `docs/PLATFORM_CORE_SCHEMA_PLAN.md` — constants, read helper, no auth enforcement, no billing
- **gate:** Scott approval before any `schema.sql` change
