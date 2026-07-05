# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-7c-player-minutes |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- `build_player_minutes_summary()` aggregates games, players, total minutes, top players
- `/status` shows Player Minutes Summary card
- `/preview` shows games-with-minutes, players-tracked, total-minutes KPIs
- `/film` uses `get_player_minutes()` with relational resolution; analysis results has minutes panel
- 318 passed, 1 skipped

### Next

Stage 8B — module state on `/preview`
