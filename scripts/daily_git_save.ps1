# Daily refresh: panel score + learning status only. No commit, no push (Scott, 2026-10-28).
# Scott decides every save/push/merge; Claude Code recommends them. The old commit+push
# block is in git history (commit 9040391) if it is ever wanted again.
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

    # Commit and push removed (Scott, 2026-10-28): the job pushed unapproved work to
    # team/auto. Files are refreshed on disk only; saving is recommended to Scott.
    Write-Log "Refresh only: no commit, no push."
    Write-Log "=== daily_git_save done ==="
    exit 0
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    Write-Log "=== daily_git_save failed ==="
    exit 1
}
