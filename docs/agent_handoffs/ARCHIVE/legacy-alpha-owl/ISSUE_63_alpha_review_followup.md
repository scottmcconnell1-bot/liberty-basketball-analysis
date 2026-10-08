# ALPHA Review Follow-Up for Issue #63

Updated: 2026-07-02
Branch: jason-5-may-updates
Reviewed against origin commit: 15cecb2
Implementation commit under review: 8809f94

## Purpose

Record ALPHA's review result for Issue #63 when direct GitHub comment mutation is unavailable from the current environment.

## Proven

- `origin/jason-5-may-updates` advanced to merge commit `15cecb2`.
- OWL implementation commit `8809f94` is present under that merge.
- `schema.sql` adds `relational_game_id` to `review_items`.
- `helpers.py` adds the migration entry for `review_items` and updates the Stage 3A backfill/update path to carry `events.relational_game_id`.
- `blueprints/clips.py` updates the `save_event()` review-item insert path to write `relational_game_id`.
- `tests/test_schema.py` now expects `review_items.relational_game_id`.
- Local ALPHA verification passed:
  - `python -m pytest tests/test_schema.py -q` => `47 passed`

## Review Finding

One bounded review-item write path is still inconsistent:

- In `blueprints/clips.py`, function `_sync_event_review_item()` still does:
  - `SELECT id, game_id FROM events WHERE id=?`
  - `INSERT OR IGNORE INTO review_items (entity_type, entity_id, game_id, review_status, reason) ...`
- That path does not read or write `relational_game_id`.

This means the additive `review_items.relational_game_id` migration is not yet carried through every bounded active write path identified during preflight.

## Required Narrow Correction

1. Update `_sync_event_review_item()` in `blueprints/clips.py` so it reads the related event's `relational_game_id`.
2. Update that function's `review_items` insert to write `relational_game_id` alongside legacy `game_id`.
3. Add a focused regression test proving this sync path persists `review_items.relational_game_id`.

## Non-Goals

- Do not reopen broader `review_items` migration work.
- Do not broaden into review UI.
- Do not touch unrelated tables.
- Do not rename stages or rewrite earlier history.

## ALPHA Decision

Issue #63 is real progress but is not yet accepted as fully complete.

Treat this file as the fallback ALPHA follow-up until a matching GitHub comment or bounded correction issue is posted.
