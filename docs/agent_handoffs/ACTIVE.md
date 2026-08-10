# Active Task

Updated: 2026-08-09 (videos Active/Archive + bulk archive)

Branch: `cursor/videos-archive-ac1f`  
Tip: `3979ef2` (encoding fix on top of `ac78b33` archive feature)

## Meta

| Field | Value |
| --- | --- |
| **id** | videos-archive |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Scope delivered

- `videos.archived` + `archived_at` via runtime ALTER (no schema.sql)
- `/videos` Active vs Archive tabs (`?view=archive`)
- Archive / Unarchive per-row buttons + high-contrast tab CSS
- APIs: `?archived=0|1|all`, `/api/videos/archive-counts`, `POST .../archive|unarchive`
- Bulk-archived all rows in `film_analysis.db`

## Try

1. `/videos` — Active list empty after bulk archive
2. `/videos?view=archive` — all games
3. Unarchive one game to move it back to Active

## Report

### Proven

- Commit `ac78b33` feature + `3979ef2` Flask import fix; pushed to origin
- DB: active=0, archived=63 (film_analysis.db)
- Flask serving archive tip on :8080

### Inferred

- Scott's unreadability was low-contrast secondary buttons / crowded action row

### Unknown

- Whether JrHigh uploads after this point should stay Active by default (new uploads start unarchived)
