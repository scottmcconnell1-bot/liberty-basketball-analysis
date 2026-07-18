@echo off
setlocal EnableExtensions
title Liberty Basketball - Backup for Transfer
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\backup_for_transfer.ps1"
echo.
pause
