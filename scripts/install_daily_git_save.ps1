# Install/replace Windows Scheduled Task: Liberty Daily Git Save (11:00 PM local).
# Run once (elevated not required for current-user task):
#   pwsh -File scripts/install_daily_git_save.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $PSScriptRoot "daily_git_save.ps1"
$TaskName = "Liberty Daily Git Save"

if (-not (Test-Path $ScriptPath)) {
    throw "Missing $ScriptPath"
}

$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCmd) { $pwsh = $pwshCmd.Source } else { $pwsh = (Get-Command powershell).Source }

$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$action = New-ScheduledTaskAction -Execute $pwsh -Argument $arg -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "11:00PM"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (daily 11:00 PM)."
Write-Host "Script: $ScriptPath"
Write-Host "Log: $RepoRoot\data\hoopsalytics\daily_git_save.log"
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
