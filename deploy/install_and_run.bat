@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Liberty Basketball Analysis - Demo
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM Liberty Demo launcher (Windows)
REM Prefer py -3.12, then py -3.13, then python.
REM Start server with venv python + scripts\launch_liberty.py --no-browser.
REM Kill only the Liberty process tree (not all python.exe).
REM Cleanup: local .venv + TEMP log. Does NOT uninstall winget Python.
REM ---------------------------------------------------------------------------

set "PACKAGE_DIR=%CD%"
set "VENV_DIR=%PACKAGE_DIR%\.venv"
set "LOG_FILE=%TEMP%\LibertyDemo_%RANDOM%.log"
set "PORT=8080"
set "PYTHON_CMD="
set "PYTHON_ARGS="
set "LAUNCHER_PID="

echo.
echo ============================================================
echo   Liberty Basketball Analysis - Demo
echo ============================================================
echo.
echo Package: %PACKAGE_DIR%
echo Log:     %LOG_FILE%
echo.
echo NOTE: winget-installed Python is permanent on this PC.
echo       Demo cleanup removes only the TEMP log and local .venv.
echo       GPU AI / large model weights / game video are not in this demo.
echo.

if not exist "%PACKAGE_DIR%\app.py" (
  echo ERROR: app.py not found. Run this from the Liberty package root.
  goto :fail
)
if not exist "%PACKAGE_DIR%\scripts\launch_liberty.py" (
  echo ERROR: scripts\launch_liberty.py not found.
  goto :fail
)

call :find_python
if errorlevel 1 goto :fail

echo Using: !PYTHON_CMD! !PYTHON_ARGS!
echo.

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Creating virtual environment...
  if defined PYTHON_ARGS (
    !PYTHON_CMD! !PYTHON_ARGS! -m venv "%VENV_DIR%" >> "%LOG_FILE%" 2>&1
  ) else (
    !PYTHON_CMD! -m venv "%VENV_DIR%" >> "%LOG_FILE%" 2>&1
  )
  if errorlevel 1 (
    echo ERROR: Failed to create venv. See %LOG_FILE%
    goto :fail
  )
) else (
  echo Reusing existing virtual environment.
)

set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo ERROR: venv python missing: %VENV_PY%
  goto :fail
)

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1

call :install_requirements
if errorlevel 1 goto :fail

echo.
echo Starting Liberty on http://127.0.0.1:%PORT% ...
echo.

REM Start via venv python (NOT bare "start scripts\launch_liberty.py").
REM Equivalent to: start ... "%VENV_DIR%\Scripts\python.exe" scripts\launch_liberty.py --no-browser
REM Start-Process is used so we can store the launcher PID for safe cleanup.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$p = Start-Process -FilePath '%VENV_PY%' -ArgumentList @('scripts\launch_liberty.py','--no-browser','--port','%PORT%') -WorkingDirectory '%PACKAGE_DIR%' -WindowStyle Minimized -PassThru -RedirectStandardOutput '%LOG_FILE%' -RedirectStandardError '%LOG_FILE%.err'; $p.Id"`) do (
  set "LAUNCHER_PID=%%P"
)

if not defined LAUNCHER_PID (
  echo WARNING: Could not capture launcher PID; will stop by command-line match on exit.
) else (
  echo Launcher PID: !LAUNCHER_PID!
)

echo Waiting for server...
set /a "WAITED=0"
:wait_loop
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/' -TimeoutSec 2; if ($r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :server_ready
set /a "WAITED+=2"
if !WAITED! GEQ 180 (
  echo ERROR: Server did not become ready within 180s.
  echo See log: %LOG_FILE%
  if exist "%LOG_FILE%.err" type "%LOG_FILE%.err"
  goto :cleanup_fail
)
timeout /t 2 /nobreak >nul
goto :wait_loop

:server_ready
echo Server ready.
start "" "http://127.0.0.1:%PORT%/"
echo.
echo ------------------------------------------------------------
echo   Demo is running at http://127.0.0.1:%PORT%/
echo   Press any key in this window to stop and clean up.
echo ------------------------------------------------------------
echo.
pause >nul

goto :cleanup_ok

REM ======================== helpers ========================

:find_python
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3.12"
    exit /b 0
  )
  py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,13) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3.13"
    exit /b 0
  )
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if v in ((3,12),(3,13)) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=python"
    set "PYTHON_ARGS="
    exit /b 0
  )
)

echo Python 3.12/3.13 not found. Attempting winget install of Python 3.12...
echo (winget Python is permanent — demo cleanup will not remove it.)
where winget >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo ERROR: winget not found. Install Python 3.12 from https://www.python.org/downloads/
  exit /b 1
)
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo ERROR: winget install failed.
  exit /b 1
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3.12 -c "pass" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3.12"
    exit /b 0
  )
)

echo ERROR: Python installed but not on PATH yet. Open a new Command Prompt
echo        and run install_and_run.bat again.
exit /b 1

:install_requirements
if exist "%PACKAGE_DIR%\requirements.txt" (
  echo Installing from requirements.txt ...
  "%VENV_PY%" -m pip install -r "%PACKAGE_DIR%\requirements.txt" >> "%LOG_FILE%" 2>&1
  if !ERRORLEVEL! EQU 0 exit /b 0
  echo WARNING: requirements.txt install failed — see log. Trying fallbacks...
)

if exist "%PACKAGE_DIR%\requirements-dev.txt" (
  echo Installing from requirements-dev.txt ...
  "%VENV_PY%" -m pip install -r "%PACKAGE_DIR%\requirements-dev.txt" >> "%LOG_FILE%" 2>&1
  if !ERRORLEVEL! EQU 0 exit /b 0
  echo WARNING: requirements-dev.txt install failed.
) else (
  echo NOTE: requirements-dev.txt not present — skipped.
)

echo ERROR: Could not install Python dependencies. See %LOG_FILE%
exit /b 1

:stop_liberty_tree
echo Stopping Liberty processes only (not all python.exe)...
powershell -NoProfile -Command ^
  "$port = %PORT%;" ^
  "$pkg = [regex]::Escape('%PACKAGE_DIR%');" ^
  "$launchPid = '%LAUNCHER_PID%';" ^
  "if ($launchPid -match '^\d+$') {" ^
  "  try {" ^
  "    $root = Get-CimInstance Win32_Process -Filter \"ProcessId=$launchPid\" -ErrorAction SilentlyContinue;" ^
  "    if ($root) {" ^
  "      $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq [int]$launchPid };" ^
  "      foreach ($c in $children) { Stop-Process -Id $c.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('  child PID ' + $c.ProcessId) }" ^
  "      Stop-Process -Id ([int]$launchPid) -Force -ErrorAction SilentlyContinue; Write-Host ('  launcher PID ' + $launchPid)" ^
  "    }" ^
  "  } catch {}" ^
  "}" ^
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" |" ^
  "  Where-Object {" ^
  "    $_.CommandLine -and (" ^
  "      $_.CommandLine -match 'launch_liberty\.py' -or" ^
  "      ($_.CommandLine -match 'app\.py' -and $_.CommandLine -match $pkg)" ^
  "    )" ^
  "  } | ForEach-Object {" ^
  "    Write-Host ('  matching PID ' + $_.ProcessId);" ^
  "    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue" ^
  "  };" ^
  "Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |" ^
  "  Select-Object -ExpandProperty OwningProcess -Unique |" ^
  "  ForEach-Object {" ^
  "    $pid_ = $_;" ^
  "    try {" ^
  "      $cl = (Get-CimInstance Win32_Process -Filter \"ProcessId=$pid_\").CommandLine;" ^
  "      if ($cl -and ($cl -match 'app\.py|launch_liberty')) {" ^
  "        Write-Host ('  port listener PID ' + $pid_);" ^
  "        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue" ^
  "      }" ^
  "    } catch {}" ^
  "  }"
exit /b 0

:cleanup_ok
call :stop_liberty_tree
echo Cleaning demo venv and log...
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%" 2>nul
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%" 2>nul
if exist "%LOG_FILE%.err" del /f /q "%LOG_FILE%.err" 2>nul
echo Done. (System Python from winget was left installed, if used.)
echo.
pause
exit /b 0

:cleanup_fail
call :stop_liberty_tree
echo Leaving .venv in place for debugging. Log: %LOG_FILE%
pause
exit /b 1

:fail
echo.
echo Setup failed. Log (if any): %LOG_FILE%
pause
exit /b 1
