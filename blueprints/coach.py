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
    # One banner per coach session — avoid stacking identical flashes.
    if not session.get("_coach_readonly_flashed"):
        flash("Coach view is read-only — changes are not saved.", "error")
        session["_coach_readonly_flashed"] = True
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
        return redirect(url_for("coach.coach_progress"))

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
            session.pop("_coach_readonly_flashed", None)
            # Soft role hint for templates / future role checks (not full user auth).
            if not session.get("user_role"):
                session["user_role"] = "coach"
            if not session.get("user_name"):
                session["user_name"] = "Coach"
            flash("Welcome — you are in Coach view.", "success")
            next_url = request.args.get("next") or url_for("coach.coach_progress")
            return redirect(next_url)

        flash("Incorrect coach password.", "error")

    return render_template(
        "coach_login.html",
        password_set=password_set,
    )


@coach_bp.route("/coach/exit")
@require_feature("ENABLE_COACH_PORTAL")
def coach_exit_full_app():
    """Leave read-only Coach view and open the full staff app in this browser."""
    session.pop("coach_portal", None)
    session.pop("_coach_readonly_flashed", None)
    flash("Left Coach view — full app (not read-only).", "success")
    return redirect(url_for("core.index"))


@coach_bp.route("/coach/logout")
@require_feature("ENABLE_COACH_PORTAL")
def coach_logout():
    """Clear coach portal session flag."""
    session.pop("coach_portal", None)
    session.pop("_coach_readonly_flashed", None)
    # Only clear soft coach hints if there is no real user login.
    if not session.get("user_id"):
        if session.get("user_role") == "coach":
            session.pop("user_role", None)
        if session.get("user_name") == "Coach":
            session.pop("user_name", None)
    # Drop queued flashes (stacked read-only warnings) so login stays clean.
    session.pop("_flashes", None)
    flash("Signed out of Coach view.", "success")
    return redirect(url_for("coach.coach_login"))


def _pct_label(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def build_coach_progress_snapshot() -> dict:
    """Live learning / program progress for coach portal (read-only)."""
    from pathlib import Path
    import json
    import sqlite3
    from datetime import datetime

    root = Path(__file__).resolve().parents[1]
    panel_path = root / "data" / "hoopsalytics" / "full_film_panel_latest.json"
    teach_path = root / "data" / "hoopsalytics" / "teach_loop_state.json"
    status_path = root / "docs" / "LEARNING_STATUS.md"
    db_path = root / "film_analysis.db"

    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "queue": {
            "hudl_taught": None,
            "hudl_videos": None,
            "pct": None,
            "note": "Unknown",
        },
        "active": [],
        "panel": {
            "overall_pass": None,
            "mean_precision": None,
            "mean_recall": None,
            "gates": [],
            "generated_at": None,
        },
        "status_markdown": None,
        "status_mtime": None,
    }

    taught_hudl = []
    if teach_path.is_file():
        try:
            state = json.loads(teach_path.read_text(encoding="utf-8"))
            taught = state.get("taught") or state.get("taught_keys") or []
            if isinstance(taught, dict):
                taught = list(taught.keys())
            taught_hudl = [k for k in taught if str(k).startswith("hudl_")]
            snapshot["queue"]["hudl_taught"] = len(taught_hudl)
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            vid_n = conn.execute(
                "SELECT COUNT(*) AS n FROM videos WHERE game_id LIKE 'hudl_%'"
            ).fetchone()["n"]
            snapshot["queue"]["hudl_videos"] = vid_n
            if snapshot["queue"]["hudl_taught"] is not None and vid_n:
                pct = 100.0 * snapshot["queue"]["hudl_taught"] / vid_n
                snapshot["queue"]["pct"] = round(pct, 1)
                snapshot["queue"]["note"] = (
                    f"{snapshot['queue']['hudl_taught']} of {vid_n} HUDL games taught"
                )
            for row in conn.execute(
                """
                SELECT analysis_key, status, progress_pct, progress_step
                FROM analysis_runs
                WHERE status = 'running'
                ORDER BY id DESC
                LIMIT 8
                """
            ):
                snapshot["active"].append(
                    {
                        "key": row["analysis_key"],
                        "progress_pct": row["progress_pct"],
                        "step": row["progress_step"] or "",
                    }
                )
            conn.close()
        except sqlite3.Error:
            pass

    if panel_path.is_file():
        try:
            panel = json.loads(panel_path.read_text(encoding="utf-8"))
            evaluation = panel.get("evaluation") or {}
            snapshot["panel"]["overall_pass"] = evaluation.get("overall_pass")
            snapshot["panel"]["mean_precision"] = evaluation.get("mean_precision")
            snapshot["panel"]["mean_recall"] = evaluation.get("mean_recall")
            snapshot["panel"]["generated_at"] = panel.get("generated_at")
            gates = (evaluation.get("gates") or {})
            for name, gate in gates.items():
                snapshot["panel"]["gates"].append(
                    {
                        "name": name,
                        "required": gate.get("required"),
                        "actual": gate.get("actual"),
                        "pass": gate.get("pass"),
                        "required_label": _pct_label(gate.get("required"))
                        if name.startswith("event_")
                        else (
                            "100%"
                            if gate.get("required") == 1.0
                            else str(gate.get("required"))
                        ),
                        "actual_label": _pct_label(gate.get("actual")),
                    }
                )
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    if status_path.is_file():
        try:
            snapshot["status_markdown"] = status_path.read_text(encoding="utf-8")
            snapshot["status_mtime"] = datetime.fromtimestamp(
                status_path.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            pass

    return snapshot


@coach_bp.route("/coach/progress")
@require_feature("ENABLE_COACH_PORTAL")
def coach_progress():
    """Always-on learning / program progress for coaches (live read)."""
    if not session.get("coach_portal"):
        return redirect(url_for("coach.coach_login", next=request.path))
    snapshot = build_coach_progress_snapshot()
    return render_template("coach_progress.html", progress=snapshot)
