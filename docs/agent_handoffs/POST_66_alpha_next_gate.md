ALPHA Next Gate After Event Read-Path Alignment
===============================================

Updated: 2026-07-03 2:35 PM America/Denver

Repo truth
----------

- Stage 5A through Stage 5F are implemented on `jason-5-may-updates`.
- Post-Stage-5 `review_items` cleanup is complete through commits `15cecb2` and `5412a54`.
- Post-Stage-5 `detections` cleanup is complete at commit `8c6c83f`.
- Post-Stage-5 `videos -> analysis_runs` relational carry-forward is complete at commit `ceaf475`.
- Post-Stage-5 `videos -> video_assets` relational carry-forward is complete at commit `cb106e5`.
- Post-Stage-5 `/api/videos` latest-linked-run alignment is complete at commit `6900763`.
- Post-Stage-5 compare-run count isolation is complete at commit `954fe91`.
- Post-Stage-5 event read-path relational alignment is complete at commit `d1a1b2c`.

What remains in the event identity surface
------------------------------------------

The smallest remaining seam is no longer event reads. It is event lifecycle cleanup for generated or run-scoped data:

- `event_generator.py:persist_events()` still clears prior AI-generated events with `DELETE FROM events WHERE game_id = ? AND human_verified = 0`
- `blueprints/ai.py:delete_video()` still deletes related events with `DELETE FROM events WHERE game_id = ?`
- those paths are still keyed primarily by legacy TEXT run identity even though the active read surface now understands canonical `relational_game_id`

Recommended next bounded slice
------------------------------

Audit and, if supported by repo truth, implement event lifecycle cleanup for generated events only:

1. verify whether generated event replacement should prefer `relational_game_id` with legacy fallback
2. verify whether video deletion should remove only run-scoped generated events or every event attached to the canonical game
3. choose the smallest safe correction that does not accidentally delete manual/reviewed events tied to the same canonical game
4. add focused regression coverage before broadening any write/delete behavior

Why this is the right next gate
-------------------------------

- read paths are now aligned
- the remaining visible seams are delete/replace semantics, which carry higher risk than reads
- blindly broadening delete behavior could remove manual review data, so this needs an explicit bounded audit before implementation

Do not broaden yet into
-----------------------

- a full `events` table migration
- broad video deletion policy redesign
- unrelated detector or UI work
- script-only cleanup outside active application paths
