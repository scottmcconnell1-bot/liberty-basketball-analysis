# Local Test Launch

Updated: 2026-07-06

One-command setup for coach testing on your machine.

## Windows (recommended)

1. Open the repo folder in File Explorer.
2. Double-click **`Start Liberty.bat`**.
3. First run:
   - Checks for Python 3.12/3.13 (installs via `winget` if missing)
   - Warns about / tries to install `ffmpeg` via `winget`
   - Creates `.venv`, installs `requirements.txt`, initializes SQLite
4. Your browser opens to **http://127.0.0.1:8080/** (dashboard).
5. Press **Ctrl+C** in the console window to stop the server.

## Linux / Ubuntu

```bash
bash scripts/launch_liberty.sh
```

Or:

```bash
python3 scripts/launch_liberty.py
```

## Options

```bash
python scripts/launch_liberty.py --port 8081
python scripts/launch_liberty.py --no-browser
python scripts/launch_liberty.py --reinstall-deps
```

## After launch — begin testing

| Page | URL |
| --- | --- |
| Dashboard | http://127.0.0.1:8080/ |
| Product preview | http://127.0.0.1:8080/preview |
| Status | http://127.0.0.1:8080/status |
| Film | http://127.0.0.1:8080/film |
| Review | http://127.0.0.1:8080/review |
| Assistant | http://127.0.0.1:8080/assistant |

See the coach walkthrough in chat or `docs/agent_handoffs/` for the full test checklist.

## Prerequisites handled automatically

| Software | Windows | Linux |
| --- | --- | --- |
| Python 3.12/3.13 | `winget` if missing | You install (`apt`) |
| pip / venv | Created on first run | Created on first run |
| ffmpeg | `winget` attempt + warning | Manual `apt install ffmpeg` |
| git | Optional warning only | Optional warning only |

## Troubleshooting

- **Port busy:** `python scripts/launch_liberty.py --port 8081`
- **Stale dependencies:** `python scripts/launch_liberty.py --reinstall-deps`
- **winget blocked:** Install Python 3.12 from python.org, then re-run `Start Liberty.bat`
