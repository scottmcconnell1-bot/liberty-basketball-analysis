@echo off
setlocal EnableExtensions
title Liberty Basketball Analysis
cd /d "%~dp0"

echo.
echo  Liberty Basketball - starting local test environment...
echo.

if exist "%~dp0scripts\launch_liberty.py" (
  goto :run_launcher
)

echo ERROR: scripts\launch_liberty.py not found.
echo Make sure you are running this file from the repo root.
pause
exit /b 1

:run_launcher
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3.12 "%~dp0scripts\launch_liberty.py" %*
  goto :done
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python "%~dp0scripts\launch_liberty.py" %*
  goto :done
)

echo Python not found. Trying winget install for Python 3.12...
where winget >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo Install Python 3.12 from https://www.python.org/downloads/ then run this again.
  pause
  exit /b 1
)

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
py -3.12 "%~dp0scripts\launch_liberty.py" %*

:done
if errorlevel 1 (
  echo.
  echo Launcher exited with an error.
  pause
)
