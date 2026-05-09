"""
Notification Service
===================

Handles sending notifications via:
- Browser Push API (Web Push)
- Email (SMTP)

Usage:
    from services.notifications import notify_message_received

    notify_message_received(db, message_id, conversation_id, sender_id, body)
"""

import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ── Config helpers ──────────────────────────────────────────

def _get_config(key, default=None):
    """Get a config value from Flask app config or environment."""
    try:
        from flask import current_app
        return current_app.config.get(key, default)
    except Exception:
        return default


def _vapid_keys():
    """Get VAPID keys from config. Returns (private_key, public_key) or (None, None)."""
    private = _get_config("VAPID_PRIVATE_KEY", "")
    public = _get_config("VAPID_PUBLIC_KEY", "")
    if private and public:
        return private, public
    return None, None


def _smtp_config():
    """Get SMTP config from app config. Returns dict or None."""
    server = _get_config("SMTP_SERVER", "")
    port = _get_config("SMTP_PORT", 587)
    username = _get_config("SMTP_USERNAME", "")
    password = _get_config("SMTP_PASSWORD", "")
    from_addr = _get_config("SMTP_FROM", "")
    use_tls = _get_config("SMTP_USE_TLS", True)

    if server and username and password:
        return {
            "server": server,
            "port": int(port),
            "username": username,
            "password": password,
            "from_addr": from_addr or username,
            "use_tls": bool(use_tls),
        }
    return None


# ── Browser Push ────────────────────────────────────────────

def send_push_notification(db, user_id, title, body, url=None):
    """Send a browser push notification to a user's subscribed devices."""
    private_key, public_key = _vapid_keys()
    if not private_key:
        logger.info("VAPID keys not configured, skipping push notification")
        return False

    # Get user's push subscriptions
    subs = db.execute(
        "SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)
    ).fetchall()

    if not subs:
        return False

    try:
        from pywebpush import webpush, WebPushException

        payload = json.dumps({
            "title": title,
            "body": body[:120],
            "url": url or "/messages",
            "icon": "/static/img/patriot-logo.jpg",
        })

        success = False
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {
                            "p256dh": sub["p256dh"],
                            "auth": sub["auth_key"],
                        },
                    },
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={"sub": "mailto:admin@libertybasketball.com"},
                )
                success = True
            except WebPushException as e:
                logger.warning(f"Push failed for user {user_id}: {e}")
                # Remove invalid subscription
                if e.response and e.response.status_code in (404, 410):
                    db.execute(
                        "DELETE FROM push_subscriptions WHERE id = ?", (sub["id"],)
                    )
                    db.commit()

        return success

    except ImportError:
        logger.warning("pywebpush not installed, cannot send push notifications")
        return False
    except Exception as e:
        logger.error(f"Push notification error: {e}")
        return False


# ── Email ───────────────────────────────────────────────────

def send_email_notification(db, user_id, subject, body_html, body_text=None):
    """Send an email notification to a user."""
    smtp = _smtp_config()
    if not smtp:
        logger.info("SMTP not configured, skipping email notification")
        return False

    # Get user email
    user = db.execute("SELECT email, display_name FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or not user["email"]:
        return False

    to_addr = user["email"]
    to_name = user["display_name"] or to_addr

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp["from_addr"]
    msg["To"] = to_addr

    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        if smtp["use_tls"]:
            server = smtplib.SMTP(smtp["server"], smtp["port"])
            server.starttls()
        else:
            server = smtplib.SMTP(smtp["server"], smtp["port"])
        server.login(smtp["username"], smtp["password"])
        server.sendmail(smtp["from_addr"], [to_addr], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False


# ── Message Notifications ───────────────────────────────────

def notify_message_received(db, message_id, conversation_id, sender_id, body):
    """
    When a message is received:
    1. Create notification records for all conversation members (except sender)
    2. Send browser push to members who have it enabled
    3. Send email to members who have it enabled
    """
    # Get sender info
    sender = db.execute("SELECT display_name FROM users WHERE id = ?", (sender_id,)).fetchone()
    sender_name = sender["display_name"] if sender else "Someone"

    # Get conversation info
    conv = db.execute("SELECT name, type FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    conv_name = conv["name"] if conv and conv["name"] else "a conversation"

    # Get all conversation members except sender
    members = db.execute(
        "SELECT user_id FROM conversation_members WHERE conversation_id = ? AND user_id != ?",
        (conversation_id, sender_id),
    ).fetchall()

    title = f"New message from {sender_name}"
    body_preview = body[:100] if body else "You have a new message"
    msg_url = f"/messages?c={conversation_id}"

    for member in members:
        member_id = member["user_id"]

        # Check notification preferences
        prefs = db.execute(
            "SELECT * FROM user_notification_prefs WHERE user_id = ?", (member_id,)
        ).fetchone()

        # 1. Create in-app notification record
        db.execute(
            "INSERT INTO notifications (user_id, type, title, body, link, source_type, source_id) VALUES (?,?,?,?,?,?,?)",
            (member_id, "message", title, body_preview, msg_url, "message", message_id),
        )

        # 2. Browser push (if enabled)
        if prefs and prefs.get("notify_push_messages"):
            # Check quiet hours
            if not _in_quiet_hours(prefs):
                send_push_notification(db, member_id, title, body_preview, msg_url)

        # 3. Email (if enabled)
        if prefs and prefs.get("notify_email_messages"):
            if not _in_quiet_hours(prefs):
                html = f"""
                <div style="font-family:Inter,sans-serif;max-width:500px;margin:0 auto;">
                    <h2 style="color:#01696f;">{title}</h2>
                    <p style="color:#1a1a1a;font-size:1rem;">{body_preview}</p>
                    <a href="https://libertybasketball.com{msg_url}"
                       style="display:inline-block;background:#01696f;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:600;">
                        Open Messages
                    </a>
                </div>
                """
                send_email_notification(
                    db, member_id,
                    subject=f"[Liberty Basketball] {title}",
                    body_html=html,
                    body_text=f"{title}\n\n{body_preview}\n\nOpen: https://libertybasketball.com{msg_url}",
                )

    db.commit()


def _in_quiet_hours(prefs):
    """Check if current time is within user's quiet hours."""
    if not prefs or not prefs.get("quiet_hours_start") or not prefs.get("quiet_hours_end"):
        return False

    from datetime import datetime
    now = datetime.now().strftime("%H:%M")
    start = prefs["quiet_hours_start"]
    end = prefs["quiet_hours_end"]

    if start <= end:
        return start <= now <= end
    else:
        # Wraps midnight (e.g., 22:00 - 07:00)
        return now >= start or now <= end
