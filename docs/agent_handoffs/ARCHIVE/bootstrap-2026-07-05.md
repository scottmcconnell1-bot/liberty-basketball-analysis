# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6a-preflight |
| **status** | `pending` |
| **issued_by** | orchestrator |
| **assigned_to** | devin *(or cursor-cloud-agent if Devin unavailable)* |

## Objective

**Planning slice only:** define Stage 6A module entitlement helper/audit wiring per `docs/PLATFORM_CORE_SCHEMA_PLAN.md`.

Deliver a short plan doc or PR comment — **no `schema.sql` changes** without Scott approval.

## Context

- Bootstrap complete: 296 passed, 1 skipped (see `ARCHIVE/bootstrap-2026-07-05.md`).
- Stage 5 and event lifecycle cleanup are complete per `PROJECT_STATUS.md`.
- Stage 6A scope: module-key constants, read helper for `module_entitlements`, keep dev feature flags separate, **no auth enforcement, no billing**.

## Checklist

- [ ] Read `docs/PLATFORM_CORE_SCHEMA_PLAN.md` Stage 6 section and `schema.sql` `module_entitlements` table
- [ ] Read `config.py` feature flags vs entitlement concept — note what stays separate
- [ ] Propose: constant module keys, helper function name/location, audit/read API or script (if any)
- [ ] List exact files to touch in a future implementation PR
- [ ] List tests to add in implementation phase
- [ ] Write plan to `docs/STAGE_6A_PLAN.md` (new file) OR as PR description
- [ ] Update Report below; set status to `done`
- [ ] **Do not** modify `schema.sql` in this slice

## Out of scope

- Schema migrations
- Auth / billing / multi-tenant packaging
- Production detector changes

## Report

_Fill in when complete._

### Proven

- 

### Inferred

- 

### Unknown

- 

### Deliverable

- 

### Commits / PR

- 
