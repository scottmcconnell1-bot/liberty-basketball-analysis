# Build LibertyDemo Windows package + 7-Zip SFX executable.
# Does not touch GPU AI jobs. Safe to run while analysis is in progress.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1
#
# Output:
#   C:\Temp\LibertyDemoPackage\   (staging)
#   C:\Temp\LibertyDemoPackage\LibertyDemo.exe
#   <repo>\dist\LibertyDemo.exe
#   <repo>\dist\README_DEMO.txt

[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$PackageDir = "C:\Temp\LibertyDemoPackage",
    [string]$StagingName = "LibertyDemo"
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $RepoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Ensure-7Zip {
    $candidates = @(
        "${env:ProgramFiles}\7-Zip\7z.exe",
        "${env:ProgramFiles(x86)}\7-Zip\7z.exe",
        "C:\Program Files\7-Zip\7z.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    $onPath = Get-Command 7z -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    Write-Step "Installing 7-Zip via winget"
    # Redirect so winget text does not become the function's return value
    & winget install -e --id 7zip.7zip --accept-package-agreements --accept-source-agreements | Out-Host
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    throw "7-Zip not found after winget install"
}

Write-Step "Preparing package directory"
if (Test-Path $PackageDir) {
    # Keep any prior LibertyDemo.exe backup aside; wipe staging content carefully
    Get-ChildItem $PackageDir -Force | Where-Object { $_.Name -ne "LibertyDemo.exe" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
} else {
    New-Item -ItemType Directory -Path $PackageDir | Out-Null
}

$Staging = Join-Path $PackageDir $StagingName
if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
New-Item -ItemType Directory -Path $Staging | Out-Null

$ExcludeDirList = @(
    ".git", ".venv", ".venv312", "__pycache__", "build", "dist",
    ".pytest_cache", "logs", "uploads", "tag-exports", "experiments",
    "benchmarks", ".idea", ".vscode", "node_modules", ".mypy_cache",
    ".ruff_cache", "htmlcov", ".tox", "agent-transcripts", "videos"
)
$ExcludeDirNames = @{}
foreach ($d in $ExcludeDirList) { $ExcludeDirNames[$d.ToLowerInvariant()] = $true }

$ExcludeFileGlobs = @(
    "*.pyc", "*.pyo", "*.mp4", "*.mov", "*.avi", "*.mkv",
    "*.pt", "*.pth", "*.onnx", "*.task", "*.ckpt", "*.safetensors",
    "film_analysis.db-wal", "film_analysis.db-shm",
    "film_analysis.demo.db", "_tmp_*.py", ".DS_Store"
)

Write-Step "Copying repo (with exclusions)"
$copiedFiles = 0
$skippedBytes = 0L

Get-ChildItem -Path $RepoRoot -Force | ForEach-Object {
    $name = $_.Name
    if ($ExcludeDirNames.ContainsKey($name.ToLowerInvariant())) {
        if ($_.PSIsContainer) {
            $sum = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
                Measure-Object Length -Sum).Sum
            if ($sum) { $script:skippedBytes += [int64]$sum }
        } else {
            $script:skippedBytes += $_.Length
        }
        Write-Host "  exclude: $name"
        return
    }

    $dest = Join-Path $Staging $name
    if ($_.PSIsContainer) {
        $rcArgs = @($_.FullName, $dest, "/E", "/XD") + $ExcludeDirList + @("/XF") + $ExcludeFileGlobs + @(
            "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1"
        )
        & robocopy @rcArgs | Out-Null
        # robocopy exit codes 0-7 are success
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $name (code $LASTEXITCODE)" }
    } else {
        $skip = $false
        foreach ($g in $ExcludeFileGlobs) {
            if ($name -like $g) { $skip = $true; break }
        }
        # Always skip full-size root weights / huge media listed above
        if ($skip) {
            $script:skippedBytes += $_.Length
            Write-Host "  exclude file: $name"
            return
        }
        if ($name -eq "film_analysis.db") {
            # handled below
            return
        }
        Copy-Item $_.FullName $dest -Force
        $copiedFiles++
    }
}

# Second pass: strip excluded dir names that robocopy may still have nested
Get-ChildItem $Staging -Recurse -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $ExcludeDirNames.ContainsKey($_.Name.ToLowerInvariant()) } |
    Sort-Object { $_.FullName.Length } -Descending |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

Get-ChildItem $Staging -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $n = $_.Name
        foreach ($g in $ExcludeFileGlobs) { if ($n -like $g) { return $true } }
        return $false
    } |
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }

Write-Step "Creating slim demo database"
$demoDbScript = Join-Path $RepoRoot "scripts\create_demo_db.py"
$demoDbOut = Join-Path $Staging "film_analysis.db"
& python $demoDbScript $demoDbOut
if ($LASTEXITCODE -ne 0) { throw "create_demo_db.py failed" }
$demoDbMb = [math]::Round((Get-Item $demoDbOut).Length / 1MB, 2)
Write-Host "Demo DB size: $demoDbMb MB"

# Keep an empty uploads dir so the app can write
New-Item -ItemType Directory -Path (Join-Path $Staging "uploads") -Force | Out-Null
# Tiny models placeholder note (weights excluded)
$modelsDir = Join-Path $Staging "models"
New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
@"
Demo package: large YOLO / court / ball detector weights (.pt) were excluded to keep
the download small. The web app, Film Tool, roster/schedule views, and tagging UI
still run. GPU AI analysis is not available in this demo.
"@ | Set-Content -Path (Join-Path $modelsDir "README_DEMO_MODELS.txt") -Encoding UTF8

Write-Step "Adding install_and_run.bat (web DONE; no Desktop shortcuts)"
Copy-Item (Join-Path $RepoRoot "deploy\install_and_run.bat") (Join-Path $Staging "install_and_run.bat") -Force

# Also mirror under deploy/ inside package for discoverability
$deployPkg = Join-Path $Staging "deploy"
if (-not (Test-Path $deployPkg)) { New-Item -ItemType Directory -Path $deployPkg | Out-Null }
Copy-Item (Join-Path $RepoRoot "deploy\install_and_run.bat") (Join-Path $deployPkg "install_and_run.bat") -Force

Write-Step "Smoke-check package contents"
$required = @(
    "app.py",
    "scripts\launch_liberty.py",
    "requirements.txt",
    "install_and_run.bat",
    "blueprints\demo.py",
    "film_analysis.db"
)
foreach ($rel in $required) {
    $p = Join-Path $Staging $rel
    if (-not (Test-Path $p)) { throw "Missing required package file: $rel" }
    Write-Host "  OK $rel"
}

# Basic bat syntax markers — no Desktop shortcut creation
$bat = Get-Content (Join-Path $Staging "install_and_run.bat") -Raw
foreach ($marker in @(
    "find_python", "install_requirements", "stop_liberty_tree", "launch_liberty.py",
    "VENV_DIR", "INSTALL_TRIED", "PYTHON_EXE", "refresh_path", "probe_common_python",
    "PERSIST_DIR", "LibertyBasketballDemo", "wipe_session_install",
    "wipe_temp_leftovers", "wait_for_server_exit", "open_browser",
    "DEMO_MODE", "--cleanup-phase", "DEMO RUNNING",
    "[BROWSER]", "Start-Process",
    "LibertyDemo_run.log", "pick_port", "PORT=8090",
    'cd /d "%~dp0"'
)) {
    if ($bat -notmatch [regex]::Escape($marker)) {
        throw "install_and_run.bat missing expected marker: $marker"
    }
}
# Reject real restart loops (not comments that mention the forbidden pattern).
$gotoLines = ($bat -split "`r?`n") | Where-Object { $_ -match '(?i)^\s*goto\s+:(find_python|check_python)\b' }
if ($gotoLines) {
    throw "install_and_run.bat must not restart via goto :find_python / :check_python (infinite winget loop risk)"
}
if ($bat -notmatch 'INSTALL_TRIED=1') {
    throw "install_and_run.bat must set INSTALL_TRIED=1 before winget (one-shot install)"
}
if ($bat -match 'create_desktop_shortcut' -or $bat -match '(?m)^\s*call\s+:create_desktop_shortcut\b') {
    throw "install_and_run.bat must NOT create Desktop shortcuts"
}
if ($bat -match 'WScript\.Shell') {
    throw "install_and_run.bat must NOT use WScript.Shell"
}
if ($bat -match '\[InternetShortcut\]') {
    throw "install_and_run.bat must NOT write InternetShortcut .url files"
}
if ($bat -match 'demo_done_dialog\.ps1' -or $bat -match 'System\.Windows\.Forms') {
    throw "install_and_run.bat must NOT use WinForms DONE dialog (web DONE button instead)"
}
if ($bat -notmatch 'DEMO_MODE=1') {
    throw "install_and_run.bat must set DEMO_MODE=1 for the web UI"
}
if ($bat -notmatch 'start\s+""\s+"http://127\.0\.0\.1:%PORT%/"' -and $bat -notmatch 'start\s+""\s+"%OPEN_URL%"') {
    throw "install_and_run.bat must open browser via start "" url"
}
if ($bat -notmatch 'robocopy') {
    throw "install_and_run.bat must robocopy payload to LocalAppData session dir"
}
if ($bat -notmatch 'wipe_session_install') {
    throw "install_and_run.bat must wipe LocalAppData session install on exit"
}
if ($bat -match 'start\s+""\s+"%PERSIST_DIR%\\install_and_run\.bat"') {
    throw "install_and_run.bat must NOT relaunch via start+exit (keep one visible console)"
}
# First executable lines after @echo off must cd to script dir
$batLines = ($bat -split "`r?`n") | Where-Object { $_.Trim() -ne "" }
if ($batLines.Count -lt 2 -or $batLines[0] -notmatch '(?i)^@echo off' -or $batLines[1] -notmatch '(?i)^cd /d "%~dp0"') {
    throw "install_and_run.bat must start with @echo off then cd /d `"%~dp0`""
}

# App must expose demo DONE API + template button
$demoPy = Get-Content (Join-Path $Staging "blueprints\demo.py") -Raw
if ($demoPy -notmatch '/api/demo/done' -or $demoPy -notmatch 'demo_mode_enabled') {
    throw "blueprints/demo.py must expose /api/demo/done and demo_mode_enabled"
}
$baseHtml = Get-Content (Join-Path $Staging "templates\base.html") -Raw
if ($baseHtml -notmatch 'demo-done-btn' -or $baseHtml -notmatch 'demo_mode') {
    throw "templates/base.html must show DONE button when demo_mode is on"
}
$appPy = Get-Content (Join-Path $Staging "app.py") -Raw
if ($appPy -notmatch 'demo_bp' -or $appPy -notmatch 'demo_mode') {
    throw "app.py must register demo_bp and inject demo_mode"
}
Write-Host "  OK install_and_run.bat markers (DEMO_MODE + browser + port fallback + same-console + no shortcuts)"

Write-Step "Locating 7-Zip + installer SFX module (7zSD.sfx)"
$sevenZip = Ensure-7Zip
Write-Host "7z: $sevenZip"
# CRITICAL: Stock Program Files\7-Zip\7z.sfx does NOT support RunProgram / Install config.
# It only extracts. Use LZMA SDK 7zSD.sfx (vendored under tools\sfx\) so the bat auto-starts.
$sfx = Join-Path $RepoRoot "tools\sfx\7zSD.sfx"
if (-not (Test-Path $sfx)) {
    throw "Missing tools\sfx\7zSD.sfx (LZMA SDK installer module). Stock 7z.sfx ignores RunProgram."
}
$sfxBytes = [System.IO.File]::ReadAllBytes($sfx)
$sfxAscii = [System.Text.Encoding]::GetEncoding(28591).GetString($sfxBytes)
if ($sfxAscii -notlike "*RunProgram*") {
    throw "SFX module at $sfx does not embed RunProgram support. Need LZMA SDK 7zSD.sfx."
}
$sfxKb = [math]::Round($sfxBytes.Length / 1KB, 0)
Write-Host "SFX: $sfx ($sfxKb KB, RunProgram=yes)"

Write-Step "Creating 7z archive"
# 7zSD.sfx expects a 7z payload (-t7z), NOT zip.
$archivePath = Join-Path $PackageDir "LibertyDemo.7z"
if (Test-Path $archivePath) { Remove-Item $archivePath -Force }
# Archive contents of staging (so SFX extracts install_and_run.bat at top level of extract folder)
Push-Location $Staging
& $sevenZip a -t7z -mx=9 $archivePath * | Out-Host
Pop-Location
if (-not (Test-Path $archivePath)) { throw "7z archive was not created" }

Write-Step "Building SFX config + LibertyDemo.exe"
$configPath = Join-Path $PackageDir "config.txt"
# Visible console: cmd /c (NOT hidcon:). User must see pip/server errors.
$configBody = @(
    ';!@Install@!UTF-8!',
    'Title="Liberty Basketball Demo"',
    'BeginPrompt="Install and run the Liberty Basketball Analysis demo?\n\nPython 3.12 may be installed via winget if missing (permanent).\nWhen finished, click DONE in the browser top menu to remove all demo files.\nGPU AI weights are not included."',
    'Directory=""',
    'RunProgram="cmd /c install_and_run.bat"',
    ';!@InstallEnd@!'
) -join "`r`n"
[System.IO.File]::WriteAllText($configPath, $configBody + "`r`n", [System.Text.Encoding]::ASCII)

$configRaw = Get-Content $configPath -Raw
if ($configRaw -match '(?i)hidcon') {
    throw "config.txt must NOT use hidcon (errors must be visible)"
}
if ($configRaw -notmatch 'Directory=""') {
    throw 'config.txt must set Directory="" so cmd resolves to system cmd.exe (not archive-root cmd)'
}
if ($configRaw -notmatch 'RunProgram="cmd /c install_and_run\.bat"') {
    throw 'config.txt must use RunProgram="cmd /c install_and_run.bat"'
}

$exePath = Join-Path $PackageDir "LibertyDemo.exe"
if (Test-Path $exePath) { Remove-Item $exePath -Force }

cmd /c "copy /b `"$sfx`" + `"$configPath`" + `"$archivePath`" `"$exePath`""
if (-not (Test-Path $exePath)) { throw "LibertyDemo.exe was not created" }

# Verify the built exe embeds Install config (not stock 7z.sfx padding)
$exePrefix = New-Object byte[] 200000
$fs = [System.IO.File]::OpenRead($exePath)
[void]$fs.Read($exePrefix, 0, 200000)
$fs.Close()
$exeAscii = [System.Text.Encoding]::GetEncoding(28591).GetString($exePrefix)
if ($exeAscii -notlike '*RunProgram="cmd /c install_and_run.bat"*') {
    throw "Built LibertyDemo.exe missing visible RunProgram=cmd /c install_and_run.bat in SFX config"
}
if ($exeAscii -match '(?i)hidcon:') {
    throw "Built LibertyDemo.exe must not use hidcon"
}
Write-Host "  OK SFX config embedded (visible cmd /c, no hidcon)"

$exeMb = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
Write-Host "LibertyDemo.exe: $exeMb MB"

Write-Step "Copying to repo dist/"
$distDir = Join-Path $RepoRoot "dist"
New-Item -ItemType Directory -Path $distDir -Force | Out-Null
Copy-Item $exePath (Join-Path $distDir "LibertyDemo.exe") -Force

$readme = @"
Liberty Basketball Analysis - Coach Demo
========================================

Double-click LibertyDemo.exe. Click Yes on the prompt. It extracts to TEMP,
opens a VISIBLE console, and runs install_and_run.bat, which:

  1. Copies the demo to %LOCALAPPDATA%\LibertyBasketballDemo\ (session only)
  2. Continues in the SAME console from LocalAppData (NO Desktop shortcut)
  3. Finds Python 3.12/3.13 or installs 3.12 via winget (once)
  4. Creates/reuses LocalAppData\.venv and installs requirements.txt
  5. Starts the app with DEMO_MODE=1 (scripts\launch_liberty.py --no-browser)
  6. Uses port 8080, or 8090 if 8080 is busy; opens the browser to that URL
  7. Coach clicks DONE in the web app top menu → POST /api/demo/done
     schedules TEMP cleanup, stops the server; bat then wipes
     %LOCALAPPDATA%\LibertyBasketballDemo and TEMP LibertyDemo_* leftovers.
     winget Python is NOT uninstalled.
  Debug log: %TEMP%\LibertyDemo_run.log

Coach blurb
-----------
Liberty is a local basketball film + tagging workstation for high-school coaches.
This demo lets you click through the dashboard, Film Tool, roster/schedule views,
and reports without cloud signup. It is a local Windows package - no GPU AI
analysis in this build (detector weights omitted to keep the download small).

Build notes ($(Get-Date -Format "yyyy-MM-dd"))
------------------------
- Staging: $PackageDir\$StagingName
- Demo DB: slim film_analysis.db ($demoDbMb MB) - schema + teams/games/roster/events;
  omitted heavy detections/review_items (and credentials). Full source DB was ~123 MB.
- Excluded: .git, .venv, __pycache__, build, dist, .pytest_cache, logs, uploads,
  tag-exports, experiments, benchmarks, .idea, .vscode, videos, large .pt/.task
  weights, media files
- SFX: LZMA SDK 7zSD.sfx (tools\sfx\) + config.txt + LibertyDemo.7z
  (NOT stock 7z.sfx — that module ignores RunProgram and only extracts)
- RunProgram="cmd /c install_and_run.bat" with Directory="" (system cmd; visible console; never hidcon)
  Without Directory="", 7zSD looks for "cmd" inside the archive and never starts the bat.
- Session install: %LOCALAPPDATA%\LibertyBasketballDemo (wiped on DONE)
- Exit UX: DONE button in web nav (DEMO_MODE); bat waits for server exit then cleans up
- Known caveats:
  * winget Python (if installed) remains after cleanup
  * GPU AI / YOLO inference is not in the demo
  * First run needs network for pip wheels
  * If 8080 is busy, demo uses 8090 automatically

Rebuild
-------
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1

Installer source of truth: deploy\install_and_run.bat + blueprints\demo.py
"@
Set-Content -Path (Join-Path $distDir "README_DEMO.txt") -Value $readme -Encoding ASCII
Set-Content -Path (Join-Path $PackageDir "README_DEMO.txt") -Value $readme -Encoding ASCII

Write-Step "Summary"
$stagingMb = [math]::Round(
    ((Get-ChildItem $Staging -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 2)
Write-Host "Staging folder: $Staging ($stagingMb MB)"
Write-Host "EXE:            $exePath ($exeMb MB)"
Write-Host "Repo copy:      $(Join-Path $distDir 'LibertyDemo.exe')"
Write-Host "Demo DB:        $demoDbMb MB"
Write-Host "Skipped ~:      $([math]::Round($skippedBytes/1MB,1)) MB of excluded trees/files"
Write-Host "Done."
