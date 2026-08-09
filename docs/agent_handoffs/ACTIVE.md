# Active Task

Updated: 2026-08-09 (extract → review → render)

Branch: `cursor/sticky-choreography-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-extract-review-render |
| **status** | `implemented` |
| **assigned_to** | cursor-agent |

## Decision (Scott)

1. Check whether source PDFs are vector or raster (OCR may be unnecessary).
2. Separate pipeline: extract structured play data → human review/correct → render animation. Scott corrects **data**, not animations.

## Approach

Three-stage pipeline (no `schema.sql`):

1. **Extract** — FastDraw vector PDF ops → structured JSON; OCR only as draft fallback.
2. **Review** — sticky choreography JSON + drag UI; Save/Reset persist across reloads.
3. **Render** — Play All reads sticky/corrected data only when present.

## Files

- `playbook_vector_extract.py`
- `playbook_choreography.py`
- `blueprints/playbook.py`
- `templates/playbook.html`
- `tests/test_playbook_vector_extract.py`
- `tests/test_playbook_choreography.py`
- `docs/playbook_pipeline.md`
- `docs/playbook_sticky_choreography.md`
- `docs/agent_handoffs/ACTIVE.md`

## Verify

- Vector classify: Fast Scout PDF → kind=vector, 0 image xrefs
- `/api/playbook/sheet-extract` on 1-Game page_0032 → source=vector, o1..o5
- Hard refresh sheet play → Save choreography → sticky banner
- Play All prefers sticky; Reset extract re-runs Stage 1
- pytest `test_playbook_vector_extract` + `test_playbook_choreography`

## Report

### Proven

- Source PDF `Fast Scout Plays 2021-2022.pdf` (and bulk_imports copies): creator FastDraw, PDF 1.4, 380 pages, **0** embedded images, text on all pages, drawings on 373 pages → **vector**.
- Digit glyphs `1`–`5` extractable with positions via PyMuPDF `get_text("words")`.
- Cut/pass/dribble strokes present as thicker draw paths (width ~2.92); court geometry is thinner (~1.46).
- Sticky choreography JSON + Save/Reset UI already on this branch; Play All prefers sticky ink/positions.
- Vector extract wired as Stage 1 preferred path (`sheet-extract` / sheet-align / sheet-paths).

### Inferred

- Vector digit centers will be more stable than OCR for FastDraw imports; ink attribution (which stroke belongs to which player) still needs Scott review on complex pages.
- Industry import remains FastDraw `.fdb` / authored frames; PDF vector extract is the practical bridge for Liberty’s existing library.

### Unknown / remaining

- Scott visual sign-off: Save on 1-Game / Rip after vector draft.
- Path-handle editor + `.fdb` adapter (next slice).
- Whether every bulk-imported play still has the sibling `.pdf` beside rendered PNGs (1-Game/Rip/Triangle/Pitt 5 do).
