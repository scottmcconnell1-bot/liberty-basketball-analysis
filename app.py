"""
Liberty Basketball Analysis - Main Application

This is the entry point for the Flask application. All routes have been
organized into Flask Blueprints under the blueprints/ directory.

Blueprint modules:
  core       - Index, schedule, videos, settings, debug, dashboard, status
  games      - Games, sources, scheduled games, NFHS matches
  clips      - Clips, events, players
  stats      - Seasons, stats
  practice   - Practices, practice notes, plan items
  player_dev - Player development clips, practice playlists
  ai         - Video upload, AI analysis, video management
  scouting   - Scouting reports, NFHS download, opponent analysis
  coach      - Coach portal shared-password soft gate + learning progress
"""

import os
from pathlib import Path
from flask import Flask, g, jsonify, request, session

from config import Config


def _load_dotenv() -> None:
    """Load repo .env into os.environ without overriding real env vars."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


_load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)
# Always reload Jinja templates from disk (production-like debug=off otherwise caches them).
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True
# Refresh password from env after .env load (Config may have been imported earlier).
app.config["COACH_PASSWORD"] = os.environ.get("LIBERTY_COACH_PASSWORD", "")
app.config["SECRET_KEY"] = (
    os.environ.get("SECRET_KEY")
    or app.config.get("SECRET_KEY")
    or "liberty-basketball-dev-secret-key-2026"
)
app.config.setdefault("DATABASE", "film_analysis.db")
app.config.setdefault("UPLOAD_FOLDER", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB max upload
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Register Blueprints ──────────────────────────────────────
from blueprints.core import core
from blueprints.games import games_bp
from blueprints.clips import clips_bp
from blueprints.stats import stats_bp
from blueprints.practice import practice
from blueprints.player_dev import player_dev
from blueprints.ai import ai_bp
from blueprints.playbook import playbook_bp
from blueprints.messaging import messaging_bp
from blueprints.users import users_bp, _current_user
from blueprints.scouting import scouting_bp
from blueprints.bulk_import import bulk_import_bp
from blueprints.coach import coach_bp, enforce_coach_ops_denylist

app.register_blueprint(messaging_bp)
app.register_blueprint(users_bp)
app.register_blueprint(core)
app.register_blueprint(games_bp)
app.register_blueprint(clips_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(practice)
app.register_blueprint(player_dev)
app.register_blueprint(ai_bp)
app.register_blueprint(playbook_bp)
app.register_blueprint(scouting_bp)
app.register_blueprint(bulk_import_bp)
app.register_blueprint(coach_bp)

# ── Template Context Processors ──────────────────────────────
from helpers import get_runtime_settings

@app.context_processor
def inject_feature_flags():
    settings = get_runtime_settings()
    coach_portal = bool(session.get("coach_portal"))
    return {
        "features": settings["features"],
        "analysis_config": settings["analysis"],
        "coach_portal": coach_portal,
        # Alias for templates that hide Save/Delete/Create in coach mode
        "coach_readonly": coach_portal,
    }


@app.before_request
def coach_portal_ops_gate():
    """Soft denylist for coach portal sessions (does not enable global auth)."""
    return enforce_coach_ops_denylist()


@app.template_global()
def nav_active(*names):
    """Return True when the current Flask endpoint matches any candidate name.

    Pass blueprint-qualified endpoints (e.g. ``core.film``). A trailing ``.*``
    matches any function in that blueprint (e.g. ``playbook.*``).
    """
    from flask import request

    endpoint = request.endpoint or ""
    for name in names:
        if name.endswith(".*"):
            prefix = name[:-2]
            if endpoint == prefix or endpoint.startswith(prefix + "."):
                return True
            continue
        if endpoint == name:
            return True
    return False

# ── CSP Header ───────────────────────────────────────────────
@app.after_request
def set_csp(response):
    response.headers["Content-Security-Policy"] = (
        "default-src * 'unsafe-inline' 'unsafe-eval'; "
        "script-src * 'unsafe-inline' 'unsafe-eval'; "
        "style-src * 'unsafe-inline'; "
        "img-src * data: blob:; "
        "font-src * data:; "
        "connect-src * ws: wss:; "
        "media-src * blob:; "
        "worker-src * blob:"
    )
    return response

# ── Teardown ─────────────────────────────────────────────────
@app.teardown_appcontext
def close_db(exception):
    """Close the database connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── Auth Middleware ───────────────────────────────────────────
@app.before_request
def require_auth_for_api():
    """Auth middleware — disabled until user system is implemented."""
    pass  # No auth enforced yet — will be enabled in a future phase


@app.before_request
def coach_portal_ops_gate():
    """Soft denylist for coach portal sessions (does not enable global auth)."""
    return enforce_coach_ops_denylist()


# ── Re-exports (for test conftest and external imports) ──────
import subprocess
from helpers import get_db, init_db, ai_runtime_available, start_analysis_subprocess

# ── CLI Commands ─────────────────────────────────────────────
import click

@app.cli.command("init-db")
def init_db_command():
    """Initialize the database."""
    from helpers import init_db
    init_db()
    click.echo("Database initialized.")


if __name__ == "__main__":
    with app.app_context():
        from helpers import ensure_db
        ensure_db()
    _debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    # launch_liberty.py / teach loop expect PORT (default 8080); do not hardcode 5000
    _port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=_port, debug=_debug, use_reloader=False)


@app.route("/sw.js")
def service_worker():
    """Serve service worker with correct MIME type."""
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"}
