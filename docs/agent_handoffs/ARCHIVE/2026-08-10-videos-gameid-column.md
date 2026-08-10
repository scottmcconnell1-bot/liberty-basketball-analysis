# Active Task

Updated: 2026-08-10 (videos GameID column)

Branch: `cursor/videos-gameid-column-ac1f`  
Base: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | videos-gameid-column |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Scope delivered

- `/videos` column header **Team** ? **GameID**
- Cell shows best available id from light list: `game_id` ? `analysis_key` ? `relational_game_id` ? video `id` (no extra API work)

## Try

1. Hard-refresh `http://127.0.0.1:8080/videos` (or Tailscale host `/videos`)
2. Confirm GameID column shows NFHS/game keys instead of "?" / Boys Varsity

## Report

### Proven

- Template-only change in `templates/videos.html`
- Light `/api/videos` already returns `game_id`, `analysis_key`, `relational_game_id`, `id`

### Inferred

- Scorebook matching wants `videos.game_id` (often NFHS key) more than schedule team_label

### Unknown

- Whether some rows lack `game_id` and will fall back to analysis_key / relational / row id
