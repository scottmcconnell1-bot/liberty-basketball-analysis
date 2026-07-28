@echo off
REM Fully detached Hoops teach loop — survives closing Cursor.
cd /d "%~dp0"
py -3.12 scripts\start_hoops_teach_detached.py %*
pause
