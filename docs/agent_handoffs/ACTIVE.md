# Active Task

Updated: 2026-07-18
Branch: `cursor/fix-demo-sfx-7z-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | fix-demo-python-detect-loop |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- LibertyDemo `install_and_run.bat` could re-enter Python discovery after winget without a max-attempt guard; when PATH was stale post-install, discovery failed again and winget/`goto` restart logic looped forever ("Python … not found … winget" / "Restarting script…").
- Fix: `INSTALL_TRIED=1` caps winget to **once**; after install, refresh Machine+User PATH from registry + prepend common Python dirs; probe `LocalAppData\Programs\Python\Python312|313`, `ProgramFiles\Python312`, and `py -3.12`/`py -3.13`; store `PYTHON_EXE` as full path (py launcher preferred via `sys.executable`).
- Smoke (this machine): detection found `C:\Users\scott\AppData\Local\Programs\Python\Python312\python.exe` via py launcher; `INSTALL_TRIED` stayed `0` (no winget).
- Rebuilt SFX (`-t7z`): `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` and `dist\LibertyDemo.exe` (26.22 MB / 27,490,284 bytes). GPU AI job left alone.

### Files

- `deploy/install_and_run.bat` — one-shot winget + PATH refresh + common probes
- `scripts/build_demo_package.ps1` — markers assert `INSTALL_TRIED` / `PYTHON_EXE` / no `goto :find_python` restart

### Leave alone

- GPU AI / Q1 rerun job — not touched
