# Stage 6A Plan — Module Entitlement Helper / Audit Wiring

Updated: 2026-07-05
Branch: `jason-5-may-updates`
Status: **Planning only** (approved for implementation after Scott review)
Stage: **6A preflight**

## Provenance

- Executor: Devin completed this planning slice locally at `c7b3523` but could not push (no GitHub credentials in Devin shell).
- Orchestrator: reproduced and pushed from Cloud Agent so the repo has the deliverable.

## Objective

Add a **read-only entitlement layer** on top of existing `module_entitlements` rows — without changing `schema.sql`, without route enforcement, and without mixing paid-package entitlements with `config.py` development feature flags.

## Background (Proven)

- `module_entitlements` exists in `schema.sql` with `team_id`, `module_key`, `enabled`, `starts_at`, `ends_at`.
- Stage 2 backfill seeds one row per Liberty team via `helpers._seed_base_module_entitlement()` using `BASE_MODULE_ENTITLEMENT["module_key"]` = **`base_platform`** (not `base`).
- `docs/PLATFORM_CORE_SCHEMA_PLAN.md` Stage 6 lists module keys: `base`, `stats`, `minutes_lineups`, `film_room`, `scouting`, `playbook_recognition`, `strategy`, `ai_assist`, `advanced_tracking`.
- `config.py` `Features.ENABLE_*` flags are **development/runtime toggles**, not customer package entitlements (`docs/BASE_PLATFORM_GAP_AUDIT.md`).

## Design decisions

### 1. Two separate control planes

| Layer | Source | Purpose | Stage 6A |
| --- | --- | --- | --- |
| **Dev feature flags** | `config.py` → `Features.ENABLE_*` | Hide incomplete work in dev | Unchanged |
| **Package entitlements** | `module_entitlements` table | Future paid modules per team | Read helpers only |

Route gating formula (future Stage 6B+, after auth):

```
route_available = feature_enabled(FLAG) AND is_module_entitled(team_id, MODULE_KEY)
```

Stage 6A implements only the entitlement side. No blueprint changes yet.

### 2. Canonical module keys

New file: **`module_keys.py`**

```python
# Locked keys — must match MODULAR_PRODUCT_ROADMAP / PLATFORM_CORE_SCHEMA_PLAN
BASE_PLATFORM = "base_platform"  # matches Stage 2 seed (not "base")
STATS = "stats"
MINUTES_LINEUPS = "minutes_lineups"
FILM_ROOM = "film_room"
SCOUTING = "scouting"
PLAYBOOK_RECOGNITION = "playbook_recognition"
STRATEGY = "strategy"
AI_ASSIST = "ai_assist"
ADVANCED_TRACKING = "advanced_tracking"

ALL_MODULE_KEYS = (...)

# Alias for docs that say "base"
LEGACY_BASE_ALIAS = "base"
```

**Action in implementation PR:** migrate `helpers.BASE_MODULE_ENTITLEMENT` to import `module_keys.BASE_PLATFORM` instead of a string literal. No schema change.

**Do not rename** the seeded `base_platform` row without Scott approval and a data migration plan.

### 3. Read helper module

New file: **`module_entitlements.py`**

Proposed public API:

| Function | Behavior |
| --- | --- |
| `get_team_entitlements(db, team_id)` | Returns all rows for team (ordered by module_key) |
| `is_module_entitled(db, team_id, module_key, *, at=None)` | True if row exists, `enabled=1`, and `at` is within `starts_at`/`ends_at` window (NULL bounds = open) |
| `list_enabled_module_keys(db, team_id, *, at=None)` | List of keys passing `is_module_entitled` |
| `audit_team_entitlements(db, team_id=None)` | Returns structured dict for `/status` or CLI — row counts, missing expected keys, disabled modules |

Implementation notes:

- Use existing `get_db()` / connection patterns from `helpers.py`.
- Normalize `module_key` to lowercase stripped string before lookup.
- Unknown `module_key` → `False` (fail closed for entitlement checks).
- Log at debug only; no user-facing errors in Stage 6A.

### 4. Audit surface (read-only)

**Option A (preferred):** extend `/status` JSON or template with an **entitlements** section calling `audit_team_entitlements()`.

**Option B:** `scripts/audit_module_entitlements.py` CLI for operators.

Stage 6A implementation should do **Option B first** (lower UI risk), then Option A in a follow-up product-proof slice if Scott wants it visible.

### 5. Move seed constant

In implementation PR:

- `helpers.py`: replace inline `BASE_MODULE_ENTITLEMENT` dict key string with import from `module_keys.BASE_PLATFORM`.
- Keep seed behavior identical (idempotent `INSERT OR IGNORE`).

## Files to touch (implementation PR — Stage 6A implementation)

| File | Change |
| --- | --- |
| `module_keys.py` | **New** — constants + `ALL_MODULE_KEYS` |
| `module_entitlements.py` | **New** — read helpers + audit |
| `helpers.py` | Import `BASE_PLATFORM` from `module_keys`; no behavior change |
| `scripts/audit_module_entitlements.py` | **New** — CLI audit |
| `tests/test_module_entitlements.py` | **New** — focused tests |
| `docs/STAGE_INDEX.md` | Mark Stage 6A planning complete; Stage 6A impl in progress when started |

## Explicit non-goals (Stage 6A)

- No `schema.sql` changes
- No blueprint `@before_request` enforcement
- No auth / `role_required` wiring
- No billing or Stripe
- No renaming `base_platform` seed row to `base`
- No coupling `Features.ENABLE_*` into entitlement helpers (callers combine both later)

## Tests (implementation PR)

| Test | Asserts |
| --- | --- |
| `test_is_module_entitled_enabled` | Seeded `base_platform` true for default Liberty team after `init_db` |
| `test_is_module_entitled_unknown_key` | Unknown key returns False |
| `test_is_module_entitled_disabled_row` | `enabled=0` returns False |
| `test_is_module_entitled_date_window` | `starts_at`/`ends_at` boundaries |
| `test_list_enabled_module_keys` | Returns seeded keys |
| `test_audit_team_entitlements` | Structured output includes team_id and module list |
| `test_module_keys_matches_seed` | `BASE_PLATFORM` matches `helpers` seed key |

Run: `python -m pytest tests/test_module_entitlements.py -q`

## Stage sequencing after 6A

| Slice | Scope |
| --- | --- |
| **6A impl** | This plan — constants + read helpers + audit CLI + tests |
| **6B** | Wire selected routes: `feature_enabled AND is_module_entitled` (Scott picks routes) |
| **6C** | `/status` or admin UI entitlement display |
| **6D** | Auth re-enabled + team-scoped permission checks |

## Acceptance criteria (implementation)

- [ ] All tests in `tests/test_module_entitlements.py` pass
- [ ] Full suite `python -m pytest tests/ -q` unchanged or improved
- [ ] `scripts/audit_module_entitlements.py` runs on fresh `init_db` and shows `base_platform` enabled
- [ ] No `schema.sql` diff
- [ ] `config.py` unchanged unless a comment clarifying separation is added

## Report

### Proven

- Planning inputs read from `PLATFORM_CORE_SCHEMA_PLAN.md`, `schema.sql`, `config.py`, `helpers.py` seed.
- Seeded module key is `base_platform`, not `base`.

### Inferred

- Devin's local commit `c7b3523` likely matches this plan; diff not verified until push credentials fixed.

### Unknown

- Whether Devin's unstaged `helpers.py` / `test_schema.py` edits overlap this plan — **discard or stash** those until implementation PR is approved.
