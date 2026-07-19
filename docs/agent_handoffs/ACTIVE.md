# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-sfx-autostart-fix |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Root cause:** Stock `Program Files\7-Zip\7z.sfx` does **not** support `;!@Install@!` / `RunProgram` (strings absent in the binary). Prior builds concatenated a config that was ignored, so double-click only extracted — no bat, no browser.
- **Second bug:** Even with LZMA SDK `7zSD.sfx`, `RunProgram="cmd /c …"` without `Directory=""` looks for `cmd` **inside the archive**, not system `cmd.exe`. Fix: `Directory=""` + visible `RunProgram="cmd /c install_and_run.bat"` (never `hidcon`).
- **Bat:** `@echo off` then `cd /d "%~dp0"`; same-console continue after robocopy (no `start`+exit); `%TEMP%\LibertyDemo_run.log`; port 8080 else 8090; pause on failure; DEMO_MODE + browser open; no Desktop shortcuts.
- **Proof (2026-07-19 ~10:13 AM):** `LibertyDemo.exe -y` → run log written → HTTP 200 on `:8080` → `[BROWSER]` lines → HTML contains `demo-done-btn`.
- **Exe:** `dist\LibertyDemo.exe` / `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` (~26.26 MB, LastWriteTime 2026-07-19 10:13:13 AM). Vendored `tools\sfx\7zSD.sfx` (LZMA SDK, public domain).

### Files

- `tools/sfx/7zSD.sfx` + `README.txt` — installer SFX module with RunProgram
- `scripts/build_demo_package.ps1` — use 7zSD.sfx; require Directory=""; reject hidcon/stock 7z.sfx
- `deploy/install_and_run.bat` — logging, port fallback, same-console, pause on fail

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
