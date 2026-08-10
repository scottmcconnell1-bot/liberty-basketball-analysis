# Active Task (archived)

Updated: 2026-08-08 (Playbook UX: A–Z list + Back to plays position restore)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-list-ux-alpha-back |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1. Plays list sorted **A–Z by name** (case-insensitive) when browsing.
2. Play detail/animation pages get clear **← Back to plays**; return restores scroll + category + search via `sessionStorage`.
3. Do not regress Rip / Triangle / Pitt 5 animation.

## Approach

- Server: `_plays_query` + `_group_plays_for_list` (+ opponent list) sort by `name COLLATE NOCASE`.
- Client: `liberty.playbook.listState` saves `scrollY`, `categoryId`, `search` before leaving list; restores on `/playbook` load.
- Template: page-header + sidebar/progression **← Back to plays**.

## Files

- `blueprints/playbook.py`
- `templates/playbook.html`
- `static/css/playbook.css`
- `static/js/playbook-dnd.js` (hint comment)
- `tests/test_playbook.py`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh: `http://127.0.0.1:8080/playbook` — names A–Z
- Open a mid-list play (e.g. Pitt 5): `http://127.0.0.1:8080/playbook/play/137`
- Click **← Back to plays** — same scroll/category/search as before

## Report

### Proven

- Prior animation polish commit `8bbf575` already on origin; this slice is list UX only.

### Inferred

- Drag-reorder still persists `list_order` but no longer drives browse order.

### Unknown / remaining

- None for this slice.
