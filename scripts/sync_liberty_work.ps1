# Sync Liberty work between home and work PCs
# Usage (either machine):
#   pwsh -File scripts/sync_liberty_work.ps1
# Optional:
#   pwsh -File scripts/sync_liberty_work.ps1 -Branch cursor/full-film-panel-ac1f

param(
    [string]$Branch = "cursor/full-film-panel-ac1f"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Invoke-Git([string[]]$GitArgs) {
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

Write-Host "=== Liberty dual-machine sync ==="
Write-Host "Repo: $RepoRoot"
Write-Host "Target branch: $Branch"
Write-Host ""

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    throw "Not a git repository: $RepoRoot"
}

Invoke-Git @("fetch", "origin")
Invoke-Git @("checkout", $Branch)

# Prefer fast-forward only so we never rewrite shared history by accident.
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& git pull --ff-only origin $Branch 2>&1 | ForEach-Object { Write-Host $_ }
$pullCode = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($pullCode -ne 0) {
    Write-Host ""
    Write-Host "ERROR: pull --ff-only failed. Resolve divergence manually (no force push)."
    Write-Host "  git status"
    Write-Host "  git log --oneline --left-right HEAD...origin/$Branch"
    exit 1
}

# Keep upstream tracking healthy for interactive git use.
Invoke-Git @("branch", "--set-upstream-to=origin/$Branch", $Branch)

Write-Host ""
Write-Host "=== git status ==="
& git status -sb
Write-Host ""
Write-Host "Does NOT sync (machine-local): .env, film_analysis.db, uploads/, teach runtime logs."
Write-Host "Truth for agents: docs/agent_handoffs/ACTIVE.md"
Write-Host ""
Write-Host "BEFORE YOU LEAVE: commit safe code/docs, then:"
Write-Host "  git push -u origin HEAD"
Write-Host "Or: pwsh -File scripts/daily_git_save.ps1  (skips .env/DB/uploads/panel runtime)"
Write-Host "=== sync done ==="
