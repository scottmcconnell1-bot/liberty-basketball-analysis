# Active Task

Updated: 2026-08-08 (Pitt 5 polish: straight screen, spacing, around cut, no T-bar)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-pitt5-choreography |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Pitt 5 (play **137**):

1. Pages: real sheets **172** (formation) + **173** (action) — keep multi-page.
2. Sequence: **1 passes to 5**; **1 left corner**; **2 right corner**; then screen action:
   - **4 sets a screen about at the 3-point line** (straight slide; hold with spacing from #5).
   - **5 goes around 4 to the right block** (curl path, not through screener).
   - **After 5 clears the screen**, **4 drops to the left block and stays** (`heldLandings` / no OCR snap-back).
3. Clean court — no sheet underlay ink, no black screen T-bar stroke. Do not regress Rip 125 or Triangle 127. No commit.

## Approach

- `apply_pitt5_sequence_routes`: straight 2-pt Screen `o4` → tip (≥65px from #5); 4-pt around Cut `o5` → right block; straight `o4_drop` tip→left block.
- Frontend: skip `drawScreenMarker` on Pitt 5; `normalizeAnimPath` trusts `pitt5Drop` / multi-point paths (no OCR yank on drop).

## Files

- `playbook_sheet_align.py`
- `templates/playbook.html`
- `tests/test_playbook_sheet_align.py`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

Hard refresh: `http://127.0.0.1:8080/playbook/play/137`

Expect Play All:

1. Pass #1 → #5
2. Cut #1 (left corner)
3. Cut #2 (right corner)
4. Screen #4 → tip ≈(208.5, 232.2) straight 2-pt; gap from #5 ≈66; no black T-bar
5. Cut #5 → around mid ≈(258.5, 214.2) → right block ≈(323.5, 97.9)
6. Cut #4 drop → left block ≈(176.5, 97.9) and **hold**

Flask restarted on :8080. Teach ports left alone.

## Report

### Proven

- Squiggle cause: `trace_ink_polyline` along printed T-bar stem for `o4` screen approach → replaced with straight 2-point path.
- Black line cause: `drawScreenMarker` black T-bar (`#111827`) after screen hold → no-op on Pitt 5; DOM `.screen-marker` count = 0.
- Spacing: screen tip pulled to ≥65px from #5 (live gap 66.2); tip (208.5, 232.2).
- Around path: `o5` 4-point polyline with mid right of screener (258.5, 214.2) → right block; not the old through-screen chord.
- #4 holds left block: live end `o4`=(176.5, 97.9) after drop; `normalizeAnimPath` keeps `pitt5Drop` destination (avoids OCR yank to right-block seed).
- Pages 172+173; `isPitt5=true`; underlayKids=0; maskCircles=0.
- Unit tests: `pitt5` + Rip + Triangle sheet-align suite green (9 passed).

### Inferred

- Travel path stroke during the beat (red) is intentional motion cue; Scott’s “black line” was the T-bar marker, not underlay.

### Unknown / remaining

- Scott visual sign-off on around-path smoothness / screen tip placement on hard refresh.
