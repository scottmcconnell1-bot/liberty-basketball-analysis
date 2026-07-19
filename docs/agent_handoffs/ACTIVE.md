# Active Task

Updated: 2026-07-19
Branch: `cursor/demo-done-uninstall-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | demo-browser-immediate-open |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Why 3c69672 still failed:** Log after "Starting Liberty" showed `Launcher PID`, then `[WAIT] attempt at 0s` (timeout) and `[WAIT] attempt at 2s` — then **stopped**. No `[BROWSER]` lines ever. Browser open was still gated behind the wait loop; `launch_liberty` re-ran pip for minutes before Flask listened, so the bat never reached `:open_browser` (second `Invoke-WebRequest` appeared stuck / loop never advanced to the 3s early-open path in practice).
- **Server was fine:** `.server`/`.err` showed Flask up on 8080 with API 200s — console wait was the failure, not the app.
- **Hard fix:** Open browser **immediately** after `Start-Process` (before any health poll). Five methods: `cmd /c start`, PowerShell `Start-Process`, `explorer.exe` URL, `start ""`, Desktop `.url` + explorer. Demo ports **8090–8100 only** (8080 reserved for main). Loud `CHOSEN DEMO PORT` / `DEMO URL` logs. Poll is log-only; re-opens browser when HTTP ready. Replaced `timeout` delay with `ping` (SFX stdin hang risk).

### Files

- `deploy/install_and_run.bat` — immediate multi-method browser; 8090+ port pick
- `scripts/build_demo_package.ps1` — smoke checks for new markers / README

### Leave alone

- GPU AI / Q1 / app-context agent work — not touched
