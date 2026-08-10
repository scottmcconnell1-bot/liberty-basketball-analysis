# Active Task

Updated: 2026-08-08 (playbook Play All → sheet slideshow)

Branch: `cursor/full-film-panel-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | playbook-sheet-slideshow-pivot |
| **status** | `implemented` (Play All slideshow for imported sheets) |
| **assigned_to** | cursor-agent |

## Decision (Scott: better tool for playbook animation?)

**Yes — better approach exists for THIS product.** Primary: **A) timed source_image sheet slideshow**.

| Option | Rank | Notes |
| --- | --- | --- |
| **A Sheet slideshow** | **1 — primary** | Ink already correct; Play All advances sheets; tokens optional/off |
| **B Editor movements_json** | 2 — keep for drawn plays | Animate only coach-drawn arrows; sheets as reference |
| **C External (FastDraw etc.)** | 3 — not now | Fine for standalone drawing; weak fit for imported Liberty PDF scout sheets already in-product |
| **D Keep fighting OCR/ink** | **Last resort** | Deferred / experimental |

**Source of truth for imported plays:** printed sheet images. **OCR digit-align + ink-path + SVG token choreography is deferred/experimental** — not the Play All path unless `movements_json` has real arrows.

### Why OCR/token Play All kept failing (Proven)

- `sheet-align` OCR digits ≠ printed formation reliably (wrong/missing o1–o5, header digits, crop drift).
- `sheet-paths` ink tracing invents or mis-follows routes between noisy digit endpoints.
- Heuristic “beats” (pass→screen→cut) when `movements_json` is empty do not match how the play actually goes.
- Tokens over a cropped underlay fight the diagram coaches already trust on the page.

Prior ACTIVE (teach hung/panel + messages identity): archived at `docs/agent_handoffs/ARCHIVE/teach-tool-hung-panel-2026-08-08.md`. Teach/analysis **not touched** this slice.

## Shipped this slice

1. **`useSheetSlideshowMode()`** — sheets present and no drawn `movements_json` arrows.
2. **Play All** → `playSheetSlideshow()` (timed advance of full `source_image` underlay; tokens/arrows cleared).
3. **Skip OCR align gate** for slideshow — banner **Ready — sheet slideshow**; Play All enabled immediately.
4. Align UI / token choreography **preserved** when sheets + real drawn movements (or editor-only plays).
5. Messaging / issue-notify / teach loop **not regressively edited**.

## Verify (Scott)

1. Open an imported multi-page play (view mode) → banner **Ready — sheet slideshow**; Play All enabled (no Aligning wait).
2. ▶ Play All → sheets advance on a white court plate; no flying SVG tokens.
3. Stop → returns to sheet 1.
4. Editor-drawn play (no `source_image`) → existing token animation still works.
5. Teach loop / analysis launcher still running if they were before (this slice did not restart them).

## Report

### Proven

- Repo Play All path was OCR align → ink paths → SVG beats over sheet underlay (`templates/playbook.html`, `playbook_sheet_align.py`).
- Slideshow pivot landed in `templates/playbook.html`; align APIs left in place for drawn-movement / experimental use.
- `tests/test_playbook_sheet_align.py` + messaging/notify tests: **23 passed, 1 skipped**.

### Inferred

- Coaches trust the PDF ink more than reconstructed tokens; slideshow matches teaching use of scout sheets.
- FastDraw-class tools help **drawing**, not reconciling Liberty’s imported multi-page PDFs.

### Unknown

- Whether coaches will later want optional experimental “token overlay” toggle.
- Hold timing (1.6s/sheet) may need coach feedback.
