# Active Task

Updated: 2026-09-14 (home PC bring-up — data OK, server+funnel live)

Branch: `cursor/film-tool-review-layout-ac1f` (local; ahead of origin)  
Base historically: `jason-5-may-updates` · `origin/main` at `59577bd` (PR #146)

## Meta

| Field | Value |
| --- | --- |
| **id** | home-pc-bringup |
| **status** | `ready` (data restored / already present) |
| **assigned_to** | cursor-agent |
| **scope** | Home PC ops + Adrian accuracy when reviewing film |

## Home PC — Proven (2026-09-14)

| Check | Result |
| --- | --- |
| `film_analysis.db` | **~14.5 GB** (not the empty ~400 KB school copy) |
| Videos in DB | **64** |
| Events | **669,677** (Adrian rows ~51k) |
| `uploads/` | **67** files (~106 GB) |
| Flask `:8080` | **Listening** (pid live) → http://127.0.0.1:8080 |
| `/coach` | **200** |
| Tailscale Funnel | **On** → https://liberty-coach.tail368a37.ts.net → `127.0.0.1:8080` |

Backup DB also present: `%USERPROFILE%\LibertyData\backups\film_analysis_20260723_173206.db` (~1.85 GB) — older than current home DB; **do not overwrite** the 14.5 GB file with this unless Scott says so.

## Do not

- Replace home `film_analysis.db` with the empty school copy
- Unpause teach loop / flip auto-accept without Scott (PR-ish `cursor/full-stack-bringup-ac1f` re-enables auto-accept — gate)
- Sync DBs/uploads via git

## Next (Scott)

1. Confirm coach login on funnel URL
2. HUDL: download on a logged-in machine → copy here → `py -3.12 scripts\import_hudl.py`
3. Resume Adrian Film Tool accuracy when ready (`ACTIVE` prior: tip_off / steal labels / overlay fix)
4. Decide whether to merge to `main` / open PR for film-tool branch (local is ahead of origin)

## Adrian film (when reviewing)

Game: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`  
Hard-refresh Film Tool → Show ledger → tip_off ~3.3s; steal ~13s (not rebound @ ~11s)
