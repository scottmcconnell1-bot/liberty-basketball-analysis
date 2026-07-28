# Daily Git Save

Automates a **safe** nightly commit + push of Liberty source changes so work is not lost after reboots.

## What it does

Each night at **11:00 PM** (local), `scripts/daily_git_save.ps1`:

1. Stages changes in the repo
2. Unstages secrets and runtime junk (`.env`, DB, `uploads/`, teach logs, compare JSON, PIDs)
3. Commits with message `chore: daily save YYYY-MM-DD` if anything remains
4. Pushes the current branch to `origin`

Log: `data/hoopsalytics/daily_git_save.log`

## Install (once)

```powershell
cd C:\Users\scott\Documents\liberty-basketball-analysis
pwsh -File scripts/install_daily_git_save.ps1
```

Creates Task Scheduler task **Liberty Daily Git Save**.

## Manual run

```powershell
pwsh -File scripts/daily_git_save.ps1
```

## Never auto-committed

- `.env` / coach password
- `film_analysis.db` and uploads
- Teach loop logs / detached PIDs / compare reports

## Notes

- Runs on whatever branch is checked out at 11 PM — keep working on a feature branch if you do not want nightly commits on `main`.
- Does **not** open or merge PRs; it only save/push the current branch.
- If push fails (offline / auth), the error is written to the log; Task Scheduler will retry next day (`StartWhenAvailable`).
