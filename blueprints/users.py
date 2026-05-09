"""
Users Blueprint
===============

User accounts, authentication, profiles, and notification preferences.

Routes included:
- login (/login)                              — Login page
- register (/register)                        — Registration page
- logout (/logout)                            — Logout
- profile (/profile)                          — User profile
- profile_edit (/profile/edit POST)           — Update profile
- settings_notifications (/settings/notifications) — Notification preferences
- api_users (/api/users)                      — List users (for mentions, DMs)
"""

import hashlib, secrets, datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app

from helpers import get_db, require_feature

users_bp = Blueprint("users", __name__)

ROLE_OPTIONS = [
    ("player", "Player"),
    ("parent", "Parent"),
    ("coach", "Coach"),
    ("manager", "Manager"),
    ("admin", "Admin"),
]

ROLE_HIERARCHY = {"player": 0, "parent": 1, "coach": 2, "manager": 3, "admin": 4}


def _hash_password(password):
    """Hash a password with SHA-256 + salt."""
    salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${pw_hash}"


def _verify_password(password, stored_hash):
    """Verify a password against a stored hash."""
    if "$" not in stored_hash:
        return False
    salt, pw_hash = stored_hash.split("$", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == pw_hash


def _current_user():
    """Get the currently logged-in user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()


def login_required(f):
    """Decorator to require login."""
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _current_user():
            return redirect(url_for("users.login", next=request.url))
        return f(*args, **kwargs)
    return wrapped


def role_required(min_role):
    """Decorator to require a minimum role level."""
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if not user:
                return redirect(url_for("users.login", next=request.url))
            if ROLE_HIERARCHY.get(user["role"], 0) < ROLE_HIERARCHY.get(min_role, 0):
                flash("You don't have permission to access this page.", "error")
                return redirect(url_for("core.index"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


@users_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login page."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)).fetchone()

        if user and _verify_password(password, user["password_hash"]):
            # Create session
            token = secrets.token_hex(32)
            expires = datetime.datetime.utcnow() + datetime.timedelta(days=30)
            db.execute(
                "INSERT INTO user_sessions (user_id, session_token, ip_address, user_agent, expires_at) VALUES (?,?,?,?,?)",
                (user["id"], token, request.remote_addr, request.user_agent.string[:200], expires),
            )
            db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            db.commit()

            session["user_id"] = user["id"]
            session["user_role"] = user["role"]
            session["user_name"] = user["display_name"]
            session["session_token"] = token

            next_url = request.args.get("next") or url_for("core.index")
            return redirect(next_url)

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@users_bp.route("/register", methods=["GET", "POST"])
def register():
    """Registration page."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        display_name = (request.form.get("display_name") or "").strip()
        role = (request.form.get("role") or "player").strip()

        errors = []
        if not email or "@" not in email:
            errors.append("Valid email is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != password2:
            errors.append("Passwords don't match.")
        if not display_name:
            errors.append("Display name is required.")
        if role not in dict(ROLE_OPTIONS):
            errors.append("Invalid role.")

        if not errors:
            db = get_db()
            existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", roles=ROLE_OPTIONS)

        db = get_db()
        pw_hash = _hash_password(password)
        db.execute(
            "INSERT INTO users (email, password_hash, display_name, role) VALUES (?,?,?,?)",
            (email, pw_hash, display_name, role),
        )
        db.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("users.login"))

    return render_template("register.html", roles=ROLE_OPTIONS)


@users_bp.route("/logout")
def logout():
    """Logout and clear session."""
    token = session.get("session_token")
    if token:
        db = get_db()
        db.execute("DELETE FROM user_sessions WHERE session_token = ?", (token,))
        db.commit()
    session.clear()
    return redirect(url_for("users.login"))


@users_bp.route("/profile")
@login_required
def profile():
    """View own profile."""
    user = _current_user()
    db = get_db()
    prefs = db.execute("SELECT * FROM user_notification_prefs WHERE user_id = ?", (user["id"],)).fetchone()
    return render_template("profile.html", user=user, prefs=prefs, roles=ROLE_OPTIONS)


@users_bp.route("/profile/edit", methods=["POST"])
@login_required
def profile_edit():
    """Update profile."""
    user = _current_user()
    display_name = (request.form.get("display_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    avatar_url = (request.form.get("avatar_url") or "").strip()

    if not display_name:
        flash("Display name is required.", "error")
        return redirect(url_for("users.profile"))

    db = get_db()
    db.execute(
        "UPDATE users SET display_name=?, phone=?, avatar_url=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (display_name, phone or None, avatar_url or None, user["id"]),
    )
    db.commit()
    session["user_name"] = display_name
    flash("Profile updated.", "success")
    return redirect(url_for("users.profile"))


@users_bp.route("/settings/notifications", methods=["GET", "POST"])
@login_required
def settings_notifications():
    """Notification preferences page."""
    user = _current_user()
    db = get_db()

    if request.method == "POST":
        db.execute(
            """INSERT OR REPLACE INTO user_notification_prefs
               (user_id, notify_email_messages, notify_email_schedule, notify_push_messages,
                notify_push_schedule, notify_sms_game_reminder, quiet_hours_start, quiet_hours_end, updated_at)
               VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (
                user["id"],
                1 if request.form.get("notify_email_messages") else 0,
                1 if request.form.get("notify_email_schedule") else 0,
                1 if request.form.get("notify_push_messages") else 0,
                1 if request.form.get("notify_push_schedule") else 0,
                1 if request.form.get("notify_sms_game_reminder") else 0,
                request.form.get("quiet_hours_start") or None,
                request.form.get("quiet_hours_end") or None,
            ),
        )
        db.commit()
        flash("Notification preferences saved.", "success")
        return redirect(url_for("users.settings_notifications"))

    prefs = db.execute("SELECT * FROM user_notification_prefs WHERE user_id = ?", (user["id"],)).fetchone()
    return render_template("notifications_settings.html", user=user, prefs=prefs)


@users_bp.route("/api/users")
@login_required
def api_users():
    """List users (for mentions, DM autocomplete)."""
    q = (request.args.get("q") or "").strip().lower()
    db = get_db()
    if q:
        users = db.execute(
            "SELECT id, display_name, email, role, avatar_url FROM users WHERE is_active = 1 AND (LOWER(display_name) LIKE ? OR LOWER(email) LIKE ?) ORDER BY display_name LIMIT 20",
            (f"%{q}%", f"%{q}%")
        ).fetchall()
    else:
        users = db.execute(
            "SELECT id, display_name, email, role, avatar_url FROM users WHERE is_active = 1 ORDER BY display_name LIMIT 20"
        ).fetchall()
    return jsonify([dict(u) for u in users])


@users_bp.route("/api/notifications")
@login_required
def api_notifications():
    """Get unread notifications for the current user."""
    user = _current_user()
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT 20",
        (user["id"],)
    ).fetchall()
    return jsonify([dict(n) for n in notifs])


@users_bp.route("/api/notifications/read", methods=["POST"])
@login_required
def api_notifications_read():
    """Mark notifications as read."""
    user = _current_user()
    data = request.get_json(force=True) if request.is_json else request.form
    notif_ids = data.get("ids", [])
    db = get_db()
    for nid in notif_ids:
        db.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (int(nid), user["id"]))
    db.commit()
    return jsonify({"ok": True})


@users_bp.route("/api/push/subscribe", methods=["POST"])
@login_required
def api_push_subscribe():
    """Register a browser push subscription."""
    user = _current_user()
    data = request.get_json(force=True)
    endpoint = data.get("endpoint", "")
    p256dh = data.get("keys", {}).get("p256dh", "")
    auth = data.get("keys", {}).get("auth", "")

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Invalid subscription data"}), 400

    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO push_subscriptions (user_id, endpoint, p256dh, auth_key) VALUES (?,?,?,?)",
        (user["id"], endpoint, p256dh, auth),
    )
    db.commit()
    return jsonify({"ok": True})


@users_bp.route("/api/push/unsubscribe", methods=["POST"])
@login_required
def api_push_unsubscribe():
    """Remove a browser push subscription."""
    user = _current_user()
    data = request.get_json(force=True)
    endpoint = data.get("endpoint", "")

    db = get_db()
    db.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user["id"], endpoint))
    db.commit()
    return jsonify({"ok": True})
