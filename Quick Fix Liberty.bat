@echo off
setlocal EnableExtensions
title Liberty Basketball - Quick Fix (venv only)
cd /d "%~dp0"

echo.
echo  Quick Fix: delete broken .venv and reinstall dependencies
echo.

if exist ".venv" (
  echo Removing .venv ...
  rmdir /s /q ".venv"
)

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: python not found. Install Python 3.12 and check Add to PATH.
  pause
  exit /b 1
)

python scripts\launch_liberty.py --reinstall-deps
if errorlevel 1 (
  echo.
  echo Quick Fix failed. See messages above.
  pause
  exit /b 1
)
