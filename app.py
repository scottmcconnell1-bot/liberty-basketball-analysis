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
"""

import os
from flask import Flask, g

from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.config["SECRET_KEY"] = app.config.get("SECRET_KEY") or "liberty-basketball-dev-secret-key-2026"
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

# ── Template Context Processors ──────────────────────────────
from helpers import get_runtime_settings

@app.context_processor
def inject_feature_flags():
    settings = get_runtime_settings()
    return {
        "features": settings["features"],
        "analysis_config": settings["analysis"],
    }

# ── CSP Header ───────────────────────────────────────────────
@app.after_request
def set_csp(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "media-src 'self' blob:; "
        "worker-src 'self' blob:"
    )
    return response

# ── Teardown ─────────────────────────────────────────────────
@app.teardown_appcontext
def close_db(exception):
    """Close the database connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


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
    app.run(host="0.0.0.0", port=8081, debug=True, use_reloader=False)


@app.route("/sw.js")
def service_worker():
    """Serve service worker with correct MIME type."""
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"}
