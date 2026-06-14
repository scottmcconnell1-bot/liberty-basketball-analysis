# Game ID Schema Fix Proposal

Updated: 2026-06-14
Branch: jason-5-may-updates
Status: Proposal only. No schema changes have been made.

## Purpose

This document proposes how to fix the project-wide `game_id` ambiguity before changing `schema.sql`.

Scott approval is required before implementation because the recommended fix changes the database schema.

## Summary

The project currently uses `game_id` for two different concepts:

1. A relational game record: `games.id`, an integer primary key.
2. A video/analysis key: text identifiers such as generated upload IDs and AI run IDs.

Because both concepts are named `game_id`, downstream features such as stats, clips, scouting, and AI analysis can appear connected while actually using incompatible identifiers.

## Proven

Verified from `schema.sql` on `jason-5-may-updates`:

- `games.id` is `INTEGER PRIMARY KEY AUTOINCREMENT`.
- `sources.game_id` is `INTEGER NOT NULL REFERENCES games(id)`.
- `scouting_reports.game_id` is `INTEGER REFERENCES games(id)`.
- `analysis_runs.game_id` is `TEXT NOT NULL`.
- `analysis_runs.base_game_id` is `TEXT`.
- `detections.game_id` is `TEXT NOT NULL`.
- `events.game_id` is `TEXT NOT NULL`.
- `stats.game_id` is `TEXT NOT NULL`.
- `videos.game_id` is `TEXT`.
- `player_development_clips.game_id` is `TEXT`.
- `player_minutes.game_id` is `TEXT NOT NULL`.
- `shot_classifications.game_id` is `TEXT NOT NULL`.
- `play_recognitions.game_id` is `TEXT NOT NULL`.
- `player_effect.game_id` is `TEXT NOT NULL`.
- `human_corrections.game_id` is `TEXT NOT NULL`.

Verified from `blueprints/clips.py`:

- `save_event()` converts incoming `game_id` to string.
- If no `game_id` is provided, `save_event()` defaults to `"default_game"`.
- `refresh_game_stats(db, game_id)` is called with that same value.

Verified from `stats.py`:

- `aggregate_stats()`, `refresh_stats()`, and enhanced stats queries filter by `game_id` across `events`, `stats`, `detections`, `player_minutes`, `shot_classifications`, `play_recognitions`, and `player_effect`.

## Inferred

- The text `game_id` values are acting as analysis/run/video keys, not always as references to `games.id`.
- A simple conversion of every `game_id` column to `INTEGER REFERENCES games(id)` would likely break the AI pipeline unless the analysis key concept is preserved.
- The safest fix is to separate relational game identity from analysis identity instead of overloading one column name.

## Unknown

- Whether existing production/local databases contain text game IDs that do not map to rows in `games`.
- Whether any uploaded videos have corresponding `games` rows.
- Whether any manual tags are currently saved under `default_game`.
- Whether Scott wants AI analysis runs to be attached to scheduled/official games immediately or remain usable for standalone scouting/upload workflows.

## Options

### Option A: Convert `events.game_id` and `stats.game_id` directly to integer references

Change:
- `events.game_id TEXT` to `events.game_id INTEGER REFERENCES games(id)`
- `stats.game_id TEXT` to `stats.game_id INTEGER REFERENCES games(id)`
- Update `save_event()` to require an integer game ID.

Pros:
- Simple relational model for manual events and box-score stats.
- Prevents new `default_game` data.

Cons:
- Does not solve AI pipeline tables that still use text `game_id`.
- May break existing text-keyed event/stat data.
- Does not handle standalone video analysis well unless a `games` row always exists first.

### Option B: Keep text `game_id` everywhere and document it as an analysis key

Change:
- No schema change.
- Rename documentation expectations only.

Pros:
- Lowest immediate implementation risk.
- Preserves current AI pipeline behavior.

Cons:
- Leaves relational ambiguity unresolved.
- Weakens data integrity.
- Makes game-linked coaching workflows harder to trust.

### Option C: Separate relational game ID from analysis key

Change conceptually:
- Preserve text analysis/run keys where the AI pipeline needs them.
- Add explicit integer game references where basketball/game workflows need them.
- Stop using `default_game` for manual tagging.

Possible schema direction:
- Keep `analysis_runs.game_id`, `detections.game_id`, and related AI tables as text analysis keys for now.
- Add or use explicit integer `game_db_id` / `source_game_id` columns where rows should link to `games(id)`.
- For manual events and stats, introduce a clear relational link to `games(id)` while preserving an optional text analysis key if needed.
- Rename future code variables so `analysis_game_id` and `game_id` are not confused.

Pros:
- Respects the existing AI pipeline.
- Supports real relational game workflows.
- Allows standalone analysis/scouting workflows.
- Avoids pretending all text analysis keys are game row IDs.

Cons:
- Requires a careful migration plan.
- Requires code updates across events, stats, videos, analysis, and UI entry points.
- Requires tests to prevent future drift.

## Recommendation

Recommended: Option C, implemented in stages.

Rationale:
- The evidence shows the project has both official game records and generated analysis/video identifiers.
- Those are different concepts and should not share one ambiguous name.
- A direct TEXT-to-INTEGER conversion would be too risky without first mapping existing data and AI workflows.

## Proposed Implementation Plan

### Stage 1: Data audit, no schema change

- Inspect the active SQLite database on the Linux machine.
- Count distinct values in all `game_id` columns.
- Identify values that match `games.id` and values that are generated text keys.
- Count events saved under `default_game`.
- Produce a migration risk report.

OWL/Hermes is the best owner for this stage because it needs local machine/database access.

### Stage 2: Schema design for Scott approval

Based on Stage 1 results, choose exact column names and migration path.

Likely direction:
- Use integer game references for coaching/game workflows.
- Use a separate text analysis key for AI pipeline workflows.
- Avoid changing feature behavior until tests are added.

### Stage 3: Code changes on a feature branch

Potential files:
- `schema.sql`
- `blueprints/clips.py`
- `blueprints/ai.py`
- `stats.py`
- `film_analysis.py`
- `event_generator.py`
- `ai_analyzer.py`
- templates/static film-tool integration as needed
- tests covering schema, events, stats, upload/analysis linkage

### Stage 4: Verification

Minimum verification:
- Schema tests assert expected column types and foreign-key intent.
- Event save rejects missing game context instead of writing `default_game`.
- Manual tag events link to the correct game record.
- Stats refresh uses the intended game identity consistently.
- Existing AI analysis flow still runs with text analysis keys.
- Migration script/report handles existing database rows.

## Approval Request

Scott approval is requested for the following direction, not for code yet:

Approve Option C as the target design principle: separate relational game identity from analysis/video identity, preserve AI text keys where needed, and stop using ambiguous `game_id` values for both concepts.

If approved, the next action should be an `[OWL ACTION]` issue asking OWL/Hermes to inspect the live/local SQLite database and report actual `game_id` values before Codex changes `schema.sql`.