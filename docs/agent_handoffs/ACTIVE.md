# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-wait-before-browser |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- Immediate multi-method browser open caused ERR_CONNECTION_REFUSED + many Chrome tabs.
- Fix shipped in `61f97de`: wait for HTTP 200 (~1s poll, max 120s) then ONE `Start-Process` browser open. No Desktop `.url`. Python `-WindowStyle Hidden`. Already-running guard skips Temp re-setup. DONE does not reopen browser.
- Machine cleaned (no 8090 listeners, no Desktop .url, LocalAppData absent). Proof test: WAIT_OK → BROWSER_OPENED_ONCE.
- Rebuilt `dist\LibertyDemo.exe` 2026-07-19 15:11:54 (26.31 MB). `dist/` is gitignored; bat/scripts committed + pushed.

### Uninstall removes vs keeps

- **Removes:** `%LOCALAPPDATA%\LibertyBasketballDemo`, TEMP `LibertyDemo_*`, leftover Desktop `.url`/`.lnk`, idle TEMP `7zS*` extracts with our markers
- **Keeps:** `dist\LibertyDemo.exe`, winget Python

### Files

- `deploy/install_and_run.bat`
- `scripts/build_demo_package.ps1`
- `blueprints/demo.py`
- `docs/agent_handoffs/ACTIVE.md`

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
