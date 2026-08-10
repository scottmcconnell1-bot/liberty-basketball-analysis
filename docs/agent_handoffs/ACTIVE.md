# Active Task

Updated: 2026-08-09 (review workspace MVP)

Branch: `cursor/review-workspace-mvp-ac1f` (based on `origin/cursor/coach-ledger-ac1f`)

## Meta

| Field | Value |
| --- | --- |
| **id** | review-workspace-mvp |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Decision

Scott-approved parallel MVP #4: Accept/Correct/Reject video review workspace. Official ledger = `events` where `review_status IN ('accepted','corrected')` (+ human_verified). AI drafts stay pending. Auto-accept stays off (inherited from coach-ledger foundation; Settings control hidden/locked to 0).

## Changes

- Film Tool **Review workspace** panel: Pending / Ledger / All filters; Accept / Correct / Reject
- Correct modal: player, event type, outcome; add/delete player via `/api/players`
- Deep link: `/film/<file>/review?game_id=…` → Film Tool with `review=1`
- `GET /api/review/events?review_status=ledger` → accepted+corrected only
- Settings: auto-accept UI hidden; save still forces `0.0`
- Videos list: Review button next to Film Tool

## Try

1. `/videos` → **Review** on a game, or
2. `/film/<stored_filename>/review?game_id=<analysis_key>`
3. Pending drafts → Accept / Correct / Reject; Ledger tab shows trusted only
4. `/settings` → auto-accept notice (locked off)

## Report

### Proven

- Rebased onto `origin/cursor/coach-ledger-ac1f` (auto-accept default/load/save = 0).
- 16 focused review tests passed (`test_review_workspace_mvp`, cleanup, UI).
- Accept/correct land on ledger filter; reject stays off; corrections write `human_corrections`.

### Inferred

- Coaches will use Film Tool review more than `/review` batch queue for day-to-day work.

### Unknown

- Whether production DB still has a non-zero stored auto-accept value (load path forces 0 regardless).
