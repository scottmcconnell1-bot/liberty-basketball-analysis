# Playbook three-stage pipeline

Updated: 2026-08-09

Scott corrects **data**, not animations.

```
1. EXTRACT  → structured JSON (positions, path polylines, pass/screen events)
2. REVIEW   → human drag/edit + Save choreography (sticky overrides)
3. RENDER   → Play All reads only sticky/corrected JSON
```

## Stage 1 — Extract

Source PDFs (`Fast Scout Plays 2021-2022.pdf`, bulk import copies) are
**FastDraw vector** (creator=`FastDraw`, 380 pages, **0** embedded images,
native text digits + draw paths). Proven via PyMuPDF.

- Module: `playbook_vector_extract.py`
- API: `POST /api/playbook/sheet-extract` (also preferred inside sheet-align / sheet-paths)
- Output shape matches sticky choreography steps
- Fallback: OCR digit map + ink trace when no sibling PDF / raster sheet

## Stage 2 — Human review / correct

- UI on `/playbook` view of a sheet play
- Drag o-tokens; optional Play All once to inspect paths
- **Save choreography** → `data/playbook/choreography/{play_id}.json`
- API: GET/PUT/DELETE `/api/playbook/choreography/<id>`
- **Reset extract** deletes sticky and re-runs Stage 1

## Stage 3 — Render

Play All prefers sticky positions + outbound ink. It does **not** re-OCR when
a sticky file exists.

## How Scott corrects data

1. Open `/playbook` → open the play (e.g. 1-Game, Rip, Triangle, Pitt 5).
2. Wait for banner: vector extract draft, OCR draft, or saved choreography.
3. Drag tokens so spacing matches the sheet.
4. Click **Save choreography**.
5. Hard refresh — banner shows sticky; ▶ Play All reuses corrected JSON.

## Files

- `playbook_vector_extract.py` — vector extract
- `playbook_choreography.py` — sticky store
- `blueprints/playbook.py` — extract + choreography APIs
- `templates/playbook.html` — review UI + Play All sticky preference
- `docs/playbook_sticky_choreography.md` — sticky detail

## Next slice

Path-handle editor (drag polyline vertices) + optional FastDraw `.fdb` import.
