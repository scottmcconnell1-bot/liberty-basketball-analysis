# Active Task

Updated: 2026-08-03 (dual-machine sync protocol)


Branch: `cursor/full-film-panel-ac1f`


## Meta

| Field | Value |
| --- | --- |
| **id** | dual-machine-sync |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |


## Objective

Home and work PCs interchangeable for code/docs: one shared branch, pull on arrive, push on leave, ACTIVE.md as truth. Local-only: DB, uploads, .env.


## Prior task (still awaiting Scott confirm)

**playbook-sheet-align** — ink path hug + no synthetic pass — status was `implemented`; Scott confirm of Play All still open. Code already on this branch.


## Dual-machine protocol

- Shared branch: `cursor/full-film-panel-ac1f` (tracks `origin/cursor/full-film-panel-ac1f`)
- Arrive: `pwsh -File scripts/sync_liberty_work.ps1`
- Leave: commit safe code/docs → `git push -u origin HEAD`
- Details: `docs/DUAL_MACHINE.md`
- Does **not** sync: `.env`, `film_analysis.db`, `uploads/`, teach/panel runtime logs


## Checklist

- [x] Confirm shared branch from ACTIVE / current HEAD
- [x] Ensure upstream tracking (`git push -u origin HEAD`)
- [x] Commit shared code/docs + sheet_align_cache; exclude secrets/DB/panel runtime
- [x] Push to origin
- [x] Add `scripts/sync_liberty_work.ps1`
- [x] Add `docs/DUAL_MACHINE.md` + ORCHESTRATION pointer
- [ ] Scott runs sync on work PC once and confirms clean pull


## Report

### Proven

- Branch `cursor/full-film-panel-ac1f` is the ACTIVE shared branch; playbook/coach code already committed here
- Sync helper and dual-machine docs added this session

### Inferred

- Work PC needs only `git pull` / sync script after this push; no DB copy required for code/docs handoff

### Unknown

- Whether work PC clone already has this remote branch checked out
- Scott Play All visual confirm for sheet-align (carried from prior handoff)


## Ops note

Do not kill `analysis_launcher` / `hoops_teach_loop` when restarting Flask.
