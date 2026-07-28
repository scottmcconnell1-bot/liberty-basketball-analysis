# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates` (must be at `d30ce94` or later — includes `docs/STAGE_6A_PLAN.md`)

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6a-implementation |
| **status** | `pending` |
| **issued_by** | orchestrator |
| **assigned_to** | **devin** |
| **approved_by** | Scott — implement Stage 6A |

## Objective

Implement Stage 6A per **`docs/STAGE_6A_PLAN.md`**: module key constants, read-only entitlement helpers, audit CLI, tests.

## Checklist

- [ ] `git pull origin jason-5-may-updates` — confirm `docs/STAGE_6A_PLAN.md` exists
- [ ] Create branch `cursor/stage-6a-implementation-ac1f` from `jason-5-may-updates`
- [ ] Add `module_keys.py` — constants + `ALL_MODULE_KEYS` per plan
- [ ] Add `module_entitlements.py` — `get_team_entitlements`, `is_module_entitled`, `list_enabled_module_keys`, `audit_team_entitlements`
- [ ] Update `helpers.py` — import `BASE_PLATFORM` from `module_keys`; seed behavior unchanged
- [ ] Add `scripts/audit_module_entitlements.py` — CLI using audit helper
- [ ] Add `tests/test_module_entitlements.py` — all tests listed in plan
- [ ] Update `docs/STAGE_INDEX.md` — Stage 6A implementation in progress
- [ ] Run `python -m pytest tests/test_module_entitlements.py -q`
- [ ] Run `python -m pytest tests/ -q` — full suite must pass
- [ ] Run `python scripts/audit_module_entitlements.py` — shows `base_platform` enabled
- [ ] Update Report below; set status to `done`
- [ ] Push branch and open PR into `jason-5-may-updates`

## Hard rules

- **No `schema.sql` changes**
- **No blueprint route enforcement**
- **No auth / billing changes**
- **Do not** mix in old unstaged `helpers.py` / `test_schema.py` experiments — start clean from `d30ce94`
- **Do not** rename `base_platform` seed key

## If push fails again

Commit locally and report commit hash. Orchestrator can push from Cloud Agent if needed.

## Report

_Fill in when complete._

### Proven

- 

### Inferred

- 

### Unknown

- 

### Tests

```
```

### Commits / PR

- 
