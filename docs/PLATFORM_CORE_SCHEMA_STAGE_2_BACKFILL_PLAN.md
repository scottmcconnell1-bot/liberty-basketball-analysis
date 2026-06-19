# Platform Core Schema Stage 2 Backfill Plan

Updated: 2026-06-18
Branch: jason-5-may-updates
Status: Implemented locally; awaiting Hermes/OWL Linux verification.

## Purpose

Stage 1 added the base platform tables needed for a modular basketball operations system:

- teams
- roster_memberships
- video_assets
- event_types
- provenance_records
- module_entitlements

Stage 2 should make those tables usable by adding safe, idempotent seed and backfill logic. This stage must not rewrite coach workflows or change production behavior beyond adding missing reference data.

## Scope

Stage 2 should populate:

1. A default Liberty team record.
2. Roster memberships for existing players.
3. Video asset records for existing uploaded videos and analysis sources.
4. Canonical event type rows.
5. Initial module entitlement rows.
6. Provenance records for automated backfill actions where useful.

## Non-Goals

Stage 2 should not:

- Rewrite the existing event system.
- Change ball detection, video analysis, or event generation behavior.
- Add paid-package enforcement to routes.
- Add possession modeling.
- Add clip review workflows.
- Delete, rename, or migrate existing game/event/stat data.

Those belong in later platform stages.

## Proposed Backfill Rules

### Default Team

Create one default team if no team exists.

Suggested values:

- name: Liberty
- display_name: Liberty
- level: high_school
- source: system_seed

The migration must be idempotent: running it twice should not create duplicate Liberty teams.

### Roster Memberships

For every existing player row, create a roster_memberships row linking that player to the default Liberty team if no membership already exists.

The backfill should preserve current player identity and avoid guessing missing facts. Unknown jersey numbers, positions, class years, or status values should remain null unless directly available in existing player data.

### Video Assets

Create video_assets rows for existing videos or analysis inputs that can be directly verified from current tables/files.

Minimum recommended fields:

- source path or filename
- linked game_id when known
- created_at or imported_at when available
- source: backfill

Do not infer opponent, date, final score, or game metadata from filenames unless a deterministic parser and review step are added.

### Event Types

Seed canonical basketball event type rows needed by the current and near-future platform.

Initial suggested set:

- made_two
- missed_two
- made_three
- missed_three
- made_free_throw
- missed_free_throw
- rebound_offensive
- rebound_defensive
- assist
- steal
- block
- turnover
- foul_personal
- foul_shooting
- substitution
- timeout
- jump_ball
- period_start
- period_end

Each event type should include a stable key, display name, category, and active flag.

### Module Entitlements

Seed module entitlement rows for package planning without enforcing access yet.

Suggested modules:

- base_platform
- stats
- minutes_lineups
- film_room
- scouting
- playbook
- strategy
- ai_assist
- advanced_tracking

The default local installation should receive base_platform only unless Scott approves broader default access.

### Provenance

For backfilled rows, include provenance where the table supports it or where a provenance_records entry is useful.

Suggested provenance fields:

- source_type: migration
- source_name: platform_core_stage_2_backfill
- confidence: 1.0 for deterministic seeds
- reviewed_by_human: false

Do not mark inferred basketball facts as proven.

## Implementation Plan

1. Inspect current tables and existing data shape for players, games, videos, analysis_runs, and events.
2. Write idempotent helper functions for each seed/backfill group.
3. Call those helpers from init_db after Stage 1 DDL exists.
4. Add focused tests using temporary SQLite databases.
5. Run local lightweight tests on Windows.
6. Ask Hermes to run Linux full-suite verification and report Proven / Inferred / Unknown.

## Verification Requirements

Stage 2 is not complete until verified with evidence:

- Running init_db twice creates no duplicate seed rows.
- Existing player rows receive roster memberships without losing player data.
- Event types are seeded exactly once.
- Module entitlements are seeded exactly once.
- Existing tests still pass.
- New schema/backfill tests pass.

## Risks

- Current player/game/video tables may not have enough metadata for rich backfill.
- Existing data may be sparse, stale, or test-only.
- Over-inference from filenames or labels could create false project truth.

## Recommendation

Proceed with Stage 2 as a narrow, additive backfill. Keep it deterministic, reversible by inspection, and limited to platform foundation data.

Do not move to review workflows, possession modeling, or paid-package enforcement until Stage 2 is implemented and verified.
