# Backup Liberty project files for moving to another computer.
# Run from repo root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\backup_for_transfer.ps1
# Optional USB or folder:
#   powershell -ExecutionPolicy Bypass -File scripts\backup_for_transfer.ps1 -Destination "E:\Liberty-Transfer"

param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host "[backup] $Message" -ForegroundColor Cyan
}

if (-not $Destination) {
    $Destination = Join-Path ([Environment]::GetFolderPath("Desktop")) "Liberty-Transfer"
}

Write-Step "Repo: $Root"
Write-Step "Destination: $Destination"

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination "uploads") | Out-Null

$db = Join-Path $Root "film_analysis.db"
if (Test-Path $db) {
    Copy-Item $db (Join-Path $Destination "film_analysis.db") -Force
    Write-Step "Copied film_analysis.db"
} else {
    Write-Host "[backup] WARNING: film_analysis.db not found" -ForegroundColor Yellow
}

$uploads = Join-Path $Root "uploads"
if (Test-Path $uploads) {
    Copy-Item "$uploads\*" (Join-Path $Destination "uploads") -Recurse -Force
    Write-Step "Copied uploads folder"
} else {
    Write-Host "[backup] WARNING: uploads folder not found" -ForegroundColor Yellow
}

$searchRoots = @(
    [Environment]::GetFolderPath("UserProfile") + "\Downloads",
    [Environment]::GetFolderPath("Desktop"),
    $Root
)
$patterns = @("events_*.json", "summary_*.json", "liberty-manual-tags*.json")
$exportDir = Join-Path $Destination "tag-exports"
New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
$found = 0
foreach ($searchRoot in $searchRoots) {
    if (-not (Test-Path $searchRoot)) { continue }
    foreach ($pattern in $patterns) {
        Get-ChildItem -Path $searchRoot -Filter $pattern -File -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item $_.FullName (Join-Path $exportDir $_.Name) -Force
            $found++
            Write-Step "Copied tag export: $($_.Name)"
        }
    }
}
if ($found -eq 0) {
    Write-Host "[backup] No events_*.json exports found on disk yet." -ForegroundColor Yellow
}

$readme = @"
Liberty Basketball — transfer package
====================================
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm")

IN THIS FOLDER:
  film_analysis.db     - video list, AI results, settings
  uploads\             - video files
  tag-exports\         - any events_*.json found on this PC

STILL REQUIRED (browser only — not in these files):
  Manual Film Tool tags live in your browser until exported.

  1. Run Start Liberty.bat
  2. Open http://127.0.0.1:8080/film in the browser you used for tagging
  3. Press F12 -> Console, paste the script from scripts\browser_export_manual_tags.js
  4. Save liberty-manual-tags-backup.json into this folder

Copy this entire Liberty-Transfer folder to USB or the new laptop.
On the new laptop: Film Tool -> Games -> Import tags.
"@
Set-Content -Path (Join-Path $Destination "README.txt") -Value $readme -Encoding UTF8

Write-Host ""
Write-Host "Backup folder ready: $Destination" -ForegroundColor Green
Write-Host "Next: export manual tags from the browser (see README.txt in that folder)." -ForegroundColor Yellow
