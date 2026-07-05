# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6a-preflight |
| **status** | `done` |
| **issued_by** | orchestrator |
| **assigned_to** | devin → orchestrator push |
| **started** | 2026-07-05 — Devin read inputs at HEAD 7ba4585 |
| **completed** | 2026-07-05 — planning pushed by orchestrator (Devin push blocked) |

## Objective

**Planning slice only:** define Stage 6A module entitlement helper/audit wiring per `docs/PLATFORM_CORE_SCHEMA_PLAN.md`.

Deliver a short plan doc or PR comment — **no `schema.sql` changes** without Scott approval.

## Checklist

- [x] Read `docs/PLATFORM_CORE_SCHEMA_PLAN.md` Stage 6 section and `schema.sql` `module_entitlements` table
- [x] Read `config.py` feature flags vs entitlement concept — note what stays separate
- [x] Propose: constant module keys, helper function name/location, audit/read API or script (if any)
- [x] List exact files to touch in a future implementation PR
- [x] List tests to add in implementation phase
- [x] Write plan to `docs/STAGE_6A_PLAN.md` (new file) OR as PR description
- [x] Update Report below; set status to `done`
- [x] **Do not** modify `schema.sql` in this slice

## Report

### Proven

- Devin synced to `7ba4585`, read all required inputs, produced local commit `c7b3523` on `cursor/stage-6a-preflight-ac1f`.
- Devin push failed: `SEC_E_NO_CREDENTIALS`; `gh` not installed in Devin shell.
- Orchestrator pushed `docs/STAGE_6A_PLAN.md` + this report to GitHub.
- Seeded entitlement key in DB is `base_platform` (from `helpers.BASE_MODULE_ENTITLEMENT`).

### Inferred

- Devin's local plan content likely aligns with pushed `docs/STAGE_6A_PLAN.md`; byte-level diff not verified.

### Unknown

- Contents of Devin's unstaged `helpers.py` / `test_schema.py` edits — **discard or stash**; do not mix into planning PR.

### Deliverable

- `docs/STAGE_6A_PLAN.md`

### Commits / PR

- Orchestrator push on `cursor/stage-6a-preflight-ac1f` (pending PR)

---

## Next task (draft — after Scott approves 6A plan)

- **id:** stage-6a-implementation
- **assigned_to:** devin or cursor-cloud-agent
- **objective:** Implement `module_keys.py`, `module_entitlements.py`, audit CLI, tests per `docs/STAGE_6A_PLAN.md`
- **gate:** Scott approval on planning PR merge
