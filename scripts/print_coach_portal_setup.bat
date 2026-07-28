@echo off
setlocal EnableExtensions
title Liberty Coach Portal — tunnel instructions
cd /d "%~dp0.."

echo.
echo  Liberty Coach Portal
echo  -------------------
echo.
echo  1. Keep the app on 0.0.0.0:8080 (Start Liberty.bat or py -3.12 app.py).
echo  2. Set a shared password, then restart the app:
echo.
echo       set LIBERTY_COACH_PASSWORD=your-shared-password
echo.
if defined LIBERTY_COACH_PASSWORD (
  echo  LIBERTY_COACH_PASSWORD is set in this shell.
) else (
  echo  LIBERTY_COACH_PASSWORD is NOT set in this shell.
)
echo.
echo  3. Local check:  http://127.0.0.1:8080/coach
echo.
echo  4. Permanent public URL — pick ONE (not free quick tunnels):
echo       - Cloudflare named tunnel  ^(needs a domain on Cloudflare^)
echo       - Tailscale Funnel         ^(https://machine.tailnet.ts.net^)
echo.
echo  See docs\COACH_PORTAL.md and scripts\setup_coach_tunnel.md
echo.
pause
