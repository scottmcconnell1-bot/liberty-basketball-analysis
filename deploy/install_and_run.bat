@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Liberty Basketball Analysis - Demo
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM Liberty Demo launcher (Windows)
REM First run (SFX TEMP extract): copy payload to
REM   %LOCALAPPDATA%\LibertyBasketballDemo\
REM create Desktop shortcut, then relaunch from that folder.
REM Subsequent runs (shortcut / LocalAppData): reuse .venv, skip winget if
REM Python is already found.
REM Prefer py -3.12 / py -3.13 (resolve to full path), then common install dirs,
REM then python on PATH. Winget install is attempted at most ONCE.
REM Start server with venv python + scripts\launch_liberty.py --no-browser.
REM Kill only the Liberty process tree (not all python.exe).
REM Cleanup: stop server + TEMP log. Keeps LocalAppData install, .venv, and
REM Desktop shortcut. Does NOT uninstall winget Python.
REM ---------------------------------------------------------------------------

set "PERSIST_DIR=%LOCALAPPDATA%\LibertyBasketballDemo"
set "SHORTCUT_NAME=Liberty Basketball Demo.lnk"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Normalize persist path (expand + strip trailing slash)
for %%I in ("%PERSIST_DIR%") do set "PERSIST_DIR=%%~fI"
if "%PERSIST_DIR:~-1%"=="\" set "PERSIST_DIR=%PERSIST_DIR:~0,-1%"

REM If not already running from the persistent install, copy + shortcut + relaunch.
if /I not "%SCRIPT_DIR%"=="%PERSIST_DIR%" (
  echo.
  echo ============================================================
  echo   Liberty Basketball Analysis - Demo Setup
  echo ============================================================
  echo.
  echo Installing demo to:
  echo   %PERSIST_DIR%
  echo.

  if not exist "%SCRIPT_DIR%\app.py" (
    echo ERROR: app.py not found in extract folder: %SCRIPT_DIR%
    goto :fail
  )

  if not exist "%PERSIST_DIR%" mkdir "%PERSIST_DIR%" 2>nul
  echo Copying package files ^(excluding .venv^)...
  robocopy "%SCRIPT_DIR%" "%PERSIST_DIR%" /E /XD .venv __pycache__ .git /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NP /R:2 /W:1 >nul
  set "RC=!ERRORLEVEL!"
  if !RC! GEQ 8 (
    echo ERROR: robocopy failed with code !RC!
    goto :fail
  )
  echo Copy complete.

  REM Ensure launcher bat is present at persist root
  if not exist "%PERSIST_DIR%\install_and_run.bat" (
    copy /y "%SCRIPT_DIR%\install_and_run.bat" "%PERSIST_DIR%\install_and_run.bat" >nul
  )

  call :create_desktop_shortcut
  if errorlevel 1 (
    echo WARNING: Desktop shortcut could not be created. You can still run:
    echo   "%PERSIST_DIR%\install_and_run.bat"
  ) else (
    echo Desktop shortcut created: %SHORTCUT_NAME%
  )

  echo.
  echo Launching from persistent install...
  echo.
  start "" "%PERSIST_DIR%\install_and_run.bat"
  exit /b 0
)

REM ========== Running from LocalAppData persistent install ==========
set "PACKAGE_DIR=%PERSIST_DIR%"
cd /d "%PACKAGE_DIR%"

set "VENV_DIR=%PACKAGE_DIR%\.venv"
set "LOG_FILE=%TEMP%\LibertyDemo_%RANDOM%.log"
set "PORT=8080"
set "PYTHON_EXE="
set "INSTALL_TRIED=0"
set "LAUNCHER_PID="

echo.
echo ============================================================
echo   Liberty Basketball Analysis - Demo
echo ============================================================
echo.
echo Install: %PACKAGE_DIR%
echo Log:     %LOG_FILE%
echo.
echo NOTE: winget-installed Python is permanent on this PC.
echo       Demo keeps this LocalAppData install, .venv, and Desktop shortcut.
echo       GPU AI / large model weights / game video are not in this demo.
echo.

REM Refresh / ensure Desktop shortcut exists on every LocalAppData run
call :create_desktop_shortcut >nul 2>&1

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

echo Using: !PYTHON_EXE!
echo.

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Creating virtual environment...
  "!PYTHON_EXE!" -m venv "%VENV_DIR%" >> "%LOG_FILE%" 2>&1
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
echo   Press any key in this window to stop the server.
echo   Install + Desktop shortcut will remain for next time.
echo ------------------------------------------------------------
echo.
pause >nul

goto :cleanup_ok

REM ======================== helpers ========================

:create_desktop_shortcut
REM Create/update Desktop shortcut via WScript.Shell.
REM Target: LocalAppData install_and_run.bat; WorkingDirectory: persist folder.
set "DESKTOP_DIR="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"
if not defined DESKTOP_DIR set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "LNK_PATH=%DESKTOP_DIR%\%SHORTCUT_NAME%"
set "TARGET_BAT=%PERSIST_DIR%\install_and_run.bat"
if not exist "%TARGET_BAT%" (
  echo ERROR: shortcut target missing: %TARGET_BAT%
  exit /b 1
)
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%LNK_PATH%');" ^
  "$s.TargetPath = '%TARGET_BAT%';" ^
  "$s.WorkingDirectory = '%PERSIST_DIR%';" ^
  "$s.WindowStyle = 1;" ^
  "$s.Description = 'Liberty Basketball Analysis Demo';" ^
  "$s.Save()"
if errorlevel 1 exit /b 1
if not exist "%LNK_PATH%" exit /b 1
echo Shortcut ready: %LNK_PATH%
exit /b 0

:refresh_path
REM Merge Machine + User Path from the registry into this session.
set "PATH="
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=!PATH!;%%B"
REM Prefer common Python install dirs even if not yet on registry PATH.
set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts;%LocalAppData%\Programs\Python\Launcher;%ProgramFiles%\Python312;%ProgramFiles%\Python313;%PATH%"
exit /b 0

:probe_common_python
REM Sets PYTHON_EXE to a known-good 3.12/3.13 interpreter if found.
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  "%LocalAppData%\Programs\Python\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    exit /b 0
  )
)
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
  "%LocalAppData%\Programs\Python\Python313\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,13) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"
    exit /b 0
  )
)
if exist "%ProgramFiles%\Python312\python.exe" (
  "%ProgramFiles%\Python312\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
    exit /b 0
  )
)
if exist "%ProgramFiles%\Python313\python.exe" (
  "%ProgramFiles%\Python313\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,13) else 1)" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PYTHON_EXE=%ProgramFiles%\Python313\python.exe"
    exit /b 0
  )
)
exit /b 1

:resolve_py_launcher
REM Prefer py launcher; store full path via sys.executable.
where py >nul 2>nul
if errorlevel 1 exit /b 1
for /f "usebackq delims=" %%P in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do (
  if exist "%%P" (
    "%%P" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
      set "PYTHON_EXE=%%P"
      exit /b 0
    )
  )
)
for /f "usebackq delims=" %%P in (`py -3.13 -c "import sys; print(sys.executable)" 2^>nul`) do (
  if exist "%%P" (
    "%%P" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,13) else 1)" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
      set "PYTHON_EXE=%%P"
      exit /b 0
    )
  )
)
exit /b 1

:resolve_path_python
where python >nul 2>nul
if errorlevel 1 exit /b 1
for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do (
  if exist "%%P" (
    "%%P" -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if v in ((3,12),(3,13)) else 1)" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
      set "PYTHON_EXE=%%P"
      exit /b 0
    )
  )
)
exit /b 1

:find_python
REM Single-pass discovery. Winget at most once (INSTALL_TRIED). Never goto :find_python.
call :resolve_py_launcher
if not errorlevel 1 exit /b 0

call :probe_common_python
if not errorlevel 1 exit /b 0

call :resolve_path_python
if not errorlevel 1 exit /b 0

if "!INSTALL_TRIED!"=="1" goto :python_not_found

echo Python 3.12-3.13 not found. Attempting to install via winget...
echo (winget Python is permanent — demo cleanup will not remove it.)
where winget >nul 2>nul
if errorlevel 1 (
  echo ERROR: winget not found.
  echo Install Python 3.12 from https://www.python.org/downloads/
  echo Then re-run install_and_run.bat.
  exit /b 1
)

set "INSTALL_TRIED=1"
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo ERROR: winget install of Python 3.12 failed.
  echo Install manually from https://www.python.org/downloads/
  exit /b 1
)

echo Python installed. Refreshing PATH and re-probing (no restart loop)...
call :refresh_path

call :resolve_py_launcher
if not errorlevel 1 exit /b 0

call :probe_common_python
if not errorlevel 1 exit /b 0

call :resolve_path_python
if not errorlevel 1 exit /b 0

:python_not_found
echo.
echo ERROR: Python 3.12 or 3.13 was not found after one install attempt.
echo Download and install Python 3.12 from:
echo   https://www.python.org/downloads/
echo During setup, enable "Add python.exe to PATH", then re-run this script.
echo.
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
echo Cleaning TEMP log only (keeping install + .venv + Desktop shortcut)...
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%" 2>nul
if exist "%LOG_FILE%.err" del /f /q "%LOG_FILE%.err" 2>nul
echo Done. Re-launch anytime via Desktop "Liberty Basketball Demo".
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
