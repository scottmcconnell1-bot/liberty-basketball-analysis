"""
Messaging Blueprint
===================

GameChanger-style team messaging system.

Routes included:
- messages (/messages)                              — Conversation list + message view
- messages_api_list (/api/messages/conversations)    — List conversations
- messages_api_send (/api/messages/send POST)        — Send a message
- messages_api_poll (/api/messages/poll)             — Poll for new messages
- messages_api_read (/api/messages/read POST)        — Mark messages as read
"""

from flask import Blueprint, render_template, request, jsonify, session

from helpers import get_db, require_feature

messaging_bp = Blueprint("messaging", __name__)


def _resolve_sender_id(explicit=None):
    """Prefer logged-in staff user id; fall back to coach portal or explicit/default.

    Matches nav auth: ``session['user_id']`` is the staff login key (not coach_portal).
    """
    user_id = session.get("user_id")
    if user_id is not None and str(user_id).strip() != "":
        return str(user_id)
    if session.get("coach_portal"):
        return "coach"
    explicit = (explicit or "").strip()
    return explicit or "coach"


def _user_row_is_active(row):
    """Legacy users may have NULL is_active — treat as active (same as usable login)."""
    if row is None:
        return False
    try:
        keys = row.keys()
    except Exception:
        keys = ()
    if "is_active" not in keys:
        return True
    val = row["is_active"]
    if val is None:
        return True
    try:
        return int(val) == 1
    except (TypeError, ValueError):
        return bool(val)


def _current_messaging_identity(db):
    """Return display identity for the messages UI (staff login or coach portal).

    Must stay aligned with ``base.html`` nav, which shows the account link whenever
    ``session['user_id']`` is set (using ``session['user_name']``). Do not require a
    successful users-table join to treat the staff session as signed in.
    """
    user_id = session.get("user_id")
    if user_id is not None and str(user_id).strip() != "":
        row = None
        try:
            row = db.execute(
                "SELECT id, display_name, email, role, is_active FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        except Exception:
            row = None
        if row is not None and _user_row_is_active(row):
            return {
                "sender_id": str(row["id"]),
                "display_name": row["display_name"] or session.get("user_name") or "Account",
                "email": row["email"],
                "role": row["role"] or session.get("user_role") or "staff",
                "signed_in": True,
            }
        # Session cookie present (nav would show this user) — trust session even if
        # the users row is missing/inactive in this DB copy.
        return {
            "sender_id": str(user_id),
            "display_name": session.get("user_name") or "Account",
            "email": None,
            "role": session.get("user_role") or "staff",
            "signed_in": True,
        }
    if session.get("coach_portal"):
        return {
            "sender_id": "coach",
            "display_name": session.get("user_name") or "Coach",
            "email": None,
            "role": "coach",
            "signed_in": True,
        }
    return {
        "sender_id": "coach",
        "display_name": "Guest",
        "email": None,
        "role": None,
        "signed_in": False,
    }


@messaging_bp.route("/messages")
@require_feature("ENABLE_PRACTICES")
def messages():
    """Main messaging page — conversation list + active conversation."""
    db = get_db()
    conversations = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count,
                  (SELECT m.body FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1) as last_message,
                  (SELECT m.created_at FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1) as last_message_at
           FROM conversations c
           JOIN conversation_members cm ON cm.conversation_id = c.id
           ORDER BY c.updated_at DESC"""
    ).fetchall()

    active_conversation = None
    active_messages = []
    active_members = []

    conv_id = request.args.get("c", type=int)
    if conv_id:
        active_conversation = db.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if active_conversation:
            active_messages = db.execute(
                """SELECT m.*, 
                          (SELECT COUNT(*) FROM message_read_receipts mr WHERE mr.message_id = m.id) as read_count
                   FROM messages m
                   WHERE m.conversation_id = ?
                   ORDER BY m.created_at ASC""",
                (conv_id,)
            ).fetchall()
            active_members = db.execute(
                "SELECT * FROM conversation_members WHERE conversation_id = ?", (conv_id,)
            ).fetchall()

    identity = _current_messaging_identity(db)
    directory_users = []
    try:
        rows = db.execute(
            """SELECT id, display_name, email, role, is_active FROM users
               ORDER BY display_name LIMIT 100"""
        ).fetchall()
        self_id = identity["sender_id"] if identity.get("signed_in") else None
        for u in rows:
            if not _user_row_is_active(u):
                continue
            if self_id and str(u["id"]) == str(self_id):
                continue
            directory_users.append({
                "id": u["id"],
                "display_name": u["display_name"],
                "email": u["email"],
                "role": u["role"],
            })
    except Exception:
        directory_users = []

    return render_template(
        "messages.html",
        conversations=[dict(c) for c in conversations],
        active_conversation=dict(active_conversation) if active_conversation else None,
        active_messages=[dict(m) for m in active_messages],
        active_members=[dict(m) for m in active_members],
        messaging_identity=identity,
        directory_users=directory_users,
    )


@messaging_bp.route("/api/messages/conversations", methods=["GET"])
@require_feature("ENABLE_PRACTICES")
def messages_api_list():
    """List all conversations for the current user."""
    db = get_db()
    conversations = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count,
                  (SELECT m.body FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1) as last_message,
                  (SELECT m.created_at FROM messages m WHERE m.conversation_id = c.id ORDER BY m.created_at DESC LIMIT 1) as last_message_at
           FROM conversations c
           JOIN conversation_members cm ON cm.conversation_id = c.id
           ORDER BY c.updated_at DESC"""
    ).fetchall()
    return jsonify([dict(c) for c in conversations])


@messaging_bp.route("/api/messages/send", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def messages_api_send():
    """Send a message to a conversation.

    New chats may omit conversation_id and supply recipient_id instead; the
    server creates the conversation and adds both members.
    """
    data = request.get_json(force=True) if request.is_json else request.form
    conversation_id = data.get("conversation_id")
    body = (data.get("body") or "").strip()
    sender_id = _resolve_sender_id(data.get("sender_id"))
    recipient_id = (data.get("recipient_id") or "").strip() or None
    attachment_url = (data.get("attachment_url") or "").strip() or None
    title = (data.get("title") or "").strip() or None

    if not body:
        return jsonify({"error": "body required"}), 400
    if not conversation_id and not recipient_id:
        # Keep legacy clients working: conversation_id was previously required.
        return jsonify({"error": "conversation_id and body required"}), 400

    db = get_db()

    if not conversation_id:
        # Start a new direct conversation with an optional recipient.
        if not title and recipient_id:
            recip = db.execute(
                "SELECT display_name FROM users WHERE id = ? AND is_active = 1",
                (recipient_id,),
            ).fetchone()
            if recip:
                title = f"Chat with {recip['display_name']}"
            else:
                title = "Direct Message"
        if not title:
            title = "New conversation"
        cur_conv = db.execute(
            "INSERT INTO conversations (type, created_by, title) VALUES (?,?,?)",
            ("direct", sender_id, title),
        )
        conversation_id = cur_conv.lastrowid
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (conversation_id, sender_id, "owner"),
        )
        if recipient_id and str(recipient_id) != str(sender_id):
            db.execute(
                "INSERT OR IGNORE INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
                (conversation_id, str(recipient_id), "member"),
            )
    else:
        conv = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not conv:
            db.execute(
                "INSERT INTO conversations (id, type, created_by, title) VALUES (?,?,?,?)",
                (conversation_id, "direct", sender_id, title or "Direct Message"),
            )
            db.execute(
                "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
                (conversation_id, sender_id, "owner"),
            )
            if recipient_id and str(recipient_id) != str(sender_id):
                db.execute(
                    "INSERT OR IGNORE INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
                    (conversation_id, str(recipient_id), "member"),
                )

    cur = db.execute(
        "INSERT INTO messages (conversation_id, sender_id, body, attachment_url) VALUES (?,?,?,?)",
        (conversation_id, sender_id, body, attachment_url),
    )
    db.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conversation_id,),
    )
    db.commit()

    # Send notifications to conversation members
    try:
        from services.notifications import notify_message_received
        notify_message_received(db, cur.lastrowid, conversation_id, sender_id, body)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Notification error: {e}")

    return jsonify({
        "id": cur.lastrowid,
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "body": body,
        "created_at": "now",
    })


@messaging_bp.route("/api/messages/poll")
@require_feature("ENABLE_PRACTICES")
def messages_api_poll():
    """Poll for new messages in a conversation."""
    conversation_id = request.args.get("conversation_id", type=int)
    since_id = request.args.get("since_id", type=int, default=0)

    if not conversation_id:
        return jsonify({"error": "conversation_id required"}), 400

    db = get_db()
    messages = db.execute(
        """SELECT m.*,
                  (SELECT COUNT(*) FROM message_read_receipts mr WHERE mr.message_id = m.id) as read_count
           FROM messages m
           WHERE m.conversation_id = ? AND m.id > ?
           ORDER BY m.created_at ASC""",
        (conversation_id, since_id)
    ).fetchall()

    return jsonify([dict(m) for m in messages])


@messaging_bp.route("/api/messages/read", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def messages_api_read():
    """Mark messages as read."""
    data = request.get_json(force=True) if request.is_json else request.form
    message_ids = data.get("message_ids", [])
    user_id = (data.get("user_id") or "coach").strip()

    if not message_ids:
        return jsonify({"error": "message_ids required"}), 400

    db = get_db()
    for mid in message_ids:
        try:
            db.execute(
                "INSERT OR IGNORE INTO message_read_receipts (message_id, user_id) VALUES (?,?)",
                (int(mid), user_id),
            )
        except Exception:
            pass
    db.commit()
    return jsonify({"ok": True})
