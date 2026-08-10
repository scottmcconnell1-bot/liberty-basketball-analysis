# liberty_spiral_scorebook

Primary Liberty spiral scorebook template (two-page teal grid).

| File | Role |
| --- | --- |
| `blank.png` | Empty form — one-time calibration source |
| `layout.json` | Anchors + cell map (priority: jersey/name/FG2/FG3/FTA/FTM/TP + final score) |
| `sample_*.png` | Filled copies for validation (also under `uploads/stat_books/samples/`) |

## Checksum (player rows)

`TP = 2 * FG2 + 3 * FG3 + FTM`

Footer **TEAM TOTALS** FG2/FG3 cells on some books store *points* from those shot types, not make counts — player-row checksums are authoritative for OCR review.

Drop a clearer blank re-scan here anytime; re-save layout via `/stat-books/templates/liberty_spiral_scorebook`.
