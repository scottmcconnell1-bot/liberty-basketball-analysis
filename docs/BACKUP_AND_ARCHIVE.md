# Backups & Archives — separate from the live app

**Live (hot path):** `film_analysis.db` + `uploads/` in the project folder.  
**Cold storage:** `%USERPROFILE%\LibertyData\` (or `LIBERTY_DATA_ROOT` on an external drive).

| Folder | Purpose |
| --- | --- |
| `LibertyData/backups/` | Full SQLite snapshots (`backup_db.py`) — disaster recovery |
| `LibertyData/archives/seasons/` | Per-season exports (`archive_season.py`) — history / school records |

Backups never write next to the live DB by default. Archives are **export-only** (live DB unchanged). Pruning old seasons from the live DB is a separate, Scott-approved step.

```bat
Backup Liberty Database.bat
py -3.12 scripts/backup_db.py --keep 14
py -3.12 scripts/archive_season.py --list
py -3.12 scripts/archive_season.py --season-id 3
```

Point at another drive:

```powershell
$env:LIBERTY_DATA_ROOT = "E:\LibertyData"
py -3.12 scripts/backup_db.py --keep 14
```
