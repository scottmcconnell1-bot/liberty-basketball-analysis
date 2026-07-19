# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-wait-before-browser |
| **status** | `in_progress` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- Immediate multi-method browser open caused ERR_CONNECTION_REFUSED + many Chrome tabs (server not ready / DONE re-opened).
- Fix: wait for HTTP 200 (poll ~1s, max 120s) then ONE `powershell Start-Process` browser open. No Desktop `.url`. Python `-WindowStyle Hidden`. Skip re-setup if demo already listening. DONE does not open browser; uninstall wipes LocalAppData + TEMP leftovers, keeps `dist\LibertyDemo.exe`.

### Files

- `deploy/install_and_run.bat` — wait-for-200, single browser, no shortcut, hidden server, already-running guard
- `scripts/build_demo_package.ps1` — smoke checks aligned
- `blueprints/demo.py` — cleanup also tries idle 7zS* SFX temps

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
