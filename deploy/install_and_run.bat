@echo off
cd /d "%~dp0"
setlocal EnableExtensions EnableDelayedExpansion
title Liberty Basketball Analysis - Demo

REM ---------------------------------------------------------------------------
REM Liberty Demo launcher (Windows)
REM First run (SFX TEMP extract): copy payload to
REM   %LOCALAPPDATA%\LibertyBasketballDemo\
REM then CONTINUE in this same visible console (no second window / no shortcut).
REM Prefer py -3.12 / py -3.13, then common dirs, then PATH. Winget at most ONCE.
REM Start server with DEMO_MODE=1 + launch_liberty.py --no-browser.
REM Bat opens the browser after server is ready. Port 8080, else 8090.
REM Wait for server exit (web DONE), then wipe LocalAppData + TEMP leftovers.
REM Does NOT uninstall winget Python. NO Desktop shortcuts.
REM ---------------------------------------------------------------------------

set "LOG_FILE=%TEMP%\LibertyDemo_run.log"
echo ===== LibertyDemo start %DATE% %TIME% =====> "%LOG_FILE%"
call :log "cwd=%CD%"
call :log "script=%~f0"

set "PERSIST_DIR=%LOCALAPPDATA%\LibertyBasketballDemo"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Normalize persist path (expand + strip trailing slash)
for %%I in ("%PERSIST_DIR%") do set "PERSIST_DIR=%%~fI"
if "%PERSIST_DIR:~-1%"=="\" set "PERSIST_DIR=%PERSIST_DIR:~0,-1%"

REM Cleanup handoff: bat may live under PERSIST_DIR; wipe from a TEMP copy.
if /I "%~1"=="--cleanup-phase" (
  set "PACKAGE_DIR=%PERSIST_DIR%"
  set "PORT=8080"
  if not "%~2"=="" set "LOG_FILE=%~2"
  if not "%~3"=="" set "LAUNCHER_PID=%~3"
  if /I "%~4"=="fail" (goto :cleanup_fail_body) else (goto :cleanup_ok_body)
)

REM If not already running from the session install, copy then CONTINUE here.
if /I not "%SCRIPT_DIR%"=="%PERSIST_DIR%" (
  call :log ""
  call :log "============================================================"
  call :log "  Liberty Basketball Analysis - Demo Setup"
  call :log "============================================================"
  call :log "Installing demo for this session to: %PERSIST_DIR%"

  if not exist "%SCRIPT_DIR%\app.py" (
    call :log "ERROR: app.py not found in extract folder: %SCRIPT_DIR%"
    goto :fail
  )

  if not exist "%PERSIST_DIR%" mkdir "%PERSIST_DIR%" 2>nul
  call :log "Copying package files (excluding .venv)..."
  robocopy "%SCRIPT_DIR%" "%PERSIST_DIR%" /E /XD .venv __pycache__ .git /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NP /R:2 /W:1 >> "%LOG_FILE%" 2>&1
  set "RC=!ERRORLEVEL!"
  if !RC! GEQ 8 (
    call :log "ERROR: robocopy failed with code !RC!"
    goto :fail
  )
  call :log "Copy complete."

  if not exist "%PERSIST_DIR%\install_and_run.bat" (
    copy /y "%SCRIPT_DIR%\install_and_run.bat" "%PERSIST_DIR%\install_and_run.bat" >nul
  )

  call :log "Continuing from session install in THIS console (no shortcut)..."
  cd /d "%PERSIST_DIR%"
  if errorlevel 1 (
    call :log "ERROR: could not cd to %PERSIST_DIR%"
    goto :fail
  )
  set "SCRIPT_DIR=%PERSIST_DIR%"
)

REM ========== Running from LocalAppData session install ==========
set "PACKAGE_DIR=%PERSIST_DIR%"
cd /d "%PACKAGE_DIR%"
if errorlevel 1 (
  call :log "ERROR: could not cd to package dir %PACKAGE_DIR%"
  goto :fail
)

set "VENV_DIR=%PACKAGE_DIR%\.venv"
set "PORT=8080"
set "PYTHON_EXE="
set "INSTALL_TRIED=0"
set "LAUNCHER_PID="

REM Signal demo mode for the web UI (env + flag file)
set "DEMO_MODE=1"
echo 1> "%TEMP%\LibertyDemo_mode.flag"
echo 1> "%PACKAGE_DIR%\.liberty_demo_mode"

call :log ""
call :log "============================================================"
call :log "  Liberty Basketball Analysis - Demo"
call :log "============================================================"
call :log "Session install: %PACKAGE_DIR%"
call :log "Log:             %LOG_FILE%"
call :log "DEMO_MODE:       %DEMO_MODE%"
call :log "NOTE: Click DONE in the browser top menu when finished."
call :log "      GPU AI / large model weights / game video are not in this demo."
call :log ""

if not exist "%PACKAGE_DIR%\app.py" (
  call :log "ERROR: app.py not found. Run this from the Liberty package root."
  goto :fail
)
if not exist "%PACKAGE_DIR%\scripts\launch_liberty.py" (
  call :log "ERROR: scripts\launch_liberty.py not found."
  goto :fail
)

call :find_python
if errorlevel 1 goto :fail

call :log "Using: !PYTHON_EXE!"
call :log ""

if not exist "%VENV_DIR%\Scripts\python.exe" (
  call :log "Creating virtual environment..."
  "!PYTHON_EXE!" -m venv "%VENV_DIR%" >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    call :log "ERROR: Failed to create venv. See %LOG_FILE%"
    goto :fail
  )
) else (
  call :log "Reusing existing virtual environment."
)

set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
if not exist "%VENV_PY%" (
  call :log "ERROR: venv python missing: %VENV_PY%"
  goto :fail
)

call :log "Upgrading pip..."
"%VENV_PY%" -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1

call :install_requirements
if errorlevel 1 goto :fail

call :pick_port
if errorlevel 1 goto :fail

call :log ""
call :log "Starting Liberty on http://127.0.0.1:!PORT! (DEMO_MODE=1, --no-browser)..."
call :log ""

REM Start via venv python (NOT bare "start scripts\launch_liberty.py").
REM DEMO_MODE is inherited from this cmd session into PowerShell / child.
REM Start-Process is used so we can store the launcher PID for wait + cleanup.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$env:DEMO_MODE='1'; $p = Start-Process -FilePath '%VENV_PY%' -ArgumentList @('scripts\launch_liberty.py','--no-browser','--port','%PORT%') -WorkingDirectory '%PACKAGE_DIR%' -WindowStyle Minimized -PassThru -RedirectStandardOutput '%LOG_FILE%.server' -RedirectStandardError '%LOG_FILE%.err'; $p.Id"`) do (
  set "LAUNCHER_PID=%%P"
)

if not defined LAUNCHER_PID (
  call :log "WARNING: Could not capture launcher PID; will wait for port / done flag."
) else (
  call :log "Launcher PID: !LAUNCHER_PID!"
)

call :log "Waiting for server..."
set /a "WAITED=0"
:wait_loop
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/' -TimeoutSec 2; if ($r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto :server_ready
set /a "WAITED+=2"
if !WAITED! GEQ 180 (
  call :log "ERROR: Server did not become ready within 180s on port %PORT%."
  call :log "See log: %LOG_FILE%"
  if exist "%LOG_FILE%.err" type "%LOG_FILE%.err"
  goto :cleanup_fail
)
timeout /t 2 /nobreak >nul
goto :wait_loop

:server_ready
call :log "Server ready at http://127.0.0.1:%PORT%/"
call :open_browser
call :log ""
call :log "========================================"
call :log "  DEMO RUNNING — http://127.0.0.1:%PORT%"
call :log "  Click DONE in the browser top menu"
call :log "  to uninstall and exit."
call :log "========================================"
call :log ""
call :wait_for_server_exit
goto :cleanup_ok

REM ======================== helpers ========================

:log
echo %~1
>>"%LOG_FILE%" echo %~1
exit /b 0

:pick_port
REM Prefer 8080; if busy (e.g. main Liberty), use 8090. Fail if both busy.
set "PORT=8080"
powershell -NoProfile -Command "try { if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 } } catch { exit 0 }" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
  call :log "Port 8080 is free — using it."
  exit /b 0
)
call :log "Port 8080 is in use — trying 8090..."
set "PORT=8090"
powershell -NoProfile -Command "try { if (Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 } } catch { exit 0 }" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
  call :log "Port 8090 is free — using it."
  exit /b 0
)
call :log "ERROR: Ports 8080 and 8090 are both in use."
call :log "Stop the other Liberty/app using those ports, then re-run."
exit /b 1

:open_browser
REM Bat MUST open the browser — launch_liberty is started with --no-browser.
set "OPEN_URL=http://127.0.0.1:%PORT%/"
call :log ""
call :log "[BROWSER] Opening %OPEN_URL% ..."
call :log "[BROWSER] Method 1: cmd start \"\" url"
start "" "%OPEN_URL%"
call :log "[BROWSER] cmd start ERRORLEVEL=%ERRORLEVEL%"
call :log "[BROWSER] Method 2: powershell Start-Process"
powershell -NoProfile -Command "try { Start-Process '%OPEN_URL%'; Write-Host '[BROWSER] Start-Process: OK' } catch { Write-Host ('[BROWSER] Start-Process FAILED: ' + $_.Exception.Message); exit 1 }"
call :log "[BROWSER] Browser open commands finished — check lines above."
exit /b 0

:wait_for_server_exit
REM Primary: wait until launcher PID exits (web DONE calls os._exit).
REM Also accept %TEMP%\LibertyDemo_done.flag from the API.
echo Waiting for web DONE ^(server process exit^)...
:wait_exit_loop
if exist "%TEMP%\LibertyDemo_done.flag" (
  echo DONE flag detected — proceeding to cleanup...
  timeout /t 2 /nobreak >nul
  exit /b 0
)
if defined LAUNCHER_PID (
  powershell -NoProfile -Command "try { Get-Process -Id %LAUNCHER_PID% -ErrorAction Stop | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if !ERRORLEVEL! NEQ 0 (
    echo Launcher PID %LAUNCHER_PID% exited — uninstalling...
    exit /b 0
  )
) else (
  powershell -NoProfile -Command "try { $c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($c) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if !ERRORLEVEL! NEQ 0 (
    echo Port %PORT% no longer listening — uninstalling...
    exit /b 0
  )
)
timeout /t 2 /nobreak >nul
goto :wait_exit_loop

:remove_leftover_shortcuts
REM Best-effort delete of any leftover .url/.lnk from older demo builds.
echo Removing leftover Desktop shortcut^(s^) if any...
set "_REMOVED=0"
for %%D in (
  "%USERPROFILE%\Desktop"
  "%USERPROFILE%\OneDrive\Desktop"
  "%PUBLIC%\Desktop"
) do (
  if exist "%%~D\Liberty Basketball Demo.url" (
    del /f /q "%%~D\Liberty Basketball Demo.url" 2>nul
    if not exist "%%~D\Liberty Basketball Demo.url" (
      echo   deleted: %%~D\Liberty Basketball Demo.url
      set "_REMOVED=1"
    )
  )
  if exist "%%~D\Liberty Basketball Demo.lnk" (
    del /f /q "%%~D\Liberty Basketball Demo.lnk" 2>nul
    if not exist "%%~D\Liberty Basketball Demo.lnk" (
      echo   deleted: %%~D\Liberty Basketball Demo.lnk
      set "_REMOVED=1"
    )
  )
)
if "!_REMOVED!"=="0" echo   ^(no leftover Desktop shortcuts found^)
exit /b 0

:wipe_temp_leftovers
REM Delete TEMP LibertyDemo_* logs / leftover dirs we created.
REM Do NOT delete this cleanup bat until the very end ^(caller handles that^).
echo Removing TEMP LibertyDemo leftovers...
set "_TEMP_REMOVED=0"
for %%F in (
  "%TEMP%\LibertyDemo_*.log"
  "%TEMP%\LibertyDemo_*.log.err"
  "%TEMP%\LibertyDemo_mode.flag"
  "%TEMP%\LibertyDemo_done.flag"
  "%TEMP%\LibertyDemo_wait_done.ps1"
  "%TEMP%\LibertyDemo_web_cleanup.bat"
) do (
  if exist "%%~fF" (
    del /f /q "%%~fF" 2>nul
    if not exist "%%~fF" (
      echo   deleted: %%~fF
      set "_TEMP_REMOVED=1"
    )
  )
)
for /d %%D in ("%TEMP%\LibertyDemo_*") do (
  if exist "%%~fD" (
    rd /s /q "%%~fD" 2>nul
    if not exist "%%~fD" (
      echo   deleted: %%~fD
      set "_TEMP_REMOVED=1"
    ) else (
      echo   FAILED delete: %%~fD
    )
  )
)
if "!_TEMP_REMOVED!"=="0" echo   ^(no TEMP LibertyDemo_* leftovers found^)
exit /b 0

:wipe_session_install
REM Delete %LOCALAPPDATA%\LibertyBasketballDemo entirely.
echo Removing session install...
if exist "%PERSIST_DIR%" (
  powershell -NoProfile -Command ^
    "$dir = '%PERSIST_DIR%';" ^
    "if (Test-Path -LiteralPath $dir) {" ^
    "  try {" ^
    "    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction Stop;" ^
    "    Write-Host ('  deleted: ' + $dir)" ^
    "  } catch {" ^
    "    Write-Host ('  retry after brief wait...');" ^
    "    Start-Sleep -Seconds 2;" ^
    "    try {" ^
    "      Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction Stop;" ^
    "      Write-Host ('  deleted: ' + $dir)" ^
    "    } catch {" ^
    "      Write-Host ('  FAILED delete: ' + $dir + ' — ' + $_.Exception.Message);" ^
    "      Get-ChildItem -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {" ^
    "        try { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue } catch {}" ^
    "      };" ^
    "      try { Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction Stop; Write-Host ('  deleted: ' + $dir) }" ^
    "      catch { Write-Host ('  STILL PRESENT: ' + $dir) }" ^
    "    }" ^
    "  }" ^
    "} else { Write-Host ('  (already gone: ' + $dir + ')') }"
) else (
  echo   ^(already gone: %PERSIST_DIR%^)
)
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
set "_CLEANUP_ARG=ok"
goto :handoff_cleanup_goto

:cleanup_fail
set "_CLEANUP_ARG=fail"
goto :handoff_cleanup_goto

:handoff_cleanup_goto
REM Transfer control to a TEMP copy so we can wipe PERSIST_DIR (this folder).
REM Invoking the other .bat without CALL does not return here.
set "CLEANUP_BAT=%TEMP%\LibertyDemo_cleanup_run.bat"
copy /y "%~f0" "%CLEANUP_BAT%" >nul
if not exist "%CLEANUP_BAT%" (
  echo WARNING: Could not copy cleanup helper to TEMP; wiping in-place.
  if /I "%_CLEANUP_ARG%"=="fail" (goto :cleanup_fail_body) else (goto :cleanup_ok_body)
)
"%CLEANUP_BAT%" --cleanup-phase "%LOG_FILE%" "%LAUNCHER_PID%" %_CLEANUP_ARG%
exit /b 0

:cleanup_ok_body
call :stop_liberty_tree
echo.
echo Cleaning up all demo files...
echo Removed items:
if defined LOG_FILE if exist "%LOG_FILE%" (
  del /f /q "%LOG_FILE%" 2>nul
  echo   deleted: %LOG_FILE%
)
if defined LOG_FILE if exist "%LOG_FILE%.err" (
  del /f /q "%LOG_FILE%.err" 2>nul
  echo   deleted: %LOG_FILE%.err
)
call :wipe_temp_leftovers
call :remove_leftover_shortcuts
call :wipe_session_install
echo.
echo ========================================
echo   Uninstall complete.
echo   Demo files removed from this PC.
echo   winget Python ^(if installed^) was NOT removed.
echo ========================================
echo.
echo You can close this window.
timeout /t 5 /nobreak >nul
REM Remove TEMP cleanup helper if we are that helper
if /I "%~nx0"=="LibertyDemo_cleanup_run.bat" del /f /q "%~f0" 2>nul
exit /b 0

:cleanup_fail_body
call :stop_liberty_tree
echo.
echo Setup/start failed — still cleaning demo files...
echo Removed items:
if defined LOG_FILE if exist "%LOG_FILE%" (
  echo   log kept for debug: %LOG_FILE%
) else (
  echo   ^(no log file^)
)
if defined LOG_FILE if exist "%LOG_FILE%.server" (
  echo   server log kept: %LOG_FILE%.server
)
if defined LOG_FILE if exist "%LOG_FILE%.err" (
  echo   err log kept: %LOG_FILE%.err
)
call :wipe_temp_leftovers_keep_run_log
call :remove_leftover_shortcuts
call :wipe_session_install
echo.
echo Demo files cleaned. ^(winget Python, if installed, was left alone.^)
echo Full debug log: %TEMP%\LibertyDemo_run.log
echo.
echo Press any key to close this window...
pause >nul
if /I "%~nx0"=="LibertyDemo_cleanup_run.bat" del /f /q "%~f0" 2>nul
exit /b 1

:wipe_temp_leftovers_keep_run_log
REM Like wipe_temp_leftovers but keep LibertyDemo_run.log for debugging failures.
echo Removing TEMP LibertyDemo leftovers ^(keeping run log^)...
set "_TEMP_REMOVED=0"
for %%F in (
  "%TEMP%\LibertyDemo_*.log.err"
  "%TEMP%\LibertyDemo_*.log.server"
  "%TEMP%\LibertyDemo_mode.flag"
  "%TEMP%\LibertyDemo_done.flag"
  "%TEMP%\LibertyDemo_wait_done.ps1"
  "%TEMP%\LibertyDemo_web_cleanup.bat"
) do (
  if exist "%%~fF" (
    del /f /q "%%~fF" 2>nul
    if not exist "%%~fF" (
      echo   deleted: %%~fF
      set "_TEMP_REMOVED=1"
    )
  )
)
for /d %%D in ("%TEMP%\LibertyDemo_*") do (
  if exist "%%~fD" (
    rd /s /q "%%~fD" 2>nul
    if not exist "%%~fD" (
      echo   deleted: %%~fD
      set "_TEMP_REMOVED=1"
    )
  )
)
if "!_TEMP_REMOVED!"=="0" echo   ^(no TEMP LibertyDemo_* leftovers found^)
exit /b 0

:fail
echo.
call :log "Setup failed. Log: %LOG_FILE%"
echo.
echo Press any key to close this window...
pause >nul
exit /b 1
