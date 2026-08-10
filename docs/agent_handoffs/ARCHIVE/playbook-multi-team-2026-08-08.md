# Active Task

Updated: 2026-08-08 (Multi-team playbooks + copy between teams)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-multi-team |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1. `/playbook` dropdown switches among four team playbooks: HS Boys, HS Girls, Jr High Boys, Jr High Girls.
2. Existing plays default to **High School Boys** so nothing disappears.
3. Copy a play into another team (deep copy of play + steps/sheets + progressions).
4. Keep A–Z list + Back-to-plays restore within the selected team.
5. Do not regress Rip / Triangle / Pitt 5 on default-team play ids.
6. Avoid stomping concurrent 1-Game choreography work in `playbook_sheet_align.py`.

## Approach

- Additive runtime column `plays.team_key` (ALTER on first playbook access). **schema.sql not edited** (Scott gate deferred).
- Keys: `hs_boys`, `hs_girls`, `jh_boys`, `jh_girls`. Default / backfill: `hs_boys`.
- List filter + session/`?team=` + `localStorage`/`sessionStorage` persistence.
- `POST /playbook/play/<id>/copy-to-team` deep-copies play + steps (`source_image`) + progressions.

## Files

- `blueprints/playbook.py`
- `templates/playbook.html`
- `static/css/playbook.css`
- `tests/test_playbook.py`
- `docs/agent_handoffs/ACTIVE.md`
- `docs/agent_handoffs/ARCHIVE/playbook-list-ux-alpha-back-2026-08-08.md`

## Verify

- `http://127.0.0.1:8080/playbook` — dropdown; existing plays under High School Boys
- `http://127.0.0.1:8080/playbook?team=hs_girls` — empty or girls-only list
- Copy to… on a play → other team → appears there; source unchanged
- Rip / Triangle / Pitt 5 still on HS Boys: `/playbook/play/125`, `/127`, `/137`

## Report

### Proven

- 30/30 `tests/test_playbook.py` passed including filter-by-team + copy + progression copy.
- Did not touch `playbook_sheet_align.py`.

### Inferred

- Unused live-DB `program='shared'` column left alone; `team_key` is the team playbook discriminator.
- Opponent scout plays stay excluded via `playbooks.kind != 'opponent'`.

### Unknown / remaining

- Whether Scott wants `team_key` promoted into `schema.sql` later (gate).
- Bulk-import path may still need an explicit team picker (new imports inherit session team).
