# Review UI Plan

Updated: 2026-06-25
Branch: jason-5-may-updates
Status: Implemented by Codex on Windows; pending Hermes/OWL Linux verification.

## Purpose

The review UI is the coach-facing trust layer for basketball analysis.

Stage 3A created the review data model and JSON APIs. Stage 3B should make those APIs usable by coaches so pending AI/manual/inferred events can be accepted, corrected, or rejected before they feed future possessions, stats, clips, scouting, player development, or AI assistant answers.

## Current Proven Baseline

Verified from repository files and GitHub issue #18:

- `review_items` exists.
- `events.review_status`, `events.source_type`, `events.reviewed_by_user_id`, `events.reviewed_at`, and `events.review_notes` exist.
- `GET /api/review/events` lists reviewable events.
- `POST /api/review/events/<event_id>/accept` accepts an event.
- `POST /api/review/events/<event_id>/correct` corrects an event and writes `human_corrections`.
- `POST /api/review/events/<event_id>/reject` marks an event rejected without deleting it and writes `human_corrections`.
- Review actions write `provenance_records`.
- Hermes/OWL verified Stage 3A on Linux: 195 passed, 1 skipped.
- Existing UI is Flask/Jinja with `base.html`, route-level templates, and small page-specific JavaScript.

Verified by Codex on Windows after Stage 3B implementation:

- `GET /review` renders `templates/review_events.html`.
- The route is gated by `ENABLE_MANUAL_TAG_MVP`.
- `base.html` exposes `Review Queue` under Film & Stats when manual tagging is enabled.
- The page calls the existing Stage 3A review APIs for list, accept, correct, and reject actions.
- Focused Review UI/API tests reported 7 passed.
- Full local app suite reported 198 passed, 1 skipped.

## Current Gaps

- Coaches cannot see a unified pending review queue.
- Coaches cannot accept, correct, or reject events from a page.
- There is no count or workflow signal showing how much untrusted event data remains.
- Existing review APIs are available only to API callers.
- No UI exists for viewing review status, confidence, source type, or review notes.

## Stage 3B Implementation Slice

Implemented first code slice:

1. Add a page route:
   - `GET /review`
   - Feature gate: `ENABLE_MANUAL_TAG_MVP`
   - Template: `templates/review_events.html`

2. Add navigation:
   - Add `Review Queue` under the Film & Stats navigation group.
   - Keep it available only when manual tagging/review features are enabled.

3. Build the review queue page:
   - Header with pending count and selected filter summary.
   - Filters for review status, game_id, event_type, source_type, player, and confidence range.
   - Event list sorted by game and timestamp, matching the API order.
   - Detail panel for the selected event.
   - Notes field shared by accept/correct/reject actions.

4. Add coach actions:
   - Accept selected event.
   - Reject selected event.
   - Correct selected event fields:
     - player
     - event_type
     - shot_result
     - timestamp_ms
     - confidence
     - details_json

5. Add user feedback:
   - Loading state.
   - Empty queue state.
   - Success/error messages.
   - Refresh after each action.

6. Add tests:
   - `/review` renders.
   - Review page contains required controls.
   - Navigation exposes Review Queue when the feature is enabled.
   - Existing review API tests continue to pass.

## Non-Goals

Stage 3B should not:

- implement possession modeling
- implement canonical clips
- rewrite the event ledger
- add paid-package enforcement
- train or tune models
- change ball detection behavior
- change event review semantics from Stage 3A
- require video playback or frame thumbnails

## Design Notes

The first version should be a dense operations page, not a marketing page or a new app shell.

Recommended layout:

- Top filter band.
- Left event queue/table.
- Right event detail and action panel.
- Mobile layout stacks filters, selected event, then event list.

This keeps the workflow fast for repeated coach review while leaving room for later video/frame evidence.

## Verification Requirements

Stage 3B is not complete until:

- route-level tests pass
- existing Stage 3A review API tests pass
- full local suite passes
- page renders without missing template/static errors
- review actions still write `human_corrections` and `provenance_records`
- reject still preserves events rather than deleting them
- no possession/canonical clip/paid-package/model/ball-detection behavior is added
- Hermes/OWL Linux verification passes after Codex implementation

Current verification status:

- Codex local Windows verification is complete.
- Hermes/OWL Linux verification is pending.

## Open Questions

1. Should the first UI be all-events review, or pending-only by default with a status filter?
2. Should corrected events remain visible in the same queue after correction, or disappear from the default pending view?
3. Should event review eventually open video at timestamp, or should that wait for canonical clips?
4. Should low-confidence events receive higher queue priority?

## Recommendation

Proceed with Stage 3B as a lightweight coach review queue page backed by the existing Stage 3A APIs.

Default assumptions if Scott approves implementation:

- Default view: pending events only.
- Corrected/accepted/rejected events disappear from the default queue after action but remain visible through the status filter.
- Video evidence is deferred until a later canonical clips or film-linking stage.
- No new schema is needed for Stage 3B.
