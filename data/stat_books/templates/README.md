# Stat book templates

Blank form assets and layout metadata for coach stat books.

## Layout

```
data/stat_books/templates/<template_id>/
  blank.png          # or blank.pdf / multi-page assets
  layout.json        # field regions + labels (OCR / review assist)
```

- `<template_id>` is a stable slug (e.g. `liberty_hs_v1`). Confirmed boxes reference it as `template_id`.
- Do not put per-game scans here — those go under `uploads/stat_books/<game_id>/`.
- Confirmed box JSON (source of truth) lives at `data/stat_books/confirmed/<game_id>.json`.

See `docs/stat_books/CONFIRMED_BOX_SCHEMA.md` for the confirmed JSON contract.

## `layout.json` (placeholder shape)

Foundation only — OCR agents will flesh this out:

```json
{
  "template_id": "liberty_hs_v1",
  "page_count": 1,
  "fields": []
}
```

## Example folder

`liberty_hs_v1/` is a stub template id reserved for the Liberty HS book. Add blank sheet + real `layout.json` when OCR work starts.
