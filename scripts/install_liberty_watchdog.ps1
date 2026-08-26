# Install/replace Windows Scheduled Task: Liberty Server Watchdog (every 30 min).
# Keeps http://127.0.0.1:8080 up for Tailscale Funnel / coach portal.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_liberty_watchdog.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $PSScriptRoot "watchdog_liberty_server.ps1"
$TaskName = "Liberty Server Watchdog"

if (-not (Test-Path $ScriptPath)) {
    throw "Missing $ScriptPath"
}

$ps = (Get-Command powershell).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $RepoRoot
# Repeat every 30 minutes (coach funnel 502 recovery)
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (every 30 minutes)."
Write-Host "Script: $ScriptPath"
Write-Host "Log: $RepoRoot\data\hoopsalytics\liberty_watchdog.log"
Write-Host ""
Write-Host "Run once now:"
& $ps -NoProfile -ExecutionPolicy Bypass -File $ScriptPath
Write-Host ""
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List NextRunTime, LastRunTime, LastTaskResult
