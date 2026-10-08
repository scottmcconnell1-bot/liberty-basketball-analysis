# ALPHA Next Step After OWL DONE on Issue #61

Updated: 2026-07-02
Branch: jason-5-may-updates

Purpose:

- Prevent queue stall after OWL marks Issue #61 `OWL DONE`
- Record the exact next bounded slice if GitHub issue creation/commenting is unavailable from the current ALPHA environment

## Proven

- Stage 5A through Stage 5F are implemented on `jason-5-may-updates`.
- `detections` already has `relational_game_id` in `schema.sql`, migration coverage in `helpers.py`, and schema tests in `tests/test_schema.py`.
- `videos` already has `relational_game_id` in `schema.sql`, migration coverage in `helpers.py`, and schema tests in `tests/test_schema.py`.
- `review_items` still has legacy `game_id` but no additive `relational_game_id` column in `schema.sql`.

## ALPHA Decision

The next bounded slice should target `review_items`, not `detections` or `videos`.

Reason:

- `review_items` is the smallest unresolved explicit `TEXT game_id` surface.
- It is downstream and review-scoped, so risk is lower than core ingest/video identity tables.
- `detections` and `videos` are no longer clean new slices because partial groundwork already exists and should be audited separately before any broad continuation.

## Exact Next Issue Draft

Title:

`[OWL ACTION] Stage 6A preflight: review_items relational_game_id cleanup`

Body:

```md
Objective:
Preflight the next bounded additive relational game identity slice for `review_items`.

Repository:
- `scottmcconnell1-bot/liberty-basketball-analysis`
- Branch: `jason-5-may-updates`

Required preflight:
1. Run Repository Truth Preflight from `AGENT_PROTOCOL.md`.
2. Verify `review_items` still lacks `relational_game_id` on origin.
3. Verify the active write/update/backfill paths that populate `review_items`.
4. Identify the exact files that would need bounded changes for an additive migration.
5. Confirm whether the slice can preserve legacy `game_id` while adding `relational_game_id INTEGER REFERENCES games(id)`.

Deliverable:
- Comment on this issue with Proven / Inferred / Unknown
- Include a yes/no recommendation on whether `review_items` is still the safest next bounded implementation slice
- Add `OWL DONE` only if the preflight is complete and unblocked

Out of scope:
- Implementing the migration
- Broadening scope to `detections`, `videos`, `video_assets`, `possessions`, `clips`, or `events`
```

## If GitHub Is Available

ALPHA should create the issue above immediately and let OWL pick it up by the normal poller contract.

## If GitHub Is Not Available

This file is the temporary source-of-truth handoff. ALPHA should create the GitHub issue as soon as issue-write access is restored instead of waiting for Scott to relay the next step manually.
