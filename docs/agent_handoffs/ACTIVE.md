# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-8a-demo-entitlements |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- `DEMO_MODULE_ENTITLEMENTS` seeds `stats` and `scouting` via INSERT OR IGNORE (no schema change)
- `_backfill_demo_module_entitlements_stage8a()` runs on `init_db`
- `seed_demo_module_entitlements()` public helper + `scripts/seed_demo_module_entitlements.py` CLI
- Audit/preview surfaces show stats + scouting enabled on default team
- 326 passed, 1 skipped

### Next

Phase 4 deploy gates (9A secrets audit) — Scott gate; or polish/docs pass on COMPLETION_PATH
