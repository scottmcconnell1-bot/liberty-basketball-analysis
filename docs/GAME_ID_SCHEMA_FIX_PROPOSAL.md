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
2. A video/analysis key: text identifiers such as NFHS IDs, generated upload IDs, and AI run IDs.

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

Verified from OWL/Hermes Stage 1 data audit in `docs/GAME_ID_DATA_AUDIT.md`:

- Active database audited: `/home/monk-admin/PROJECTS/liberty-basketball-analysis/film_analysis.db`.
- Database has 1 row in `games`.
- `events`, `stats`, `analysis_runs`, `detections`, `videos`, `player_minutes`, `shot_classifications`, `play_recognitions`, `player_effect`, and `human_corrections` have 0 rows.
- There are no `default_game` rows.
- There are no existing text-keyed downstream rows to migrate.
- Migration risk from existing data is low.

## Inferred

- The text `game_id` values are intended to act as analysis/run/video keys in parts of the AI pipeline.
- A simple conversion of every `game_id` column to `INTEGER REFERENCES games(id)` would likely break the AI pipeline unless the analysis key concept is preserved.
- The safest fix is to separate relational game identity from analysis identity instead of overloading one column name.
- Because the database is nearly empty, the implementation can be cleaner than it would be after significant production data accumulation.

## Unknown

- The exact text key format AI analysis should use long term.
- Whether uploaded video workflows should always create or attach to a `games` row before analysis.
- Whether Scott wants standalone scouting/upload analysis to exist without a scheduled game.

## Options

### Option A: Convert all game_id columns directly to integer references

Change every relevant `game_id` column from `TEXT` to `INTEGER REFERENCES games(id)`.

Pros:
- Simple relational model.
- Strong integrity if all workflows start from `games`.

Cons:
- Risks breaking AI/video flows that use text identifiers.
- Does not preserve NFHS/upload/generated analysis keys cleanly.
- Too broad for the current uncertainty.

### Option B: Keep text `game_id` everywhere and document it as an analysis key

Change:
- No schema change.
- Documentation only.

Pros:
- Lowest immediate implementation risk.

Cons:
- Leaves relational ambiguity unresolved.
- Allows future `default_game` orphan data.
- Weakens game-linked coaching workflows.

### Option C: Separate relational game ID from analysis key

Change conceptually:
- Preserve text analysis/run keys where the AI pipeline needs them.
- Add explicit integer game references where basketball/game workflows need them.
- Stop using `default_game` for manual tagging.

Pros:
- Respects the existing AI pipeline.
- Supports real relational game workflows.
- Allows standalone analysis/scouting workflows if Scott wants them.
- Avoids pretending all text analysis keys are `games.id` values.

Cons:
- Requires careful naming and tests.
- Requires staged code updates.

## Recommendation

Recommended: simplified Option C.

Specific direction:

1. Add `analysis_key TEXT` to `analysis_runs` for AI/video identifiers such as NFHS IDs, upload-derived keys, and rerun keys.
2. Add/standardize `analysis_runs.game_id INTEGER REFERENCES games(id)` as the optional relational game link.
3. Keep existing text `game_id` columns in downstream AI tables for the moment, but treat them as analysis keys until each feature is migrated.
4. Fix `save_event()` so manual tagging rejects missing/invalid game context instead of writing `default_game`.
5. Migrate additional tables feature-by-feature with tests rather than doing a broad schema rewrite.

Rationale:
- The live database is clean enough to change direction safely.
- The code clearly has two identity concepts.
- A staged split lowers risk while moving the system toward reliable basketball/game workflows.

## Proposed Stage 2: Exact Schema Design

If Scott approves this direction, Codex should prepare an implementation branch with a narrow Stage 2 design and test plan before broad migration.

Initial target files are likely:

- `schema.sql`
- `blueprints/clips.py`
- `blueprints/ai.py`
- `helpers.py`
- `stats.py`
- `tests/test_schema.py`
- `tests/test_api.py` or a focused new test file
- `PROJECT_STATUS.md`
- `DECISION_LOG.md`
- `WORKLOG.md`

Minimum behavior goals:

- New manual events must not be saved under `default_game`.
- Manual event save must require valid game context.
- Analysis runs must distinguish relational game row from text analysis key.
- Existing AI pipeline behavior must not be broken without an approved migration path.
- Tests must prove the new identity expectations.

## Approval Request

Scott approval is requested for this design direction:

Approve simplified Option C: separate relational `games.id` from AI/video `analysis_key`, prevent new `default_game` rows, and migrate text `game_id` usage in stages as each feature is actively stabilized.

No implementation should begin until Scott approves this direction.