ALPHA Next Gate After Issue #65
===============================

Updated: 2026-07-03 12:24 PM America/Denver

Repo truth
----------

- Stage 5A through Stage 5F are implemented on `jason-5-may-updates`.
- Post-Stage-5 `review_items` cleanup is complete through commits `15cecb2` and `5412a54`.
- Post-Stage-5 `detections` cleanup is complete at commit `8c6c83f`.
- Post-Stage-5 `videos -> analysis_runs` relational carry-forward is complete at commit `ceaf475`.
- Post-Stage-5 `videos -> video_assets` relational carry-forward is complete at commit `cb106e5`.
- GitHub issue `#65` is closed with audit + implementation evidence.

What remains in the video-linked surface
----------------------------------------

The most likely remaining bounded seam is `/api/videos` latest-run identity/status behavior:

- the route still chooses its joined `analysis_runs` row by `analysis_key = v.game_id`
- rerun/latest-run display may still be keyed to legacy text identity rather than the stronger video/source linkage now present
- `analysis_run_count` and joined-row selection may not be using the same identity rule

Recommended next bounded slice
------------------------------

Audit `/api/videos` latest-run identity/status behavior and recommend the smallest correction.

Audit goals
-----------

1. Verify how `/api/videos` chooses the representative `analysis_runs` row per video.
2. Verify whether reruns/latest status can drift from the joined row shown in the listing.
3. Confirm whether the route should prefer `source_video_id` and/or linked relational game identity over legacy `analysis_key = v.game_id`.
4. Recommend the smallest safe correction slice.

Do not broaden yet into
-----------------------

- broader `events` cleanup
- UI redesign
- `video_assets` expansion beyond the already completed carry-forward
- unrelated schema changes
