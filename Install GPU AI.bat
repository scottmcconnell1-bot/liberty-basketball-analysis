@echo off
setlocal EnableExtensions
title Liberty Basketball - Install GPU AI packages
cd /d "%~dp0"

echo.
echo  Install PyTorch (GPU when available), OpenCV, and Ultralytics into .venv
echo  No venv activation required.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_ai_deps.ps1"
if errorlevel 1 (
  echo.
  echo Install failed. See messages above.
  pause
  exit /b 1
)

echo.
echo Done. Start Liberty with Start Liberty.bat, then check Settings -^> Runtime.
pause
