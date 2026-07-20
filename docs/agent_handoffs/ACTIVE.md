# Active Task

Updated: 2026-07-19
Branch: `cursor/film-tool-reports-fix-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | film-tool-reports-fix |
| **status** | `completed` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Blank.pdf** (184 KB): print output with report chrome but **0 players / 0 PTS** — matches empty box score when Liberty tags stored blank team (`""`, UI label "Select").
- **Root cause:** `statAccumulator` used `r.team || 'Unknown'`; box/player/team totals filter `p.Team === liberty` so 42 Liberty Q1 tags were excluded. Manual vs AI already worked via `normalizeManualTeamForCompare`.
- **Fix:** `statAccumulator`, `getScoreState`, `addMinutesToStatAccumulator`, `openReportDrilldown`, and game list `scoreFromRows` all normalize blank/Select → Liberty.
- **Wilder metadata** (DB patch on `game-1784304093435`): date `2026-01-30`, `competitionType` conference, `gameResult` win; Q1 tag score 18–4; `games.id=27` `is_conference=1`.
- Cache bust: `film-tool.js?v=20260719reportsFix`
- Liberty restarted on **8080** (PID 23652 at patch time).

### Inferred

- Full-game score 55–17 from MaxPreps; film tags are Q1-only so list score shows partial 18–4 until more quarters tagged.
- Settings **Local AI Models** = Ollama LLM for practice notes / reasoning; unrelated to YOLO film detector or Cursor chat model.

### Changes

- `static/js/film-tool.js` — team normalize for all report types + score
- `templates/film_tool.html` — cache bust
- `blueprints/core.py` — build probe cache string
- `tests/test_film_tool_report_team_normalize.py`
