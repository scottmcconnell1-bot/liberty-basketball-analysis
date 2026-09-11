"""Tests for the Messaging feature."""

import json


class TestMessagesPage:
    def test_messages_page_loads(self, client):
        r = client.get("/messages")
        assert r.status_code == 200
        assert b"Messages" in r.data or b"Conversations" in r.data or b"messaging" in r.data.lower()

    def test_new_chat_uses_in_app_modal_not_window_prompt(self, client):
        """+ New Chat must open an in-app form, not browser window.prompt."""
        r = client.get("/messages")
        assert r.status_code == 200
        html = r.data.decode("utf-8", errors="replace")
        assert "prompt(" not in html
        assert 'id="new-chat-modal"' in html
        assert 'id="new-chat-body"' in html
        assert 'id="new-chat-recipient"' in html
        assert "openNewChatModal" in html

    def test_authenticated_staff_sees_own_identity(self, client, db):
        """Nav and Messages must agree: session user_id → signed-in as that person."""
        db.execute(
            "INSERT INTO users (email, password_hash, display_name, role, is_active) VALUES (?,?,?,?,1)",
            ("scott@example.com", "x", "Scott McConnell", "admin"),
        )
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE email = ?", ("scott@example.com",)).fetchone()[0]

        with client.session_transaction() as sess:
            sess["user_id"] = uid
            sess["user_name"] = "Scott McConnell"
            sess["user_role"] = "admin"

        r = client.get("/messages")
        assert r.status_code == 200
        html = r.data.decode("utf-8", errors="replace")
        assert "Not signed in" not in html
        assert "Signed in as" in html
        assert "Scott McConnell" in html
        assert "guest coach identity" not in html.lower()
        # Sender id in JS should be the staff user id, not hardcoded coach guest
        assert f'const MSG_SENDER_ID = "{uid}"' in html or f"const MSG_SENDER_ID = {uid}" in html

    def test_session_identity_without_users_row_still_signed_in(self, client):
        """If users row is missing, still mirror nav (session user_name) — not Guest."""
        with client.session_transaction() as sess:
            sess["user_id"] = 4242
            sess["user_name"] = "Scott McConnell"
            sess["user_role"] = "admin"

        r = client.get("/messages")
        assert r.status_code == 200
        html = r.data.decode("utf-8", errors="replace")
        assert "Not signed in" not in html
        assert "Scott McConnell" in html
        assert "Signed in as" in html

    def test_send_api_uses_session_user_as_sender(self, client, db):
        db.execute(
            "INSERT INTO users (email, password_hash, display_name, role, is_active) VALUES (?,?,?,?,1)",
            ("scott2@example.com", "x", "Scott McConnell", "admin"),
        )
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE email = ?", ("scott2@example.com",)).fetchone()[0]

        with client.session_transaction() as sess:
            sess["user_id"] = uid
            sess["user_name"] = "Scott McConnell"

        r = client.post(
            "/api/messages/send",
            data=json.dumps({"conversation_id": 55, "body": "Hello from Scott", "sender_id": "coach"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["sender_id"] == str(uid)
        assert data["body"] == "Hello from Scott"

class TestMessagesAPIList:
    def test_list_conversations_empty(self, client):
        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_list_conversations_with_data(self, client, db):
        # Create a conversation
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", "coach"),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (1, "coach", "owner"),
        )
        db.commit()

        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) >= 1
        assert data[0]["id"] == 1


class TestMessagesSend:
    def test_send_message(self, client):
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "Test message",
            "sender_id": "coach",
        })
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["body"] == "Test message"
        assert data["sender_id"] == "coach"

    def test_send_message_requires_body(self, client):
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "",
            "sender_id": "coach",
        })
        assert r.status_code == 400

    def test_send_message_requires_conversation_id(self, client):
        r = client.post("/api/messages/send", data={
            "body": "Test",
            "sender_id": "coach",
        })
        assert r.status_code == 400

    def test_send_message_json(self, client):
        r = client.post("/api/messages/send",
            data=json.dumps({
                "conversation_id": 2,
                "body": "JSON message",
                "sender_id": "assistant",
            }),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["body"] == "JSON message"

    def test_send_creates_conversation_if_missing(self, client):
        r = client.post("/api/messages/send", data={
            "conversation_id": 999,
            "body": "New convo message",
            "sender_id": "coach",
        })
        assert r.status_code == 200

    def test_send_with_recipient_creates_conversation(self, client, db):
        db.execute(
            "INSERT INTO users (email, password_hash, display_name, role, is_active) VALUES (?,?,?,?,1)",
            ("assist@example.com", "x", "Assistant One", "coach"),
        )
        db.commit()
        recip = db.execute("SELECT id FROM users WHERE email = ?", ("assist@example.com",)).fetchone()[0]

        r = client.post(
            "/api/messages/send",
            data=json.dumps({
                "body": "Hello teammate",
                "sender_id": "coach",
                "recipient_id": str(recip),
            }),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["body"] == "Hello teammate"
        assert data["conversation_id"]

        members = [
            row[0]
            for row in db.execute(
                "SELECT user_id FROM conversation_members WHERE conversation_id = ?",
                (data["conversation_id"],),
            ).fetchall()
        ]
        assert "coach" in members
        assert str(recip) in members


class TestMessagesPoll:
    def test_poll_messages(self, client, db):
        # Create conversation and message
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", "coach"),
        )
        db.execute(
            "INSERT INTO messages (conversation_id, sender_id, body) VALUES (?,?,?)",
            (1, "coach", "Hello"),
        )
        db.commit()

        r = client.get("/api/messages/poll?conversation_id=1&since_id=0")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) >= 1
        assert data[0]["body"] == "Hello"

    def test_poll_requires_conversation_id(self, client):
        r = client.get("/api/messages/poll")
        assert r.status_code == 400

    def test_poll_since_id(self, client, db):
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", "coach"),
        )
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (1, 1, "coach", "First"),
        )
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (2, 1, "coach", "Second"),
        )
        db.commit()

        r = client.get("/api/messages/poll?conversation_id=1&since_id=1")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["body"] == "Second"


class TestMessagesRead:
    def test_mark_read(self, client, db):
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", "coach"),
        )
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (1, 1, "coach", "Test"),
        )
        db.commit()

        r = client.post("/api/messages/read", data={
            "message_ids": [1],
            "user_id": "coach",
        })
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["ok"] is True

    def test_mark_read_requires_message_ids(self, client):
        r = client.post("/api/messages/read", data={
            "user_id": "coach",
        })
        assert r.status_code == 400

    def test_mark_read_json(self, client, db):
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", "coach"),
        )
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (1, 1, "coach", "Test"),
        )
        db.commit()

        r = client.post("/api/messages/read",
            data=json.dumps({"message_ids": [1], "user_id": "coach"}),
            content_type="application/json",
        )
        assert r.status_code == 200


class TestMessagesDB:
    def test_messaging_tables_exist(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "conversations" in tables
        assert "conversation_members" in tables
        assert "messages" in tables
        assert "message_read_receipts" in tables

    def test_message_read_receipts_unique(self, db):
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", "coach"),
        )
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (1, 1, "coach", "Test"),
        )
        db.execute(
            "INSERT INTO message_read_receipts (message_id, user_id) VALUES (?,?)",
            (1, "coach"),
        )
        db.commit()

        # Duplicate should be ignored (unique constraint)
        try:
            db.execute(
                "INSERT INTO message_read_receipts (message_id, user_id) VALUES (?,?)",
                (1, "coach"),
            )
            db.commit()
        except Exception:
            db.rollback()

        count = db.execute(
            "SELECT COUNT(*) FROM message_read_receipts WHERE message_id = 1"
        ).fetchone()[0]
        assert count == 1


def test_settings_notifications_save_persists_all_columns(client, app):
    """Regression: the INSERT had 9 columns and 8 values -> every save of the page 500'd."""
    client.post("/register", data={"email": "n@example.com", "password": "password-1", "password2": "password-1",
                                   "display_name": "N", "role": "coach"}, follow_redirects=False)
    client.post("/login", data={"email": "n@example.com", "password": "password-1"}, follow_redirects=False)
    r = client.post("/settings/notifications", data={"notify_email_messages": "1", "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}, follow_redirects=False)
    assert r.status_code in (200, 302, 303), r.data[:200]
    with app.app_context():
        from helpers import get_db
        row = get_db().execute("SELECT notify_email_messages, quiet_hours_start, quiet_hours_end FROM user_notification_prefs").fetchone()
    assert tuple(row) == (1, "22:00", "07:00")
