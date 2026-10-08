# Encrypted archive: Adrian detections (2026-10-07)

`liberty_adrian_detections_20261007.enc` holds the `detections` rows of five older
Adrian reruns, taken out of `film_analysis.db` on 2026-10-08 to shrink it.

| Rerun | Rows |
| --- | --- |
| `..._rerun_20260915_193718` | 866,471 |
| `..._rerun_20260927_042234` | 623,541 |
| `..._rerun_20260928_031027` | 883,276 |
| `..._rerun_20260930_160546` | 883,276 |
| `..._rerun_20260930_191418` | 883,276 |

Total 4,139,840 rows. Before encryption every row was compared with the live database
and all matched. The game's own rows and the newest rerun (`..._rerun_20261006_033941`)
were not archived.

The file is AES-256-GCM encrypted. The passphrase is **not** in this repository. Scott
has it in `C:\Users\scott\Documents\LIBERTY-ARCHIVE-PASSPHRASE-do-not-commit.txt` on the
home PC. Keep a second copy somewhere else. Without it the file cannot be opened.

## Get the rows back

```
python encrypted-archive/archive_crypto.py decrypt encrypted-archive/liberty_adrian_detections_20261007.enc db-archive
python db-archive/restore_detections.py detections__rerun_20260928_031027.csv.xz          # check only
python db-archive/restore_detections.py detections__rerun_20260928_031027.csv.xz --apply   # write (stop Flask first)
```

Run these from the repo root. Decrypting into `db-archive/` puts
`restore_detections.py` where it expects to be, one level below `film_analysis.db`.
`db-archive/` is ignored by git. Rows already present are skipped.
