# Liberty server watchdog: if Flask is not healthy on :8080, start it again.
# Safe to run every 30 minutes (does not restart a healthy server).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/watchdog_liberty_server.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "data\hoopsalytics"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

try {
    & py -3.12 (Join-Path $RepoRoot "scripts\watchdog_liberty_server.py")
    exit $LASTEXITCODE
}
catch {
    $line = "{0} ERROR: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $_.Exception.Message
    Add-Content -Path (Join-Path $LogDir "liberty_watchdog.log") -Value $line
    Write-Host $line
    exit 1
}
