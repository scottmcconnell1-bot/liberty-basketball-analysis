# Stage 1: game_id Data Audit Report

**Auditor:** OWL (Hermes agent)
**Date:** 2026-06-14
**Database:** `/home/monk-admin/PROJECTS/liberty-basketball-analysis/film_analysis.db` (303KB, most recent)

---

## Database State

### Tables with Data
| Table | Row Count |
|-------|-----------|
| games | 1 |
| seasons | 0 |
| scheduled_games | 0 |
| events | 0 |
| stats | 0 |
| analysis_runs | 0 |
| detections | 0 |
| videos | 0 |
| player_minutes | 0 |
| shot_classifications | 0 |
| play_recognitions | 0 |
| player_effect | 0 |
| human_corrections | 0 |

### The Single Game Row
```
games.id = 1
games.source_type = 'nfhs'
games.source_key = 'gamfad8d650d0'
games.nfhs_game_id = 'gamfad8d650d0'
games.nfhs_url = 'https://www.nfhsnetwork.com/events/caldwell-high-school-caldwell-id/gamfad8d650d0'
games.scheduled_game_id = NULL
games.home_score = NULL
games.away_score = NULL
```

---

## Verified Schema: game_id Column Types

### INTEGER (relational references to games.id)
| Table | Column | Type |
|-------|--------|------|
| games | id | INTEGER PRIMARY KEY AUTOINCREMENT |
| sources | game_id | INTEGER NOT NULL REFERENCES games(id) |
| scouting_reports | game_id | INTEGER REFERENCES games(id) |

### TEXT (analysis/video/run keys)
| Table | Column | Type |
|-------|--------|------|
| events | game_id | TEXT NOT NULL |
| stats | game_id | TEXT NOT NULL |
| analysis_runs | game_id | TEXT NOT NULL |
| analysis_runs | base_game_id | TEXT |
| detections | game_id | TEXT NOT NULL |
| videos | game_id | TEXT |
| player_minutes | game_id | TEXT NOT NULL |
| shot_classifications | game_id | TEXT NOT NULL |
| play_recognitions | game_id | TEXT NOT NULL |
| player_effect | game_id | TEXT NOT NULL |
| human_corrections | game_id | TEXT NOT NULL |
| player_development_clips | game_id | TEXT |

---

## Actual game_id Values in Database

**All 12 TEXT game_id columns are empty.** Zero rows in events, stats, analysis_runs, detections, videos, player_minutes, shot_classifications, play_recognitions, player_effect, human_corrections.

The only game_id value in the entire database is `games.id = 1` (INTEGER).

There are **no** `"default_game"` values, no text keys, no orphaned references. The database is essentially clean — one game record, no downstream data.

---

## Code Behavior Analysis

### How game_id Values Get Written

1. **blueprints/clips.py:save_event()** (line 72):
   ```python
   game_id = str(data.get("game_id", "default_game"))[:128]
   ```
   - Converts to string, defaults to `"default_game"`
   - No validation that the game_id matches a real `games.id`

2. **blueprints/clips.py:refresh_game_stats()** (line 98):
   - Passes string game_id to stats aggregation
   - Stats queries filter by string game_id

3. **blueprints/ai.py** — Multiple routes:
   - `/api/analysis_status/<game_id>` — queries analysis_runs by text game_id
   - `/api/stats/<game_id>` — refreshes stats by text game_id
   - `/api/analysis_progress/<game_id>` — queries by text game_id

4. **stats.py:**
   - `aggregate_stats()` — filters events by text game_id
   - `refresh_stats()` — deletes/inserts stats by text game_id
   - `_enhance_stats_from_analysis()` — joins player_minutes by text game_id

### How Analysis Runs Get Their game_id

The AI pipeline (ai_analyzer.py, event_generator.py) writes to analysis_runs and detections. Need to check what game_id values these use — likely text keys from video filenames or NFHS IDs, not integers.

---

## Assessment

### Risk Level: LOW (for migration)

The database is nearly empty. There is **one game row** and **zero dependent rows** in any TEXT game_id column. This means:

1. **Migration risk is minimal** — no existing data would be broken by changing game_id types
2. **The `"default_game"` problem is theoretical** — no events exist under that key
3. **The AI pipeline has no stored runs** — no text keys would need migration

### However: The Design Problem Is Real

Even though the data is clean now, the code **will** create problems:

1. `save_event()` defaults to `"default_game"` — every manual tag without a game context creates orphan data
2. `stats.py` aggregates by text game_id — if someone passes `"1"` (string) vs `1` (integer from games.id), stats won't match the game
3. AI pipeline uses text keys (likely NFHS IDs like `"gamfad8d650d0"`) which won't join to `games.id`
4. The single game row has `source_key = 'gamfad8d650d0'` (text) — the AI pipeline likely references this, not `games.id = 1`

### Migration Complexity: MEDIUM

While the data is clean, the code changes span:
- `schema.sql` — change 12 columns from TEXT to INTEGER where appropriate
- `blueprints/clips.py` — stop defaulting to `"default_game"`, validate game exists
- `blueprints/ai.py` — adapt AI routes for integer game_id or add separate analysis key
- `stats.py` — ensure integer game_id throughout
- `ai_analyzer.py` / `event_generator.py` — need to understand what keys they use

---

## Recommendation

**Option C (from Codex proposal) is the right approach**, but simplified by the empty database:

1. **Add a new column `analysis_key` (TEXT)** to `analysis_runs` for AI/video identifiers (NFHS IDs, video filenames, etc.)
2. **Add a new column `game_id` (INTEGER REFERENCES games(id))** to `analysis_runs` for the optional relational link
3. **Keep existing TEXT game_id columns as-is** for now — they're empty and the fix can be done table-by-table as data accumulates
4. **Fix `save_event()`** to reject missing game_id instead of defaulting to `"default_game"`
5. **For existing TEXT columns**: migrate them to INTEGER in stages as each feature is actively developed

This is lower risk than a big-bang schema change because:
- No existing data to migrate
- The AI pipeline continues working with text keys via `analysis_key`
- Coaching features get proper integer foreign keys
- Each TEXT→INTEGER conversion is done when that feature is actively being worked on

**Scott approval needed before proceeding to Stage 2 (schema design).**
