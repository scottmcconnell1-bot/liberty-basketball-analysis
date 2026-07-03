# Next OWL Action After Issue #63 Approval

Updated: 2026-07-03
Branch: jason-5-may-updates

## Purpose

Record the next bounded OWL assignment while direct GitHub issue creation/comment mutation is unavailable from the current ALPHA environment.

## Exact Next Issue Draft

Title:

`[OWL ACTION] Audit next bounded slice after review_items relational_game_id cleanup`

Body:

```md
Context:
- ALPHA has verified the bounded `review_items` relational game identity cleanup on `jason-5-may-updates`.
- Verified remote fix commit: `5412a54`.
- ALPHA-side verification passed:
  - `python -m pytest tests/test_api.py -k "sync_event_review_item_sets_relational_game_id" -q` => `1 passed`
  - `python -m pytest tests/test_api.py tests/test_schema.py -q` => `148 passed`
- The next step should not blindly continue every remaining `game_id` surface.
- Earlier audit work showed `detections` and `videos` already contain partial additive `relational_game_id` groundwork and are no longer clean first-pass slices.

Required OWL work:
1. Run Repository Truth Preflight against `origin/jason-5-may-updates`.
2. Confirm the `review_items` slice is now present on origin at or beyond `5412a54`.
3. Audit `detections` and `videos` specifically:
   - schema state
   - migration state
   - active write paths
   - active query/filter/join paths
   - tests already present vs missing
4. Determine whether the next safest bounded slice is:
   - `detections` only,
   - `videos` only, or
   - a smaller audit/correction slice before either implementation.
5. Return exactly one recommended next bounded slice with rationale.
6. Return Proven / Inferred / Unknown.

Return format:
- Comment on this issue with:
  - Proven
  - Inferred
  - Unknown
  - Exact files/functions likely affected by the recommended slice
  - Recommended next bounded slice
- Add `OWL DONE` only if the audit is complete.
- Use `OWL NEEDS` only if blocked, with the exact next action needed from ALPHA.

Non-goals:
- Do not implement code in this issue.
- Do not broaden into `video_assets`, `possessions`, `events`, review UI, or unrelated core tables.
- Do not rename prior stages.
```

## ALPHA Decision

The next correct program move is an audit/planning gate focused on `detections` and `videos`, not immediate implementation.

Reason:

- Both surfaces already contain partial relational groundwork.
- We need one clean truth pass before naming the next implementation slice.
