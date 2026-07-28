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

import json
from flask import Blueprint, render_template, request, jsonify

from helpers import get_db, require_feature

messaging_bp = Blueprint("messaging", __name__)


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

    return render_template(
        "messages.html",
        conversations=[dict(c) for c in conversations],
        active_conversation=dict(active_conversation) if active_conversation else None,
        active_messages=[dict(m) for m in active_messages],
        active_members=[dict(m) for m in active_members],
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
    """Send a message to a conversation."""
    data = request.get_json(force=True) if request.is_json else request.form
    conversation_id = data.get("conversation_id")
    body = (data.get("body") or "").strip()
    sender_id = (data.get("sender_id") or "coach").strip()
    attachment_url = (data.get("attachment_url") or "").strip() or None

    if not conversation_id or not body:
        return jsonify({"error": "conversation_id and body required"}), 400

    db = get_db()
    # Create conversation if it doesn't exist
    conv = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if not conv:
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (conversation_id, "direct", sender_id),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (conversation_id, sender_id, "owner"),
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
