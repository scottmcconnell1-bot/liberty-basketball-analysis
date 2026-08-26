@echo off
REM Register Windows task: restart Liberty on :8080 if it dies (every 30 min).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_liberty_watchdog.ps1
pause
