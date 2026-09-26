"""Tests for the Messaging feature (auth + membership required)."""

import json


def _sign_in_user(client, db, *, email="scott@example.com", name="Scott McConnell", role="admin"):
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        uid = existing[0]
    else:
        db.execute(
            "INSERT INTO users (email, password_hash, display_name, role, is_active) VALUES (?,?,?,?,1)",
            (email, "x", name, role),
        )
        db.commit()
        uid = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    with client.session_transaction() as sess:
        sess.pop("coach_portal", None)
        sess["user_id"] = uid
        sess["user_name"] = name
        sess["user_role"] = role
    return str(uid)


class TestMessagesPage:
    def test_messages_page_requires_auth(self, client):
        r = client.get("/messages", follow_redirects=False)
        assert r.status_code in (302, 303)

    def test_messages_page_loads(self, client, db):
        _sign_in_user(client, db)
        r = client.get("/messages")
        assert r.status_code == 200
        assert b"Messages" in r.data or b"Conversations" in r.data or b"messaging" in r.data.lower()

    def test_new_chat_uses_in_app_modal_not_window_prompt(self, client, db):
        """+ New Chat must open an in-app form, not browser window.prompt."""
        _sign_in_user(client, db)
        r = client.get("/messages")
        assert r.status_code == 200
        html = r.data.decode("utf-8", errors="replace")
        assert "prompt(" not in html
        assert "openNewChatModal" in html or "new-chat" in html.lower()
        assert "recipient" in html.lower() or "new-chat-recipient" in html

    def test_authenticated_staff_sees_own_identity(self, client, db):
        """Nav and Messages must agree: session user_id → signed-in as that person."""
        uid = _sign_in_user(client, db)

        r = client.get("/messages")
        assert r.status_code == 200
        html = r.data.decode("utf-8", errors="replace")
        assert "Not signed in" not in html
        assert "Signed in as" in html
        assert "Scott McConnell" in html
        assert "guest coach identity" not in html.lower()
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
        uid = _sign_in_user(client, db, email="scott2@example.com")
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (55, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (55, uid, "owner"),
        )
        db.commit()

        r = client.post(
            "/api/messages/send",
            data=json.dumps({"conversation_id": 55, "body": "Hello from Scott", "sender_id": "coach"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["sender_id"] == uid
        assert data["body"] == "Hello from Scott"

    def test_send_rejects_spoof_when_not_member(self, client, db):
        uid = _sign_in_user(client, db, email="player@example.com", name="Player", role="player")
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (77, "direct", "admin"),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (77, "admin", "owner"),
        )
        db.commit()
        r = client.post(
            "/api/messages/send",
            data=json.dumps({"conversation_id": 77, "body": "spoof", "sender_id": "admin"}),
            content_type="application/json",
        )
        assert r.status_code == 403
        assert uid


class TestMessagesAPIList:
    def test_list_requires_auth(self, client):
        r = client.get("/api/messages/conversations")
        assert r.status_code == 401

    def test_list_conversations_empty(self, client, db):
        _sign_in_user(client, db)
        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_list_conversations_with_data(self, client, db):
        uid = _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (1, uid, "owner"),
        )
        db.commit()

        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) >= 1
        assert data[0]["id"] == 1

    def test_list_hides_other_users_conversations(self, client, db):
        _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (2, "direct", "other"),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (2, "other", "owner"),
        )
        db.commit()
        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        ids = [c["id"] for c in json.loads(r.data)]
        assert 2 not in ids


class TestMessagesSend:
    def test_send_message(self, client, db):
        uid = _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (1, uid, "owner"),
        )
        db.commit()
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "Test message",
            "sender_id": "admin",
        })
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["body"] == "Test message"
        assert data["sender_id"] == uid

    def test_send_message_requires_body(self, client, db):
        uid = _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (1, uid, "owner"),
        )
        db.commit()
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "",
            "sender_id": "coach",
        })
        assert r.status_code == 400

    def test_send_message_requires_conversation_id(self, client, db):
        _sign_in_user(client, db)
        r = client.post("/api/messages/send", data={
            "body": "Test",
            "sender_id": "coach",
        })
        assert r.status_code == 400

    def test_send_message_json(self, client, db):
        uid = _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (2, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (2, uid, "owner"),
        )
        db.commit()
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
        assert data["sender_id"] == uid

    def test_send_unknown_conversation_is_404(self, client, db):
        _sign_in_user(client, db)
        r = client.post("/api/messages/send", data={
            "conversation_id": 999,
            "body": "New convo message",
            "sender_id": "coach",
        })
        assert r.status_code == 404

    def test_send_with_recipient_creates_conversation(self, client, db):
        uid = _sign_in_user(client, db)
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
                "sender_id": "spoof",
                "recipient_id": str(recip),
            }),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["body"] == "Hello teammate"
        assert data["conversation_id"]
        assert data["sender_id"] == uid

        members = [
            str(row[0])
            for row in db.execute(
                "SELECT user_id FROM conversation_members WHERE conversation_id = ?",
                (data["conversation_id"],),
            ).fetchall()
        ]
        assert uid in members
        assert str(recip) in members


class TestMessagesPoll:
    def test_poll_messages(self, client, db):
        uid = _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (1, uid, "owner"),
        )
        db.execute(
            "INSERT INTO messages (conversation_id, sender_id, body) VALUES (?,?,?)",
            (1, uid, "hello"),
        )
        db.commit()

        r = client.get("/api/messages/poll?conversation_id=1&since_id=0")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) >= 1

    def test_poll_requires_membership(self, client, db):
        _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (3, "direct", "other"),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (3, "other", "owner"),
        )
        db.commit()
        r = client.get("/api/messages/poll?conversation_id=3&since_id=0")
        assert r.status_code == 403


class TestMessagesRead:
    def test_mark_read(self, client, db):
        uid = _sign_in_user(client, db)
        db.execute(
            "INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)",
            (1, "direct", uid),
        )
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (1, uid, "owner"),
        )
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (10, 1, uid, "hi"),
        )
        db.commit()
        r = client.post(
            "/api/messages/read",
            data=json.dumps({"message_ids": [10], "user_id": "spoof"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        row = db.execute(
            "SELECT user_id FROM message_read_receipts WHERE message_id=10"
        ).fetchone()
        assert row is not None
        assert str(row[0]) == uid


class TestMessagingTables:
    def test_messaging_tables_exist(self, db):
        tables = {
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "conversations" in tables
        assert "messages" in tables
        assert "conversation_members" in tables
        assert "message_read_receipts" in tables
