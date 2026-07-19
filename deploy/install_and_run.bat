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
REM Start server with DEMO_MODE=1 + launch_liberty.py --no-browser (hidden window).
REM Wait until http://127.0.0.1:PORT/ returns HTTP 200, THEN open browser ONCE
REM via a single PowerShell Start-Process. Never writes Desktop shortcuts.
REM Wait for server exit (web DONE), then wipe LocalAppData + TEMP leftovers.
REM Does NOT uninstall winget Python. Does NOT delete dist\LibertyDemo.exe.
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
  set "PORT=8090"
  if not "%~2"=="" set "LOG_FILE=%~2"
  if not "%~3"=="" set "LAUNCHER_PID=%~3"
  if not "%~4"=="" if /I not "%~4"=="ok" if /I not "%~4"=="fail" set "PORT=%~4"
  if /I "%~5"=="fail" (goto :cleanup_fail_body)
  if /I "%~5"=="ok" (goto :cleanup_ok_body)
  if /I "%~4"=="fail" (goto :cleanup_fail_body) else (goto :cleanup_ok_body)
)

REM Guard: if already running from LocalAppData session, or a demo server is
REM already listening on 8090-8100, do NOT re-copy from Temp / re-enter setup.
call :check_already_running
if "!ALREADY_RUNNING!"=="1" (
  call :log "Demo already running at http://127.0.0.1:!PORT!/ — opening browser once and exiting setup."
  call :open_browser
  call :log "Attach to existing demo. Click DONE in the browser when finished."
  call :log "This console will close; the existing demo console owns cleanup."
  ping -n 4 127.0.0.1 >nul 2>&1
  exit /b 0
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
set "PORT=8090"
set "PYTHON_EXE="
set "INSTALL_TRIED=0"
set "LAUNCHER_PID="
set "BROWSER_OPENED=0"

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

call :log .
call :log "************************************************************"
call :log "  DEMO PORT CHOSEN: !PORT!"
call :log "  DEMO URL:         http://127.0.0.1:!PORT!/"
call :log "  (8080 is reserved for main Liberty — demo never uses it)"
call :log "************************************************************"
call :log .
call :log "Starting Liberty on http://127.0.0.1:!PORT! (DEMO_MODE=1, --no-browser)..."
call :log .

REM Start via venv python (NOT bare "start scripts\launch_liberty.py").
REM WindowStyle Hidden so only this bat console is visible.
REM Do NOT use start /wait — that would block this console on python.
del /f /q "%LOG_FILE%.server" "%LOG_FILE%.err" 2>nul
del /f /q "%TEMP%\LibertyDemo_done.flag" 2>nul
set "LAUNCHER_PID="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$env:DEMO_MODE='1'; $p = Start-Process -FilePath '%VENV_PY%' -ArgumentList @('scripts\launch_liberty.py','--no-browser','--port','!PORT!') -WorkingDirectory '%PACKAGE_DIR%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%LOG_FILE%.server' -RedirectStandardError '%LOG_FILE%.err'; Write-Output $p.Id"`) do (
  set "LAUNCHER_PID=%%P"
)

if not defined LAUNCHER_PID (
  call :log "WARNING: Could not capture launcher PID; will poll port / done flag."
) else (
  call :log "Launcher PID: !LAUNCHER_PID!"
)

REM Wait for HTTP 200 BEFORE opening the browser (avoids ERR_CONNECTION_REFUSED).
REM Poll every ~1s, max 120s. Show console "Waiting for server..." so user knows.
set /a "WAITED=0"
set "SERVER_READY=0"
set "BROWSER_OPENED=0"
call :log "Waiting for server at http://127.0.0.1:!PORT!/ (up to 120s)..."
call :log "First launch may take a few minutes while pip finishes — please wait."

:wait_loop
call :log "[WAIT] Waiting for server... (!WAITED!s)"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:!PORT!/' -TimeoutSec 2; Write-Output ('[WAIT] HTTP ' + $r.StatusCode); if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { Write-Output ('[WAIT] not ready: ' + $_.Exception.Message); exit 1 }" >> "%LOG_FILE%" 2>&1
if !ERRORLEVEL! EQU 0 (
  set "SERVER_READY=1"
  call :log "[WAIT] server ready (HTTP 200) at !WAITED!s"
  goto :after_wait
)

if !WAITED! GEQ 120 (
  call :log "ERROR: No HTTP 200 within 120s on port !PORT!."
  call :log "See log: %LOG_FILE%"
  if exist "%LOG_FILE%.err" (
    call :log "--- err log (tail) ---"
    powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG_FILE%.err' -Tail 40 -ErrorAction SilentlyContinue"
  )
  if exist "%LOG_FILE%.server" (
    call :log "--- server log (tail) ---"
    powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG_FILE%.server' -Tail 40 -ErrorAction SilentlyContinue"
  )
  goto :cleanup_fail
)

REM ~1 second delay (avoid "timeout" — can hang when stdin redirected from SFX)
ping -n 2 127.0.0.1 >nul 2>&1
set /a "WAITED+=1"
goto :wait_loop

:after_wait
REM ONE browser open only — after HTTP 200. Never open on DONE / cleanup.
if "!SERVER_READY!"=="1" if "!BROWSER_OPENED!"=="0" (
  call :log "Opening browser ONCE (server ready)..."
  call :open_browser
  set "BROWSER_OPENED=1"
)

call :log .
call :log "========================================"
call :log "  DEMO RUNNING — http://127.0.0.1:!PORT!"
call :log "  Click DONE in the browser top menu"
call :log "  to uninstall and exit."
call :log "========================================"
call :log .
call :log "Demo running — use DONE in the web UI."
call :wait_for_server_exit
goto :cleanup_ok

REM ======================== helpers ========================

:log
REM Empty args / blank marker must not use bare "echo" (prints "ECHO is off.").
if "%~1"=="" (
  echo.
  >>"%LOG_FILE%" echo.
  exit /b 0
)
if "%~1"=="." (
  echo.
  >>"%LOG_FILE%" echo.
  exit /b 0
)
echo(%~1
>>"%LOG_FILE%" echo(%~1)
exit /b 0

:check_already_running
REM Sets ALREADY_RUNNING=1 and PORT if a demo HTTP server is already up.
set "ALREADY_RUNNING=0"
REM If we were launched from Temp/SFX again while LocalAppData session exists
REM and listens, skip re-setup entirely.
for /L %%N in (8090,1,8100) do (
  powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%%N/' -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    REM Prefer confirming it looks like our demo (mode flag or persist dir lock).
    if exist "%TEMP%\LibertyDemo_mode.flag" (
      set "PORT=%%N"
      set "ALREADY_RUNNING=1"
      exit /b 0
    )
    if exist "%PERSIST_DIR%\.liberty_demo_mode" (
      set "PORT=%%N"
      set "ALREADY_RUNNING=1"
      exit /b 0
    )
  )
)
exit /b 0

:pick_port
REM Demo NEVER uses 8080 (main Liberty). Find first free port from 8090 upward.
call :log "Selecting demo port (8090+; 8080 reserved for main app)..."
powershell -NoProfile -Command "try { if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) { Write-Output 'NOTE: Port 8080 is in use (likely main Liberty) — demo will not use it.' } else { Write-Output 'NOTE: Port 8080 is free but reserved for main Liberty — demo still uses 8090+.' } } catch { Write-Output 'NOTE: Could not probe 8080; demo uses 8090+.' }" >> "%LOG_FILE%" 2>&1
for /L %%N in (8090,1,8100) do (
  set "PORT=%%N"
  powershell -NoProfile -Command "try { if (Get-NetTCPConnection -LocalPort %%N -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 } } catch { exit 0 }" >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    call :log "CHOSEN DEMO PORT: %%N  (URL http://127.0.0.1:%%N/)"
    exit /b 0
  )
  call :log "Port %%N is in use — trying next..."
)
call :log "ERROR: No free demo port in 8090-8100."
call :log "Stop other apps using those ports, then re-run."
exit /b 1

:open_browser
REM Bat MUST open the browser — launch_liberty is started with --no-browser.
REM ONE method only: PowerShell Start-Process. No Desktop .url. No pile-on.
set "OPEN_URL=http://127.0.0.1:!PORT!/"
call :log .
call :log "[BROWSER] Opening !OPEN_URL! (single Start-Process)..."
powershell -NoProfile -Command "Start-Process 'http://127.0.0.1:!PORT!/'" >> "%LOG_FILE%" 2>&1
call :log "[BROWSER] Start-Process done ERRORLEVEL=!ERRORLEVEL!"
call :log .
exit /b 0

:wait_for_server_exit
REM Primary: wait until launcher PID exits (web DONE calls os._exit).
REM Also accept %TEMP%\LibertyDemo_done.flag from the API.
REM Do NOT open the browser here.
echo Waiting for web DONE ^(server process exit^)...
:wait_exit_loop
if exist "%TEMP%\LibertyDemo_done.flag" (
  echo DONE flag detected — proceeding to cleanup...
  ping -n 3 127.0.0.1 >nul 2>&1
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
ping -n 3 127.0.0.1 >nul 2>&1
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
REM Also best-effort wipe orphaned 7zS* extract folders (SFX temp) if idle.
REM Do NOT delete this cleanup bat until the very end ^(caller handles that^).
echo Removing TEMP LibertyDemo leftovers...
set "_TEMP_REMOVED=0"
for %%F in (
  "%TEMP%\LibertyDemo_*.log"
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
    ) else (
      echo   FAILED delete: %%~fD
    )
  )
)
REM Safe 7zS* cleanup: only folders that look like our SFX extract (have our bat)
REM and are not our current script directory.
powershell -NoProfile -Command ^
  "$cur = [string]'%~dp0';" ^
  "Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter '7zS*' -ErrorAction SilentlyContinue | ForEach-Object {" ^
  "  $d = $_.FullName;" ^
  "  if ($cur -and ($d.TrimEnd('\') -ieq $cur.TrimEnd('\'))) { return }" ^
  "  $marker = Join-Path $d 'install_and_run.bat';" ^
  "  $app = Join-Path $d 'app.py';" ^
  "  if ((Test-Path -LiteralPath $marker) -and (Test-Path -LiteralPath $app)) {" ^
  "    try {" ^
  "      Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction Stop;" ^
  "      Write-Host ('  deleted SFX temp: ' + $d)" ^
  "    } catch {" ^
  "      Write-Host ('  skip busy SFX temp: ' + $d)" ^
  "    }" ^
  "  }" ^
  "}"
if "!_TEMP_REMOVED!"=="0" echo   ^(no TEMP LibertyDemo_* leftovers found^)
exit /b 0

:wipe_session_install
REM Delete %LOCALAPPDATA%\LibertyBasketballDemo entirely.
REM NEVER touch dist\LibertyDemo.exe or the repo deliverable.
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
REM Do NOT open browser during cleanup.
set "CLEANUP_BAT=%TEMP%\LibertyDemo_cleanup_run.bat"
copy /y "%~f0" "%CLEANUP_BAT%" >nul
if not exist "%CLEANUP_BAT%" (
  echo WARNING: Could not copy cleanup helper to TEMP; wiping in-place.
  if /I "%_CLEANUP_ARG%"=="fail" (goto :cleanup_fail_body) else (goto :cleanup_ok_body)
)
"%CLEANUP_BAT%" --cleanup-phase "%LOG_FILE%" "%LAUNCHER_PID%" !PORT! %_CLEANUP_ARG%
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
if defined LOG_FILE if exist "%LOG_FILE%.server" (
  del /f /q "%LOG_FILE%.server" 2>nul
  echo   deleted: %LOG_FILE%.server
)
call :wipe_temp_leftovers
call :remove_leftover_shortcuts
call :wipe_session_install
echo.
echo ========================================
echo   Uninstall complete.
echo   Demo files removed from this PC.
echo   Kept: dist\LibertyDemo.exe ^(deliverable^) and winget Python.
echo ========================================
echo.
echo You can close this window.
ping -n 6 127.0.0.1 >nul 2>&1
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
