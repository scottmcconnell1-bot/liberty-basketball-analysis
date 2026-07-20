# Active Task

Updated: 2026-07-20
Branch: `cursor/film-tool-reports-fix-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | film-tool-empty-open-wilder |
| **status** | `completed` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Symptom:** Videos → Film Tool for Wilder (`nfhs_gam30b09cbb4f.mp4`) opened empty: black video chrome at 0:00, OUR TEAM 0 vs OPPONENT 0, 0 tagged / 0 AI — despite `film_tool_games` row `game-1784304093435` with **71** tags.
- **Root cause (code):** `getGameMeta()` always wrote `analysisGameId` from `FILM_TOOL_GAME_ID`. Opening bare `/film` (empty game id) then autosaving **wiped** `film_tool_games.analysis_key` / `analysisGameId` to NULL/"". Videos deep-link uses `?game_id=<latest analysis_key>`, so `findSavedGameForAnalysisId` and `?analysis_key=` API filter returned **0 games**.
- **Root cause (data at fix time):** Wilder row had `analysis_key=NULL`, `analysisGameId=""`, still 71 tags; video 8 file present (~4.9GB).
- **Fix:** Preserve linked analysis key on save (JS + server); inject `FILM_TOOL_CLIENT_GAME_ID` / `FILM_TOOL_VIDEO_OPPONENT` from `/film/<file>`; load saved game on tagger deep-link (not only Reports); match rerun-family keys; cache bust `film-tool.js?v=20260720filmOpen`.
- **Local DB:** Relinked `game-1784304093435` → analysis_key `…__rerun_20260718_215754`, `relational_game_id=27`.
- **Verification:** `GET /api/film-tool-games?analysis_key=<video8 key>` → 1 game, **71** rows; Film HTML bootstraps client id + opponent + upload URL. Tests: 14 passed (`test_film_tool_open_bootstrap`, games, report normalize). Liberty on **8080**.

### Inferred

- Video player may sit at 0:00 until the large MP4 buffers; empty score was from missing tags, not a missing file.
- AI events panel uses the same `game_id` analysis key; after relink it should show the taught rerun’s events.

### Unknown

- Whether browser localStorage still holds an empty autosave that could prompt “Restore autosaved game?” on bare `/film` (deep links from Videos skip autosave restore).

### Working click path

1. Videos → Wilder / `nfhs_gam30b09cbb4f` → **Film Tool**
2. Or open: `http://127.0.0.1:8080/film/nfhs_gam30b09cbb4f.mp4?game_id=nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754&focus=1`
3. Expect: video loaded, opponent Wilder, date 2026-01-30, score from tags (~18–4 Q1), **71** tagged events.

### Changes

- `static/js/film-tool.js` — preserve `linkedAnalysisGameId`; richer deep-link match; load tags on open
- `templates/film_tool.html` — bootstrap client/opponent; cache bust
- `blueprints/core.py` — resolve client_game_id + opponent on `/film/<file>`
- `film_tool_games.py` — no wipe of analysis_key; list matches rerun family
- `tests/test_film_tool_open_bootstrap.py` — new
- `tests/test_film_tool_report_team_normalize.py` — cache bust assert
