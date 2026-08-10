# Confirmed Stat Book Box — JSON Schema (foundation)

**Status:** Confirmed for implementation. No `schema.sql` table yet — this JSON is the contract that a future SQLite table will mirror.

**Updated:** 2026-08-09  
**Branch:** `cursor/coach-ledger-ac1f`

## Paths

| Role | Path | Notes |
| --- | --- | --- |
| Blank template + layout | `data/stat_books/templates/<template_id>/` | One folder per form layout. Contains blank sheet image(s) and `layout.json`. |
| Per-game uploads (scans / photos) | `uploads/stat_books/<game_id>/` | Raw coach uploads for that game. Not the source of truth for box stats. |
| Confirmed box (source of truth) | `data/stat_books/confirmed/<game_id>.json` | **One JSON file per game.** Written only after human confirm. |

## Design rules

1. **One confirmed JSON per game** — keyed by stable `game_id` (same string used elsewhere in Liberty).
2. **Stable keys** — field names below are intentional; a future table should use the same names (or 1:1 column mapping).
3. **Confirmed ≠ OCR draft** — OCR / assist output may live elsewhere; only human-confirmed values belong in `confirmed/`.
4. **Checksums** — store hashes of the upload(s) and/or blank template used so we can detect drift later.

## Top-level object

```json
{
  "schema_version": 1,
  "game_id": "string",
  "template_id": "string",
  "final_score_home": 0,
  "final_score_away": 0,
  "home_team": "string",
  "away_team": "string",
  "players": [],
  "quarters": [],
  "checksums": {},
  "confirmed_at": "ISO-8601 timestamp",
  "confirmed_by": "string"
}
```

### Field reference (maps to future table)

| Key | Type | Future table notes |
| --- | --- | --- |
| `schema_version` | int | Bump when breaking JSON shape. |
| `game_id` | string | PK / FK to games. |
| `template_id` | string | FK to template registry / folder name. |
| `final_score_home` | int | Nullable until confirmed. |
| `final_score_away` | int | Nullable until confirmed. |
| `home_team` | string | Display name at confirm time. |
| `away_team` | string | Display name at confirm time. |
| `players` | array | Normalize later to `stat_book_player_rows` if needed. |
| `quarters` | array | Period-level totals / notes. |
| `checksums` | object | Opaque string map; keep flexible. |
| `confirmed_at` | string (ISO-8601) | When coach confirmed. |
| `confirmed_by` | string | User id or display name. |

### `players[]` row

Stable per-player keys (extend later; do not rename):

| Key | Type | Notes |
| --- | --- | --- |
| `jersey` | string \| int | Prefer string to preserve leading zeros. |
| `name` | string | |
| `team` | `"home"` \| `"away"` | |
| `pts` | int | |
| `fouls` | int | |
| `fgm` | int | optional |
| `fga` | int | optional |
| `tpm` | int | optional (3PM) |
| `tpa` | int | optional (3PA) |
| `ftm` | int | optional |
| `fta` | int | optional |
| `reb` | int | optional |
| `ast` | int | optional |
| `stl` | int | optional |
| `blk` | int | optional |
| `to` | int | optional |
| `min` | string \| number | optional |

Unknown columns from a template may be stored under `extras` (object) without renaming the stable keys above.

### `quarters[]` entry

| Key | Type | Notes |
| --- | --- | --- |
| `period` | int \| string | `1`–`4`, `OT`, etc. |
| `home_pts` | int | |
| `away_pts` | int | |
| `notes` | string | optional |

### `checksums` object

Suggested keys (all optional strings):

| Key | Meaning |
| --- | --- |
| `upload_sha256` | Hash of primary uploaded scan. |
| `uploads_manifest_sha256` | Hash of multi-file manifest if used. |
| `template_layout_sha256` | Hash of `layout.json` at confirm time. |
| `blank_sheet_sha256` | Hash of blank template image used. |

## Minimal example

See [`data/stat_books/confirmed/example_game.json`](../../data/stat_books/confirmed/example_game.json).

## Out of scope (this foundation)

- OCR pipeline / layout digitizer
- Review UI for confirming boxes
- `schema.sql` table DDL (ask Scott before adding)
