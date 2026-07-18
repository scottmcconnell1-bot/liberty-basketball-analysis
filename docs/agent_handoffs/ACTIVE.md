# Active Task

Updated: 2026-07-18
Branch: `cursor/demo-desktop-shortcut-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-desktop-shortcut |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- First run (SFX TEMP extract) robocopies payload to `%LOCALAPPDATA%\LibertyBasketballDemo\` (excludes `.venv`), creates Desktop shortcut `Liberty Basketball Demo.lnk` via WScript.Shell targeting that folder's `install_and_run.bat`, then relaunches from LocalAppData so TEMP cleanup cannot break the shortcut.
- Subsequent runs from LocalAppData / shortcut: skip copy, reuse `.venv`, winget only if Python missing (still one-shot `INSTALL_TRIED`).
- On exit: stop Liberty process tree + delete TEMP log; keep install, `.venv`, and Desktop shortcut.
- Rebuilt SFX (`-t7z`): `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` and `dist\LibertyDemo.exe` (26.22 MB / 27,489,939 bytes).
- Shortcut COM smoke: CreateShortcut wrote a valid `.lnk` with Target + WorkingDirectory under LocalAppData.

### Files

- `deploy/install_and_run.bat` — persist install + Desktop shortcut + keep `.venv`
- `scripts/build_demo_package.ps1` — markers + README_DEMO text for persist/shortcut

### Leave alone

- GPU AI / Q1 rerun job — not touched
