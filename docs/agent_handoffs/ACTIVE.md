# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-web-done-no-shortcut |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **No Desktop shortcuts:** `install_and_run.bat` has no `create_desktop_shortcut`, `[InternetShortcut]`, `.url` write, or WinForms dialog. Cleanup still best-effort deletes leftover `.url`/`.lnk` from older builds.
- **Browser open:** After server ready, bat logs `[BROWSER]` and runs `start "" "%OPEN_URL%"` plus PowerShell `Start-Process`. Does not rely on `launch_liberty` (still started with `--no-browser`).
- **DEMO_MODE:** Bat sets `DEMO_MODE=1` (+ TEMP/local flag files). Nav shows prominent **DONE** only when `demo_mode` is true. Smoke: HTML contains `id="demo-done-btn"`.
- **Web DONE:** `POST /api/demo/done` (alias `/api/demo/uninstall`) schedules `%TEMP%\LibertyDemo_web_cleanup.bat`, writes done flag, then `os._exit` after response. Outer bat waits for launcher PID exit / done flag, then TEMP handoff wipe of `%LOCALAPPDATA%\LibertyBasketballDemo`.
- **Tests:** `tests/test_demo_mode.py` — 4 passed.
- **Rebuilt SFX:** `dist\LibertyDemo.exe` and `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` (26.28 MB, 2026-07-19 ~9:50 AM).

### Files

- `deploy/install_and_run.bat` — no shortcuts; DEMO_MODE; browser open; wait for server exit
- `blueprints/demo.py` — DONE/uninstall API
- `app.py` / `templates/base.html` — demo_mode inject + DONE button
- `scripts/build_demo_package.ps1` — markers/README updated
- removed `deploy/demo_done_dialog.ps1`

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
