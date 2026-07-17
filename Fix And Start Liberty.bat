@echo off
setlocal EnableExtensions
title Liberty Basketball - Fix and Start
cd /d "%~dp0"

echo.
echo  Liberty Basketball - repair and start (OneDrive / git / venv fix)
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\fix_and_start.ps1"
if errorlevel 1 (
  echo.
  echo Fix and Start failed. See messages above.
  pause
  exit /b 1
)
