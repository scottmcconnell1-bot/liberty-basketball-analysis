"""Tests for the Playbook feature."""

import json
import pytest


class TestPlaybookList:
    def test_playbook_page_loads(self, client):
        r = client.get("/playbook")
        assert r.status_code == 200
        assert b"Playbook" in r.data

    def test_playbook_create_page_loads(self, client):
        r = client.get("/playbook/create")
        assert r.status_code == 200
        assert b"Save Play" in r.data or b"Playbook" in r.data


class TestPlaybookSave:
    def test_save_play_minimal(self, client):
        r = client.post("/playbook/save", data={
            "name": "Test Play",
            "category": "offense",
            "description": "",
            "tags": "",
            "playbook_id": "",
            "diagram_json": "{}",
            "steps_json": "[]",
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_save_play_with_steps(self, client):
        steps = [
            {
                "positions": {
                    "1": {"x": 250, "y": 420},
                    "2": {"x": 120, "y": 350},
                    "3": {"x": 380, "y": 350},
                    "4": {"x": 140, "y": 250},
                    "5": {"x": 360, "y": 250},
                },
                "movements": [
                    {"from": "1", "to": "2", "type": "pass"},
                ],
                "label": "Initial",
                "notes": "Point guard passes to wing",
            }
        ]
        r = client.post("/playbook/save", data={
            "name": "Box Zone Entry",
            "category": "offense",
            "description": "Basic zone entry from box set",
            "tags": "zone, entry",
            "playbook_id": "",
            "diagram_json": "{}",
            "steps_json": json.dumps(steps),
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_save_play_requires_name(self, client):
        r = client.post("/playbook/save", data={
            "name": "",
            "category": "offense",
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_save_play_default_category(self, client):
        r = client.post("/playbook/save", data={
            "name": "No Category Play",
        }, follow_redirects=True)
        assert r.status_code == 200


class TestPlaybookView:
    def test_view_play(self, client, db):
        # First create a play directly in DB
        cur = db.execute(
            "INSERT INTO plays (name, category, diagram_json) VALUES (?, ?, ?)",
            ("View Test Play", "defense", "{}"),
        )
        play_id = cur.lastrowid
        db.commit()

        r = client.get(f"/playbook/play/{play_id}")
        assert r.status_code == 200
        assert b"View Test Play" in r.data

    def test_view_nonexistent_play(self, client):
        r = client.get("/playbook/play/99999", follow_redirects=True)
        assert r.status_code == 200


class TestPlaybookEdit:
    def test_edit_play_page(self, client, db):
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Edit Test Play", "offense"),
        )
        play_id = cur.lastrowid
        db.commit()

        r = client.get(f"/playbook/play/{play_id}/edit")
        assert r.status_code == 200

    def test_edit_play_update(self, client, db):
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Edit Update Play", "offense"),
        )
        play_id = cur.lastrowid
        db.commit()

        r = client.post("/playbook/save", data={
            "play_id": str(play_id),
            "name": "Updated Play Name",
            "category": "transition",
            "steps_json": "[]",
        }, follow_redirects=True)
        assert r.status_code == 200


class TestPlaybookDelete:
    def test_delete_play(self, client, db):
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Delete Me", "offense"),
        )
        play_id = cur.lastrowid
        db.commit()

        r = client.post(f"/playbook/play/{play_id}/delete", follow_redirects=True)
        assert r.status_code == 200

        # Verify it's gone
        row = db.execute("SELECT id FROM plays WHERE id = ?", (play_id,)).fetchone()
        assert row is None


class TestPlaybookDuplicate:
    def test_duplicate_play(self, client, db):
        """Duplicating a play should create a copy with same steps."""
        # Create a play with steps
        cur = db.execute(
            "INSERT INTO plays (name, category, description, tags) VALUES (?, ?, ?, ?)",
            ("Original Play", "offense", "A test play", "test, zone"),
        )
        play_id = cur.lastrowid
        db.execute(
            "INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes) VALUES (?,?,?,?,?,?)",
            (play_id, 0, "Step 1", '{"1":{"x":250,"y":420}}', '[]', "First step"),
        )
        db.execute(
            "INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes) VALUES (?,?,?,?,?,?)",
            (play_id, 1, "Step 2", '{"1":{"x":200,"y":400}}', '[]', "Second step"),
        )
        db.commit()

        # Duplicate
        r = client.post(f"/playbook/play/{play_id}/duplicate", follow_redirects=True)
        assert r.status_code == 200

        # Verify copy exists
        row = db.execute("SELECT * FROM plays WHERE name = ?", ("Original Play (copy)",)).fetchone()
        assert row is not None
        assert row["category"] == "offense"
        assert row["description"] == "A test play"
        assert row["tags"] == "test, zone"

        # Verify steps were copied
        copy_id = row["id"]
        steps = db.execute("SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (copy_id,)).fetchall()
        assert len(steps) == 2
        assert steps[0]["label"] == "Step 1"
        assert steps[1]["label"] == "Step 2"

    def test_duplicate_nonexistent_play(self, client):
        r = client.post("/playbook/play/99999/duplicate", follow_redirects=True)
        assert r.status_code == 200


class TestPlaybookAPI:
    def test_api_get_play(self, client, db):
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("API Test Play", "offense"),
        )
        play_id = cur.lastrowid
        db.commit()

        r = client.get(f"/api/playbook/play/{play_id}")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "play" in data
        assert "steps" in data
        assert data["play"]["name"] == "API Test Play"

    def test_api_get_nonexistent_play(self, client):
        r = client.get("/api/playbook/play/99999")
        assert r.status_code == 404


class TestPlaybookExport:
    def test_export_play(self, client, db):
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Export Test Play", "offense"),
        )
        play_id = cur.lastrowid
        db.commit()

        r = client.get(f"/playbook/export/{play_id}")
        assert r.status_code == 200
        assert r.content_type == "application/json"
        data = json.loads(r.data)
        assert "play" in data
        assert "steps" in data


class TestPlaybookDB:
    def test_playbook_tables_exist(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "playbooks" in tables
        assert "plays" in tables
        assert "play_steps" in tables

    def test_play_steps_cascade_delete(self, db):
        """Deleting a play should delete its steps."""
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Cascade Test", "offense"),
        )
        play_id = cur.lastrowid
        db.execute(
            "INSERT INTO play_steps (play_id, step_number, positions_json) VALUES (?, ?, ?)",
            (play_id, 0, "{}"),
        )
        db.commit()

        # Verify step exists
        steps = db.execute("SELECT * FROM play_steps WHERE play_id = ?", (play_id,)).fetchall()
        assert len(steps) == 1

        # Delete play
        db.execute("DELETE FROM plays WHERE id = ?", (play_id,))
        db.commit()

        # Steps should be gone
        steps = db.execute("SELECT * FROM play_steps WHERE play_id = ?", (play_id,)).fetchall()
        assert len(steps) == 0
