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
  stat_books - Handwritten spiral scorebook extract / confirm
"""

import logging
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
# Refresh env-backed settings after .env load: config.Config read os.environ
# when it was imported, which is before _load_dotenv() ran.
app.config["COACH_PASSWORD"] = os.environ.get("LIBERTY_COACH_PASSWORD", "")
for _config_key, _env_key in (("DATABASE", "LIBERTY_DATABASE"), ("UPLOAD_FOLDER", "LIBERTY_UPLOAD_FOLDER")):
    if os.environ.get(_env_key):
        app.config[_config_key] = os.environ[_env_key]
_DEV_SECRET_KEY = "liberty-basketball-dev-secret-key-2026"
app.config["SECRET_KEY"] = (
    os.environ.get("SECRET_KEY")
    or app.config.get("SECRET_KEY")
    or _DEV_SECRET_KEY
)
if app.config["SECRET_KEY"] == _DEV_SECRET_KEY:
    # This key is committed to the repo, so anyone who has read it can forge
    # a session cookie (including an admin login). Set SECRET_KEY in .env.
    logging.getLogger(__name__).warning(
        "SECRET_KEY is unset - using the committed dev fallback. "
        "Set SECRET_KEY in .env before exposing the app on a network."
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
from blueprints.stat_books import stat_books_bp

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
app.register_blueprint(stat_books_bp)

# ── Template Context Processors ──────────────────────────────
from helpers import get_runtime_settings

@app.context_processor
def inject_feature_flags():
    settings = get_runtime_settings()
    coach_portal = bool(session.get("coach_portal"))
    # Verified account (live session token), not the raw cookie, which outlives logout.
    try:
        signed_in_user = _current_user()
    except Exception:
        signed_in_user = None
    from audience_access import is_family_role
    family_viewer = bool(signed_in_user) and is_family_role(signed_in_user["role"])
    return {
        "signed_in_user": dict(signed_in_user) if signed_in_user else None,
        "features": settings["features"],
        "analysis_config": settings["analysis"],
        "coach_portal": coach_portal,
        # Alias for templates that hide Save/Delete/Create in coach mode
        "coach_readonly": coach_portal,
        # Parents and players watch. Coaches edit. Unsigned home use stays editable.
        "family_viewer": family_viewer,
        "audience_can_edit": (not family_viewer) and (not coach_portal),
    }


@app.before_request
def coach_portal_ops_gate():
    """Soft denylist for coach portal sessions (does not enable global auth)."""
    return enforce_coach_ops_denylist()


@app.before_request
def family_viewer_gate():
    """Parents and players may watch. They may not change coach tools or see the team board.

    Unsigned requests are left alone so the home machine stays usable while
    sign-in is not required.
    """
    from flask import flash, redirect, url_for
    from audience_access import FAMILY_POST_ALLOW, FAMILY_REDIRECT_PREFIXES, is_family_role

    user = None
    try:
        user = _current_user()
    except Exception:
        user = None
    if not user or not is_family_role(user["role"]):
        return None
    path = request.path or "/"
    if path.startswith("/static/") or path in ("/sw.js", "/favicon.ico"):
        return None
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if path in FAMILY_POST_ALLOW or path.startswith("/play/share/"):
            return None
        # Their own messages, notification prefs, and sign-in. Coach settings
        # still hit the route, which refuses anyone who is not an admin.
        if path.startswith("/api/messages/") or path.startswith("/api/notifications") or path in (
            "/settings/notifications",
            "/settings",
            "/settings/ollama/pull",
            "/register",
        ):
            return None
        if path.startswith("/api/"):
            return jsonify({"error": "Parents and players can view only."}), 403
        flash("Parents and players can view only.", "error")
        return redirect(url_for("core.my_stats"))
    if path == "/settings/notifications":
        return None
    if path == "/" or path.startswith(FAMILY_REDIRECT_PREFIXES):
        if path.startswith("/api/"):
            return jsonify({"error": "Parents and players can view only their own stats."}), 403
        return redirect(url_for("core.my_stats"))
    return None


@app.template_global()
def nav_active(*names):
    """Return True when the current Flask endpoint matches any candidate name.

    Pass blueprint-qualified endpoints (e.g. ``core.film``). A trailing ``.*``
    matches any function in that blueprint (e.g. ``playbook.*``).
    """
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
# Reachable without signing in even when the gate is on.
_AUTH_PUBLIC_PATHS = {"/login", "/logout", "/register", "/sw.js", "/favicon.ico"}
_AUTH_PUBLIC_PREFIXES = ("/static/", "/coach", "/play/share/")


@app.before_request
def require_auth_for_api():
    """Require a signed-in user when ENABLE_AUTH_MIDDLEWARE is on (default off).

    Coach-portal sessions pass through only while ENABLE_COACH_PORTAL is on;
    enforce_coach_ops_denylist() keeps them read-only. APIs get 401 JSON, pages redirect to /login.
    """
    from flask import redirect, url_for
    from helpers import feature_enabled

    if not feature_enabled("ENABLE_AUTH_MIDDLEWARE"):
        return None
    path = request.path or "/"
    if path in _AUTH_PUBLIC_PATHS or path.startswith(_AUTH_PUBLIC_PREFIXES):
        return None
    # A coach_portal cookie only counts while the portal feature is on; otherwise a
    # stale cookie would pass here and also skip the read-only denylist.
    if session.get("coach_portal") and feature_enabled("ENABLE_COACH_PORTAL"):
        return None
    if session.get("user_id") and _current_user() is not None:
        return None
    if path.startswith("/api/") or request.is_json:
        return jsonify({"error": "Sign-in required."}), 401
    next_path = request.full_path if request.query_string else path
    return redirect(url_for("users.login", next=next_path))
# ── Re-exports (for test conftest and external imports) ──────
import subprocess  # noqa: F401
from helpers import get_db, init_db, ai_runtime_available, start_analysis_subprocess  # noqa: F401

# ── CLI Commands ─────────────────────────────────────────────
import click

@app.cli.command("init-db")
def init_db_command():
    """Initialize the database."""
    init_db()
    click.echo("Database initialized.")


@app.route("/sw.js")
def service_worker():
    """Serve service worker with correct MIME type.

    Must be registered before the `__main__` block: `python app.py` (how the home PC
    runs) never gets past app.run(), so routes defined below it did not exist.
    """
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"}


if __name__ == "__main__":
    with app.app_context():
        from helpers import ensure_db
        ensure_db()
    _debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    # launch_liberty.py / teach loop expect PORT (default 8080); do not hardcode 5000
    _port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=_port, debug=_debug, use_reloader=False)
