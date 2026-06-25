# Platform Core Schema Plan

Date: 2026-06-23
Branch: jason-5-may-updates
Status: Stages 1, 2, 3A, and 3B are implemented and verified. Stage 3C Possessions and Canonical Clips Foundation is implemented locally and pending Hermes/OWL Linux verification.

## Purpose

This plan defines the platform-core data model needed before Liberty adds paid client modules or coach-facing AI assistant behavior.

The goal is to make the repository capable of supporting:
- Manual-first film breakdown
- Reviewed event data
- Possessions
- Player minutes and lineups
- Searchable clips
- Stats generated from trusted events
- Scouting and strategy modules
- AI answers grounded in provenance

This plan follows docs/BASE_PLATFORM_GAP_AUDIT.md and MODULAR_PRODUCT_ROADMAP.md.

## Guiding Rules

1. Repository evidence beats agent memory.
2. No production schema migration should happen until Scott approves the migration stage.
3. Existing data must be audited before every destructive or type-changing migration.
4. The event ledger is the shared source of truth.
5. AI-generated rows must be reviewable before they become trusted operational data.
6. Paid modules may be separated by permissions later, but they must not create separate truth systems.

## Current Proven Baseline

Source: schema.sql and docs/BASE_PLATFORM_GAP_AUDIT.md.

Existing foundations:
- seasons
- scheduled_games
- games
- sources
- players
- videos
- events
- stats
- detections
- analysis_runs
- human_corrections
- player_minutes
- shot_classifications
- play_recognitions
- player_effect
- scouting tables
- playbook tables
- practice and playlist tables
- users, roles, sessions, notifications, and messaging tables

Known gaps:
- No teams table.
- No roster_memberships table.
- No possessions table.
- No canonical clips table shared by film room, scouting, and player development.
- No generalized provenance_records table.
- No module entitlements or package permissions table.
- Several downstream tables still use TEXT game_id rather than a relational games.id key.
- events is not yet rich enough to serve as the full basketball operations ledger.

## Target Platform Core

The target core should be built around these shared objects:

- teams
- players
- roster_memberships
- seasons
- scheduled_games
- games
- video_assets
- possessions
- events
- clips
- review_items
- provenance_records
- human_corrections
- module_entitlements

These objects should support every future package:
- Stats
- Minutes and Lineups
- Film Room
- Scouting
- Playbook and Play Recognition
- Strategy
- AI Assist
- Advanced Tracking

## Proposed Tables

### teams

Purpose:
- Represent customer/team identity instead of encoding team information only as text fields on players and scheduled_games.

Proposed fields:
- id INTEGER PRIMARY KEY
- organization_name TEXT
- team_name TEXT NOT NULL
- program_name TEXT
- gender TEXT
- level TEXT
- season_default_id INTEGER REFERENCES seasons(id)
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial migration approach:
- Create a default Liberty team from existing program_name/gender/level fields.
- Backfill scheduled_games.team_id and players.team_id later after review.

Acceptance criteria:
- A game, player, roster membership, clip, and report can all resolve to a team.
- Existing Liberty data can be represented without losing current program/gender/level values.

### roster_memberships

Purpose:
- Track player identity by team and season, including jersey numbers that can change over time.

Proposed fields:
- id INTEGER PRIMARY KEY
- player_id INTEGER NOT NULL REFERENCES players(id)
- team_id INTEGER NOT NULL REFERENCES teams(id)
- season_id INTEGER REFERENCES seasons(id)
- jersey_number INTEGER
- position TEXT
- grade INTEGER
- status TEXT NOT NULL DEFAULT 'active'
- start_date DATE
- end_date DATE
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial migration approach:
- Keep existing player fields.
- Add roster_memberships as the new source for season/team context.
- Backfill one membership per existing player when team and season can be determined.

Acceptance criteria:
- A player can appear on different rosters across seasons.
- Jersey number is no longer treated as permanent player identity.
- Stats and minutes can resolve to roster membership, not only free-text player names or tracker IDs.

### video_assets

Purpose:
- Replace the overloaded videos/sources split with a durable model for uploaded, downloaded, or linked video files.

Proposed fields:
- id INTEGER PRIMARY KEY
- game_id INTEGER REFERENCES games(id)
- source_id INTEGER REFERENCES sources(id)
- original_filename TEXT
- stored_filename TEXT
- file_path TEXT
- source_type TEXT
- camera_label TEXT
- angle_label TEXT
- file_size_bytes INTEGER
- duration_ms INTEGER
- frame_rate REAL
- width INTEGER
- height INTEGER
- checksum TEXT
- transcode_status TEXT
- sync_group_id TEXT
- primary_asset INTEGER NOT NULL DEFAULT 0
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial migration approach:
- Preserve videos and sources initially.
- Create video_assets as the target canonical video table.
- Backfill video_assets from videos and sources without deleting old tables.

Acceptance criteria:
- Multiple video angles can attach to one game.
- A clip can point to a specific video asset.
- Future transcoding and sync work has a stable place to store metadata.

### possessions

Purpose:
- Make possession boundaries first-class so stats, scouting, play recognition, and AI answers use consistent basketball units.

Proposed fields:
- id INTEGER PRIMARY KEY
- game_id INTEGER NOT NULL REFERENCES games(id)
- team_id INTEGER REFERENCES teams(id)
- opponent_team_id INTEGER REFERENCES teams(id)
- period INTEGER
- start_timestamp_ms INTEGER NOT NULL
- end_timestamp_ms INTEGER
- start_event_id INTEGER REFERENCES events(id)
- end_event_id INTEGER REFERENCES events(id)
- outcome TEXT
- points_for INTEGER DEFAULT 0
- source TEXT NOT NULL DEFAULT 'manual'
- review_status TEXT NOT NULL DEFAULT 'unreviewed'
- confidence REAL
- notes TEXT
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial migration approach:
- Add possessions before changing existing event flows.
- Allow manual creation/editing first.
- Later infer possessions from reviewed event sequences.

Acceptance criteria:
- Events can be grouped into possessions.
- Possession summaries can be generated without relying only on timestamps.
- Possessions can be reviewed and corrected.

### event_types

Purpose:
- Standardize the event taxonomy instead of relying only on free-form event_type text.

Proposed fields:
- id INTEGER PRIMARY KEY
- code TEXT UNIQUE NOT NULL
- label TEXT NOT NULL
- category TEXT
- counts_for_stats INTEGER NOT NULL DEFAULT 1
- is_scoring_event INTEGER NOT NULL DEFAULT 0
- is_possession_boundary INTEGER NOT NULL DEFAULT 0
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial migration approach:
- Keep events.event_type for compatibility.
- Add event_type_id to events later.
- Seed common basketball events: two_attempt, three_attempt, free_throw_attempt, make, miss, assist, rebound, turnover, steal, block, foul, substitution, timeout, period_start, period_end, note, bookmark.

Acceptance criteria:
- Stats code can map events through a controlled taxonomy.
- Unknown/manual notes can still be preserved without breaking stats.

### event_participants

Purpose:
- Support multiple actors on one event, such as shooter, assister, defender, rebounder, screener, fouler, and corrected player identity.

Proposed fields:
- id INTEGER PRIMARY KEY
- event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE
- player_id INTEGER REFERENCES players(id)
- roster_membership_id INTEGER REFERENCES roster_memberships(id)
- team_id INTEGER REFERENCES teams(id)
- role TEXT NOT NULL
- tracker_id INTEGER
- confidence REAL
- source TEXT NOT NULL DEFAULT 'manual'
- created_at TIMESTAMP

Initial migration approach:
- Keep events.player for compatibility.
- Create one event_participants row from events.player where player identity can be resolved.
- New workflows should write participants explicitly.

Acceptance criteria:
- A single event can represent a made shot with shooter, assister, and defender.
- Player identity is no longer limited to a free-text events.player value.

### clips

Purpose:
- Create a canonical clip model shared by film room, player development, scouting, review queues, and AI answers.

Proposed fields:
- id INTEGER PRIMARY KEY
- game_id INTEGER REFERENCES games(id)
- video_asset_id INTEGER REFERENCES video_assets(id)
- event_id INTEGER REFERENCES events(id)
- possession_id INTEGER REFERENCES possessions(id)
- clip_type TEXT NOT NULL DEFAULT 'event'
- title TEXT NOT NULL
- start_timestamp_ms INTEGER NOT NULL
- end_timestamp_ms INTEGER NOT NULL
- created_by_user_id INTEGER REFERENCES users(id)
- source TEXT NOT NULL DEFAULT 'manual'
- review_status TEXT NOT NULL DEFAULT 'reviewed'
- confidence REAL
- notes TEXT
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial migration approach:
- Preserve player_development_clips and scouting_clips initially.
- Create clips as the shared model.
- Add optional links from module-specific clip tables to clips.id.

Acceptance criteria:
- A clip can be reused by film room, scouting, practice, and AI answer citations.
- Clips can be searched by game, event, possession, player, and tag.

### clip_tags

Purpose:
- Make film searchable without stuffing tags into unrelated module tables.

Proposed fields:
- id INTEGER PRIMARY KEY
- clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE
- tag TEXT NOT NULL
- category TEXT
- created_by_user_id INTEGER REFERENCES users(id)
- created_at TIMESTAMP

Acceptance criteria:
- Coaches can filter film by tags such as transition, zone, BLOB, SLOB, ATO, PNR, defensive breakdown, rebounding, or player-development focus.

### review_items

Purpose:
- Provide a single review queue for manual and AI-generated facts.

Proposed fields:
- id INTEGER PRIMARY KEY
- item_type TEXT NOT NULL
- item_id INTEGER NOT NULL
- game_id INTEGER REFERENCES games(id)
- assigned_to_user_id INTEGER REFERENCES users(id)
- review_status TEXT NOT NULL DEFAULT 'open'
- priority TEXT NOT NULL DEFAULT 'normal'
- reason TEXT
- confidence REAL
- created_at TIMESTAMP
- reviewed_at TIMESTAMP
- reviewed_by_user_id INTEGER REFERENCES users(id)

Initial item_type values:
- event
- possession
- clip
- player_identity
- shot_classification
- play_recognition
- lineup_segment
- scouting_claim

Acceptance criteria:
- Uncertain AI output can be sent to review without being treated as trusted.
- Review status is visible to downstream stats, scouting, and AI assistant answers.

### provenance_records

Purpose:
- Generalize evidence tracking across detections, events, possessions, clips, stats, scouting claims, and AI answers.

Proposed fields:
- id INTEGER PRIMARY KEY
- entity_type TEXT NOT NULL
- entity_id INTEGER NOT NULL
- source_type TEXT NOT NULL
- source_id TEXT
- source_path TEXT
- source_frame INTEGER
- source_timestamp_ms INTEGER
- model_name TEXT
- model_version TEXT
- confidence REAL
- created_by_user_id INTEGER REFERENCES users(id)
- created_at TIMESTAMP
- details_json TEXT

Acceptance criteria:
- A coach-facing fact can show where it came from: manual tag, AI model, imported PBP, corrected review, or source video.
- AI assistant answers can cite reviewed evidence instead of unsupported claims.

### module_entitlements

Purpose:
- Prepare for paid packages without splitting the database into separate truth systems.

Proposed fields:
- id INTEGER PRIMARY KEY
- team_id INTEGER REFERENCES teams(id)
- module_key TEXT NOT NULL
- enabled INTEGER NOT NULL DEFAULT 1
- starts_at TIMESTAMP
- ends_at TIMESTAMP
- notes TEXT
- created_at TIMESTAMP
- updated_at TIMESTAMP

Initial module_key values:
- base
- stats
- minutes_lineups
- film_room
- scouting
- playbook_recognition
- strategy
- ai_assist
- advanced_tracking

Acceptance criteria:
- Routes and workflows can check package access without creating module-specific data silos.
- Module access can be enabled per team/customer later.

## Existing Table Changes

### games

Proposed additions:
- team_id INTEGER REFERENCES teams(id)
- opponent_team_id INTEGER REFERENCES teams(id)

Rationale:
- scheduled_games has text opponent_name and team metadata, but a client-ready system needs relational team identity.

### scheduled_games

Proposed additions:
- team_id INTEGER REFERENCES teams(id)
- opponent_team_id INTEGER REFERENCES teams(id)

Rationale:
- Schedule should connect to team identity and later support multiple customer teams.

### players

Proposed additions:
- team_id INTEGER REFERENCES teams(id)

Rationale:
- Current fields program_name, gender, level, season_id, jersey_number, position, and grade should remain for compatibility, but roster_memberships should become the stronger season/team identity model.

### events

Proposed additions:
- relational_game_id INTEGER REFERENCES games(id)
- event_type_id INTEGER REFERENCES event_types(id)
- possession_id INTEGER REFERENCES possessions(id)
- team_id INTEGER REFERENCES teams(id)
- primary_player_id INTEGER REFERENCES players(id)
- primary_roster_membership_id INTEGER REFERENCES roster_memberships(id)
- review_status TEXT NOT NULL DEFAULT 'unreviewed'
- source_type TEXT NOT NULL DEFAULT 'manual'
- created_by_user_id INTEGER REFERENCES users(id)
- updated_at TIMESTAMP

Compatibility rule:
- Keep events.game_id TEXT during migration.
- New code should move toward relational_game_id, but existing analysis-key behavior must not be broken without tests.

### videos

Proposed additions:
- relational_game_id INTEGER REFERENCES games(id)
- video_asset_id INTEGER REFERENCES video_assets(id)

Compatibility rule:
- Keep videos.game_id TEXT until all analysis-key lookups are migrated.

### stats and analysis-output tables

Tables:
- stats
- detections
- player_minutes
- shot_classifications
- play_recognitions
- player_effect
- human_corrections
- player_development_clips

Proposed direction:
- Add relational_game_id INTEGER REFERENCES games(id) where safe.
- Preserve TEXT game_id until each route/helper is migrated.
- Add provenance/review references where outputs can affect coach-facing facts.

## Migration Stages

### Stage 0: Data Audit Before Migration

Tasks:
- Count rows in every table with game_id.
- Identify distinct TEXT game_id values.
- Classify each value as relational game id, analysis key, video key, or unknown.
- Confirm production/local database path.
- Confirm backup exists.

Acceptance criteria:
- A committed audit report lists row counts and risky values.
- No migration begins until Scott approves the audit.

### Stage 1: Additive Core Tables

Tasks:
- Add teams.
- Add roster_memberships.
- Add video_assets.
- Add event_types.
- Add provenance_records.
- Add module_entitlements.

Acceptance criteria:
- Existing tests pass.
- init_db creates the new tables.
- Existing routes continue to work.
- No existing columns are removed or type-changed.

### Stage 2: Backfill Default Liberty Core

Tasks:
- Create default Liberty team.
- Backfill players.team_id where possible.
- Backfill roster_memberships for existing players.
- Backfill video_assets from videos and sources.
- Seed event_types.

Acceptance criteria:
- Backfill is idempotent.
- No duplicate default teams or event types are created.
- Existing manual tagging and stats tests still pass.

### Stage 3A: Review Workflow Foundation

Tasks:
- Add review_items.
- Add event review state fields.
- Backfill review state for existing events.
- Wire human_corrections into event correction/rejection.
- Add review APIs for event review.

Acceptance criteria:
- Coaches can list pending events.
- Coaches can accept, correct, or reject an event.
- Corrections are stored in human_corrections and provenance_records where useful.
- Rejected events are preserved with review_status='rejected' rather than silently deleted.
- Existing manual tagging and stats behavior remains usable.

See docs/REVIEW_WORKFLOW_PLAN.md.

### Stage 3C: Possessions and Canonical Clips Foundation

Tasks:
- Add possessions.
- Add clips.
- Add clip_tags.
- Add review_items.
- Add possession_id and clip links to relevant workflows.

Acceptance criteria:
- A manually tagged event can be attached to a possession.
- A canonical clip can be created from an event or possession.
- Existing player_development_clips and scouting_clips remain readable.

### Stage 4: Event Ledger Upgrade

Tasks:
- Add relational_game_id and event_type_id to events.
- Add event_participants.
- Add review_status/source_type/created_by_user_id to events.
- Update save_event() to write the new fields while preserving old behavior.

Acceptance criteria:
- Manual tagging still works.
- Stats still derive from events.
- Events can be reviewed before powering downstream modules.
- No default_game or orphan event behavior returns.

### Stage 5: Downstream game_id Cleanup

Tasks:
- Add relational_game_id to downstream tables still using TEXT game_id.
- Migrate route/helper reads in small batches.
- Keep analysis_key separated from relational game id.

Priority tables:
1. events
2. videos
3. stats
4. player_development_clips
5. player_minutes
6. shot_classifications
7. play_recognitions
8. player_effect
9. human_corrections
10. detections

Acceptance criteria:
- Tests cover each table migration.
- Analysis runs still use analysis_key for AI/video identity.
- Basketball operations data can resolve to games.id.

### Stage 6: Module Entitlement Wiring

Tasks:
- Define module_key constants.
- Add helper to check module_entitlements.
- Keep existing feature flags for development/runtime control.
- Add team/module permission checks after auth is re-enabled.

Acceptance criteria:
- Development flags and paid package entitlements are separate concepts.
- Module routes do not duplicate data into separate truth stores.

## Data Governance Rules

Every generated or imported fact should eventually answer:
- What entity does this describe?
- What source produced it?
- Was it human reviewed?
- What confidence was assigned?
- What video/frame/timestamp supports it?
- What correction history exists?

Required future entities:
- events
- possessions
- clips
- shot classifications
- play recognitions
- player minutes
- lineup segments
- scouting claims
- AI assistant answers

## Non-Goals For First Implementation

Do not implement these in the first schema migration:
- Automated play recognition improvements.
- Paid billing integration.
- Full multi-tenant customer isolation.
- Cloud video transcoding.
- AI assistant question answering.
- New detector post-processing.

Reason:
- The immediate need is shared truth, not more automation.

## Verification Requirements

Each implementation stage must include:
- Repository preflight: fetch and compare HEAD to origin/jason-5-may-updates.
- Database row-count audit before migration.
- Migration idempotency check.
- Unit/API tests for touched routes.
- Schema tests for new tables and columns.
- Manual proof that existing critical workflows still work.
- Proven / Inferred / Unknown report.

Minimum tests expected after Stage 1:
- schema table existence tests.
- init_db creates new tables.
- existing event/save/stats tests still pass.
- feature flag tests still pass.

## Proposed First Implementation Slice

If Scott approves implementation after reviewing this plan, the first code PR should be Stage 1 only:

- Add teams.
- Add roster_memberships.
- Add video_assets.
- Add event_types.
- Add provenance_records.
- Add module_entitlements.
- Add schema tests.
- Do not change existing route behavior.
- Do not migrate existing TEXT game_id columns yet.

Why:
- It is additive and low risk.
- It creates the foundation without breaking current workflows.
- It gives Hermes/OWL a clear verification target.

## Questions For Scott

1. Should the first team model be Liberty-only, or should it be multi-customer from the start?
2. Should third-party play-by-play import be part of Platform Core, or a later Stats module task?
3. Should video_assets replace videos long term, or should videos remain the upload table and video_assets become the enriched metadata layer?
4. Should clips be created manually first, or should save_event() automatically create a default clip window?

## Recommended Decision

Approve Stage 1 as the next implementation proposal, but do not implement it until:
- Hermes/OWL verifies this plan exists on origin/jason-5-may-updates.
- Scott answers the four schema direction questions above or approves the default assumptions.

Default assumptions if Scott wants Codex to proceed:
- Start Liberty-only but design tables so multi-customer can be added later.
- Treat third-party play-by-play import as a later Stats module task.
- Keep videos as the upload table and add video_assets as the enriched canonical media table.
- Start with manual clip creation; add automatic clip windows after review workflow is defined.
