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

Write-Step "Adding install_and_run.bat"
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
    "film_analysis.db"
)
foreach ($rel in $required) {
    $p = Join-Path $Staging $rel
    if (-not (Test-Path $p)) { throw "Missing required package file: $rel" }
    Write-Host "  OK $rel"
}

# Basic bat syntax: cmd /c with echo only parse via findstr markers
$bat = Get-Content (Join-Path $Staging "install_and_run.bat") -Raw
foreach ($marker in @(
    "find_python", "install_requirements", "stop_liberty_tree", "launch_liberty.py",
    "VENV_DIR", "INSTALL_TRIED", "PYTHON_EXE", "refresh_path", "probe_common_python",
    "PERSIST_DIR", "LibertyBasketballDemo", "create_desktop_shortcut",
    "resolve_desktop_dir", "remove_desktop_shortcuts", "wipe_session_install",
    "InternetShortcut", "OneDrive", "PUBLIC",
    "--cleanup-phase"
)) {
    if ($bat -notmatch [regex]::Escape($marker)) {
        throw "install_and_run.bat missing expected marker: $marker"
    }
}
if ($bat -notmatch '%PUBLIC%\\Desktop') {
    throw "install_and_run.bat must also write shortcut to %PUBLIC%\Desktop when present"
}
# Reject real restart loops (not comments that mention the forbidden pattern).
$gotoLines = ($bat -split "`r?`n") | Where-Object { $_ -match '(?i)^\s*goto\s+:(find_python|check_python)\b' }
if ($gotoLines) {
    throw "install_and_run.bat must not restart via goto :find_python / :check_python (infinite winget loop risk)"
}
if ($bat -notmatch 'INSTALL_TRIED=1') {
    throw "install_and_run.bat must set INSTALL_TRIED=1 before winget (one-shot install)"
}
if ($bat -match 'WScript\.Shell') {
    throw "install_and_run.bat must NOT use WScript.Shell for Desktop shortcuts (use plain .url echo)"
}
if ($bat -notmatch 'Liberty Basketball Demo\.url') {
    throw "install_and_run.bat must create Desktop InternetShortcut Liberty Basketball Demo.url"
}
if ($bat -notmatch '\[InternetShortcut\]') {
    throw "install_and_run.bat must write [InternetShortcut] via cmd echo"
}
if ($bat -notmatch 'robocopy') {
    throw "install_and_run.bat must robocopy payload to LocalAppData session dir"
}
if ($bat -notmatch 'wipe_session_install') {
    throw "install_and_run.bat must wipe LocalAppData session install on exit"
}
Write-Host "  OK install_and_run.bat markers (session install + Desktop URL shortcuts + full wipe + one-shot winget)"

Write-Step "Locating 7-Zip"
$sevenZip = Ensure-7Zip
Write-Host "7z: $sevenZip"
$sfx = Join-Path (Split-Path $sevenZip -Parent) "7z.sfx"
if (-not (Test-Path $sfx)) {
    throw "7z.sfx not found next to 7z.exe ($sfx). Reinstall 7-Zip full package."
}

Write-Step "Creating 7z archive"
# Stock 7z.sfx expects a 7z payload (-t7z), NOT zip. Using -tzip produces a broken SFX
# that fails with "Cannot open the file as [7z] archive / Is not archive".
$archivePath = Join-Path $PackageDir "LibertyDemo.7z"
if (Test-Path $archivePath) { Remove-Item $archivePath -Force }
# Archive contents of staging (so SFX extracts install_and_run.bat at top level of extract folder)
Push-Location $Staging
& $sevenZip a -t7z -mx=9 $archivePath * | Out-Host
Pop-Location
if (-not (Test-Path $archivePath)) { throw "7z archive was not created" }

Write-Step "Building SFX config + LibertyDemo.exe"
$configPath = Join-Path $PackageDir "config.txt"
@"
;!@Install@!UTF-8!
Title="Liberty Basketball Demo"
BeginPrompt="Install and run the Liberty Basketball Analysis demo?\n\nPython 3.12 may be installed via winget if missing (permanent).\nDemo files are removed when you finish.\nGPU AI weights are not included."
RunProgram="cmd /c install_and_run.bat"
;!@InstallEnd@!
"@ | Set-Content -Path $configPath -Encoding ASCII

$exePath = Join-Path $PackageDir "LibertyDemo.exe"
if (Test-Path $exePath) { Remove-Item $exePath -Force }

# Use visible 7z.sfx (not 7zCon.sfx / hidcon) so install progress is visible
cmd /c "copy /b `"$sfx`" + `"$configPath`" + `"$archivePath`" `"$exePath`""
if (-not (Test-Path $exePath)) { throw "LibertyDemo.exe was not created" }

$exeMb = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
Write-Host "LibertyDemo.exe: $exeMb MB"

Write-Step "Copying to repo dist/"
$distDir = Join-Path $RepoRoot "dist"
New-Item -ItemType Directory -Path $distDir -Force | Out-Null
Copy-Item $exePath (Join-Path $distDir "LibertyDemo.exe") -Force

$readme = @"
Liberty Basketball Analysis - Coach Demo
========================================

Double-click LibertyDemo.exe. It extracts a TEMP copy and runs
install_and_run.bat, which:

  1. Copies the demo to %LOCALAPPDATA%\LibertyBasketballDemo\ (session only)
  2. Creates Desktop InternetShortcut .url (plain cmd echo, no PowerShell):
       %USERPROFILE%\Desktop\Liberty Basketball Demo.url
       (also %PUBLIC%\Desktop when writable; OneDrive\Desktop fallback)
     Opens http://127.0.0.1:8080
  3. Relaunches from LocalAppData for the session
  4. Finds Python 3.12/3.13 or installs 3.12 via winget (once)
  5. Creates/reuses LocalAppData\.venv and installs requirements.txt
  6. Starts the app (scripts\launch_liberty.py --no-browser) and opens :8080
  7. On keypress: stops Liberty (PID-based), deletes Desktop shortcuts,
     wipes %LOCALAPPDATA%\LibertyBasketballDemo, deletes TEMP logs

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
- SFX: 7-Zip 7z.sfx + config.txt + LibertyDemo.7z (-t7z; stock sfx requires 7z not zip)
- Session install: %LOCALAPPDATA%\LibertyBasketballDemo (wiped on exit)
- Known caveats:
  * winget Python (if installed) remains after cleanup
  * GPU AI / YOLO inference is not in the demo
  * First run needs network for pip wheels
  * If something already serves port 8080, stop it or change PORT in the bat

Rebuild
-------
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1

Installer source of truth: deploy\install_and_run.bat
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
