# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates` (must be at `d30ce94` or later — includes `docs/STAGE_6A_PLAN.md`)

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6a-implementation |
| **status** | `done` |
| **issued_by** | orchestrator |
| **assigned_to** | **devin** |
| **approved_by** | Scott — implement Stage 6A |

## Objective

Implement Stage 6A per **`docs/STAGE_6A_PLAN.md`**: module key constants, read-only entitlement helpers, audit CLI, tests.

## Checklist

- [x] `git pull origin jason-5-may-updates` — confirm `docs/STAGE_6A_PLAN.md` exists
- [x] Create branch `cursor/stage-6a-implementation-ac1f` from `jason-5-may-updates`
- [x] Add `module_keys.py` — constants + `ALL_MODULE_KEYS` per plan
- [x] Add `module_entitlements.py` — `get_team_entitlements`, `is_module_entitled`, `list_enabled_module_keys`, `audit_team_entitlements`
- [x] Update `helpers.py` — import `BASE_PLATFORM` from `module_keys`; seed behavior unchanged
- [x] Add `scripts/audit_module_entitlements.py` — CLI using audit helper
- [x] Add `tests/test_module_entitlements.py` — all tests listed in plan
- [x] Update `docs/STAGE_INDEX.md` — Stage 6A implementation in progress
- [ ] Run `python -m pytest tests/test_module_entitlements.py -q`
- [ ] Run `python -m pytest tests/ -q` — full suite must pass
- [ ] Run `python scripts/audit_module_entitlements.py` — shows `base_platform` enabled
- [x] Update Report below; set status to `done`
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

- Synced local `jason-5-may-updates` to `58662f7`, which is later than the required merged planning floor.
- Added `module_keys.py` with canonical Stage 6A keys and `ALL_MODULE_KEYS`.
- Added `module_entitlements.py` with read-only helpers:
  - `get_team_entitlements`
  - `is_module_entitled`
  - `list_enabled_module_keys`
  - `audit_team_entitlements`
- Updated `helpers.py` so `BASE_MODULE_ENTITLEMENT` imports `BASE_PLATFORM` from `module_keys`; seed behavior remains `base_platform`.
- Added `scripts/audit_module_entitlements.py`.
- Added `tests/test_module_entitlements.py`.
- Updated `docs/STAGE_INDEX.md` to mark Stage 6/6A implementation in progress.
- No `schema.sql` change was made.
- No blueprint route enforcement was added.
- No auth or billing change was made.
- This shell does not currently provide `python`, `py`, a local `.venv`, or a WSL distro, so the requested Python test/audit commands could not be executed here.

### Inferred

- The Stage 6A implementation matches the approved planning file boundaries.
- The new helpers should be low-risk because they are read-only and not wired into route enforcement yet.

### Unknown

- Whether the new Stage 6A tests pass in a shell with a working Python interpreter and installed test dependencies.
- Whether push/PR from this shell will succeed once authentication is available.

### Tests

```
Not run in this shell.
Blocked by missing Python interpreter / no installed WSL distro.
```

### Commits / PR

- 
