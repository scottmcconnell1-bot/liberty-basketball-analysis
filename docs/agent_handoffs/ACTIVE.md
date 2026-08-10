# Active Task

Updated: 2026-08-09 (branches unified on coach-ledger)

Branch: `cursor/coach-ledger-ac1f`  
Current working tip for Scott: foundation + review workspace + stat-book + playbook sticky/assisted sample work.

## Meta

| Field | Value |
| --- | --- |
| **id** | coach-ledger-unified |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Included on this tip

- Videos light-list (`cursor/videos-fast-list-ac1f`)
- Coach-ledger foundation (auto-accept off + confirmed-box schema)
- Review workspace MVP — Accept/Correct/Reject in Film Tool
- Stat-book MVP — spiral scorebook extract/confirm
- Sticky choreography / FastDraw vector path (`cursor/sticky-choreography-ac1f`)
- Assisted stating SAMPLE prototype (`cursor/assisted-stat-sample-ac1f`)
- Full-film panel lineage (ancestor of sticky)

## Try

1. `/videos` — light list + Review button
2. `/film/<stored_filename>/review?game_id=<analysis_key>` — Accept / Correct / Reject
3. `/stat-books` and `/stat-books/sample` — scorebook OCR review/confirm
4. `/film/assisted-stat-sample` — SAMPLE assisted stating prototype
5. Playbook Play All / sticky choreography flows (existing playbook UI)
6. `/settings` — auto-accept locked off

## Not merged into jason

`jason-5-may-updates` left at prior tip; consolidate here on `cursor/coach-ledger-ac1f` first.

## Report

### Proven

- Merged `review-workspace-mvp` (`2925973`) and `stat-book-mvp` (`1246067`) into coach-ledger.
- Merged `assisted-stat-sample` (includes sticky + full-film lineage) with both route sets kept.
- Untracked local probes/DB dumps left uncommitted.

### Inferred

- Playbook sticky + jason-based ledger can coexist; conflicts were limited to docs + blueprint registration.

### Unknown

- Whether Scott wants `jason-5-may-updates` fast-forwarded to this tip next.
