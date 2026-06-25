# Liberty Stage Index

Updated: 2026-06-25
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
| Stage 4 | Event ledger upgrade | In progress through lettered slices | relational_game_id, event_type_id, event_participants, richer event writes |
| Stage 4A | Event participants foundation | Implemented and Hermes/OWL verified | event_participants, events relational links, primary player/team links, legacy player-name backfill |
| Stage 4B | Manual event write upgrade | Implemented and Hermes/OWL verified | save_event wires relational_game_id, event_type_id, team_id, primary_player_id, event_participants |
| Stage 5 | Downstream game_id cleanup | Not started | downstream relational_game_id migration while preserving analysis_key |
| Stage 6 | Module entitlement wiring | Not started | module_key helpers and team/module permission checks |

## Rules

- Stage 3B always means Review UI.
- Stage 3C always means Possessions and Canonical Clips Foundation.
- Stage 4A always means Event Participants Foundation.
- Do not use Stage 3B for possessions or clips in future reports.
- Do not rewrite past issues, commits, or reports to rename completed stages.
- Use Proven / Inferred / Unknown when reporting stage status.
- Update this file when a stage moves from local implementation to Hermes/OWL verified.

## Current Next Gate

Stage 4A Event Participants Foundation is implemented locally and needs Hermes/OWL Linux verification after Codex push.
