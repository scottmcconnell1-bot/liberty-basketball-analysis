REJECTED by Claude Code, 2026-11-03 (read-only queries on film_analysis.db): (1) these two games ALREADY have Scott's tags in events as trusted rows (Adrian: 244 'shot' rows accepted/corrected, 42 makes; e.g. t=39400 shot miss accepted human_verified=1, t=41900 shot make accepted) - the box score already counts his tagged results, so importing coach calls here changes nothing true and could only overwrite human-verified tags with less information; (2) the pass line 'Liberty FG makes == 32' is wrong: the page exports only 42 shots, the other 116 are not in the file, so their tagged makes (20) stay - and forcing 32 would mean overwriting Scott's correct tags; (3) 'exactly one row per timestamp' is false: Adrian has trusted shot rows sharing a timestamp (38000, 192800, 342200, 728800, 1713800 each x2); (4) 'duplicate' -> DELETE event + cascade is a destructive write on data Scott has not gated; (5) the real target is an UNTAGGED game, which has no shot list today - the import needs program-found shots first. Back to Scott for the order.

COACH CALLS TO BOX SCORE SPEC v1 - not run

Goal
----
Coach clicks on the review page (Make / Miss / Duplicate / blank note) must land in the game's box score as verified shot results — no file hand-off, no manual copy step. This spec covers item 2 of the three-item plan: "Coach input goes straight into the box score - the coach's clicks land in the game's stats without sending a file."

Scope
-----
- Two games only: Adrian (Liberty at Adrian) and Notus A1 (Notus at Liberty), both jrhigh boys, 2026-08-09.
- Coach export file: `coach_calls.json` rows `{shot: "<film>_<t ms>", game, clock, program: "auto"|"review", coach_call: "make"|"miss"|"duplicate"|"", note}`.
- Shots not on the page = auto misses (both models said miss) — they are not editable and not in the export.
- Page is static local HTML (`Liberty_Shot_Outputs/review_queue/page_v6/review.html`) served from the repo; minors in film so it must stay local/private.
- HS Boys, HS Girls, JH Girls data untouched.
- Nothing published; page stays local.

Where coach calls land (existing table/route)
---------------------------------------------
The `events` table (schema.sql:66–92) already stores human-verified shot results:

- `human_verified` (INTEGER NOT NULL DEFAULT 0) — 1 = coach-decided
- `review_status` (TEXT NOT NULL DEFAULT 'pending') — values: 'pending', 'accepted', 'corrected', 'rejected'
- `source_type` (TEXT DEFAULT 'ai') — 'ai' or 'manual'
- `reviewed_by_user_id`, `reviewed_at`, `review_notes` — audit trail
- `shot_result` (TEXT) — 'make' | 'miss'
- `details_json` — stores `shot_kind` ("2", "3", "ft"), `team_side` ("home"/"away"), `jersey_number`, etc.

The box score (`game_boxscore.py:408–705`, `build_official_box`) reads events with:

```python
trusted = ("accepted", "corrected") if not event_counts else ("accepted", "corrected", "pending")
...
WHERE review_status IN (?,?,...)
```

So coach-verified calls must become `review_status='corrected'` (overriding AI) or `'accepted'` (confirming AI), with `human_verified=1`, `source_type='manual'`. This fits the existing flow — no new table, no schema change.

How the page sends them (pick one)
----------------------------------
Option (b): an import command/route that reads the exported `coach_calls.json`.

Why: The review page is a static local HTML file (no Flask template, no server round-trip). It writes a download via `URL.createObjectURL`. Adding a POST endpoint would require serving the page through Flask (template + CSRF + auth), which breaks the "local/private" constraint and adds complexity. A one-shot import script/route keeps the page as-is and is trivial to test.

Plan: Add a Flask route `POST /api/coach/import_calls` (under `coach_bp` or `clips_bp`) that:
1. Accepts JSON body = the exported `coach_calls.json` array.
2. Validates each row against the canonical analysis key for that game.
3. Writes/updates `events` rows with `review_status='corrected'` (or 'accepted' if coach agrees with AI), `human_verified=1`, `source_type='manual'`.
4. Returns a summary: `{updated: N, created: M, duplicates_removed: K, skipped_blank: L, errors: []}`.
5. Calls `refresh_game_stats(db, game_id)` after commit so the box score reflects changes immediately.

Alternative (a) — local Flask route the page POSTs to — is rejected because it requires the page to be served by Flask (template render + nonce/CSRF) and the page must stay a static file Scott can open from disk without the server running.

Mapping: shot id -> game_id and event row
-----------------------------------------
Shot id format: `"adrian_123456"` or `"notus_a1_789012"` (film key + timestamp_ms).

1. Film key → canonical analysis key:
   - `adrian` → `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334` (or its latest `__rerun_` copy per `canonical_event_key` in `program_mode.py:294`)
   - `notus_a1` → `jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334`

2. Timestamp_ms → event row:
   - Query `events` where `game_id = <canonical_key>` AND `timestamp_ms = <t>` AND `event_type` IN ('make','miss','made_two','missed_two','made_three','missed_three','made_free_throw','missed_free_throw','shot').
   - If exactly one row: update it.
   - If zero rows: INSERT a new event with `event_type='make'` or `'miss'`, `shot_result` from coach_call, `details_json` with `shot_kind` (to be filled by spec 3), `human_verified=1`, `review_status='corrected'`, `source_type='manual'`.
   - If multiple rows: ERROR — log and skip (should not happen; `timestamp_ms` is unique per shot in a game).

3. `coach_call` handling:
   - `"make"` → `shot_result='make'`, `review_status='corrected'` (overrides AI miss) or `'accepted'` (confirms AI make), `event_type` set per shot_kind (spec 3).
   - `"miss"` → `shot_result='miss'`, `review_status='corrected'` (overrides AI make) or `'accepted'` (confirms AI miss), `event_type` = missed_*.
   - `"duplicate"` → DELETE the event row (remove from stats entirely). Also remove any `possessions` / `clips` / `player_development_clips` referencing it (see `clips.py:300–323` delete_event cascade).
   - `""` (blank) → no change; leave AI decision as-is.

Idempotency: Re-importing the same JSON must produce the same box score. Use `shot` id as natural key; on re-import, UPDATE existing human-verified rows (match by `timestamp_ms` + `game_id` + `human_verified=1` + `source_type='manual'`), do not double-create.

Scott gates needed
------------------
- **No schema.sql edit** — uses existing `events` columns.
- **No core file edit** (`game_boxscore.py`, `program_mode.py`, `ai_analyzer.py`, `event_generator.py`, `court_memory.py`, `net_detector.py`, `manual_tag_teach.py`, `scoreboard_clock.py`) — import writes to `events`; box score reads `events` with existing filters.
- **Route addition** — new `POST /api/coach/import_calls` in `blueprints/coach.py` or `blueprints/clips.py`. Scott gate: new route file/lines only, no core logic change.
- **DB backup** — mandatory before any write on real DB. Spec requires test run on a COPY first.

The `applied_to_core` flag (not found in codebase — Claude Code to check) guards whether AI promotions (`promote_useful_events_to_ledger` in `program_mode.py:341`) overwrite human decisions. Coach-verified rows have `human_verified=1` and `review_status IN ('accepted','corrected')`; `promote_useful_events_to_ledger` only touches `review_status='pending'` (line 347–359), so human rows are **not** overwritten. No bypass needed.

Tests (no video)
----------------
1. **Mapping**: Import a JSON with 3 known `adrian_<t>` shots; verify 3 `events` rows updated with `human_verified=1`, `review_status='corrected'`, correct `shot_result`.
2. **Duplicate**: One row with `coach_call="duplicate"`; verify the event row is DELETED and no orphan `possessions`/`clips` remain.
3. **Blank**: One row with `coach_call=""`; verify the event row is unchanged (AI decision stands).
4. **Idempotent re-import**: Run import twice; second run changes 0 rows, returns `updated=0, created=0`.
5. **Other teams untouched**: After import, query `events` for HS Boys / HS Girls / JH Girls games; counts and `review_status` unchanged.
6. **Box score parity**: On a DB COPY, import the real `coach_calls (5).json` (41/42 called). Compute `build_official_box(db, game_id)` for both games; Liberty FG makes must equal coach-called makes (32 across both per Scott). No other team's stats change.

One run (acceptance)
--------------------
1. Copy `film_analysis.db` → `film_analysis_coach_test.db`.
2. Run import script/route against the copy with `coach_calls (5).json`.
3. For each game (Adrian, Notus A1), call `build_official_box(db, game_id, event_counts=False)`.
4. Assert: `box['team']['liberty']['fgm2'] + box['team']['liberty']['fgm3'] == 32` (coach makes total).
5. Assert: No other game's box score changed (spot-check 2 other games).
6. If pass → Scott decides on real DB. If fail → debug, fix, re-test.

Roles
-----
- **Claude Code (Vetter)**: Checks this spec, the import route code, and the test script. VETTED or REJECT.
- **Muse (GLM via OpenCode)**: AGREE or DISAGREE with each VETTED/PASS. DISAGREE stops the loop for Scott.
- **Cursor (OpenCode/DeepSeek = Coder)**: Builds only a plan stamped VETTED by Claude Code; does not commit before Claude checks diff and tests.

References
----------
- `make_review_queue_page.py` lines 183–188, 379–386 (export format)
- `game_boxscore.py` lines 408–705 (`build_official_box`, event filtering)
- `program_mode.py` lines 294–338 (`canonical_event_key`), 341–393 (`promote_useful_events_to_ledger`)
- `schema.sql` lines 66–92 (`events` table)
- `clips.py` lines 132–221 (`save_event` with `human_verified`, `review_status`), 300–323 (`delete_event` cascade)
- `blueprints/coach.py` (coach portal, read-only gate — import route goes here or `clips.py`)
- `verify_boxscores.py` (box score verification pattern)