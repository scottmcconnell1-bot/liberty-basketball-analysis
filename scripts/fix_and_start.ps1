# Liberty Basketball — repair OneDrive/git/venv issues and start the app.
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\fix_and_start.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Fix {
    param([string]$Message)
    Write-Host ("fix: " + $Message)
}

Write-Host ""
Write-Host "============================================================"
Write-Host " Liberty Basketball — Fix and Start"
Write-Host "============================================================"
Write-Host ""

function Find-Python {
    $candidates = @(
        @("py", "-3.12"),
        @("py", "-3.13"),
        @("python"),
        @("python3")
    )
    foreach ($cmd in $candidates) {
        if (-not (Get-Command $cmd[0] -ErrorAction SilentlyContinue)) { continue }
        try {
            $args = @()
            if ($cmd.Length -gt 1) {
                $args = $cmd[1..($cmd.Length - 1)]
            }
            $version = & $cmd[0] @args -c "import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1]))" 2>$null
            $version = ($version | Out-String).Trim()
            if ($version -eq "3.12" -or $version -eq "3.13") {
                return $cmd
            }
        } catch {}
    }
    throw "Python 3.12 or 3.13 not found. Install from https://www.python.org/downloads/ (check Add to PATH)."
}

$pythonCmd = Find-Python
Write-Fix ("Using Python: " + ($pythonCmd -join " "))

# Backup game data before git repairs.
$backupDir = Join-Path $env:TEMP ("liberty-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backupDir | Out-Null
foreach ($item in @("film_analysis.db", "uploads")) {
    $source = Join-Path $Root $item
    if (Test-Path $source) {
        Copy-Item $source $backupDir -Recurse -Force
        Write-Fix ("Backed up " + $item)
    }
}

# Repair git if fetch fails (common with partial OneDrive sync).
$gitOk = $false
if (Get-Command git -ErrorAction SilentlyContinue) {
    git fsck --full 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        git fetch origin 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            git checkout cursor/q1-manual-ai-compare-ac1f 2>$null | Out-Null
            git pull origin cursor/q1-manual-ai-compare-ac1f 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $gitOk = $true }
        }
    }
}

if (-not $gitOk) {
    Write-Fix "Git repo corrupted — repairing .git from GitHub..."
    $clonePath = Join-Path $env:TEMP ("liberty-git-repair-" + (Get-Random))
    if (Test-Path $clonePath) { Remove-Item $clonePath -Recurse -Force }
    git clone --branch cursor/q1-manual-ai-compare-ac1f --single-branch `
        https://github.com/scottmcconnell1-bot/liberty-basketball-analysis.git $clonePath
    if ($LASTEXITCODE -ne 0) { throw "git clone failed. Check internet connection." }
    if (Test-Path ".git") { Remove-Item ".git" -Recurse -Force }
    Copy-Item (Join-Path $clonePath ".git") ".git" -Recurse -Force
    git checkout cursor/q1-manual-ai-compare-ac1f
    git reset --hard origin/cursor/q1-manual-ai-compare-ac1f
    Remove-Item $clonePath -Recurse -Force
    Write-Fix "Git repaired."
}

# Restore backed-up data.
foreach ($item in @("film_analysis.db", "uploads")) {
    $src = Join-Path $backupDir $item
    if (Test-Path $src) {
        Copy-Item $src $Root -Recurse -Force
        Write-Fix ("Restored " + $item)
    }
}

# Optional ffmpeg (skip msstore certificate errors).
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Fix "Installing ffmpeg (winget source)..."
        winget install -e --id Gyan.FFmpeg --source winget `
            --accept-package-agreements --accept-source-agreements 2>$null | Out-Null
    }
}

Write-Fix "Recreating virtual environment and starting app..."
$launchArgs = @("scripts\launch_liberty.py", "--repair")
if ($pythonCmd.Length -gt 1) {
    & $pythonCmd[0] $pythonCmd[1] @launchArgs
} else {
    & $pythonCmd[0] @launchArgs
}
exit $LASTEXITCODE
