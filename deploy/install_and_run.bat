@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Liberty Basketball Analysis - Demo
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM Liberty Demo launcher (Windows)
REM First run (SFX TEMP extract): copy payload to
REM   %LOCALAPPDATA%\LibertyBasketballDemo\
REM create Desktop URL shortcut (.url via cmd echo), then relaunch from that folder.
REM Subsequent runs from LocalAppData: reuse .venv for the session.
REM Prefer py -3.12 / py -3.13 (resolve to full path), then common install dirs,
REM then python on PATH. Winget install is attempted at most ONCE.
REM Start server with venv python + scripts\launch_liberty.py --no-browser.
REM Kill only the Liberty process tree (not all python.exe).
REM Cleanup on exit: stop server, wipe LocalAppData install, delete TEMP log,
REM delete Desktop shortcuts. Does NOT uninstall winget Python.
REM ---------------------------------------------------------------------------

set "PERSIST_DIR=%LOCALAPPDATA%\LibertyBasketballDemo"
set "SHORTCUT_URL=Liberty Basketball Demo.url"
set "DEMO_URL=http://127.0.0.1:8080"
set "DESKTOP_DIR="
set "URL_PATH="
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

REM If not already running from the session install, copy + shortcut + relaunch.
if /I not "%SCRIPT_DIR%"=="%PERSIST_DIR%" (
  echo.
  echo ============================================================
  echo   Liberty Basketball Analysis - Demo Setup
  echo ============================================================
  echo.
  echo Installing demo for this session to:
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
    echo ERROR: Desktop shortcut creation failed. See messages above.
    echo Demo install is at %PERSIST_DIR% but no Desktop shortcut was created.
    pause
    exit /b 1
  )

  echo.
  echo Launching from session install...
  echo.
  start "" "%PERSIST_DIR%\install_and_run.bat"
  exit /b 0
)

REM ========== Running from LocalAppData session install ==========
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
echo Session install: %PACKAGE_DIR%
echo Log:             %LOG_FILE%
echo.
echo NOTE: winget-installed Python ^(if needed^) stays on this PC.
echo       When you press a key, this demo wipes LocalAppData files
echo       and removes the Desktop shortcut^(s^).
echo       GPU AI / large model weights / game video are not in this demo.
echo.

REM Refresh / ensure Desktop URL shortcuts exist for this session
call :create_desktop_shortcut

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
echo   Desktop shortcut opens that URL while the demo runs.
echo   Press any key in this window to stop and remove all
echo   installed demo files ^(LocalAppData + Desktop shortcuts^).
echo ------------------------------------------------------------
echo.
pause >nul

goto :cleanup_ok

REM ======================== helpers ========================

:resolve_desktop_dir
REM Simple Desktop resolve — no PowerShell. Prefer USERPROFILE\Desktop, then OneDrive.
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
if not exist "%DESKTOP_DIR%" set "DESKTOP_DIR=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESKTOP_DIR%" (
  echo ERROR: Desktop folder not found.
  echo Tried: %USERPROFILE%\Desktop
  echo        %USERPROFILE%\OneDrive\Desktop
  exit /b 1
)
exit /b 0

:create_desktop_shortcut
REM Create InternetShortcut .url with plain cmd echo (no PowerShell).
REM Writes to user Desktop and Public Desktop when present.
REM Echoes ERRORLEVEL + dir listing so the console proves creation.
set "URL_OK=0"

call :resolve_desktop_dir
if errorlevel 1 exit /b 1

set "URL_PATH=%DESKTOP_DIR%\%SHORTCUT_URL%"
echo.
echo Creating Desktop shortcut ^(InternetShortcut .url^)...
echo Desktop folder: %DESKTOP_DIR%
echo Target URL:     %DEMO_URL%
echo Output file:    %URL_PATH%

(
  echo [InternetShortcut]
  echo URL=%DEMO_URL%
) > "%URL_PATH%"
echo ERRORLEVEL after write: %ERRORLEVEL%
if errorlevel 1 (
  echo ERROR: Failed to write %URL_PATH%
  echo ERRORLEVEL=%ERRORLEVEL%
  pause
  exit /b 1
)
if not exist "%URL_PATH%" (
  echo ERROR: File missing after write: %URL_PATH%
  pause
  exit /b 1
)
echo Shortcut created:
dir "%URL_PATH%"
set "URL_OK=1"

REM Also place on Public Desktop when that folder exists (all-users visibility).
if exist "%PUBLIC%\Desktop" (
  set "PUBLIC_URL=%PUBLIC%\Desktop\%SHORTCUT_URL%"
  echo Also writing Public Desktop: !PUBLIC_URL!
  (
    echo [InternetShortcut]
    echo URL=%DEMO_URL%
  ) > "!PUBLIC_URL!"
  echo ERRORLEVEL after Public write: !ERRORLEVEL!
  if exist "!PUBLIC_URL!" (
    dir "!PUBLIC_URL!"
  ) else (
    echo WARNING: Public Desktop write failed ^(continuing — user Desktop OK^).
  )
)

if "!URL_OK!"=="0" exit /b 1
exit /b 0

:remove_desktop_shortcuts
REM Delete .url (and any leftover .lnk) from known Desktop paths — plain cmd.
echo Removing Desktop shortcut^(s^)...
set "_REMOVED=0"
for %%D in (
  "%USERPROFILE%\Desktop"
  "%USERPROFILE%\OneDrive\Desktop"
  "%PUBLIC%\Desktop"
) do (
  if exist "%%~D\%SHORTCUT_URL%" (
    del /f /q "%%~D\%SHORTCUT_URL%"
    if not exist "%%~D\%SHORTCUT_URL%" (
      echo   deleted: %%~D\%SHORTCUT_URL%
      set "_REMOVED=1"
    ) else (
      echo   FAILED delete: %%~D\%SHORTCUT_URL%
    )
  )
  if exist "%%~D\Liberty Basketball Demo.lnk" (
    del /f /q "%%~D\Liberty Basketball Demo.lnk"
    if not exist "%%~D\Liberty Basketball Demo.lnk" (
      echo   deleted: %%~D\Liberty Basketball Demo.lnk
      set "_REMOVED=1"
    )
  )
)
if "!_REMOVED!"=="0" echo   ^(no Desktop shortcuts found to delete^)
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
if defined LOG_FILE if exist "%LOG_FILE%" (
  del /f /q "%LOG_FILE%" 2>nul
  echo   deleted: %LOG_FILE%
)
if defined LOG_FILE if exist "%LOG_FILE%.err" (
  del /f /q "%LOG_FILE%.err" 2>nul
  echo   deleted: %LOG_FILE%.err
)
REM Also sweep any leftover LibertyDemo_*.log in TEMP
for %%F in ("%TEMP%\LibertyDemo_*.log" "%TEMP%\LibertyDemo_*.log.err") do (
  if exist "%%~fF" (
    del /f /q "%%~fF" 2>nul
    echo   deleted: %%~fF
  )
)
call :remove_desktop_shortcuts
call :wipe_session_install
echo.
echo Done. Demo files removed. ^(winget Python, if installed, was left alone.^)
echo.
pause
REM Remove TEMP cleanup helper if we are that helper
if /I "%~nx0"=="LibertyDemo_cleanup_run.bat" del /f /q "%~f0" 2>nul
exit /b 0

:cleanup_fail_body
call :stop_liberty_tree
echo.
echo Setup/start failed — still cleaning demo files...
if defined LOG_FILE if exist "%LOG_FILE%" (
  echo   log kept for debug: %LOG_FILE%
) else (
  echo   ^(no log file^)
)
call :remove_desktop_shortcuts
call :wipe_session_install
echo.
pause
if /I "%~nx0"=="LibertyDemo_cleanup_run.bat" del /f /q "%~f0" 2>nul
exit /b 1

:fail
echo.
echo Setup failed. Log (if any): %LOG_FILE%
pause
exit /b 1
