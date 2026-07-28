"""Tests for the Messaging feature."""

import json
import pytest


class TestMessagesPage:
    def test_messages_page_loads(self, client):
        r = client.get("/messages")
        assert r.status_code == 200
        assert b"Messages" in r.data or b"Conversations" in r.data or b"messaging" in r.data.lower()


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
