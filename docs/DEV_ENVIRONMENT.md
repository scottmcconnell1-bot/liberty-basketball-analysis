# Dev Environment

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Python version

Use **Python 3.12 or 3.13**. Python 3.15 beta breaks numpy/pandas installs for the pinned stack.

## Quick start (web + tests)

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python -m pytest tests/ -q
python app.py
```

`requirements.txt` includes `requirements-dev.txt` (Flask, pytest, pandas, scipy).

## Full AI / video analysis

Use Docker (recommended):

```bash
docker compose up -d --build
```

Or install `requirements.docker.txt` on a Linux host with Python 3.12 after installing torch per `Dockerfile`.

### Windows (manual AI install)

PyTorch only publishes wheels for **Python 3.12 or 3.13 (64-bit)**. If `pip install torch` says `from versions: none`, your active `python` is probably 3.14+, 3.11, or 32-bit.

```powershell
cd C:\Users\scott\Projects\liberty-basketball-analysis
python --version
py -0p

# If needed, install Python 3.12 and recreate the venv:
winget install Python.Python.3.12
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Recommended one-shot installer:
.\scripts\install_ai_deps.ps1
```

Then restart the app and confirm **Settings → Runtime** shows OpenCV and Ultralytics as **Yes**.


## Files

| File | Purpose |
| --- | --- |
| `requirements.txt` | Default — web app + unit tests |
| `requirements-dev.txt` | Lightweight dependency list (included by requirements.txt) |
| `requirements.docker.txt` | OpenCV, ultralytics, gunicorn for containers/production AI |
