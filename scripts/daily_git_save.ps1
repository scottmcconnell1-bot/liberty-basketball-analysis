# Daily save: refresh learning status, commit safe source changes, push to origin.
# Never commits secrets, DB, uploads, or teach/panel runtime files.
# Usage: pwsh -File scripts/daily_git_save.ps1
# Scheduled: Task Scheduler → Liberty Daily Git Save

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "data\hoopsalytics"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "daily_git_save.log"

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Ensure-GitIdentityEnv {
    # Scheduled Task often has no git user.name/email. Prefer process env (no git config).
    if (-not $env:GIT_AUTHOR_NAME) { $env:GIT_AUTHOR_NAME = "scottmcconnell1-bot" }
    if (-not $env:GIT_AUTHOR_EMAIL) { $env:GIT_AUTHOR_EMAIL = "scottmcconnell1@gmail.com" }
    if (-not $env:GIT_COMMITTER_NAME) { $env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME }
    if (-not $env:GIT_COMMITTER_EMAIL) { $env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL }
    Write-Log ("git identity env author={0} <{1}>" -f $env:GIT_AUTHOR_NAME, $env:GIT_AUTHOR_EMAIL)
}

function Invoke-Git([string[]]$GitArgs) {
    # Native git stderr must not trip $ErrorActionPreference=Stop.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & git @GitArgs 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $_.Exception.Message
            } else {
                Write-Host $_
            }
        }
        if ($LASTEXITCODE -ne 0) {
            throw "git $($GitArgs -join ' ') failed with exit $LASTEXITCODE"
        }
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

function Invoke-PySoft([string]$Label, [string[]]$PyArgs, [switch]$RetryOnSqliteLock) {
    Write-Log ("Running {0}: py -3.12 {1}" -f $Label, ($PyArgs -join " "))
    & py -3.12 @PyArgs
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Write-Log ("{0} ok (exit 0)" -f $Label)
        return
    }
    if ($RetryOnSqliteLock) {
        Write-Log ("{0} exit {1} - retrying once (possible SQLite lock)" -f $Label, $code)
        Start-Sleep -Seconds 3
        & py -3.12 @PyArgs
        $code = $LASTEXITCODE
        if ($code -eq 0) {
            Write-Log ("{0} ok after retry (exit 0)" -f $Label)
            return
        }
    }
    Write-Log ("WARNING: {0} failed with exit {1} - continuing daily save" -f $Label, $code)
}

try {
    Write-Log "=== daily_git_save start ==="
    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        throw "Not a git repository: $RepoRoot"
    }

    Ensure-GitIdentityEnv

    $branch = (& git branch --show-current).Trim()
    if (-not $branch) { throw "Detached HEAD - skip daily save" }
    Write-Log "branch=$branch"

    # Refresh panel + learning status before staging (soft-fail so source work is not lost).
    Invoke-PySoft "full_film_panel" @("scripts/score_full_film_panel.py")
    Invoke-PySoft "learning_status" @("scripts/generate_learning_status.py") -RetryOnSqliteLock

    # Stage everything, then peel off unsafe / runtime paths.
    Invoke-Git @("add", "-A")

    $unstage = @(
        ".env",
        ".env.*",
        "*.db",
        "*.db-shm",
        "*.db-wal",
        "film_analysis.db",
        "uploads",
        "data/hoopsalytics/*.log",
        "data/hoopsalytics/*.err.log",
        "data/hoopsalytics/*.out.log",
        "data/hoopsalytics/detached_pids.json",
        "data/hoopsalytics/coach_*.txt",
        "data/hoopsalytics/improve_pass*",
        "data/hoopsalytics/compare_*.json",
        "data/hoopsalytics/detached_*.json",
        "data/hoopsalytics/teach_loop_state.json",
        "data/hoopsalytics/boxscore_teach_report.json",
        "data/hoopsalytics/full_film_panel_latest.json",
        "data/hoopsalytics/full_film_panel_history.jsonl",
        "data/hoopsalytics/daily_git_save.log"
    )
    foreach ($pattern in $unstage) {
        & git reset -q HEAD -- $pattern 2>$null
    }

    # Ensure the human-readable status report is staged when present.
    $statusDoc = Join-Path $RepoRoot "docs\LEARNING_STATUS.md"
    if (Test-Path $statusDoc) {
        Invoke-Git @("add", "--", "docs/LEARNING_STATUS.md")
    }

    # Refuse if a staged file looks like a secret.
    $staged = & git diff --cached --name-only
    $blocked = $staged | Where-Object {
        $_ -match '(^|/)\.env($|\.)' -or
        $_ -match '\.(pem|pfx|p12)$' -or
        $_ -match '(^|/)credentials\.json$' -or
        $_ -match '(^|/)film_analysis\.db$' -or
        $_ -match '(^|/)uploads/' -or
        $_ -match 'full_film_panel_latest\.json$' -or
        $_ -match 'full_film_panel_history\.jsonl$' -or
        $_ -match 'teach_loop_state\.json$'
    }
    if ($blocked) {
        throw ("Refusing to commit sensitive/runtime paths: " + ($blocked -join ", "))
    }

    $pending = & git diff --cached --name-only
    if (-not $pending) {
        Write-Log "No safe changes to commit."
        Write-Log "=== daily_git_save done (noop) ==="
        exit 0
    }

    Write-Log ("Staging {0} files" -f @($pending).Count)
    $date = Get-Date -Format "yyyy-MM-dd"
    $msg = @"
chore: daily learning status $date

Automated Liberty daily snapshot: learning status report + safe source changes (no .env/DB/uploads/logs/panel runtime).
"@
    Invoke-Git @("commit", "-m", $msg)

    # Always push explicitly to origin. Do NOT probe @{u}: with
    # $ErrorActionPreference=Stop, a failed rev-parse aborts before fallback.
    # -u keeps tracking healthy for interactive git use.
    Write-Log "Pushing HEAD to origin (set upstream)"
    Invoke-Git @("push", "-u", "origin", "HEAD")

    Write-Log "=== daily_git_save done ==="
    exit 0
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    Write-Log "=== daily_git_save failed ==="
    exit 1
}
