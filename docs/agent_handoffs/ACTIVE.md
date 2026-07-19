# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-done-uninstall-button |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **DONE UX:** While the demo runs, console shows `DEMO RUNNING — http://127.0.0.1:8080` and `deploy/demo_done_dialog.ps1` opens a TopMost WinForms dialog with a large **DONE** button. Clicking DONE (or closing the form) continues cleanup. Fallback: type `DONE` (case-insensitive) or press Enter in the console.
- **On DONE:** stop Liberty by launcher PID / cmdline / port listener → delete Desktop `.url`/`.lnk` from user/OneDrive/Public Desktop → wipe `%LOCALAPPDATA%\LibertyBasketballDemo` via TEMP handoff bat (avoids self-delete race) → sweep `%TEMP%\LibertyDemo_*` logs/dirs → print removed list → explicitly leave winget Python alone → exit.
- **Cleanup smoke (this machine):** Created dummy `%LOCALAPPDATA%\LibertyBasketballDemo` + Desktop `.url` + TEMP log; ran `install_and_run.bat --cleanup-phase … ok`. AFTER: persist=`False`, url=`False`, log=`False`. Console printed `deleted: …\LibertyBasketballDemo` and Desktop shortcut path.
- **DONE dialog smoke:** Started `demo_done_dialog.ps1`, found window title `Liberty Basketball Demo`, closed it, process ExitCode=`0`.
- **Rebuilt SFX (-t7z):** `dist\LibertyDemo.exe` and `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` (see commit/report for size/timestamp). Staging includes `demo_done_dialog.ps1` + `wait_for_done` markers.

### Files

- `deploy/install_and_run.bat` — DONE wait + wipe_temp_leftovers + cleanup messaging
- `deploy/demo_done_dialog.ps1` — WinForms DONE button
- `scripts/build_demo_package.ps1` — package dialog + markers/README
- `dist/LibertyDemo.exe` / `dist/README_DEMO.txt` — rebuilt package

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
