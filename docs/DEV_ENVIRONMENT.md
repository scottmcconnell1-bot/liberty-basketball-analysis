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

## Files

| File | Purpose |
| --- | --- |
| `requirements.txt` | Default — web app + unit tests |
| `requirements-dev.txt` | Lightweight dependency list (included by requirements.txt) |
| `requirements.docker.txt` | OpenCV, ultralytics, gunicorn for containers/production AI |
