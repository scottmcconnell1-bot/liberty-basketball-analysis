# Handwritten Stat Book MVP

Built on foundation schema: [`CONFIRMED_BOX_SCHEMA.md`](CONFIRMED_BOX_SCHEMA.md).

## Try (Flask restart)

| URL | Purpose |
| --- | --- |
| `/stat-books` | Upload scan / open sample |
| `/stat-books/templates/liberty_spiral_scorebook` | Blank + layout editor |
| `/stat-books/sample` | Seed HSB/Liberty filled sample → review |
| `/stat-books/games/<game_id>/review` | Grid next to photo, validation flags, confirm |
| `/stat-books/confirmed/<game_id>` | Confirmed JSON API |

Confirmed files: `data/stat_books/confirmed/<game_id>.json`

## Stubbed vs real

| Step | Status |
| --- | --- |
| Blank template + samples | Real (`liberty_spiral_scorebook/`) |
| `layout.json` from blank grid | Real (v1 coords; refine as needed) |
| Homography from 4 corners | Real when OpenCV present |
| Cell crop + digit OCR | Real when EasyOCR/Tesseract present; else manual review |
| Name OCR | Stubbed (manual on review) |
| Validation `pts=2*fg2+3*fg3+ftm` | Real |
| Confirm → JSON | Real (no confidence auto-accept) |

## Spiral field mapping

Form FG2/FG3/FTA/FTM/TP → `extras.fg2` / `extras.fg3` + foundation `fta`/`ftm`/`pts` (`tpm`≈fg3, `fgm`≈fg2+fg3).
