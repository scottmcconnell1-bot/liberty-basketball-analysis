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

    def test_save_reorders_and_renames_steps(self, client, db):
        """Sheet order in steps_json becomes step_number; labels persist."""
        cur = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Reorder Sheets Play", "offense"),
        )
        play_id = cur.lastrowid
        db.execute(
            """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes, source_image)
               VALUES (?,?,?,?,?,?,?)""",
            (play_id, 0, "Step 1 (Page 87)", "{}", "[]", "", "/a.png"),
        )
        db.execute(
            """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes, source_image)
               VALUES (?,?,?,?,?,?,?)""",
            (play_id, 1, "Step 2 (Page 88)", "{}", "[]", "", "/b.png"),
        )
        db.commit()

        # Swap order and rename labels (as the editor does after drag + edit).
        steps = [
            {
                "positions": {},
                "movements": [],
                "label": "Pass to wing",
                "notes": "",
                "source_image": "/b.png",
                "ball": "o1",
            },
            {
                "positions": {},
                "movements": [],
                "label": "Initial set",
                "notes": "",
                "source_image": "/a.png",
                "ball": "o1",
            },
        ]
        r = client.post(
            "/playbook/save",
            data={
                "play_id": str(play_id),
                "name": "Reorder Sheets Play",
                "category": "offense",
                "steps_json": json.dumps(steps),
            },
            follow_redirects=True,
        )
        assert r.status_code == 200
        rows = db.execute(
            "SELECT step_number, label, source_image FROM play_steps WHERE play_id=? ORDER BY step_number",
            (play_id,),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["step_number"] == 0
        assert rows[0]["label"] == "Pass to wing"
        assert rows[0]["source_image"] == "/b.png"
        assert rows[1]["label"] == "Initial set"
        assert rows[1]["source_image"] == "/a.png"


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


class TestPlaybookReorder:
    def test_list_sorts_alphabetically_by_name(self, client, db):
        """Browse list is A–Z by name even when list_order says otherwise."""
        from blueprints.playbook import _group_plays_for_list

        rows = []
        for name, order in (("Zebra", 0), ("alpha", 1), ("Mike", 2)):
            cur = db.execute(
                "INSERT INTO plays (name, category, list_order) VALUES (?, ?, ?)",
                (name, "offense", order),
            )
            rows.append(cur.lastrowid)
        db.commit()
        plays = db.execute(
            "SELECT * FROM plays WHERE id IN (?, ?, ?)",
            rows,
        ).fetchall()
        grouped = _group_plays_for_list(db, plays)
        assert [p["name"] for p in grouped] == ["alpha", "Mike", "Zebra"]

    def test_reorder_top_level_plays(self, client, db):
        ids = []
        for name in ("Alpha", "Bravo", "Charlie"):
            cur = db.execute(
                "INSERT INTO plays (name, category, list_order) VALUES (?, ?, ?)",
                (name, "offense", len(ids)),
            )
            ids.append(cur.lastrowid)
        db.commit()

        new_order = [ids[2], ids[0], ids[1]]
        r = client.post(
            "/api/playbook/reorder",
            json={"parent_play_id": None, "ordered_ids": new_order},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["ordered_ids"] == new_order

        rows = db.execute(
            f"SELECT id, list_order FROM plays WHERE id IN ({','.join('?' * len(ids))}) ORDER BY list_order",
            ids,
        ).fetchall()
        assert [row["id"] for row in rows] == new_order

        # List page still renders A–Z regardless of persisted list_order.
        page = client.get("/playbook")
        assert page.status_code == 200
        html = page.data.decode("utf-8")
        pos_alpha = html.find("Alpha")
        pos_bravo = html.find("Bravo")
        pos_charlie = html.find("Charlie")
        assert pos_alpha != -1 and pos_bravo != -1 and pos_charlie != -1
        assert pos_alpha < pos_bravo < pos_charlie

    def test_reorder_progressions(self, client, db):
        parent = db.execute(
            "INSERT INTO plays (name, category) VALUES (?, ?)",
            ("Parent Set", "offense"),
        ).lastrowid
        child_ids = []
        for i, name in enumerate(("First", "Second", "Third")):
            cur = db.execute(
                """INSERT INTO plays (name, category, parent_play_id, progression_order)
                   VALUES (?, ?, ?, ?)""",
                (name, "offense", parent, i),
            )
            child_ids.append(cur.lastrowid)
        db.commit()

        new_order = [child_ids[1], child_ids[2], child_ids[0]]
        r = client.post(
            "/api/playbook/reorder",
            json={"parent_play_id": parent, "ordered_ids": new_order},
        )
        assert r.status_code == 200

        rows = db.execute(
            """SELECT id FROM plays WHERE parent_play_id = ?
               ORDER BY progression_order ASC""",
            (parent,),
        ).fetchall()
        assert [row["id"] for row in rows] == new_order

    def test_move_plays_to_category(self, client, db):
        from playbook_taxonomy import ensure_playbook_taxonomy, resolve_category_id_by_path

        ensure_playbook_taxonomy(db)
        db.commit()
        man_id = resolve_category_id_by_path(db, "offense/man")
        zone_id = resolve_category_id_by_path(db, "offense/zone")
        assert man_id and zone_id

        play_id = db.execute(
            "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
            ("Move Me", "offense", man_id),
        ).lastrowid
        child_id = db.execute(
            """INSERT INTO plays (name, category, category_id, parent_play_id, progression_order)
               VALUES (?, ?, ?, ?, ?)""",
            ("Move Me Child", "offense", man_id, play_id, 0),
        ).lastrowid
        db.commit()

        r = client.post(
            "/api/playbook/move-category",
            json={"play_ids": [play_id], "category_id": zone_id},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["moved_ids"] == [play_id]
        assert data["category_id"] == zone_id

        parent = db.execute("SELECT category_id FROM plays WHERE id = ?", (play_id,)).fetchone()
        child = db.execute("SELECT category_id FROM plays WHERE id = ?", (child_id,)).fetchone()
        assert parent["category_id"] == zone_id
        assert child["category_id"] == zone_id

    def test_move_rejects_parent_folder(self, client, db):
        from playbook_taxonomy import ensure_playbook_taxonomy, resolve_category_id_by_path

        ensure_playbook_taxonomy(db)
        db.commit()
        offense_id = resolve_category_id_by_path(db, "offense")
        man_id = resolve_category_id_by_path(db, "offense/man")
        play_id = db.execute(
            "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
            ("Stay Put", "offense", man_id),
        ).lastrowid
        db.commit()

        r = client.post(
            "/api/playbook/move-category",
            json={"play_ids": [play_id], "category_id": offense_id},
        )
        assert r.status_code == 400

    def test_playbook_list_has_dnd_hooks(self, client):
        r = client.get("/playbook")
        assert r.status_code == 200
        assert b"playbook-dnd.js" in r.data
        assert b"PlaybookDragDrop" in r.data


    def test_zone_23_unnumbered_progressions(self, client, db):
        from playbook_taxonomy import ensure_playbook_taxonomy, resolve_category_id_by_path
        from blueprints.playbook import ensure_zone_23_progressions

        ensure_playbook_taxonomy(db)
        zone_id = resolve_category_id_by_path(db, "defense/zone")
        parent_id = db.execute(
            "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
            ("2-3 Zone", "defense", zone_id),
        ).lastrowid
        basic_id = db.execute(
            "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
            ("Basic Startup", "defense", zone_id),
        ).lastrowid
        cuts_id = db.execute(
            "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
            ("Defending PG cuts", "defense", zone_id),
        ).lastrowid
        other_id = db.execute(
            "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
            ("1-3-1", "defense", zone_id),
        ).lastrowid
        db.commit()

        ensure_zone_23_progressions(db)

        basic = db.execute("SELECT parent_play_id FROM plays WHERE id = ?", (basic_id,)).fetchone()
        cuts = db.execute("SELECT parent_play_id FROM plays WHERE id = ?", (cuts_id,)).fetchone()
        other = db.execute("SELECT parent_play_id FROM plays WHERE id = ?", (other_id,)).fetchone()
        assert basic["parent_play_id"] == parent_id
        assert cuts["parent_play_id"] == parent_id
        assert other["parent_play_id"] in (None, 0)


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
