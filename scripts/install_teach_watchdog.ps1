# Install/replace Windows Scheduled Task: Liberty Teach Watchdog (every 15 min).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_teach_watchdog.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $PSScriptRoot "watchdog_teach_loop.ps1"
$TaskName = "Liberty Teach Watchdog"

if (-not (Test-Path $ScriptPath)) {
    throw "Missing $ScriptPath"
}

$ps = (Get-Command powershell).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $RepoRoot
# Repeat every 15 minutes for 10 years (Task Scheduler rejects TimeSpan.MaxValue)
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (every 15 minutes)."
Write-Host "Script: $ScriptPath"
Write-Host "Log: $RepoRoot\data\hoopsalytics\teach_watchdog.log"
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List NextRunTime, LastRunTime, LastTaskResult
