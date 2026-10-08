ALPHA Next Gate After Issue #64
===============================

Updated: 2026-07-03 11:55 AM America/Denver

Repo truth
----------

- Stage 5A through Stage 5F are implemented on `jason-5-may-updates`.
- The post-Stage-5 `review_items` cleanup is complete through commits `15cecb2` and `5412a54`.
- The bounded `detections` relational query-path cleanup is complete at commit `8c6c83f`.
- GitHub issue `#64` has been closed by ALPHA with verification evidence.

What was just completed
-----------------------

- `blueprints/ai.py` now counts/deletes detections through `analysis_runs.game_id` / `relational_game_id` with legacy fallback.
- `blueprints/core.py` status counts now prefer canonical detections identity.
- `event_generator.py` reads detections through `relational_game_id` when provided, with legacy fallback.
- `film_analysis.py` detection queries now use a shared relational-or-legacy filter helper.
- `tests/test_api.py` adds focused regression coverage for relational detections counting.

Verification
------------

- `python -m pytest tests/test_api.py -q` -> 47 passed
- `python -m pytest tests/test_schema.py -q` -> 47 passed
- `python -m py_compile blueprints/ai.py blueprints/core.py event_generator.py film_analysis.py tests/test_api.py` -> passed

Recommended next bounded slice
------------------------------

Choose `videos`-linked relational game identity as the next audit/correction candidate.

Why this is next
----------------

1. `detections` was the clearest partially migrated surface; that gap is now closed.
2. `videos` already has additive groundwork in schema and migrations, but active route/query behavior still needs a fresh bounded audit before implementation.
3. This keeps the program moving in narrow slices instead of broadening into `video_assets`, `events`, or other core identity tables.

Bounded audit prompt
--------------------

Audit only `videos`-linked relational game identity behavior:

- verify active write/update/query paths
- identify whether any remaining route logic still relies on legacy-only text identity where relational identity should now be preferred
- recommend the smallest safe correction slice

Do not broaden yet into:

- `video_assets`
- `events`
- `sources`
- `teams`
- `players`
- unrelated schema expansion
