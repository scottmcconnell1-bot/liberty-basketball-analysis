# Active Task

Updated: 2026-07-18
Branch: `cursor/demo-desktop-shortcut-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-desktop-shortcut-cleanup |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- Prior build kept LocalAppData forever and only used `[Environment]::GetFolderPath('Desktop')` (+ `%USERPROFILE%\Desktop` fallback). That missed OneDrive/registry Desktop on some PCs, and cleanup left install + shortcut behind.
- Now resolves Desktop via GetFolderPath, `$HOME\Desktop`, `$HOME\OneDrive\Desktop`, and registry `User Shell Folders\Desktop`; picks first existing writable path; echoes full shortcut paths.
- Creates **Liberty Basketball Demo.lnk** (cmd `start` → `http://127.0.0.1:8080`) and **Liberty Basketball Demo.url** (`[InternetShortcut]`).
- On keypress: PID-based Liberty stop → delete TEMP logs → delete Desktop .lnk/.url on all candidate Desktops → wipe `%LOCALAPPDATA%\LibertyBasketballDemo` (via TEMP bat handoff so self-delete works). Winget Python left alone.
- On this machine Desktop candidates: only `C:\Users\scott\Desktop` (exists+writable); OneDrive\Desktop absent. Shortcut create/delete smoke passed.
- Rebuilt: `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` and `dist\LibertyDemo.exe` (~26.22 MB).

### Files

- `deploy/install_and_run.bat` — multi-path Desktop URL shortcuts + full wipe on exit
- `scripts/build_demo_package.ps1` — markers + README_DEMO for session wipe behavior

### Leave alone

- GPU AI / Q1 rerun job — not touched
