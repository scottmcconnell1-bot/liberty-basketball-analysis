# Active Task

Updated: 2026-08-09 (sticky choreography)

Branch: `cursor/sticky-choreography-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-sticky-choreography |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

Competitors animate from authored vector models. Liberty re-OCRs PDF sheets every load. Persist sticky choreography JSON (positions + ink) so Scott can correct once and Play All stops re-guessing.

## Approach

- JSON file store `data/playbook/choreography/{play_id}.json` (no schema.sql).
- API GET/PUT/DELETE `/api/playbook/choreography/<id>`.
- View UI: drag tokens update `sheetAlignByStep`; **Save choreography** / **Reset OCR**.
- Play All prefers sticky positions + outbound ink when present.

## Files

- `playbook_choreography.py`
- `blueprints/playbook.py`
- `templates/playbook.html`
- `tests/test_playbook_choreography.py`
- `docs/playbook_sticky_choreography.md`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Hard refresh sheet plays → Save choreography → refresh again → banner “saved choreography”
- Drag o-tokens → Save → Play All uses new spots
- Rip 125 / Triangle 127 / Pitt 5 137 / 1-Game 98 still Play All without sticky file
- pytest playbook_choreography + sheet_align

## Report

### Proven

- CoachCanvas: draw in-browser; Free plan imports FastDraw library; PDF is export, not import-for-animation.
- HoopCoach: coach draws movements (cut/pass/screen); animates those steps; PDF/GIF export; no PDF→vector import.
- Basketball Tactic Board (`com.jenda.basketballboard`): frame-by-frame authored animation; import/export proprietary tactic/animation files between devices — not PDF OCR.
- Liberty already has `positions_json`/`movements_json` for canvas plays; sheet Play All ignored coach drags (OCR path).

### Inferred

- Industry “import” almost always means FastDraw `.fdb` or same-app proprietary frames, never reliable OCR of printed playbooks.
- Sticky JSON is the practical bridge until an exchange format exists.

### Unknown / remaining

- Scott visual sign-off after Save on 1-Game / Rip.
- Path-handle editor + FastDraw `.fdb` adapter (next slice).
