# Active Task

Updated: 2026-08-09 (coach-ledger foundation)

Branch: `cursor/coach-ledger-ac1f`  
Base: `jason-5-may-updates` + videos light-list commits (`cursor/videos-fast-list-ac1f`)

## Meta

| Field | Value |
| --- | --- |
| **id** | coach-ledger-foundation |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Scott approvals (2026-08-09)

1. **New direction approved** — coach ledger / confirmed stat book box + human review (not auto-accept-led).
2. **Working branch** — use `cursor/coach-ledger-ac1f` going forward (includes videos light-list fix).
3. **Auto-accept off** for review testing — default `ai.auto_accept_event_confidence` is `0`; `load_all_settings` forces `0` (ignores legacy DB `0.50`); threshold `<= 0` does not promote drafts. Settings UI documents that saving other settings does **not** silently restore `0.50`. Remove the load-path force when Scott re-enables auto-accept.
4. **Confirmed box JSON schema** — contract in `docs/stat_books/CONFIRMED_BOX_SCHEMA.md` (no `schema.sql` yet; ask Scott before DDL).
5. **Do not** build full OCR or full review UI in foundation slice.

## Sequencing (MVP agents)

Use branch **`cursor/coach-ledger-ac1f`** as the shared base for both MVP follow-ons:

| Order | Slice | Notes |
| --- | --- | --- |
| Done | Foundation (this) | Branch merge + auto-accept off + confirmed JSON contract + ACTIVE |
| Next A | Review / coach ledger MVP | Human confirm path; respect auto-accept=0 |
| Next B | Stat book assist MVP | Templates + uploads paths; write only to drafts until confirm → `data/stat_books/confirmed/<game_id>.json` |

Videos nav fix is already on this branch (`GET /api/videos` light by default).

## Foundation delivered

- Branch `cursor/coach-ledger-ac1f` = `jason-5-may-updates` + videos-fast-list (2 commits)
- `AI_DEFAULTS["auto_accept_event_confidence"]` → `0.0`; fail-closed parse; `threshold <= 0` returns 0 accepts
- Docs: `docs/stat_books/CONFIRMED_BOX_SCHEMA.md`, `data/stat_books/templates/README.md`, example `data/stat_books/confirmed/example_game.json`
- Paths reserved: `data/stat_books/templates/<template_id>/`, `uploads/stat_books/<game_id>/`, `data/stat_books/confirmed/<game_id>.json`

## Operator note (existing DBs)

`load_all_settings` and Settings save both force `ai.auto_accept_event_confidence` to `0` for review testing. Legacy DB values of `0.50` are ignored until Scott removes those force lines to re-enable.

## Report

### Proven

- Videos branch was exactly 2 commits ahead of `jason-5-may-updates` (clean fast-forward lineage).
- `auto_accept_high_confidence_events(..., threshold=0)` already returned 0; default now matches.

### Inferred

- MVP agents can fork from `cursor/coach-ledger-ac1f` without re-merging videos.

### Unknown

- When Scott wants `schema.sql` for confirmed boxes (gate).
