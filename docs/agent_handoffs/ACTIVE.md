# Active Task

Updated: 2026-08-09 (branches unified on coach-ledger)

Branch: `cursor/coach-ledger-ac1f`  
Includes: videos light-list, coach-ledger foundation (auto-accept off + confirmed-box schema), review-workspace MVP, stat-book MVP.

## Meta

| Field | Value |
| --- | --- |
| **id** | coach-ledger-unified |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Unified

Scott-approved MVPs merged onto foundation base `cursor/coach-ledger-ac1f` and pushed as the current working tip.

### Review workspace MVP

- Film Tool **Review workspace** panel: Pending / Ledger / All; Accept / Correct / Reject
- Deep link: `/film/<file>/review?game_id=...`
- Ledger filter: `review_status IN ('accepted','corrected')`
- Auto-accept stays off (Settings locked)

### Stat-book MVP

- Handwritten spiral scorebook: template + align + OCR + checksum + confirm JSON
- Try: `/stat-books`, `/stat-books/sample`
- Confirmed: `data/stat_books/confirmed/<game_id>.json`

## Try

1. `/videos` — light list + Review button
2. `/film/<stored_filename>/review?game_id=<analysis_key>` — Accept / Correct / Reject
3. `/stat-books` — upload/sample → review/confirm
4. `/settings` — auto-accept notice (locked off)

## Leftovers (not merged — diverge from pre-foundation jason)

- `cursor/sticky-choreography-ac1f` — FastDraw sticky choreography / pass style
- `cursor/assisted-stat-sample-ac1f` — AI-assisted stating SAMPLE
- `cursor/full-film-panel-ac1f` — 1-Game Play All re-anchor

## Report

### Proven

- `review-workspace-mvp` (`2925973`) and `stat-book-mvp` (`1246067`) merged into `cursor/coach-ledger-ac1f`.
- Videos light-list already ancestor of coach-ledger.
- No `schema.sql` changes in this unification; auto-accept remains off.

### Inferred

- Playbook sticky tips need a separate rebase onto coach-ledger if Scott wants them on this tip.

### Unknown

- Whether Scott wants `jason-5-may-updates` fast-forwarded to coach-ledger yet (not done in this pass).
