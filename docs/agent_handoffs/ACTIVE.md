# Active Task

Updated: 2026-08-08 (1-Game pass overshoot polish)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-1-game-pass-polish |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1-Game play 98 close but not right: **passes overshoot** (ball past receiver then snap back). Spacing/destinations/paths need cleanup. Do not regress Rip 125, Triangle 127, Pitt 5 137.

## Approach

- Root cause: digit→digit passes kept ink midpoints (arrow tip past glyph) while only endpoints snapped; `normalizeAnimPath` preferred stale `path.to` over `live[receiver]` after same-sheet pops.
- Fix: straight 2-point passes in `apply_game_sequence_routes._ensure_pass`; frontend retargets non-orphan passes onto live tokens and drops ink midpoints; screen clearance ≥65px (Pitt 5); pops wider at 45° above 3pt.
- Cache bump `v12`.

## Files

- `playbook_sheet_align.py`
- `templates/playbook.html`
- `tests/test_playbook_sheet_align.py`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh: `http://127.0.0.1:8080/playbook/play/98` → **Play All**
- Sheet-align tests: 26 passed
- Headless: all five passes `passGap=0` / `nPts=2`; Rip/Triangle/Pitt 5 still animate

## Report

### Proven

- Pass overshoot: ink polylines had 40–56 midpoints past the receiver; endpoint snap alone left the ball traveling past then yanking back. Straight 2-pt + live-token retarget → `passGap=0` on 1→5, 5→4, 4→1, 1→3, 3→5.
- Screen clearance bumped to 65px; pop tips (118,225)/(382,225); clean court (`underlay=false`, `maskCircles=0`, `screenMarkers=0`).
- Tests 26 passed; LIVE_PROOF_OK for 98/125/127/137.

### Inferred

- Formation seeds still fill OCR gaps on 3/4/5; curl waypoints for “goes around” are geometric (not ink).

### Unknown / remaining

- Scott visual sign-off on pop angle / curl aesthetics after this pass fix.
