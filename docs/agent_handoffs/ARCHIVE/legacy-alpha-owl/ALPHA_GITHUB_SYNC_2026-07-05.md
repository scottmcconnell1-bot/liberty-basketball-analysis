# ALPHA GitHub Sync - 2026-07-05

Updated: 2026-07-05 America/Denver
Branch: `jason-5-may-updates`
Audience: any new ALPHA/OWL/Hermes/Codex-style agent reading GitHub without chat context

## Purpose

This file is the current GitHub-visible handoff snapshot for the Liberty Basketball Analysis project.

If you are a new agent, read this file first, then read:

1. `docs/STAGE_INDEX.md`
2. `PROJECT_STATUS.md`
3. `ROADMAP.md`
4. latest files in `docs/agent_handoffs/`

## Repo Truth

### Proven

- Active working branch is `jason-5-may-updates`.
- Stage 5A through Stage 5F are implemented on this branch.
- Post-Stage-5 cleanup slices already completed on this branch include:
  - `review_items` relational identity cleanup
  - `detections` relational query-path cleanup
  - `videos -> analysis_runs` relational carry-forward
  - `videos -> video_assets` relational carry-forward
  - `/api/videos` latest-linked-run alignment
  - compare-run count isolation
  - event read-path relational alignment
  - generated-event lifecycle cleanup in `blueprints/ai.py` and `event_generator.py`
- Recent product-facing commits on this branch are:
  - `8a5a067` `feat: add human_verified=0 guard to delete_video events delete to prevent deletion of verified/manual events`
  - `163b70d` `Finish bounded persist_events() relational cleanup in event_generator.py`
  - `8390381` `test(platform): replace brittle clips coverage and resolve ai conflicts`
  - `85b2120` `feat(status): add product progress checklist`
  - `4956601` `feat(status): add product verification links and canonical counts`
  - `e5bb541` `feat(preview): add coach-facing final product preview page`
- The repo now contains a coach-facing preview page at route `/preview`.
- The repo now contains a status/proof page at route `/status`.
- `PROJECT_STATUS.md`, `ROADMAP.md`, and `docs/STAGE_INDEX.md` were refreshed on 2026-07-05 to match branch truth.

### Verified tests from recent ALPHA work

- `python -m pytest tests/test_api.py -q` -> `114 passed`
- `python -m pytest tests/test_event_pipeline.py -q` -> `9 passed`

## What Landed Recently

### 1. Generated-event lifecycle safety is complete

- `blueprints/ai.py:delete_video()` now preserves verified/manual events by guarding deletes with `human_verified = 0`.
- `event_generator.py:persist_events()` now prefers `relational_game_id` for generated-event replacement while preserving legacy fallback when needed.
- Focused regression coverage was added for the event pipeline and clips/event maintenance paths.

### 2. Product proof/status surface improved

- `/status` now exposes:
  - a product progress checklist
  - direct verification links into major product surfaces
  - canonical per-game counts that prefer relational identity over stale legacy text where the bounded slices are complete

### 3. Final-product preview surface added

- `/preview` is not an engineering status page.
- `/preview` is a coach-facing product preview page intended to show the finished platform shape:
  - Team Operations
  - Film Room
  - Analysis & Trust
  - Player Development
  - Scouting & Playbook
- `/preview` links directly into the real modules already present in the application shell.

## What A New Agent Should Understand

### Do not assume

- Do not assume the next task is still the old event lifecycle cleanup. That work is already complete.
- Do not assume the status page is the only proof surface. There is now a separate `/preview` page.
- Do not assume stale issue comments or stale handoff docs are still current. Use the latest branch docs first.

### Current project posture

- The branch is now in a product-proof / next-gate clarification state, not a blind schema-migration state.
- The immediate engineering challenge is no longer the earlier Stage 5 cleanup chain.
- The branch needs bounded, deliberate next slices that improve either:
  - product proof / visible trust in the real app, or
  - Stage 6 planning/wiring around module entitlements

## Recommended Next Gate

### Recommended

Choose a bounded post-cleanup next gate, with this order of preference:

1. Stage 6A planning/helper slice for module entitlement wiring
2. product-proof slice for another real coach-facing surface
3. only then broader expansion work

### Strong leading candidate

`Stage 6A: module entitlement helper/audit wiring`

Bounded definition:

- define module-key constants clearly
- add a helper that can read `module_entitlements`
- keep development feature flags separate from entitlement logic
- do not enforce auth globally yet
- do not add billing
- do not broaden into multi-tenant packaging

Why this is the leading candidate:

- it matches the locked stage plan in `docs/PLATFORM_CORE_SCHEMA_PLAN.md`
- it is narrower and safer than inventing a larger new feature
- it advances the platform architecture without destabilizing coach workflows

## Product Routes Worth Checking

- `/preview`
- `/status`
- `/schedule`
- `/film`
- `/videos`
- `/review`
- `/practices`
- `/scouting`
- `/playbook`
- `/messages`

## Agent Operating Notes

### If you are ALPHA

- keep repo docs as the source of truth
- prefer bounded slices
- update `docs/STAGE_INDEX.md`, `PROJECT_STATUS.md`, and `ROADMAP.md` when the branch truth changes materially

### If you are OWL

- your queue is the newest open GitHub issue labeled `OWL ACTION`
- if the issue also has `OWL NEEDS`, keep polling that same issue for a newer `[OWL FOLLOWUP]`
- do not go idle while an actionable open queue item exists
- when GitHub comments are unavailable, use `docs/agent_handoffs/` fallback files

## Short Summary

The branch is materially ahead of some older handoff notes. Stage 5 cleanup and event lifecycle cleanup are already done. The repo now has both a proof/status surface (`/status`) and a coach-facing final-product preview (`/preview`). The next smart move is a bounded post-cleanup gate, with Stage 6A module entitlement helper/audit wiring as the best current candidate.
