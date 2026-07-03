# Liberty Stage Index

Updated: 2026-07-02
Branch: jason-5-may-updates
Status: Source-of-truth stage numbering for Codex, Hermes/OWL/Rex, and future agents.

## Purpose

This file locks the project stage names so completed work is not renamed and future work does not reuse stage numbers.

Repository history, GitHub issues, and verification reports already reference these stages. Do not renumber completed stages. If a new slice is needed between existing stages, add a lettered stage such as `3C`, `3D`, or `4A` rather than rewriting history.

## Locked Stage Numbering

| Stage | Name | Status | Evidence |
| --- | --- | --- | --- |
| Stage 0 | Data audit before migration | Completed for game_id/analysis_key risk; broader data governance remains ongoing | docs/GAME_ID_DATA_AUDIT.md and source-of-truth docs |
| Stage 1 | Additive core tables | Implemented and Hermes/OWL verified | teams, roster_memberships, video_assets, event_types, provenance_records, module_entitlements |
| Stage 2 | Default Liberty core backfill | Implemented and Hermes/OWL verified | default Liberty team, roster memberships, video_assets, event_types, module_entitlements, provenance |
| Stage 3A | Review workflow foundation | Implemented and Hermes/OWL verified | review_items, event review state, review APIs, human_corrections/provenance wiring |
| Stage 3B | Review UI | Implemented and Hermes/OWL verified | /review page, Review Queue nav, filters, detail panel, accept/correct/reject UI |
| Stage 3C | Possessions and canonical clips foundation | Implemented and Hermes/OWL verified | possessions, clips, clip_tags, events.possession_id, player_development_clips.canonical_clip_id |
| Stage 4 | Event ledger upgrade | Implemented through lettered slices (4A, 4B, 4C, 4D) | relational_game_id, event_type_id, event_participants, relational stats derivation, player_minutes foundation |
| Stage 4A | Event participants foundation | Implemented and Hermes/OWL verified | event_participants, events relational links, primary player/team links, legacy player-name backfill |
| Stage 4B | Manual event write upgrade | Implemented and Hermes/OWL verified | save_event wires relational_game_id, event_type_id, team_id, primary_player_id, event_participants |
| Stage 4C | Relational stats derivation | Implemented and Hermes/OWL verified | stats.aggregate_stats reads event_types taxonomy via event_type_id; counts_for_stats + review_status filtering; legacy event_type alias seeds added |
| Stage 4D | Player minutes foundation | Implemented and Hermes/OWL verified | player_minutes table schema-gated + migration; player_minutes.py backfill from detections.tracker_id (idempotent INSERT OR REPLACE); tests verify computation, idempotency, per-game/per-player query, stats.py integration |
| Stage 5 | Downstream game_id cleanup | In progress through lettered slices | additive downstream `relational_game_id` migration while preserving legacy TEXT analysis-key behavior |
| Stage 5A | Relational game_id cleanup for stats and player_minutes | Implemented and committed | additive `relational_game_id` columns for `stats` and `player_minutes`; bounded query/write cleanup while preserving legacy TEXT `game_id` behavior |
| Stage 5B | Relational game_id cleanup for player_development_clips | Implemented and committed | additive `relational_game_id` for `player_development_clips`; bounded CRUD/query support while preserving legacy TEXT `game_id` behavior |
| Stage 5C | Relational game_id cleanup for shot_classifications | Implemented and committed | additive `relational_game_id` for `shot_classifications`; bounded film/stats query and write cleanup |
| Stage 5D | Relational game_id cleanup for play_recognitions | Implemented and committed | additive `relational_game_id` for `play_recognitions`; bounded play recognition write/query cleanup |
| Stage 5E | Relational game_id cleanup for player_effect | Implemented and committed | additive `relational_game_id` for `player_effect`; bounded effect write/query cleanup |
| Stage 5F | Relational game_id cleanup for human_corrections | Implemented and committed | additive `relational_game_id` for `human_corrections`; review correction writes preserve relational game identity |
| Stage 6 | Module entitlement wiring | Not started | module_key helpers and team/module permission checks |

## Rules

- Stage 3B always means Review UI.
- Stage 3C always means Possessions and Canonical Clips Foundation.
- Stage 4A always means Event Participants Foundation.
- Stage 5A always means relational game_id cleanup for `stats` and `player_minutes`.
- Stage 5B always means relational game_id cleanup for `player_development_clips`.
- Stage 5C always means relational game_id cleanup for `shot_classifications`.
- Stage 5D always means relational game_id cleanup for `play_recognitions`.
- Stage 5E always means relational game_id cleanup for `player_effect`.
- Stage 5F always means relational game_id cleanup for `human_corrections`.
- Do not use Stage 3B for possessions or clips in future reports.
- Do not rewrite past issues, commits, or reports to rename completed stages.
- Use Proven / Inferred / Unknown when reporting stage status.
- Update this file when a stage moves from local implementation to Hermes/OWL verified.

## Current Next Gate

Stage 5F is implemented in code at commit `a923ee8`. The post-Stage-5 `review_items` cleanup is implemented through commits `15cecb2` and `5412a54`, and the bounded `detections` relational query-path cleanup is implemented at commit `8c6c83f`. The next gate should be a fresh bounded audit/correction slice for `videos`-linked relational game identity rather than continuing blind across every remaining `TEXT game_id` table.
