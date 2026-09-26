"""Tests for the Messaging feature.

Messaging identity comes from the signed-in session only: anonymous callers get 401 and
non-members get 403 (see tests/e2e/test_journey_access.py for the full journeys).
"""

import json
import pytest

from blueprints.users import _hash_password


def _sign_in(client, db, email="staff@example.com", name="Staff User", role="coach"):
    """Create an active user and sign in through /login (real session token)."""
    db.execute(
        "INSERT INTO users (email, password_hash, display_name, role, is_active) VALUES (?,?,?,?,1)",
        (email, _hash_password("messaging-pass-1"), name, role),
    )
    db.commit()
    uid = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    r = client.post("/login", data={"email": email, "password": "messaging-pass-1"})
    assert r.status_code == 302
    return uid


@pytest.fixture
def staff(client, db):
    """Signed-in staff user id; ``client`` carries the session."""
    return _sign_in(client, db)


def _conversation(db, conv_id, member_ids, messages=()):
    db.execute("INSERT INTO conversations (id, type, created_by) VALUES (?,?,?)", (conv_id, "direct", "coach"))
    for uid in member_ids:
        db.execute(
            "INSERT INTO conversation_members (conversation_id, user_id, role) VALUES (?,?,?)",
            (conv_id, str(uid), "member"),
        )
    for mid, body in messages:
        db.execute(
            "INSERT INTO messages (id, conversation_id, sender_id, body) VALUES (?,?,?,?)",
            (mid, conv_id, "coach", body),
        )
    db.commit()


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
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (_hash_password("messaging-pass-1"), uid))
        db.commit()
        assert client.post("/login", data={"email": "scott@example.com",
                                           "password": "messaging-pass-1"}).status_code == 302

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
        uid = _sign_in(client, db, "scott2@example.com", "Scott McConnell", "admin")

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
    def test_list_requires_sign_in(self, client):
        r = client.get("/api/messages/conversations")
        assert r.status_code == 401

    def test_list_conversations_empty(self, client, staff):
        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data == []

    def test_list_conversations_with_data(self, client, db, staff):
        _conversation(db, 1, [staff, "coach"])
        _conversation(db, 2, ["coach"])            # not a member -> not listed

        r = client.get("/api/messages/conversations")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert [c["id"] for c in data] == [1]


class TestMessagesSend:
    def test_send_requires_sign_in(self, client, db):
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "Test message",
            "sender_id": "coach",
        })
        assert r.status_code == 401
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0

    def test_send_message(self, client, staff):
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "Test message",
            "sender_id": "coach",
        })
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["body"] == "Test message"
        assert data["sender_id"] == str(staff)

    def test_send_to_conversation_without_membership_is_refused(self, client, db, staff):
        _conversation(db, 7, ["coach"])
        r = client.post("/api/messages/send", json={"conversation_id": 7, "body": "hi"})
        assert r.status_code == 403

    def test_send_message_requires_body(self, client, staff):
        r = client.post("/api/messages/send", data={
            "conversation_id": 1,
            "body": "",
            "sender_id": "coach",
        })
        assert r.status_code == 400

    def test_send_message_requires_conversation_id(self, client, staff):
        r = client.post("/api/messages/send", data={
            "body": "Test",
            "sender_id": "coach",
        })
        assert r.status_code == 400

    def test_send_message_json(self, client, staff):
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

    def test_send_creates_conversation_if_missing(self, client, staff):
        r = client.post("/api/messages/send", data={
            "conversation_id": 999,
            "body": "New convo message",
            "sender_id": "coach",
        })
        assert r.status_code == 200

    def test_send_with_recipient_creates_conversation(self, client, db, staff):
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
        assert sorted(members) == sorted([str(staff), str(recip)])


class TestMessagesPoll:
    def test_poll_messages(self, client, db, staff):
        _conversation(db, 1, [staff], [(1, "Hello")])

        r = client.get("/api/messages/poll?conversation_id=1&since_id=0")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) >= 1
        assert data[0]["body"] == "Hello"

    def test_poll_requires_sign_in_and_membership(self, client, db):
        _conversation(db, 1, ["coach"], [(1, "Hello")])
        assert client.get("/api/messages/poll?conversation_id=1").status_code == 401
        _sign_in(client, db)
        assert client.get("/api/messages/poll?conversation_id=1").status_code == 403

    def test_poll_requires_conversation_id(self, client):
        r = client.get("/api/messages/poll")
        assert r.status_code == 400

    def test_poll_since_id(self, client, db, staff):
        _conversation(db, 1, [staff], [(1, "First"), (2, "Second")])

        r = client.get("/api/messages/poll?conversation_id=1&since_id=1")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data) == 1
        assert data[0]["body"] == "Second"


class TestMessagesRead:
    def test_mark_read(self, client, db, staff):
        _conversation(db, 1, [staff], [(1, "Test")])

        r = client.post("/api/messages/read", data={
            "message_ids": [1],
            "user_id": "coach",
        })
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["ok"] is True
        readers = [row[0] for row in db.execute("SELECT user_id FROM message_read_receipts WHERE message_id = 1")]
        assert readers == [str(staff)]

    def test_mark_read_requires_sign_in(self, client, db):
        _conversation(db, 1, ["coach"], [(1, "Test")])
        r = client.post("/api/messages/read", json={"message_ids": [1], "user_id": "coach"})
        assert r.status_code == 401
        assert db.execute("SELECT COUNT(*) FROM message_read_receipts").fetchone()[0] == 0

    def test_mark_read_requires_message_ids(self, client):
        r = client.post("/api/messages/read", data={
            "user_id": "coach",
        })
        assert r.status_code == 400

    def test_mark_read_json(self, client, db, staff):
        _conversation(db, 1, [staff], [(1, "Test")])

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
