# Active Task

Updated: 2026-08-01 (Play All follows play sheets)


Branch: `cursor/full-film-panel-ac1f`


## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-sheet-reorder |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |


## Objective

Play sheets (steps) can be reordered and relabeled in Edit, then saved.


## Checklist

- [x] Drag ☰ / ▲▼ reorder sheets in Edit mode
- [x] Editable sheet labels + dirty banner + Save Play persists order
- [x] Test: `test_save_reorders_and_renames_steps`
- [ ] Scott confirms on Rub (Edit → drag → rename → Save)


## Report

### Proven

- `playbook_save` writes `step_number` from array index; labels + `source_image` round-trip

### Inferred

- View mode stays read-only; use Edit for sheet changes

### Unknown

- None


## Ops note

Do not kill `analysis_launcher` / `hoops_teach_loop` when restarting Flask.
