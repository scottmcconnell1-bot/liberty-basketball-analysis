# Home-computer handoff — pick up here

Updated: 2026-09-14 (school session wrote this; **home PC later confirmed data is already good**)

## Home verified (2026-09-14 evening)

Do **not** restore over home’s live DB. Home is source of truth:

| Asset | Status |
| --- | --- |
| `film_analysis.db` | ~14.5 GB — 64 videos, large event set |
| `uploads/` | ~106 GB / 67 files |
| `LibertyData\backups\` | Older ~1.85 GB Jul 23 backup — **do not** overwrite live DB with it |
| App / coach / Funnel | `:8080` and `https://liberty-coach.tail368a37.ts.net` working on home |

School PC copy was empty; ignore school DB for restore.

## Goal (remaining)

1. Keep home as source of truth (already OK).
2. Decide merge path: Film Tool branch vs `main` vs auto-accept PR #147 / `cursor/full-stack-bringup-ac1f` (Scott gate).
3. Import **new** HUDL only after files are on disk (no remote HUDL login).

## Proven state (school PC — historical; home does not match)

| Item | Status |
| --- | --- |
| App repo | `C:\Users\smcconnell\Documents\liberty-basketball-analysis` on branch `cursor/full-stack-bringup-ac1f` |
| PR | [#147](https://github.com/scottmcconnell1-bot/liberty-basketball-analysis/pull/147) — auto-accept 0.85 unlock (merge when CI green) |
| Local site | Was serving **http://127.0.0.1:8080** and **/coach** → 200 |
| Python | 3.12 `.venv` with torch / ultralytics / OpenCV / EasyOCR |
| Models | `models/ball_detector.pt` etc. present (~165MB+) |
| Teach loop | Process started; **failed on analyze** because DB had **0 videos** |
| Tailscale | **Installed, logged out** — Funnel URL dead until login |
| Live DB | `film_analysis.db` ~404 KB — **empty** (0 games / 0 videos / 0 players / 0 uploads) |
| HUDL download by agent | **Not allowed / not possible** — Scott must export files |

## Steps for home PC (in order)

### A. Open the right repo
```bat
cd %USERPROFILE%\Documents\liberty-basketball-analysis
git fetch origin
git checkout main
git pull origin main
```
If #147 is not merged yet:
```bat
git fetch origin pull/147/head:cursor/full-stack-bringup-ac1f
git checkout cursor/full-stack-bringup-ac1f
```

### B. Hunt for the real data (before starting empty)
See **“Where to look for old video uploads”** below. Prefer restoring a large `film_analysis.db` + `uploads\` over rebuilding from scratch.

When you find a good backup:
1. Stop Liberty if running.
2. Copy current empty DB aside: `copy film_analysis.db film_analysis.empty.db`
3. Copy the good DB to `film_analysis.db`.
4. Restore `uploads\` (and any `data\stat_books\`, photos) next to the repo.
5. Start Liberty and confirm games appear.

### C. Start Liberty
```bat
cd %USERPROFILE%\Documents\liberty-basketball-analysis
Start Liberty.bat
```
Or:
```bat
.\.venv\Scripts\python.exe app.py
```
Open: http://127.0.0.1:8080 and http://127.0.0.1:8080/coach

### D. Tailscale Funnel (public coach link)
1. Open Tailscale app → **Log in**.
2. Then in an admin PowerShell:
```bat
"C:\Program Files\Tailscale\tailscale.exe" status
"C:\Program Files\Tailscale\tailscale.exe" funnel 8080
```
3. Share: `https://<machine>.<tailnet>.ts.net/coach`  
   (Old school hostname was `liberty-coach.tail368a37.ts.net` — may change after re-login.)

### E. HUDL / Hoopsalytics film
Agent cannot log into HUDL. On a machine with HUDL access:
1. Download full games (+ All-Athletes CSVs if available).
2. Put them in one folder, e.g. `%USERPROFILE%\Documents\HUDL`  
   (import script default used to be `C:\Users\scott\Documents\HUDL`).
3. On home PC:
```bat
py -3.12 scripts\import_hudl.py --dry-run
py -3.12 scripts\import_hudl.py
```
Pass `--source "D:\path\to\HUDL"` if not the default.

### F. Teach / reanalyze
Only after videos exist in DB:
```bat
py -3.12 scripts\start_hoops_teach_detached.py --status
py -3.12 scripts\start_hoops_teach_detached.py
```

## Where to look for old video uploads

Search **home PC first**, then any external drives.

### Highest probability
| Location | What |
| --- | --- |
| `%USERPROFILE%\LibertyData\backups\` | Dated `film_analysis.db` backups (`Backup Liberty Database.bat`) |
| `%USERPROFILE%\Documents\liberty-basketball-analysis\uploads\` | Uploaded game film |
| `%USERPROFILE%\Documents\liberty-basketball-analysis\film_analysis.db` | Live DB (want **many MB**, not ~400 KB) |
| `E:\LibertyData\` or `D:\LibertyData\` | Optional external root from backup script |
| `%USERPROFILE%\Documents\HUDL\` or `C:\Users\scott\Documents\HUDL\` | HUDL exports (videos + CSVs) |
| Old user profile `C:\Users\scott\Documents\liberty-basketball-analysis\` | Historical path in migrate scripts |

### Also check
- `data\uploads\`, `data\videos\`, `videos\`
- `data\stat_books\confirmed\` (scorebook JSON; images may sit beside uploads)
- Desktop / Downloads zips named `liberty`, `film`, `backup`, `uploads`
- OneDrive / Google Drive if Scott ever synced there
- External SSD/USB used at games
- School PC share only if it ever had a **large** DB (school copy was empty)

### Quick PowerShell scan (home PC)
```powershell
Get-ChildItem $env:USERPROFILE, E:\, D:\ -Filter film_analysis.db -Recurse -ErrorAction SilentlyContinue -Depth 5 |
  Select-Object FullName, Length, LastWriteTime | Sort-Object Length -Descending

Get-ChildItem $env:USERPROFILE\Documents, $env:USERPROFILE\LibertyData, E:\ -Filter *.mp4 -Recurse -ErrorAction SilentlyContinue -Depth 4 |
  Select-Object -First 40 FullName, Length
```
A good DB is usually **>> 1 MB**. A good uploads tree has many `.mp4` files.

## Do not
- Expect school PC empty DB to be the source of truth
- Ask the agent to log into HUDL/Hoopsalytics
- Change `ball_confidence` / ball model / precision generator without Scott OK
- Mass-delete park branches until site verified

## Done when
- [ ] Large DB + uploads restored (or HUDL import completed)
- [ ] http://127.0.0.1:8080 shows games/rosters/film
- [ ] Tailscale logged in + Funnel serves `/coach`
- [ ] #147 merged (or cherry-picked) if auto-accept unlock still needed on `main`
