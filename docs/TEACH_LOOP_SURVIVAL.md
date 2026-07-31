# Teach loop survival (no babysitting)

The Hoops/HUDL teach loop used to **exit** when SQLite briefly locked (`database is locked`) while Flask or a GPU worker held the DB. Leaving the PC overnight then meant a dead loop and stale `running` rows.

## What we do now

1. **Survive locks** — `hoops_teach_loop.py` retries SQLite locks and **never exits** the main cycle on DB/transient errors (sleep + retry).
2. **Zombie reclaim** — if `analysis_runs` says `running` but no `analysis_launcher` is alive, the loop clears the row so it does not wait forever.
3. **Watchdog (Task Scheduler)** — every **15 minutes**, `scripts/watchdog_teach_loop.ps1` checks for a live `hoops_teach_loop.py`. If missing, it starts `scripts/start_hoops_teach_detached.py` (does not kill a live GPU analysis).

## Install once

```powershell
cd C:\Users\scott\Documents\liberty-basketball-analysis
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_teach_watchdog.ps1
```

Task name: **Liberty Teach Watchdog**  
Log: `data/hoopsalytics/teach_watchdog.log`

## Manual checks

```powershell
py -3.12 scripts/start_hoops_teach_detached.py --status
Get-Content data\hoopsalytics\detached_teach_loop.out.log -Tail 30
Get-Content data\hoopsalytics\teach_watchdog.log -Tail 20
```

## Still requires

- PC left **on** (Sleep is OK; full Shutdown/Restart still stops GPU mid-game until watchdog starts the loop again after login).
- Liberty web on `:8080` for starting new analyses (watchdog start path also tries to bring the server up).
