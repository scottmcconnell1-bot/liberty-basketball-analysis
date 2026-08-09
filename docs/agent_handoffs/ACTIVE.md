# Active Task

Updated: 2026-08-08 (Copy to… fix + 1-Game spacing)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-copy-and-1game-spacing |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Two required playbook fixes: (A) multi-team **Copy to…** broken on list; (B) 1-Game play 98 spacing/spots still wrong vs imported sheet steps. Do not regress Rip/Triangle/Pitt5. Flask-only restart.

## Approach

### A — Copy to…
- Root cause: flash used `flash()` but list template never called `get_flashed_messages`; dropdown defaulted to **current** team so same-team copy looked like a no-op; category filter could hide the new row after team switch.
- Fix: render flashes; require explicit other-team select; reject empty `target_team`; redirect `?copied=<id>` + clear filters/highlight; DnD ignores action controls.

### B — 1-Game spacing
- FT-line formation for 2/3/4/5; basket-line blocks (y≈48, rim-aligned); 4+5 parallel pop; 4 curls midcourt-side of 1’s screen; 5 to left block; 1 held left on downscreen; 4 low screen then 5 above to right block. Cache `v13`.

## Files

- `blueprints/playbook.py`
- `templates/playbook.html`
- `static/js/playbook-dnd.js`
- `static/css/playbook.css`
- `playbook_sheet_align.py`
- `tests/test_playbook.py`
- `tests/test_playbook_sheet_align.py`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh: `http://127.0.0.1:8080/playbook` → Copy to… another team → flash + highlight
- Hard refresh: `http://127.0.0.1:8080/playbook/play/98` → **Play All**
- pytest playbook + sheet_align

## Report

### Proven

- Copy endpoint worked server-side; UI failed to show flash / required intentional team choice / highlight.
- 1-Game seeds were ~y=205 (past FT toward midcourt); blocks at y=100 (mid-paint). Retargeted to FT≈168 and blocks y=48.

### Inferred

- Parallel 4+5 pop via `parallelGroup` + shared rAF matches Scott “same time” better than back-to-back beats.

### Unknown / remaining

- Scott visual sign-off on 1-Game paths after hard refresh (sheet PNGs may be absent locally; routes use seeded geometry).
