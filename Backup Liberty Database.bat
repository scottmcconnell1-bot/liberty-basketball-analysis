@echo off
REM Backup live film_analysis.db to %%USERPROFILE%%\LibertyData\backups
REM (separate from the project so backups cannot corrupt the hot DB).
REM Optional: set LIBERTY_DATA_ROOT=E:\LibertyData for an external drive.

cd /d "%~dp0"
py -3.12 scripts\backup_db.py --keep 14
echo.
pause
