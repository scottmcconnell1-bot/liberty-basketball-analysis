# Active Task

Updated: 2026-08-09 (stat-book MVP)

Branch: `cursor/stat-book-mvp-ac1f`  
Base: `origin/cursor/coach-ledger-ac1f` (videos light-list + auto-accept off + confirmed-box schema)

## Meta

| Field | Value |
| --- | --- |
| **id** | stat-book-mvp |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Objective

Handwritten spiral scorebook extraction MVP: blank template + layout → upload → align → cell OCR → checksum → review → confirmed JSON.

## Try

- `/stat-books`
- `/stat-books/templates/liberty_spiral_scorebook`
- `/stat-books/sample` → review/confirm
- Confirmed: `data/stat_books/confirmed/<game_id>.json`

## Delivered

- Template `liberty_spiral_scorebook/` with Scott blank + filled samples + calibrated `layout.json`
- Flask `/stat-books/...` + review UI
- Validation `pts == 2*fg2 + 3*fg3 + ftm` (foundation schema + `extras.fg2/fg3`)
- Tests: `tests/test_stat_book.py`

## Report

### Proven

- Blank + samples ingested; layout has 240 cells over 2 pages / 16 rows each.
- `pytest tests/test_stat_book.py` — 7 passed.
- No `schema.sql` changes; no confidence auto-accept.

### Inferred

- v1 cell coords from blank peak detection may need nudge after OCR on real photos.
- Name OCR left manual for v1.

### Unknown

- Exact OCR accuracy on Scott’s handwriting without EasyOCR/Tesseract installed on this machine.
