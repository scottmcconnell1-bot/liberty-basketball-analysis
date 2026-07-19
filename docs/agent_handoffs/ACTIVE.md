# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-browser-wait-stuck |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Stuck console after "ECHO is off.":** `call :log ""` with bare `echo %~1` under `@echo off` prints `ECHO is off.` Blank-line calls looked like a hang and hid the next steps.
- **Browser never opened:** wait loop required HTTP success before `:open_browser` (up to 180s) and used `%ERRORLEVEL%` (stale) instead of `!ERRORLEVEL!`. Server could be up (minimized python window) while the bat never reached browser open.
- **8080 now:** Not listening (DOWN; only TimeWait). Prior `.server` log showed Flask had started successfully on an earlier run.
- **Fix:** Safe `:log` blank lines; poll with `[WAIT]` lines to `LibertyDemo_run.log` (max 60s); open browser on HTTP 200 **or** after ~3s (PID preferred); dual `start ""` + PowerShell `Start-Process` with `[BROWSER]` logs; then "Demo running — use DONE" and wait for PID/done flag.
- **Exe:** rebuilt to `dist\LibertyDemo.exe` and `C:\Temp\LibertyDemoPackage\LibertyDemo.exe`.

### Files

- `deploy/install_and_run.bat` — empty-echo fix; early browser; 60s poll
- `scripts/build_demo_package.ps1` — smoke checks for `[BROWSER]` / `[WAIT]`
- Prior DONE API fix still on this branch (`blueprints/demo.py`, etc.)

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
