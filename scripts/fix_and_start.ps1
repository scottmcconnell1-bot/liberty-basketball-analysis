# Liberty Basketball — repair OneDrive/git/venv issues and start the app.
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\fix_and_start.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host ""
Write-Host "============================================================"
Write-Host " Liberty Basketball — Fix and Start"
Write-Host "============================================================"
Write-Host ""

function Find-Python {
    foreach ($cmd in @(
        @("py", "-3.12"),
        @("py", "-3.13"),
        @("python"),
        @("python3")
    )) {
        if (-not (Get-Command $cmd[0] -ErrorAction SilentlyContinue)) { continue }
        try {
            $version = & $cmd[0] $cmd[1..($cmd.Length - 1)] -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
            if ($version -match "^3\.(12|13)$") {
                return $cmd
            }
        } catch {}
    }
    throw "Python 3.12 or 3.13 not found. Install from https://www.python.org/downloads/ (check Add to PATH)."
}

$pythonCmd = Find-Python
Write-Host "[fix] Using Python: $($pythonCmd -join ' ')"

# Backup game data before git repairs.
$backupDir = Join-Path $env:TEMP "liberty-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $backupDir | Out-Null
foreach ($item in @("film_analysis.db", "uploads")) {
    if (Test-Path (Join-Path $Root $item)) {
        Copy-Item (Join-Path $Root $item) $backupDir -Recurse -Force
        Write-Host "[fix] Backed up $item"
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
    Write-Host "[fix] Git repo corrupted — repairing .git from GitHub..."
    $clonePath = Join-Path $env:TEMP "liberty-git-repair-$(Get-Random)"
    if (Test-Path $clonePath) { Remove-Item $clonePath -Recurse -Force }
    git clone --branch cursor/q1-manual-ai-compare-ac1f --single-branch `
        https://github.com/scottmcconnell1-bot/liberty-basketball-analysis.git $clonePath
    if ($LASTEXITCODE -ne 0) { throw "git clone failed. Check internet connection." }
    if (Test-Path ".git") { Remove-Item ".git" -Recurse -Force }
    Copy-Item (Join-Path $clonePath ".git") ".git" -Recurse -Force
    git checkout cursor/q1-manual-ai-compare-ac1f
    git reset --hard origin/cursor/q1-manual-ai-compare-ac1f
    Remove-Item $clonePath -Recurse -Force
    Write-Host "[fix] Git repaired."
}

# Restore backed-up data.
foreach ($item in @("film_analysis.db", "uploads")) {
    $src = Join-Path $backupDir $item
    if (Test-Path $src) {
        Copy-Item $src $Root -Recurse -Force
        Write-Host "[fix] Restored $item"
    }
}

# Optional ffmpeg (skip msstore certificate errors).
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "[fix] Installing ffmpeg (winget source)..."
        winget install -e --id Gyan.FFmpeg --source winget `
            --accept-package-agreements --accept-source-agreements 2>$null | Out-Null
    }
}

Write-Host "[fix] Recreating virtual environment and starting app..."
& $pythonCmd[0] $pythonCmd[1..($pythonCmd.Length - 1)] scripts\launch_liberty.py --repair
exit $LASTEXITCODE
