# Active Task

Updated: 2026-08-08 (1-Game Scott choreography)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-1-game-choreography |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Authoritative **1-Game** sequence (4-high → pops → screens/passes → 5 on right block). One-mover-at-a-time: simultaneous sheet actions = same phase, back-to-back beats. Clean court (no digit masks / underlay ink / T-bar markers). Do not regress Rip 125, Triangle 127, Pitt 5 137.

## Approach

- `apply_game_sequence_routes` + `seed_game_sheet_positions` (pages 0032–0036) in `playbook_sheet_align.py`.
- Frontend `isGamePlay` / `orderGameBeats` / `ensureGameBeats`; skip heuristic screens + T-bar markers.
- Cache bump `v11` for formation seeds (OCR often misses 3/4/5 on these sheets).

## Files

- `playbook_sheet_align.py`
- `templates/playbook.html`
- `tests/test_playbook_sheet_align.py`
- `docs/agent_handoffs/ACTIVE.md`
- `docs/agent_handoffs/ARCHIVE/playbook-multi-team-2026-08-08.md`

## Verify

- Hard refresh: `http://127.0.0.1:8080/playbook/play/98` → **Play All**
- Headless beat list matches Scott steps (see Report)
- Smoke: `/playbook/play/125`, `/127`, `/137` still animate

## Report

### Proven

- Play **id 98** · pages **32–36** (`page_0032.png` … `page_0036.png`).
- Sheet-align tests: **26 passed** (includes 5 new 1-Game route tests).
- Headless Play All: Game beats correct; clean court (`underlay=false`, `maskCircles=0`, `screenMarkers=0`); Rip/Triangle/Pitt 5 still move.

**Final beat list (mapped to Scott):**

| Scott step | Sheet | Beats |
| --- | --- | --- |
| 1–2 (+ pass start) | 0 (p32) | Cut #4 pop, Cut #5 pop, Cut #3→left block *(same phase)*, Pass #1→#5 |
| 3 (screen) | 1 (p33) | Screen #1, Cut #4→top |
| 4–5 | 2 (p34) | Pass #5→#4, Pass #4→#1, Screen #3, Cut #5 around→left block |
| 6 | 3 (p35) | Screen #4 down, Cut #3→top |
| 7–8 | 4 (p36) | Pass #1→#3, Screen #4 *(same phase)*, Cut #5 around→right block, Pass #3→#5 |

### Inferred

- Formation seeds fill OCR gaps; ink tips used when present for passes.
- Concurrent multi-team playbook UI landed in the same working tree; archived separately.

### Unknown / remaining

- Scott visual sign-off on spacing of pop angles / curl paths.
