"""
Coach Portal Blueprint
======================

Shared-password soft gate for coaches viewing the live app.

Routes:
  GET/POST /coach          — password gate (or setup instructions)
  GET      /coach/login    — alias of /coach
  GET      /coach/logout   — clear coach_portal session

When session["coach_portal"] is set, the soft gate is also **read-only**:
GET/HEAD/OPTIONS (and ops-denylist exceptions) are allowed; mutating methods
are blocked except auth login/logout POSTs.
"""

from __future__ import annotations

import hmac
import os

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from helpers import feature_enabled, require_feature

coach_bp = Blueprint("coach", __name__)

# Ops paths coaches must not reach while coach_portal is set.
# Matched as exact path or prefix (path == item or path.startswith(item + "/")).
COACH_OPS_DENY_PREFIXES = (
    "/settings",
    "/users",
    "/debug",
    "/status",
    "/preview",
    "/nfhs-matches",
    "/api/admin",
    "/api/nfhs_matches",
    "/upload",
)

# Analysis / reset style endpoints (suffix or contains match on path).
COACH_OPS_DENY_SUFFIXES = (
    "/analyze",
    "/regenerate-events",
)

COACH_OPS_DENY_EXACT = {
    "/api/upload_video",
    "/api/upload_chunk",
    "/api/admin/reset",
}

# Safe HTTP methods always allowed in coach portal (subject to ops denylist).
COACH_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Mutating requests allowed only for auth flow (coach + app login/logout).
COACH_MUTATING_ALLOW_PATHS = frozenset({
    "/coach",
    "/coach/login",
    "/coach/logout",
    "/login",
    "/logout",
})


def coach_password_configured() -> bool:
    return bool((os.environ.get("LIBERTY_COACH_PASSWORD") or "").strip())


def get_coach_password() -> str:
    return (os.environ.get("LIBERTY_COACH_PASSWORD") or "").strip()


def normalize_coach_path(path: str) -> str:
    """Normalize a request path for denylist / allowlist checks."""
    if not path:
        return "/"
    normalized = path.split("?", 1)[0] or "/"
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def path_denied_for_coach(path: str) -> bool:
    """Return True if a coach_portal session must not access this path."""
    if not path:
        return False
    normalized = normalize_coach_path(path)

    if normalized in COACH_OPS_DENY_EXACT:
        return True

    for prefix in COACH_OPS_DENY_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True

    for suffix in COACH_OPS_DENY_SUFFIXES:
        if normalized.endswith(suffix):
            return True

    # NFHS download / matching ops under scouting
    if normalized.startswith("/api/scouting/nfhs"):
        return True

    return False


def _wants_json_response() -> bool:
    if request.path.startswith("/api/"):
        return True
    if request.is_json:
        return True
    content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        return True
    if request.accept_mimetypes.best == "application/json":
        return True
    return False


def coach_readonly_blocked_response():
    """403 (JSON) or flash + redirect for coach read-only mutations."""
    if _wants_json_response():
        return jsonify({"error": "Coach view is read-only"}), 403
    flash("Coach view is read-only — changes are not saved.", "error")
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for("core.index"))


def coach_mutation_allowed(path: str) -> bool:
    """Return True if a non-safe method is allowed for this path in coach mode."""
    return normalize_coach_path(path) in COACH_MUTATING_ALLOW_PATHS


def enforce_coach_ops_denylist():
    """before_request helper: ops denylist + read-only for coach_portal sessions."""
    if not session.get("coach_portal"):
        return None
    if not feature_enabled("ENABLE_COACH_PORTAL"):
        return None

    path = request.path or "/"

    # Static assets always allowed
    if path.startswith("/static"):
        return None

    # Coach auth routes: allow (login/logout POST included via mutating allowlist)
    if path.startswith("/coach"):
        if request.method in COACH_SAFE_METHODS or coach_mutation_allowed(path):
            return None
        return coach_readonly_blocked_response()

    # Ops denylist (all methods, including GET)
    if path_denied_for_coach(path):
        if _wants_json_response():
            abort(403)
        flash("That page is not available in Coach view.", "error")
        return redirect(url_for("core.index"))

    # Read-only: block POST/PUT/PATCH/DELETE except auth allowlist
    if request.method not in COACH_SAFE_METHODS and not coach_mutation_allowed(path):
        return coach_readonly_blocked_response()

    return None


@coach_bp.route("/coach", methods=["GET", "POST"])
@coach_bp.route("/coach/login", methods=["GET", "POST"])
@require_feature("ENABLE_COACH_PORTAL")
def coach_login():
    """Shared-password gate into coach portal session."""
    if session.get("coach_portal"):
        return redirect(url_for("core.index"))

    password_set = coach_password_configured()

    if request.method == "POST":
        if not password_set:
            flash("Coach portal password is not configured yet.", "error")
            return render_template(
                "coach_login.html",
                password_set=False,
            ), 503

        submitted = request.form.get("password") or ""
        expected = get_coach_password()
        submitted_b = submitted.encode("utf-8")
        expected_b = expected.encode("utf-8")
        # Length mismatch → reject (shared soft gate; avoid compare_digest ValueError).
        if len(submitted_b) == len(expected_b) and hmac.compare_digest(submitted_b, expected_b):
            session["coach_portal"] = True
            # Soft role hint for templates / future role checks (not full user auth).
            if not session.get("user_role"):
                session["user_role"] = "coach"
            if not session.get("user_name"):
                session["user_name"] = "Coach"
            flash("Welcome — you are in Coach view.", "success")
            next_url = request.args.get("next") or url_for("core.index")
            return redirect(next_url)

        flash("Incorrect coach password.", "error")

    return render_template(
        "coach_login.html",
        password_set=password_set,
    )


@coach_bp.route("/coach/logout")
@require_feature("ENABLE_COACH_PORTAL")
def coach_logout():
    """Clear coach portal session flag."""
    session.pop("coach_portal", None)
    # Only clear soft coach hints if there is no real user login.
    if not session.get("user_id"):
        if session.get("user_role") == "coach":
            session.pop("user_role", None)
        if session.get("user_name") == "Coach":
            session.pop("user_name", None)
    flash("Signed out of Coach view.", "success")
    return redirect(url_for("coach.coach_login"))
