# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates` (must be at `d30ce94` or later; includes `docs/STAGE_6A_PLAN.md`)

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6a-implementation |
| **status** | `done` |
| **issued_by** | orchestrator |
| **assigned_to** | **devin** |
| **approved_by** | Scott; implement Stage 6A |

## Objective

Implement Stage 6A per **`docs/STAGE_6A_PLAN.md`**: module key constants, read-only entitlement helpers, audit CLI, tests.

## Checklist

- [x] `git pull origin jason-5-may-updates`; confirm `docs/STAGE_6A_PLAN.md` exists
- [x] Create branch `cursor/stage-6a-implementation-ac1f` from `jason-5-may-updates`
- [x] Add `module_keys.py`; constants + `ALL_MODULE_KEYS` per plan
- [x] Add `module_entitlements.py`; `get_team_entitlements`, `is_module_entitled`, `list_enabled_module_keys`, `audit_team_entitlements`
- [x] Update `helpers.py`; import `BASE_PLATFORM` from `module_keys`; seed behavior unchanged
- [x] Add `scripts/audit_module_entitlements.py`; CLI using audit helper
- [x] Add `tests/test_module_entitlements.py`; all tests listed in plan
- [x] Update `docs/STAGE_INDEX.md`; Stage 6A implementation in progress
- [x] Run `python -m pytest tests/test_module_entitlements.py -q`
- [ ] Run `python -m pytest tests/ -q`; full suite must pass
- [x] Run `python scripts/audit_module_entitlements.py`; shows `base_platform` enabled
- [x] Update Report below; set status to `done`
- [ ] Push branch and open PR into `jason-5-may-updates`

## Hard rules

- **No `schema.sql` changes**
- **No blueprint route enforcement**
- **No auth / billing changes**
- **Do not** mix in old unstaged `helpers.py` / `test_schema.py` experiments; start clean from `d30ce94`
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
- Installed and used `C:\Users\scott\AppData\Local\Programs\Python\Python315\python.exe`.
- `tests/test_module_entitlements.py` passed under that interpreter.
- `scripts/audit_module_entitlements.py` ran successfully when invoked with `PYTHONPATH=.`.
- Full-suite execution stopped during collection at `tests/test_event_pipeline.py` because `pandas` is not installed in the Python 3.15 environment.
- Installing the full `requirements-dev.txt` set on Python 3.15 failed at `numpy` metadata generation because that interpreter is too new for the pinned scientific stack on this machine and no C/C++ compiler toolchain is present.

### Inferred

- The Stage 6A implementation matches the approved planning file boundaries.
- The new helpers are low-risk because they are read-only and not wired into route enforcement yet.
- A stable Python version such as 3.12 or 3.13 should allow the pinned `requirements-dev.txt` stack to install cleanly and unblock the full-suite verification path.

### Unknown

- Whether the full repo test suite passes once run under a stable Python with the pinned scientific stack installed.
- Whether push/PR from this shell will succeed once authentication is available.

### Tests

```text
python -m pytest tests/test_module_entitlements.py -q
8 passed in 3.20s

$env:PYTHONPATH='.'; python scripts/audit_module_entitlements.py
team_count=1
team_id=1
  enabled=base_platform
  disabled=(none)
  missing=stats, minutes_lineups, film_room, scouting, playbook_recognition, strategy, ai_assist, advanced_tracking

python -m pytest tests/ -q
ERROR tests/test_event_pipeline.py
ModuleNotFoundError: No module named 'pandas'

python -m pip install -r requirements-dev.txt
Failed on numpy metadata generation under Python 3.15.0b3 because no compatible wheel/compiler toolchain was available.
```

### Commits / PR

- `69e7855` - `feat(stage6a): add module entitlement helpers and audit tooling`
