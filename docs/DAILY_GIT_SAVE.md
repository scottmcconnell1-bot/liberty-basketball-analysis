# Daily Git Save

Automates a **safe** nightly commit + push of Liberty source changes, and refreshes a human-readable learning status report so you can see how teaching is going without opening runtime JSON.

## What it does

Each night at **11:00 PM** (local), `scripts/daily_git_save.ps1`:

1. Runs `py -3.12 scripts/score_full_film_panel.py` (compare-only). Panel gate FAIL is exit 0 by design; a hard script failure is logged and the save continues.
2. Runs `py -3.12 scripts/generate_learning_status.py` (retries once on SQLite lock). Writes `docs/LEARNING_STATUS.md`. If generation fails, logs a warning and continues so source work is not lost.
3. Stages changes in the repo
4. Unstages secrets and runtime junk (`.env`, DB, `uploads/`, teach logs, compare JSON, panel latest/history, teach state, PIDs)
5. Commits with message `chore: daily learning status YYYY-MM-DD` if anything safe remains (including the status report)
6. Pushes the current branch to `origin`

Commit identity uses process env `GIT_AUTHOR_*` / `GIT_COMMITTER_*` defaults (`scottmcconnell1-bot` / `scottmcconnell1@gmail.com`) when unset — **no `git config` changes**.

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

Generate the report alone (no commit):

```powershell
py -3.12 scripts/generate_learning_status.py
```

## Never auto-committed

- `.env` / coach password
- `film_analysis.db` and uploads
- Teach loop logs / detached PIDs / compare reports
- `full_film_panel_latest.json` / `full_film_panel_history.jsonl` / `teach_loop_state.json`

## Tracked report

- `docs/LEARNING_STATUS.md` — fixed-panel gates, per-game table, queue summary, trend vs prior snapshot, Proven/Inferred/Unknown

## Notes

- Runs on whatever branch is checked out at 11 PM — keep working on a feature branch if you do not want nightly commits on `main`.
- Does **not** open or merge PRs; it only save/push the current branch.
- If push fails (offline / auth), the error is written to the log; Task Scheduler will retry next day (`StartWhenAvailable`).
- Does not stop teach loop / analysis / Flask.
