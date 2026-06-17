# Base Platform Gap Audit

Date: 2026-06-17
Branch: jason-5-may-updates
Verified HEAD at audit start: af09f0a

Purpose:
- Compare the current repository to MODULAR_PRODUCT_ROADMAP.md.
- Identify what exists, what is partial, and what is missing before new client-package work begins.
- Keep the project pointed at a modular basketball operations platform with an eventual AI assistant coach.

## Executive Summary

The repository already contains a broad Flask application with schedule, game/source management, video upload/analysis, manual events, clips, basic stats, practices, player development playlists, playbook, scouting, users, messaging, and benchmark artifacts.

The main product gap is not page count. The main gap is trust architecture:

- There is no dedicated possession table.
- There is no roster-membership table tying players to teams/seasons/jersey history.
- There is no canonical clip table shared across film room, scouting, and player development.
- Several analysis tables still use TEXT game_id instead of a relational games.id foreign key.
- Manual tagging exists, but review/correction/provenance is not yet a complete coach-facing workflow.
- Feature flags exist, but paid module entitlements and package boundaries are not implemented.
- AI assistant strategy is documented, but there is no assistant query interface over reviewed data yet.

Conclusion:

Liberty should move next to a Platform Core schema/workflow audit and implementation plan. More detector post-processing is not the best next step unless new labeled data changes the evidence.

## Proven

These facts are directly verified from repository files.

### Active App Structure

Source: app.py and blueprints/

- app.py registers 11 blueprints: messaging, users, core, games, clips, stats, practice, player_dev, ai, playbook, scouting, and bulk_import.
- The app uses schema.sql as the database schema source through helpers.init_db().
- The default database is film_analysis.db unless LIBERTY_DATABASE overrides it.
- Auth middleware exists in app.py but is currently disabled by returning early.

### Existing Data Tables

Source: schema.sql

Platform and schedule:
- seasons
- scheduled_games
- games
- nfhs_matches
- sources
- players
- videos
- app_settings
- issue_reports

Analysis and event data:
- analysis_runs
- detections
- events
- stats
- player_minutes
- shot_classifications
- play_recognitions
- player_effect
- human_corrections

Film, practice, playbook, and scouting:
- player_development_clips
- practice_playlists
- practice_playlist_clips
- practices
- practice_plan_items
- playbooks
- plays
- play_steps
- scouting_reports
- scouting_personnel
- scouting_offensive_sets
- scouting_defensive_tendencies
- scouting_tendencies
- scouting_situational
- scouting_mismatches
- scouting_practice_points
- scouting_clips
- scouting_tendencies_aggregated

Users and communication:
- users
- user_sessions
- user_notification_prefs
- push_subscriptions
- notifications
- conversations
- conversation_members
- messages
- message_read_receipts

### Existing Product Surfaces

Source: blueprints/*.py and templates/

- Schedule and season management exist through core.py and stats.py routes.
- Game/source management exists through games.py routes.
- Video upload, analysis status, reruns, and video listing exist through ai.py.
- Manual event tagging exists through clips.py POST /api/save_event.
- Event list, update, and delete APIs exist through clips.py.
- Basic clip APIs exist through clips.py.
- Basic stat aggregation from events exists through stats.py and /api/stats/<game_id>.
- Film page and analysis result views exist through core.py and ai.py.
- Practice planning and practice reports exist through practice.py.
- Player development playlists exist through player_dev.py.
- Playbook creation, edit, duplicate, import, export, and API read exist through playbook.py and bulk_import.py.
- Scouting reports, personnel, tendencies, mismatches, practice points, clips, and generated reports exist through scouting.py.
- Users, roles, profiles, notification preferences, notifications, and messaging exist through users.py and messaging.py.

### Feature Flags and Settings

Source: config.py, settings_store.py, helpers.py

- Feature flags exist for seasons/schedule, games/sources, NFHS matching, manual tagging, auto stats, extended events, practices, player development, practice playlists, weekly packet, and season review.
- Runtime settings are stored in app_settings and loaded through settings_store.load_all_settings().
- require_feature() can hide feature-gated routes with 404 when disabled.
- AI defaults include ball_detector_model=models/ball_detector.pt, ball_class_id=0, and ball_confidence=0.25.

### Current Detector/Post-Processing Decision State

Source: DECISION_LOG.md, PROJECT_STATUS.md, docs/*EXPERIMENT_REPORT.md, benchmark CSVs

- Production ball detection remains models/ball_detector.pt, class 0, conf=0.25.
- Secondary classifier, feature filters, and temporal filters are not production candidates under current evidence.
- The next detector change should require new labeled evidence or a materially different benchmark plan.

## Roadmap Gap Matrix

### Base Platform

Roadmap need: teams, seasons, players, rosters, games, video assets, manual tagging, canonical event ledger, clips, review/correction workflow, user roles/permissions, basic reports, provenance records.

Current status:
- Seasons: partial. seasons table and routes exist.
- Teams: partial. scheduled_games and players have program/gender/level fields, but no teams table.
- Players: partial. players table exists.
- Rosters: missing as a first-class model. There is no roster_memberships table tying players to teams/seasons/jersey changes.
- Games: partial. scheduled_games and games exist, but some downstream tables still use TEXT game_id.
- Video assets: partial. videos and sources exist, but videos.game_id is TEXT and not a games.id foreign key.
- Manual tagging: partial. /api/save_event exists and validates that game_id exists.
- Canonical event ledger: partial. events exists, but event taxonomy, possession linkage, actor model, provenance, review state, and relational game_id are incomplete.
- Clips: partial. clips API exists and player_development_clips/scouting_clips exist, but there is no shared canonical clips table.
- Review/correction workflow: partial. events has human_verified and human_corrections exists, but there is no full review queue workflow.
- User roles/permissions: partial. users.role and role_required exist, but app-wide auth middleware is disabled and no package entitlements exist.
- Basic reports: partial. dashboard, practice reports, analysis results, scouting print views exist.
- Provenance records: partial. events has source_video, source_frame, confidence; human_corrections exists. There is no generalized provenance model across modules.

Base Platform readiness: partial, not ready as a stable client-package foundation.

### Stats Module

Roadmap need: box scores, team stats, player stats, shooting splits, possession summaries, Four Factors, efficiency metrics.

Current status:
- Player box-score style stats: partial. stats.py aggregates from events and persists rows in stats.
- Shooting splits: partial. shot_classifications exists and stats.py reads it.
- Team stats: limited. No explicit team_stats table or team aggregation layer verified.
- Possession summaries: missing as first-class data. No possessions table exists.
- Four Factors: missing.
- Efficiency metrics: partial. player_effect has ORTG/DRTG/net fields, but it is tracker/position based and depends on analysis output.

Stats Module readiness: early partial.

### Minutes and Lineups Module

Roadmap need: substitutions, player minutes, plus/minus, lineup segments, lineup stats, on/off impact.

Current status:
- Player minutes: partial. player_minutes table and film_analysis.calculate_player_minutes() exist.
- Plus/minus/on-off: partial. player_effect has plus_minus, possessions_on/off, points_for/against, ratings.
- Substitutions: missing as a first-class workflow/table.
- Lineup segments: missing.
- Lineup stats: missing.
- Reliable player identity: incomplete. Current minutes/effect logic is tracker_id based, not roster/player based.

Minutes and Lineups readiness: analysis prototype, not coach-trusted module.

### Film Room Module

Roadmap need: searchable clips, playlists, player film pages, possession film, coach notes, review queues, sharing/export workflows.

Current status:
- Video library: partial.
- Manual events and clips: partial.
- Player development playlists: partial.
- Practice playlists: partial.
- Player film pages: partial through player-development surfaces.
- Possession film: missing because possessions are not first-class.
- Coach notes: partial in practices/scouting/playlists, not unified on events/clips.
- Review queues: missing as a complete workflow.
- Sharing/export: partial in playbook export and scouting print; not verified for film clips.

Film Room readiness: partial, likely the best next product surface after event ledger cleanup.

### Scouting Module

Roadmap need: opponent tendencies, scouting reports, matchup notes, personnel notes, scout packets, game-plan priorities.

Current status:
- Scouting schema and routes are broad and relatively advanced.
- Reports, personnel, offensive sets, defensive tendencies, situational notes, mismatches, practice points, and clips exist.
- Generated scouting from event data exists in scouting.py.
- Scout packets/print views exist partially.
- Dependency risk: generated scouting quality depends on event/player/possession quality, which is not yet trusted.

Scouting readiness: strong feature skeleton, data-quality dependent.

### Playbook and Play Recognition Module

Roadmap need: play calls, offensive sets, defensive coverages, BLOB/SLOB/ATO tagging, action labels, human-reviewed play recognition.

Current status:
- Playbook CRUD/import/export exists.
- plays and play_steps store diagrams and notes.
- play_recognitions table exists.
- film_analysis recognizes some play types into play_recognitions.
- Human-reviewed play recognition workflow is not verified.
- BLOB/SLOB/ATO and coverage tagging are not first-class taxonomy tables.

Playbook and recognition readiness: playbook partial; recognition prototype.

### Strategy Module

Roadmap need: standout players, underperformers, strengths/weaknesses, practice focus suggestions, suggested adjustments, lineup impact summaries, playbook linkage.

Current status:
- Practice focus can be represented in practice_plan_items and scouting_practice_points.
- Scouting has executive_summary, tendencies, mismatches, and practice points.
- Player effect can support some impact summaries.
- No verified strategy recommendation engine exists.
- No unified standout/underperformer workflow exists.
- Playbook linkage to scouting/practice exists conceptually but not as a unified strategy layer.

Strategy Module readiness: not implemented as a module.

### AI Assist Module

Roadmap need: natural language questions, guided dropdown questions, clip lookup, report generation, stat summaries, anomaly flags, suggested review items, confidence-aware answers.

Current status:
- AI assistant vision is documented in AI_ASSISTANT_VISION.md.
- LLM provider/model settings exist.
- Practice report generation and scouting generation use AI-like report generation paths.
- No coach-facing typed question endpoint over reviewed data was verified.
- No guided dropdown question workflow was verified.
- No evidence-grounded answer contract exists in code.

AI Assist readiness: documented vision and some supporting settings, not implemented.

### Advanced Tracking Module

Roadmap need: player tracking, ball tracking, shot quality, spacing, defender proximity, automated play and coverage recognition.

Current status:
- Ball and person detection/tracking code exists.
- tracker_assigner.py and src/tracker_wrapper.py exist.
- detections table exists.
- shot_classifications, play_recognitions, player_minutes, and player_effect exist as enhanced analysis outputs.
- Current detector evidence shows ball false positives remain a production-quality risk.
- Advanced tracking outputs are not yet a trusted foundation for automated coaching decisions.

Advanced Tracking readiness: experimental/prototype.

## Cross-Cutting Risks

### Identity and Data Model

Proven:
- analysis_runs.game_id is now INTEGER, but detections, events, stats, videos, player_development_clips, player_minutes, shot_classifications, play_recognitions, player_effect, human_corrections, and some analysis helpers still use TEXT game_id.

Risk:
- The app can still mix analysis keys, video IDs, and relational game IDs in downstream workflows.

### Event Ledger

Proven:
- events exists with event_type, player, shot_result, timestamp_ms, source_video, source_frame, human_verified, and confidence.

Risk:
- It is not yet enough for a full basketball operations ledger because it lacks possessions, teams, actors, lineups, event taxonomy, review status history, and consistent provenance across modules.

### Module Packaging

Proven:
- Feature flags exist.
- User roles exist.

Risk:
- Feature flags are development/runtime toggles, not paid-package entitlements. There is no customer/account/module subscription model.

### Security and Client Readiness

Proven:
- app.py contains a hardcoded development SECRET_KEY fallback.
- config.py contains hardcoded VAPID key fallbacks.
- app.py auth middleware is disabled.

Risk:
- The app is not ready for client-facing deployment without auth/session/security hardening.

### Test Status

Proven:
- The repo has tests for API, schema, events, playbook, player development, messaging, UI audit, tracker wrapper, schedule import/export, and LLM notes.

Unknown:
- Codex did not run the full test suite during this audit because the changes in this step are documentation-only and the current goal was repository/product assessment.

## Recommended Next Three Priorities

### 1. Platform Core Data Model Plan

Goal:
- Make the repo capable of supporting base platform plus paid modules without duplicating truth.

Plan:
- Design teams and roster_memberships.
- Design possessions.
- Design canonical clips.
- Design event taxonomy and actor/team fields.
- Define relational game_id migration order for downstream TEXT game_id tables.

Deliverable:
- docs/PLATFORM_CORE_SCHEMA_PLAN.md with migration stages and acceptance criteria.

### 2. Coach Review Workflow Plan

Goal:
- Make manual and AI-generated data reviewable before it powers stats, scouting, or AI answers.

Plan:
- Define review states for events, possessions, clips, and generated facts.
- Decide how human_corrections should connect to the event ledger.
- Define review queues for uncertain AI events, missing players, questionable shots, and possession boundaries.

Deliverable:
- docs/REVIEW_WORKFLOW_PLAN.md plus issue list for implementation.

### 3. Base Film Room MVP Scope

Goal:
- Create a useful coach workflow before advanced automation is trusted.

Plan:
- Search/filter events and clips.
- Create canonical clips from events.
- Add coach notes.
- Create review queues.
- Export/share clips or reports.

Deliverable:
- docs/FILM_ROOM_MVP_SCOPE.md with module boundaries and first implementation tasks.

## Inferred

- The shortest path to client value is not more ball-detector post-processing. It is a trusted base platform with manual tagging, review, clips, and stats derived from reviewed data.
- The current repo has enough scaffolding to evolve toward the modular product, but the core data model needs cleanup before module packaging.
- Scouting and playbook features could become paid modules later, but only after the event/clip/possession foundation is stable.
- AI assistant work should wait until the data it answers from is reviewed, queryable, and provenance-aware.

## Unknown

- Whether the current local/production database contains data requiring careful migrations beyond the nearly empty database previously audited.
- Whether Scott wants the first client-facing package to be Film Room, Stats, Scouting, or a Liberty-only internal coaching assistant.
- Whether team support should start as Liberty-only or multi-team/multi-customer from the first migration.
- Whether video clip export/sharing must work locally first or be cloud-ready immediately.
- Whether production deployment is expected before the platform-core schema cleanup.

## Recommended Immediate Decision

Scott should approve Priority 1: Platform Core Data Model Plan.

Reason:
- Every paid module depends on shared truth.
- Possessions, canonical clips, roster identity, and event provenance are the foundation for stats, minutes, scouting, play recognition, strategy, and AI assistant answers.
- This keeps the project aligned with the larger basketball operations platform instead of over-investing in one detector subsystem.
