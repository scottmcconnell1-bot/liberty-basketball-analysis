# Teach-loop watchdog: if Liberty teach loop is dead, start it again.
# Does NOT kill a live analysis_launcher. Safe to run every 15 minutes.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/watchdog_teach_loop.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "data\hoopsalytics"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "teach_watchdog.log"

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Test-TeachLoopAlive {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        $cmd = [string]$p.CommandLine
        if ($cmd -match 'hoops_teach_loop\.py') {
            return $true
        }
    }
    return $false
}

try {
    Write-Log "=== teach watchdog start ==="
    if (Test-TeachLoopAlive) {
        Write-Log "Teach loop alive - no action"
        Write-Log "=== teach watchdog done ==="
        exit 0
    }

    Write-Log "Teach loop DEAD - starting detached teach (keeps Flask if already up)"
    & py -3.12 (Join-Path $RepoRoot "scripts\start_hoops_teach_detached.py")
    $code = $LASTEXITCODE
    Start-Sleep -Seconds 3
    $alive = Test-TeachLoopAlive
    Write-Log ("start exit={0} teach_alive={1}" -f $code, $alive)
    if (-not $alive) {
        Write-Log "ERROR: teach loop still not alive after start"
        Write-Log "=== teach watchdog failed ==="
        exit 1
    }
    Write-Log "=== teach watchdog done ==="
    exit 0
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    Write-Log "=== teach watchdog failed ==="
    exit 1
}
