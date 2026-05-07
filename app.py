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
"""

import os
from flask import Flask

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

app.config.setdefault("DATABASE", "film_analysis.db")
app.config.setdefault("UPLOAD_FOLDER", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ── Register Blueprints ──────────────────────────────────────
from blueprints.core import core
from blueprints.games import games_bp
from blueprints.clips import clips_bp
from blueprints.stats import stats_bp
from blueprints.practice import practice
from blueprints.player_dev import player_dev
from blueprints.ai import ai_bp

app.register_blueprint(core)
app.register_blueprint(games_bp)
app.register_blueprint(clips_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(practice)
app.register_blueprint(player_dev)
app.register_blueprint(ai_bp)

# ── Template Context Processors ──────────────────────────────
from helpers import get_runtime_settings

@app.context_processor
def inject_feature_flags():
    settings = get_runtime_settings()
    return {
        "features": settings["features"],
        "analysis_config": settings["analysis"],
    }

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
    from helpers import ensure_db
    ensure_db()
    app.run(host="0.0.0.0", port=8081, debug=True)
