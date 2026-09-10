"""
conftest.py – pytest fixtures for Liberty Basketball Analysis tests.
"""
import os
import tempfile
import pytest
import sys

# Ensure the project root is on sys.path so app.py can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def app():
    import app as app_module

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    upload_dir = tempfile.TemporaryDirectory()

    app_module.app.config.update({
        "TESTING": True,
        "DATABASE": db_path,
        "UPLOAD_FOLDER": upload_dir.name,
    })
    os.makedirs(os.path.join(upload_dir.name, "team_photos"), exist_ok=True)

    with app_module.app.app_context():
        app_module.init_db()

    yield app_module.app

    os.unlink(db_path)
    upload_dir.cleanup()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    """Return a live DB connection inside the app context."""
    with app.app_context():
        from app import get_db
        conn = get_db()
        yield conn


@pytest.fixture(autouse=True)
def _isolate_play_match_store(tmp_path, monkeypatch):
    """Keep per-game play-match JSON out of the real repo tree.

    blueprints.ai._play_match_store_base() resolves to <app root>/data/play_matches, so any
    test that renders a film page or hits /api/film/<game>/play-matches would otherwise write
    into the working copy (seen as an untracked data/play_matches/ after a test run).
    """
    import blueprints.ai as ai_mod
    import helpers

    monkeypatch.setattr(ai_mod, "_play_match_store_base", lambda: str(tmp_path / "play_matches"))
    # Analysis launcher logs default to <repo>/logs/ai-<game>.log; keep test logs in tmp_path too.
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(helpers, "ai_analysis_log_path", lambda game_id: str(log_dir / f"ai-{game_id}.log"))


@pytest.fixture(autouse=True)
def _never_spawn_real_analysis(monkeypatch):
    """Safety net: no test may launch analysis_launcher.py for real.

    helpers.start_analysis_subprocess() spawns `python analysis_launcher.py <db> <video> <game>`
    as a detached process. Tests that exercise those routes must stub
    `blueprints.ai.start_analysis_subprocess` (or subprocess.Popen) themselves; if one forgets,
    fail loudly instead of starting a multi-minute CPU job against whatever DB/video it was
    handed. Other subprocess.Popen uses (git, bash, ffmpeg) are untouched.
    """
    import subprocess

    real_popen = subprocess.Popen

    # Must stay a class: third-party code subclasses subprocess.Popen at import time
    # (e.g. yt_dlp's `class Popen(subprocess.Popen)`), which a plain function breaks.
    class GuardedPopen(real_popen):
        def __init__(self, args, *a, **kw):
            cmd = args if isinstance(args, (list, tuple)) else [args]
            if any("analysis_launcher.py" in str(part) for part in cmd):
                raise AssertionError(
                    "Test attempted to spawn analysis_launcher.py — stub start_analysis_subprocess "
                    f"in this test. Command: {cmd}"
                )
            super().__init__(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
