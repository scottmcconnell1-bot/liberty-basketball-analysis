# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-done-uninstall-api |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Root cause of DONE alert:** `POST /api/demo/done` scheduled `os._exit` on a background thread *before* Flask finished flushing the JSON response. The browser `fetch` then failed mid-response and showed: "Could not reach the demo uninstall API…" (button stuck on Closing…/Uninstalling…).
- **Fix:** Spawn cleanup bat first; start `threading.Timer(0.5, os._exit)` only from `@after_this_request` so the HTTP 200 is returned successfully; JS retries once and only shows the network alert after real failure; `launch_liberty.resolve_demo_mode_env()` clears inherited `DEMO_MODE` / stray TEMP flag on main Documents launches (demo package still sets flag + `DEMO_MODE=1`).
- **SFX not regressed:** Build still uses vendored `tools\sfx\7zSD.sfx` + `Directory=""` + visible `cmd /c install_and_run.bat` (commit 2df9f50).
- **Tests:** `tests/test_demo_mode.py` — 6 passed (includes return-200-before-exit).
- **Exe:** `dist\LibertyDemo.exe` / `C:\Temp\LibertyDemoPackage\LibertyDemo.exe` (~26.26 MB).

### Files

- `blueprints/demo.py` — response-before-exit; cleanup spawn before Timer
- `templates/base.html` — Uninstalling… + one retry
- `scripts/launch_liberty.py` — clear stale DEMO_MODE on non-demo trees
- `tests/test_demo_mode.py` — handler ordering test
- Prior SFX: `tools/sfx/7zSD.sfx`, `scripts/build_demo_package.ps1`, `deploy/install_and_run.bat`

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
