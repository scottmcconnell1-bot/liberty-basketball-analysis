# ALPHA Audit Result After Issue #63 Approval

Updated: 2026-07-03
Branch: jason-5-may-updates
Reviewed against origin: cbcfd20

## Role Check

ALPHA role:

- own program sequencing
- keep the work aligned to the roadmap and stage outline
- choose the next bounded slice
- prevent OWL from drifting into broad uncontrolled cleanup
- review and approve bounded implementation before the queue advances

OWL role:

- execute the bounded slice
- verify it
- report Proven / Inferred / Unknown with evidence

## Current Program Position

Proven:

- Stage 3A through Stage 4D are complete and verified.
- Stage 5A through Stage 5F are complete in code.
- The bounded `review_items` relational game identity cleanup requested after Stage 5 is complete and ALPHA-approved.
- The branch now includes:
  - commit `5412a54` fixing `_sync_event_review_item()` relational carry-through
  - commit `cbcfd20` recording ALPHA approval for Issue #63 and queuing the next audit

Inferred:

- The program is now in the post-`review_items` bounded cleanup selection step, not in broad implementation mode.
- The correct next move is to choose one narrowly scoped audit/correction slice between `detections` and `videos`.

## Audit Findings

### Detections

Proven:

- `schema.sql` defines `detections.relational_game_id`.
- `helpers.py` contains the `detections.relational_game_id` migration entry.
- `ai_analyzer.py` already writes `detections(game_id, relational_game_id, ...)`.
- `tests/test_schema.py` already contains Stage 5G schema/idempotency coverage for `detections`.
- Multiple active read/count/delete/query paths still use legacy TEXT `game_id` behavior:
  - `blueprints/ai.py` detection counts tied to `analysis_runs.analysis_key`
  - `blueprints/ai.py` deletion path `DELETE FROM detections WHERE game_id=?`
  - `blueprints/core.py` grouped detection counts by `game_id`
  - `event_generator.py` reads detections by `game_id`

Inference:

- `detections` is partially migrated: write path and schema are ahead of active query/read cleanup.
- This is the strongest candidate for the next bounded audit/correction slice.

### Videos

Proven:

- `schema.sql` defines `videos.relational_game_id`.
- `helpers.py` contains the `videos.relational_game_id` migration entry.
- `blueprints/ai.py` upload/insert paths already write `videos.relational_game_id`.
- `tests/test_schema.py` already contains Stage 5H schema/idempotency coverage for `videos`.
- Most active `videos` route behavior appears to query by `id`, filename, duplicate linkage, or upload metadata rather than by relational game joins.

Inference:

- `videos` also has partial groundwork, but its most important active write paths already appear aligned.
- Compared to `detections`, `videos` looks less urgent as the next correction slice.

## Recommended Next Bounded Slice

Choose `detections` as the next bounded audit/correction slice.

Reason:

1. The schema and migration groundwork already exist.
2. The write path already carries `relational_game_id`.
3. Multiple active query/count/delete paths still visibly rely on legacy TEXT `game_id`.
4. That makes `detections` the clearest partially migrated surface that can be tightened without broadening into core video identity or unrelated tables.

## Exact Next OWL Assignment

Title:

`[OWL ACTION] Audit/correction: detections relational_game_id query-path cleanup`

Scope:

- `detections` only
- smallest supporting query/count/delete/read paths
- preserve legacy TEXT `game_id` fallback behavior where required
- do not broaden into `videos`, `video_assets`, `events`, UI, or unrelated tables

Likely files:

- `blueprints/ai.py`
- `blueprints/core.py`
- `event_generator.py`
- `tests/test_api.py`
- `tests/test_schema.py` only if a small bounded test addition is needed

## ALPHA Decision

The program should resume with a bounded `detections` audit/correction slice next.

Do not open a `videos` implementation slice first.
