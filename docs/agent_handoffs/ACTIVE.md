# Active Task

Updated: 2026-08-09 (1-Game PDF re-anchor)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-1game-pdf-reanchor |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1-Game play 98 Play All was inventing formation geometry (forced o2@y=125, FT templates, o1@72, etc.) that disagreed with uploaded sheet PNGs pages 32–36. Re-anchor starts/destinations to OCR + sheet landmarks; keep sequence/order.

## Approach

- Remove `_GAME_FORCE_OIDS` — never overwrite OCR digit centers.
- Gap-fill missing 3/4/5 from measured page landmarks (elbows ≈191/308×188, wing mirror of OCR o2, pop tips on 3pt, left post ≈178×100).
- Routes: sequence gates unchanged; endpoints from PDF arrow tips; `trace_ink_polyline` when crop has a stroke corridor.
- Cache `v14` invalidates prior overrides.

## Files

- `playbook_sheet_align.py`
- `tests/test_playbook_sheet_align.py`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh: `http://127.0.0.1:8080/playbook/play/98` → **Play All**
- pytest playbook + sheet_align (57 passed)
- No regress Rip 125 / Triangle 127 / Pitt 5 137 / Copy-to UX

## Report

### Proven

- Overlay of page_0032: OCR o2@(433.5,209) sits on printed 2; forced y=125 did not.
- Elbow/pop/wing gap seeds match printed digits + arrow tips on the PNG.
- OCR finds 1+2 on all five pages; 3/4 on several; 3/4/5 still missed on opening (ink-bridged).

### Inferred

- Ink tip-walks alone wander on court lines; endpoint-constrained A* ink hug is more reliable for path *shape* once landmarks fix destinations.

### Unknown / remaining

- Scott visual sign-off after hard refresh on Play All.
- Whether page 36 cut tip should land closer to the rim ink tip vs right-block landmark used for Pass 3→5.
