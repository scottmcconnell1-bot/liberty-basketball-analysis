# Review Workflow Plan

Updated: 2026-06-18
Branch: jason-5-may-updates
Status: Planning only; not implemented.

## Purpose

The review workflow is the trust layer between raw/manual/AI-generated basketball data and coach-facing facts.

Before Liberty expands possessions, play recognition, strategy reports, or AI assistant answers, coaches need a repeatable way to:

- see unreviewed events and clips
- accept correct facts
- correct wrong facts
- reject bad facts
- record who reviewed what
- preserve evidence and provenance
- keep stats and future AI answers tied to reviewed data

## Current Proven Baseline

Verified from schema.sql, blueprints/clips.py, player_development.py, and tests.

- events exists and includes human_verified and confidence.
- manual event creation exists through /api/save_event.
- event list/update/delete APIs exist in blueprints/clips.py.
- save_event validates game_id against games.id and stores the relational id as text in events.game_id.
- event updates can change player, event_type, shot_result, timestamp_ms, details_json, human_verified, and confidence.
- human_corrections exists in schema.sql.
- provenance_records exists and is populated by Stage 2 deterministic backfill.
- player_development_clips exists and has CRUD helpers and APIs.
- scouting_clips exists separately from player_development_clips.
- canonical clips and review_items tables are planned in docs/PLATFORM_CORE_SCHEMA_PLAN.md but are not implemented.

## Current Gaps

- There is no single review queue.
- human_corrections is not yet wired into event update/delete workflows.
- events has human_verified but no review_status, reviewed_by_user_id, reviewed_at, source_type, or review_notes.
- AI/manual/provenance state is split across fields rather than one clear coach-facing review model.
- Clips are module-specific; there is no canonical clip that can be reused across film room, scouting, AI answers, and review.
- Stats can be refreshed after event changes, but there is no formal "accepted event ledger" boundary.
- The AI assistant has no reliable reviewed/unreviewed distinction to use when answering coach questions.

## Guiding Rules

1. Reviewed facts outrank AI guesses.
2. Coach corrections must be stored, not just overwritten.
3. Review workflow must be fast enough for real film sessions.
4. No AI-generated fact should become trusted without a review state.
5. Manual tagging should remain usable while the review layer is added.
6. Review history should support future training data and audit trails.

## Proposed Workflow

### 1. Review Queue

Create a queue of review_items that can point to events, clips, detections, possessions, scouting claims, or AI-generated summaries.

Initial focus should be events only.

Review states:

- pending
- accepted
- corrected
- rejected
- needs_followup

Queue filters:

- game
- source_type
- event_type
- confidence range
- review_status
- player
- time range

### 2. Event Review

For each event, a coach should be able to:

- accept as-is
- edit event_type
- edit player
- edit shot_result
- edit timestamp_ms
- edit details_json
- reject event
- add note
- open or create a related clip

Every material change should create a human_corrections row and a provenance_records row.

### 3. Accepted Event Boundary

Stats, reports, scouting summaries, and AI assistant answers should prefer accepted/corrected events.

Unreviewed events may still be visible, but should be labeled as unreviewed or inferred.

### 4. Correction History

human_corrections should become the durable record of coach intervention.

Minimum correction facts:

- game_id
- event_id
- correction_type
- field_changed
- original_value
- corrected_value
- timestamp_ms
- notes
- created_at

Later fields may include reviewed_by_user_id, reviewed_at, and applied_to_model.

### 5. Evidence and Clips

Stage 3A should not require a full canonical clips migration.

However, the review UI should be designed so each reviewed event can later attach to:

- video_asset
- clip
- source_frame
- source_timestamp_ms
- provenance_records

## Proposed Schema Direction

Stage 3A should be additive.

Recommended minimum additions:

### review_items

Purpose:
- one queue for facts needing coach review.

Fields:
- id INTEGER PRIMARY KEY
- entity_type TEXT NOT NULL
- entity_id INTEGER NOT NULL
- game_id TEXT
- review_status TEXT NOT NULL DEFAULT 'pending'
- priority TEXT NOT NULL DEFAULT 'normal'
- reason TEXT
- assigned_to_user_id INTEGER REFERENCES users(id)
- reviewed_by_user_id INTEGER REFERENCES users(id)
- reviewed_at TIMESTAMP
- notes TEXT
- created_at TIMESTAMP
- updated_at TIMESTAMP

### events review columns

Add only if needed for efficient filtering:

- review_status TEXT NOT NULL DEFAULT 'pending'
- source_type TEXT
- reviewed_by_user_id INTEGER REFERENCES users(id)
- reviewed_at TIMESTAMP
- review_notes TEXT

Alternative:
- keep events unchanged and store review state only in review_items.

Recommendation:
- add review columns to events for direct filtering and keep review_items as the queue/history layer.

### human_corrections extensions

Potential later additions:

- reviewed_by_user_id INTEGER REFERENCES users(id)
- reviewed_at TIMESTAMP
- review_item_id INTEGER REFERENCES review_items(id)

Do not add these until implementation planning confirms route needs.

## Stage 3A Implementation Slice

Recommended first code slice after Scott approval:

1. Add review_items table.
2. Add events.review_status, events.source_type, events.reviewed_by_user_id, events.reviewed_at, and events.review_notes.
3. Backfill existing events:
   - human_verified = 1 -> accepted
   - human_verified = 0 -> pending
4. Create review_items for existing pending events.
5. Add API endpoints:
   - GET /api/review/events
   - POST /api/review/events/<event_id>/accept
   - POST /api/review/events/<event_id>/correct
   - POST /api/review/events/<event_id>/reject
6. Record human_corrections on correction/rejection.
7. Add tests for idempotent migration/backfill and review API behavior.

## Non-Goals

Stage 3A should not:

- implement possession modeling
- implement canonical clips
- rewrite the event ledger
- change ball detection behavior
- build the full coach UI
- enforce paid packages
- train models from corrections

## Verification Requirements

Stage 3A is not complete until:

- running init_db twice does not duplicate review_items
- existing events receive deterministic review_status values
- pending AI/inferred events can be listed
- accepted events are marked accepted and human_verified
- corrected events update the event and create human_corrections
- rejected events are not deleted by default; they are marked rejected
- existing event APIs still pass
- full local suite passes
- Hermes/OWL Linux verification passes

## Open Questions

1. Should rejected events remain in events with review_status='rejected', or move to a separate archive later?
2. Should manual events default to accepted or pending?
3. Should AI-generated events always default to pending regardless of confidence?
4. Should review actions require logged-in users now, or allow null reviewed_by_user_id until auth is enforced?
5. Should review start with event APIs only, or include a small coach-facing review page in the first implementation slice?

## Recommendation

Proceed with Stage 3A as a review-workflow foundation before possession modeling.

Default assumptions if Scott approves implementation:

- rejected events stay in events with review_status='rejected'
- manual events default to accepted
- AI-generated events default to pending
- reviewed_by_user_id may be null until auth is enforced
- first implementation includes APIs and tests, then a UI planning pass
