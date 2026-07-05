# AGENTS.md

## Cursor Cloud specific instructions

This is a single-product Python 3.12 Flask app ("Liberty Basketball Analysis") with an embedded SQLite database. Server-rendered Jinja templates + vanilla JS; there is no Node/npm build step.

The update script creates `.venv` and installs `requirements-dev.txt`. Activate it with `. .venv/bin/activate` (or call binaries directly, e.g. `.venv/bin/python`).

### Dependency caveat (important)
- `requirements.txt` and `requirements.docker.txt` are referenced by the README/Dockerfile but do **not** exist in the repo. Only `requirements-dev.txt` is present, and it is sufficient to run the full web app and the entire test suite.
- Heavy CV/ML deps (`torch`, `opencv-python`, `ultralytics`, `mediapipe`, `pywebpush`, `gunicorn`) are intentionally **not** installed. The web app boots and all tests pass without them; the AI film-analysis pipeline (video → auto-generated events), LLM notes (Ollama), and push notifications will not run in this environment. Install those extras manually only if you need to work on the CV/AI pipeline.

### Running the app
- `FLASK_DEBUG=0 .venv/bin/python app.py` — dev server.
- Port gotcha: `python app.py` binds to **port 5000** (hardcoded in the `__main__` block), NOT the `8080`/`PORT` value in the README. `PORT`/`8080` only applies to the Docker/gunicorn paths. `LIBERTY_DEBUG` is ignored by `python app.py`; use `FLASK_DEBUG=1` for debug mode.
- The `__main__` block auto-runs `ensure_db()`, so the SQLite DB (`film_analysis.db`) is created on first launch; no separate init step is required. To init manually: `.venv/bin/flask init-db`.

### Testing
- `.venv/bin/python -m pytest tests/ -q` (config in `pytest.ini`, `testpaths = tests`). Tests use isolated temp DBs via `tests/conftest.py`, so they don't touch `film_analysis.db`.
- No linter is configured (no ruff/flake8/black config in the repo).
