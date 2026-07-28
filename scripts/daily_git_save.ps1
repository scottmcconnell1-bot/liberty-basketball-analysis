# Daily save: commit tracked + safe source changes and push to origin.
# Never commits secrets, DB, uploads, or teach runtime logs.
# Usage: pwsh -File scripts/daily_git_save.ps1
# Scheduled: Task Scheduler → Daily Git Save (Liberty)

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

function Invoke-Git([string[]]$GitArgs) {
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit $LASTEXITCODE"
    }
}

try {
    Write-Log "=== daily_git_save start ==="
    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        throw "Not a git repository: $RepoRoot"
    }

    $branch = (& git branch --show-current).Trim()
    if (-not $branch) { throw "Detached HEAD — skip daily save" }
    Write-Log "branch=$branch"

    # Stage everything, then peel off unsafe paths.
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
        "data/hoopsalytics/boxscore_teach_report.json"
    )
    foreach ($pattern in $unstage) {
        & git reset -q HEAD -- $pattern 2>$null
    }

    # Refuse if a staged file looks like a secret.
    $staged = & git diff --cached --name-only
    $blocked = $staged | Where-Object {
        $_ -match '(^|/)\.env($|\.)' -or
        $_ -match '\.(pem|pfx|p12)$' -or
        $_ -match '(^|/)credentials\.json$' -or
        $_ -match '(^|/)film_analysis\.db$' -or
        $_ -match '(^|/)uploads/'
    }
    if ($blocked) {
        throw ("Refusing to commit sensitive paths: " + ($blocked -join ", "))
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
chore: daily save $date

Automated Liberty daily snapshot of safe source changes (no .env/DB/uploads/logs).
"@
    Invoke-Git @("commit", "-m", $msg)

    $upstream = & git rev-parse --abbrev-ref "@{u}" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $upstream) {
        Write-Log "No upstream — pushing -u origin $branch"
        Invoke-Git @("push", "-u", "origin", "HEAD")
    } else {
        Write-Log "Pushing to $upstream"
        Invoke-Git @("push")
    }

    Write-Log "=== daily_git_save done ==="
    exit 0
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    Write-Log "=== daily_git_save failed ==="
    exit 1
}
