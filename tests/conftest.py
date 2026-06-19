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
