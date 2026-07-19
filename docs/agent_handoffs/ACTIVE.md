# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-desktop-shortcut-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-desktop-shortcut-url-fix |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Root cause:** Prior shortcut path used fragile multi-line `powershell -Command ^` + WScript.Shell / `[IO.File]::WriteAllText` with nested `\"` quoting. Failures were soft-warned (`WARNING: ... Demo will still run`) so the demo appeared to work with no Desktop icon. Complex Desktop resolve via PowerShell was unnecessary on this PC (`C:\Users\scott\Desktop` exists and is writable).
- **Fix:** Plain cmd `(echo [InternetShortcut] & echo URL=...) > "%DESKTOP%\Liberty Basketball Demo.url"` — no PowerShell for create. Also attempts `%PUBLIC%\Desktop` (Access Denied without admin is non-fatal). Failures now `pause` + hard exit (not swallowed).
- **Live proof on Scott's machine:** `dir` shows `C:\Users\scott\Desktop\Liberty Basketball Demo.url` (47 bytes, 2026-07-18 11:37 PM) with contents `[InternetShortcut]` / `URL=http://127.0.0.1:8080`. Left in place for user to see.
- **Rebuilt:** `dist\LibertyDemo.exe` and `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` — 27,491,724 bytes, LastWriteTime 2026-07-18 11:38:26 PM. Extracted SFX `install_and_run.bat` contains new `echo [InternetShortcut]` / `echo URL=` lines and has **no** WScript.

### Files

- `deploy/install_and_run.bat` — cmd .url shortcut create/remove
- `scripts/build_demo_package.ps1` — markers + README_DEMO for .url-only path
- `dist/LibertyDemo.exe` / `dist/README_DEMO.txt` — rebuilt package

### Leave alone

- GPU AI / Q1 rerun job — not touched
